"""
Execution Plan Management API Endpoints

Provides REST API for managing execution plans with:
- Plan creation and management
- Suite scheduling within plans
- Execution tracking and statistics
- Retry management
- Notifications and webhooks
"""

import logging
import threading
from typing import Optional, List, Union, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from fastapi.security import OAuth2PasswordBearer
from pydantic import BaseModel, Field, validator
from datetime import datetime
from auroqa.models.user import User
from auroqa.Services.ExecutionPlanService import ExecutionPlanService
from auroqa.Services.ParallelExecutionEngine import ParallelExecutionEngine
from auroqa.Utils.Connectors.db_utils import get_db_connection, return_db_connection

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/execution-plans", tags=["execution-plans"])

# This will be set by main.py during app initialization
_current_user_func = None
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/login")

def set_get_current_user(func):
    """Set the get_current_user dependency function"""
    global _current_user_func
    _current_user_func = func

async def get_current_user_from_token(token: str = Depends(oauth2_scheme)) -> User:
    """Wrapper that gets the actual get_current_user function and calls it"""
    if _current_user_func is None:
        raise HTTPException(status_code=500, detail="Authentication not configured")
    # Call the actual get_current_user function with the token
    return await _current_user_func(token)

# Initialize services
execution_plan_service = ExecutionPlanService()
parallel_execution_engine = ParallelExecutionEngine()


# ============================================================================
# Pydantic Models
# ============================================================================

class ExecutionPlanCreate(BaseModel):
    """Request model for creating an execution plan"""
    name: str = Field(..., description="Plan name")
    description: Optional[str] = Field(None, description="Plan description")
    client_id: str = Field(..., description="Client ID")
    project_id: str = Field(..., description="Project ID")
    created_by: Optional[Union[str, int]] = Field(None, description="User ID who created the plan")
    environment_id: Optional[int] = Field(None, description="Environment ID for test execution")
    plan_type: str = Field("sequential", description="Plan type: sequential, parallel, hybrid")
    schedule_type: str = Field("manual", description="Schedule type: manual, once, recurring, cron")
    max_parallel_suites: int = Field(1, description="Maximum parallel suites")
    max_retries: int = Field(0, description="Maximum retry attempts")
    retry_delay_seconds: int = Field(5, description="Delay between retries")
    timeout_seconds: int = Field(3600, description="Execution timeout")
    
    @validator('created_by', pre=True, always=True)
    def convert_created_by_to_string(cls, v):
        if v is not None:
            return str(v)
        return v


class ExecutionPlanUpdate(BaseModel):
    """Request model for updating an execution plan"""
    name: Optional[str] = Field(None, description="Plan name")
    description: Optional[str] = Field(None, description="Plan description")
    environment_id: Optional[int] = Field(None, description="Environment ID for test execution")
    plan_type: Optional[str] = Field(None, description="Plan type")
    schedule_type: Optional[str] = Field(None, description="Schedule type")
    max_parallel_suites: Optional[int] = Field(None, description="Maximum parallel suites")
    max_retries: Optional[int] = Field(None, description="Maximum retry attempts")
    retry_delay_seconds: Optional[int] = Field(None, description="Delay between retries")
    timeout_seconds: Optional[int] = Field(None, description="Execution timeout")


class ExecutionPlanResponse(BaseModel):
    """Response model for an execution plan"""
    id: int
    name: str
    description: Optional[str]
    project_id: str
    environment_id: Optional[int]
    plan_type: str
    schedule_type: str
    max_parallel_suites: int
    max_retries: int
    retry_delay_seconds: int
    timeout_seconds: int
    status: str
    created_at: datetime
    updated_at: datetime
    last_executed_at: Optional[datetime]
    next_execution_at: Optional[datetime]
    cron_expression: Optional[str] = None
    recurrence_pattern: Optional[str] = None


class ExecutionPlanListResponse(BaseModel):
    """Response model for execution plan list"""
    plans: List[ExecutionPlanResponse]
    total: int


class AddSuiteToPlantRequest(BaseModel):
    """Request model for adding suite to plan"""
    suite_id: int = Field(..., description="Test suite ID")
    execution_order: int = Field(..., description="Execution order")
    environment_id: Optional[int] = Field(None, description="Environment ID")
    timeout_seconds: Optional[int] = Field(None, description="Suite timeout")
    max_retries: Optional[int] = Field(None, description="Suite max retries")


class PlanSuiteResponse(BaseModel):
    """Response model for suite in plan"""
    id: int
    suite_id: int
    execution_order: int
    environment_id: Optional[int]
    timeout_seconds: Optional[int]
    max_retries: Optional[int]
    status: str


class ExecutePlanRequest(BaseModel):
    """Request model for executing a plan"""
    triggered_by: str = Field("manual", description="Trigger source")


class ExecutionRunResponse(BaseModel):
    """Response model for execution run"""
    id: int
    plan_id: int
    started_at: datetime
    completed_at: Optional[datetime]
    status: str
    total_suites: Optional[int]
    passed_suites: Optional[int]
    failed_suites: Optional[int]
    skipped_suites: Optional[int]
    total_tests: Optional[int]
    passed_tests: Optional[int]
    failed_tests: Optional[int]
    skipped_tests: Optional[int]
    duration_seconds: Optional[float]
    triggered_by: str


class PlanStatisticsResponse(BaseModel):
    """Response model for plan statistics"""
    id: int
    name: str
    status: str
    total_suites: int
    total_runs: int
    passed_runs: int
    failed_runs: int
    last_executed_at: Optional[datetime]
    next_execution_at: Optional[datetime]


# ============================================================================
# Helper Functions
# ============================================================================

def get_plan_from_db(plan_id: int) -> dict:
    """Get execution plan from database"""
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT id, client_id, project_id, name, description, plan_type,
                       schedule_type, max_parallel_suites, max_retries,
                       retry_delay_seconds, timeout_seconds, status,
                       created_at, updated_at, last_executed_at, next_execution_at,
                       environment_id, cron_expression, recurrence_pattern
                FROM execution_suite_plans
                WHERE id = %s AND is_active = TRUE
                """,
                (plan_id,)
            )
            result = cursor.fetchone()
            if not result:
                return None
            
            return {
                'id': result[0],
                'client_id': result[1],
                'project_id': result[2],
                'name': result[3],
                'description': result[4],
                'plan_type': result[5],
                'schedule_type': result[6],
                'max_parallel_suites': result[7],
                'max_retries': result[8],
                'retry_delay_seconds': result[9],
                'timeout_seconds': result[10],
                'status': result[11],
                'created_at': result[12],
                'updated_at': result[13],
                'last_executed_at': result[14],
                'next_execution_at': result[15],
                'environment_id': result[16],
                'cron_expression': result[17],
                'recurrence_pattern': result[18]
            }
    finally:
        return_db_connection(conn)


def get_plans_from_db(
    client_id: Optional[str] = None,
    project_id: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 100,
    offset: int = 0
) -> tuple:
    """Get execution plans from database"""
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            # Build WHERE clause
            where_clauses = ["is_active = TRUE"]
            params = []
            
            # Only filter by client_id if provided
            if client_id:
                where_clauses.append("client_id = %s")
                params.append(client_id)
            
            if project_id:
                where_clauses.append("project_id = %s")
                params.append(project_id)
            if status:
                where_clauses.append("status = %s")
                params.append(status)
            
            where_clause = " AND ".join(where_clauses)
            
            # Get total count
            cursor.execute(f"SELECT COUNT(*) FROM execution_suite_plans WHERE {where_clause}", params)
            total = cursor.fetchone()[0]
            
            # Get paginated results
            params.extend([limit, offset])
            cursor.execute(
                f"""
                SELECT id, project_id, name, description, plan_type, schedule_type,
                       max_parallel_suites, max_retries, retry_delay_seconds, timeout_seconds,
                       status, created_at, updated_at, last_executed_at, next_execution_at,
                       environment_id, cron_expression, recurrence_pattern
                FROM execution_suite_plans
                WHERE {where_clause}
                ORDER BY created_at DESC
                LIMIT %s OFFSET %s
                """,
                params
            )
            
            plans = []
            for row in cursor.fetchall():
                plans.append({
                    'id': row[0],
                    'project_id': row[1],
                    'name': row[2],
                    'description': row[3],
                    'plan_type': row[4],
                    'schedule_type': row[5],
                    'max_parallel_suites': row[6],
                    'max_retries': row[7],
                    'retry_delay_seconds': row[8],
                    'timeout_seconds': row[9],
                    'status': row[10],
                    'created_at': row[11],
                    'updated_at': row[12],
                    'last_executed_at': row[13],
                    'next_execution_at': row[14],
                    'environment_id': row[15],
                    'cron_expression': row[16],
                    'recurrence_pattern': row[17]
                })
            
            return plans, total
    finally:
        return_db_connection(conn)


def get_run_from_db(run_id: int) -> dict:
    """Get execution run from database"""
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT id, execution_suite_plan_id, started_at, completed_at, status,
                       total_suites, passed_suites, failed_suites, skipped_suites,
                       total_tests, passed_tests, failed_tests, skipped_tests,
                       duration_seconds, triggered_by
                FROM execution_suite_plan_runs
                WHERE id = %s
                """,
                (run_id,)
            )
            result = cursor.fetchone()
            if not result:
                return None
            
            return {
                'id': result[0],
                'plan_id': result[1],
                'started_at': result[2],
                'completed_at': result[3],
                'status': result[4],
                'total_suites': result[5],
                'passed_suites': result[6],
                'failed_suites': result[7],
                'skipped_suites': result[8],
                'total_tests': result[9],
                'passed_tests': result[10],
                'failed_tests': result[11],
                'skipped_tests': result[12],
                'duration_seconds': result[13],
                'triggered_by': result[14]
            }
    finally:
        return_db_connection(conn)


# ============================================================================
# Execution Plan Management Endpoints
# ============================================================================

@router.post("", response_model=ExecutionPlanResponse)
async def create_execution_plan(request: ExecutionPlanCreate):
    """Create a new execution plan"""
    try:
        # Validate client_id is provided
        if not request.client_id:
            raise HTTPException(status_code=400, detail="client_id is required")
        
        # Use created_by from request, validate it looks like a UUID or use client_id as default
        created_by = request.created_by
        if created_by:
            # Check if it's a valid UUID format (simple check)
            if len(str(created_by)) < 20 or '-' not in str(created_by):
                # Not a valid UUID, use client_id instead
                created_by = request.client_id
        else:
            created_by = request.client_id
        
        plan_id = execution_plan_service.create_execution_plan(
            client_id=request.client_id,
            project_id=request.project_id,
            name=request.name,
            description=request.description,
            plan_type=request.plan_type,
            schedule_type=request.schedule_type,
            max_parallel_suites=request.max_parallel_suites,
            max_retries=request.max_retries,
            retry_delay_seconds=request.retry_delay_seconds,
            timeout_seconds=request.timeout_seconds,
            created_by=created_by,
            environment_id=request.environment_id
        )
        
        if not plan_id:
            raise HTTPException(status_code=500, detail="Failed to create execution plan")
        
        plan = get_plan_from_db(plan_id)
        return ExecutionPlanResponse(**plan)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating execution plan: {e}")
        raise HTTPException(status_code=500, detail="Failed to create execution plan")


@router.get("", response_model=ExecutionPlanListResponse)
async def list_execution_plans(
    client_id: Optional[str] = Query(None),
    project_id: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0)
):
    """List execution plans"""
    try:
        plans, total = get_plans_from_db(
            client_id=client_id,
            project_id=project_id,
            status=status,
            limit=limit,
            offset=offset
        )
        
        return ExecutionPlanListResponse(
            plans=[ExecutionPlanResponse(**plan) for plan in plans],
            total=total
        )
    except Exception as e:
        logger.error(f"Error listing execution plans: {e}")
        raise HTTPException(status_code=500, detail="Failed to list execution plans")


@router.get("/{plan_id}", response_model=ExecutionPlanResponse)
async def get_execution_plan(
    plan_id: int,
    current_user: User = Depends(get_current_user_from_token)  # Placeholder for auth
):
    """Get execution plan details"""
    try:
        plan = get_plan_from_db(plan_id)
        if not plan:
            raise HTTPException(status_code=404, detail="Execution plan not found")
        
        return ExecutionPlanResponse(**plan)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting execution plan: {e}")
        raise HTTPException(status_code=500, detail="Failed to get execution plan")


@router.put("/{plan_id}", response_model=ExecutionPlanResponse)
async def update_execution_plan(
    plan_id: int,
    request: ExecutionPlanUpdate,
    current_user: User = Depends(get_current_user_from_token)  # Placeholder for auth
):
    """Update execution plan"""
    try:
        # Check if plan exists
        plan = get_plan_from_db(plan_id)
        if not plan:
            raise HTTPException(status_code=404, detail="Execution plan not found")
        
        # Update plan in database
        conn = get_db_connection()
        try:
            with conn.cursor() as cursor:
                updates = []
                params = []
                
                if request.name is not None:
                    updates.append("name = %s")
                    params.append(request.name)
                if request.description is not None:
                    updates.append("description = %s")
                    params.append(request.description)
                if request.plan_type is not None:
                    updates.append("plan_type = %s")
                    params.append(request.plan_type)
                if request.schedule_type is not None:
                    updates.append("schedule_type = %s")
                    params.append(request.schedule_type)
                if request.max_parallel_suites is not None:
                    updates.append("max_parallel_suites = %s")
                    params.append(request.max_parallel_suites)
                if request.max_retries is not None:
                    updates.append("max_retries = %s")
                    params.append(request.max_retries)
                if request.retry_delay_seconds is not None:
                    updates.append("retry_delay_seconds = %s")
                    params.append(request.retry_delay_seconds)
                if request.timeout_seconds is not None:
                    updates.append("timeout_seconds = %s")
                    params.append(request.timeout_seconds)
                
                if updates:
                    params.append(plan_id)
                    query = f"UPDATE execution_plans SET {', '.join(updates)} WHERE id = %s"
                    cursor.execute(query, params)
                    conn.commit()
        finally:
            return_db_connection(conn)
        
        # Retrieve and return updated plan
        plan = get_plan_from_db(plan_id)
        return ExecutionPlanResponse(**plan)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating execution plan: {e}")
        raise HTTPException(status_code=500, detail="Failed to update execution plan")


@router.delete("/{plan_id}")
async def delete_execution_plan(
    plan_id: int,
    current_user: User = Depends(get_current_user_from_token)  # Placeholder for auth
):
    """Delete execution plan"""
    try:
        # Check if plan exists
        plan = get_plan_from_db(plan_id)
        if not plan:
            raise HTTPException(status_code=404, detail="Execution plan not found")
        
        # Soft delete
        conn = get_db_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    "UPDATE execution_suite_plans SET is_active = FALSE WHERE id = %s",
                    (plan_id,)
                )
                conn.commit()
        finally:
            return_db_connection(conn)
        
        return {"status": "success", "message": "Execution plan deleted"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting execution plan: {e}")
        raise HTTPException(status_code=500, detail="Failed to delete execution plan")


# ============================================================================
# Suite Management Endpoints
# ============================================================================

@router.post("/{plan_id}/suites", response_model=PlanSuiteResponse)
async def add_suite_to_plan(
    plan_id: int,
    request: AddSuiteToPlantRequest,
    current_user: User = Depends(get_current_user_from_token)  # Placeholder for auth
):
    """Add test suite to execution plan"""
    try:
        # Check if plan exists
        plan = get_plan_from_db(plan_id)
        if not plan:
            raise HTTPException(status_code=404, detail="Execution plan not found")
        
        suite_plan_id = execution_plan_service.add_suite_to_plan(
            plan_id=plan_id,
            suite_id=request.suite_id,
            execution_order=request.execution_order,
            environment_id=request.environment_id,
            timeout_seconds=request.timeout_seconds,
            max_retries=request.max_retries
        )
        
        if not suite_plan_id:
            raise HTTPException(status_code=500, detail="Failed to add suite to plan")
        
        # Retrieve suite plan
        conn = get_db_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT id, test_suite_id, execution_order, environment_id,
                           timeout_seconds, max_retries, status
                    FROM execution_suite_plan_suites
                    WHERE id = %s
                    """,
                    (suite_plan_id,)
                )
                result = cursor.fetchone()
                if result:
                    return PlanSuiteResponse(
                        id=result[0],
                        suite_id=result[1],
                        execution_order=result[2],
                        environment_id=result[3],
                        timeout_seconds=result[4],
                        max_retries=result[5],
                        status=result[6]
                    )
        finally:
            return_db_connection(conn)
        
        raise HTTPException(status_code=500, detail="Failed to retrieve added suite")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error adding suite to plan: {e}")
        raise HTTPException(status_code=500, detail="Failed to add suite to plan")


@router.get("/{plan_id}/suites", response_model=dict)
async def get_plan_suites(
    plan_id: int,
    current_user: User = Depends(get_current_user_from_token)  # Placeholder for auth
):
    """Get all suites in execution plan"""
    try:
        # Check if plan exists
        plan = get_plan_from_db(plan_id)
        if not plan:
            raise HTTPException(status_code=404, detail="Execution plan not found")
        
        suites = execution_plan_service.get_plan_suites(plan_id)
        
        return {
            "plan_id": plan_id,
            "suites": suites,
            "total": len(suites)
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting plan suites: {e}")
        raise HTTPException(status_code=500, detail="Failed to get plan suites")


@router.delete("/{plan_id}/suites/{suite_id}")
async def remove_suite_from_plan(
    plan_id: int,
    suite_id: int,
    current_user: User = Depends(get_current_user_from_token)  # Placeholder for auth
):
    """Remove test suite from execution plan"""
    try:
        # Check if plan exists
        plan = get_plan_from_db(plan_id)
        if not plan:
            raise HTTPException(status_code=404, detail="Execution plan not found")
        
        conn = get_db_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    "DELETE FROM execution_suite_plan_suites WHERE execution_suite_plan_id = %s AND test_suite_id = %s",
                    (plan_id, suite_id)
                )
                conn.commit()
                
                if cursor.rowcount == 0:
                    raise HTTPException(status_code=404, detail="Suite not found in plan")
        finally:
            return_db_connection(conn)
        
        return {"status": "success", "message": "Suite removed from plan"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error removing suite from plan: {e}")
        raise HTTPException(status_code=500, detail="Failed to remove suite from plan")


# ============================================================================
# Execution Endpoints
# ============================================================================

def _run_plan_in_background(plan_id: int, run_id: int, max_parallel: int):
    """Background task to execute plan using ParallelExecutionEngine"""
    try:
        logger.info(f"Starting background execution for plan {plan_id}, run {run_id}")
        result = parallel_execution_engine.execute_plan(
            plan_id=plan_id,
            run_id=run_id,
            max_parallel=max_parallel
        )
        logger.info(f"Background execution completed for plan {plan_id}: {result.get('status')}")
    except Exception as e:
        logger.error(f"Background execution failed for plan {plan_id}: {e}")
        # Update run status to failed
        execution_plan_service.update_plan_run(
            run_id=run_id,
            status='failed',
            completed_at=datetime.now(),
            error_message=str(e)
        )


@router.post("/{plan_id}/run", response_model=ExecutionRunResponse)
async def execute_plan(
    plan_id: int,
    request: ExecutePlanRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user_from_token)  # Placeholder for auth
):
    """Execute an execution plan"""
    try:
        # Check if plan exists
        plan = get_plan_from_db(plan_id)
        if not plan:
            raise HTTPException(status_code=404, detail="Execution plan not found")
        
        # Create execution run record
        run_id = execution_plan_service.create_plan_run(
            plan_id=plan_id,
            triggered_by=request.triggered_by,
            triggered_by_user_id=str(current_user.id) if current_user else None
        )
        
        if not run_id:
            raise HTTPException(status_code=500, detail="Failed to create execution run")
        
        # Get max_parallel from plan settings
        max_parallel = plan.get('max_parallel_suites', 1)
        
        # Start execution in background thread
        thread = threading.Thread(
            target=_run_plan_in_background,
            args=(plan_id, run_id, max_parallel)
        )
        thread.daemon = True
        thread.start()
        
        run = get_run_from_db(run_id)
        return ExecutionRunResponse(**run)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error executing plan: {e}")
        raise HTTPException(status_code=500, detail="Failed to execute plan")


@router.get("/{plan_id}/runs", response_model=dict)
async def get_plan_runs(
    plan_id: int,
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(get_current_user_from_token)  # Placeholder for auth
):
    """Get execution runs for a plan"""
    try:
        # Check if plan exists
        plan = get_plan_from_db(plan_id)
        if not plan:
            raise HTTPException(status_code=404, detail="Execution plan not found")
        
        conn = get_db_connection()
        try:
            with conn.cursor() as cursor:
                # Get total count
                cursor.execute(
                    "SELECT COUNT(*) FROM execution_suite_plan_runs WHERE execution_suite_plan_id = %s",
                    (plan_id,)
                )
                total = cursor.fetchone()[0]
                
                # Get paginated results
                cursor.execute(
                    """
                    SELECT id, execution_suite_plan_id, started_at, completed_at, status,
                           total_suites, passed_suites, failed_suites, skipped_suites,
                           total_tests, passed_tests, failed_tests, skipped_tests,
                           duration_seconds, triggered_by
                    FROM execution_suite_plan_runs
                    WHERE execution_suite_plan_id = %s
                    ORDER BY started_at DESC
                    LIMIT %s OFFSET %s
                    """,
                    (plan_id, limit, offset)
                )
                
                runs = []
                for row in cursor.fetchall():
                    runs.append({
                        'id': row[0],
                        'plan_id': row[1],
                        'started_at': row[2],
                        'completed_at': row[3],
                        'status': row[4],
                        'total_suites': row[5],
                        'passed_suites': row[6],
                        'failed_suites': row[7],
                        'skipped_suites': row[8],
                        'total_tests': row[9],
                        'passed_tests': row[10],
                        'failed_tests': row[11],
                        'skipped_tests': row[12],
                        'duration_seconds': row[13],
                        'triggered_by': row[14]
                    })
                
                return {
                    "plan_id": plan_id,
                    "runs": runs,
                    "total": total
                }
        finally:
            return_db_connection(conn)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting plan runs: {e}")
        raise HTTPException(status_code=500, detail="Failed to get plan runs")


@router.get("/runs/{run_id}", response_model=ExecutionRunResponse)
async def get_execution_run(
    run_id: int,
    current_user: User = Depends(get_current_user_from_token)  # Placeholder for auth
):
    """Get execution run details"""
    try:
        run = get_run_from_db(run_id)
        if not run:
            raise HTTPException(status_code=404, detail="Execution run not found")
        
        return ExecutionRunResponse(**run)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting execution run: {e}")
        raise HTTPException(status_code=500, detail="Failed to get execution run")


@router.get("/runs/{run_id}/tests", response_model=dict)
async def get_run_test_results(
    run_id: int,
    current_user: User = Depends(get_current_user_from_token)  # Placeholder for auth
):
    """Get detailed test results for a specific execution run"""
    try:
        conn = get_db_connection()
        try:
            with conn.cursor() as cursor:
                # Get test results with test case names
                cursor.execute(
                    """
                    SELECT tr.id, tr.test_case_id, tc.name as test_name, 
                           tr.suite_id, ts.name as suite_name,
                           tr.status, tr.started_at, tr.completed_at, 
                           tr.duration_seconds, tr.error_message,
                           tr.retry_count
                    FROM execution_suite_plan_test_runs tr
                    LEFT JOIN test_cases tc ON tr.test_case_id = tc.id
                    LEFT JOIN test_suites ts ON tr.suite_id = ts.id
                    WHERE tr.execution_suite_plan_run_id = %s
                    ORDER BY tr.started_at ASC
                    """,
                    (run_id,)
                )
                
                tests = []
                for row in cursor.fetchall():
                    tests.append({
                        'id': row[0],
                        'test_case_id': row[1],
                        'test_name': row[2] or f"Test #{row[1]}",
                        'suite_id': row[3],
                        'suite_name': row[4] or "Unknown Suite",
                        'status': row[5],
                        'started_at': row[6].isoformat() if row[6] else None,
                        'completed_at': row[7].isoformat() if row[7] else None,
                        'duration_seconds': row[8],
                        'error_message': row[9],
                        'retry_count': row[10]
                    })
                
                # Calculate summary
                passed = sum(1 for t in tests if t['status'] == 'passed')
                failed = sum(1 for t in tests if t['status'] in ['failed', 'error'])
                skipped = sum(1 for t in tests if t['status'] == 'skipped')
                
                return {
                    "run_id": run_id,
                    "tests": tests,
                    "total": len(tests),
                    "passed": passed,
                    "failed": failed,
                    "skipped": skipped
                }
        finally:
            return_db_connection(conn)
    except Exception as e:
        logger.error(f"Error getting run test results: {e}")
        raise HTTPException(status_code=500, detail="Failed to get test results")


# ============================================================================
# Statistics Endpoints
# ============================================================================

@router.get("/{plan_id}/statistics", response_model=PlanStatisticsResponse)
async def get_plan_statistics(
    plan_id: int,
    current_user: User = Depends(get_current_user_from_token)  # Placeholder for auth
):
    """Get execution plan statistics"""
    try:
        # Check if plan exists
        plan = get_plan_from_db(plan_id)
        if not plan:
            raise HTTPException(status_code=404, detail="Execution plan not found")
        
        stats = execution_plan_service.get_plan_statistics(plan_id)
        if not stats:
            raise HTTPException(status_code=500, detail="Failed to get plan statistics")
        
        return PlanStatisticsResponse(**stats)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting plan statistics: {e}")
        raise HTTPException(status_code=500, detail="Failed to get plan statistics")


@router.get("/recent/runs", response_model=dict)
async def get_recent_runs(
    limit: int = Query(50, ge=1, le=500),
    current_user: User = Depends(get_current_user_from_token)  # Placeholder for auth
):
    """Get recent execution plan runs"""
    try:
        runs = execution_plan_service.get_recent_runs(limit=limit)
        
        return {
            "runs": runs,
            "total": len(runs)
        }
    except Exception as e:
        logger.error(f"Error getting recent runs: {e}")
        raise HTTPException(status_code=500, detail="Failed to get recent runs")


# ============================================================================
# Notification Settings Endpoints
# ============================================================================

class NotificationSettingsRequest(BaseModel):
    """Request model for notification settings"""
    notify_on_start: bool = False
    notify_on_completion: bool = True
    notify_on_failure: bool = True
    notify_on_retry: bool = False
    email_recipients: Optional[List[str]] = None
    webhook_urls: Optional[List[str]] = None
    slack_channels: Optional[List[str]] = None


@router.get("/{plan_id}/notifications", response_model=dict)
async def get_notification_settings(
    plan_id: int,
    current_user: User = Depends(get_current_user_from_token)
):
    """Get notification settings for a plan"""
    try:
        from auroqa.Services.NotificationService import NotificationService
        notification_service = NotificationService()
        
        settings = notification_service.get_notification_settings(plan_id)
        if not settings:
            # Return default settings if none exist
            return {
                "plan_id": plan_id,
                "notify_on_start": False,
                "notify_on_completion": True,
                "notify_on_failure": True,
                "notify_on_retry": False,
                "email_recipients": [],
                "webhook_urls": [],
                "slack_channels": []
            }
        
        return {
            "plan_id": plan_id,
            **settings
        }
    except Exception as e:
        logger.error(f"Error getting notification settings: {e}")
        raise HTTPException(status_code=500, detail="Failed to get notification settings")


@router.put("/{plan_id}/notifications", response_model=dict)
async def update_notification_settings(
    plan_id: int,
    request: NotificationSettingsRequest,
    current_user: User = Depends(get_current_user_from_token)
):
    """Update notification settings for a plan"""
    try:
        # Verify plan exists
        plan = get_plan_from_db(plan_id)
        if not plan:
            raise HTTPException(status_code=404, detail="Execution plan not found")
        
        from auroqa.Services.NotificationService import NotificationService
        notification_service = NotificationService()
        
        success = notification_service.save_notification_settings(
            plan_id=plan_id,
            notify_on_start=request.notify_on_start,
            notify_on_completion=request.notify_on_completion,
            notify_on_failure=request.notify_on_failure,
            notify_on_retry=request.notify_on_retry,
            email_recipients=request.email_recipients,
            webhook_urls=request.webhook_urls,
            slack_channels=request.slack_channels
        )
        
        if not success:
            raise HTTPException(status_code=500, detail="Failed to save notification settings")
        
        return {"message": "Notification settings updated successfully", "plan_id": plan_id}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating notification settings: {e}")
        raise HTTPException(status_code=500, detail="Failed to update notification settings")


# ============================================================================
# Schedule Management Endpoints
# ============================================================================

class ScheduleRequest(BaseModel):
    """Request model for updating schedule"""
    schedule_type: str = Field(..., description="Schedule type: manual, once, recurring, cron")
    cron_expression: Optional[str] = Field(None, description="Cron expression for cron scheduling")
    recurrence_pattern: Optional[str] = Field(None, description="Pattern: daily, weekly, monthly, hourly")
    scheduled_at: Optional[datetime] = Field(None, description="Scheduled time for 'once' type")


@router.put("/{plan_id}/schedule", response_model=dict)
async def update_plan_schedule(
    plan_id: int,
    request: ScheduleRequest,
    current_user: User = Depends(get_current_user_from_token)
):
    """Update schedule settings for a plan"""
    try:
        # Verify plan exists
        plan = get_plan_from_db(plan_id)
        if not plan:
            raise HTTPException(status_code=404, detail="Execution plan not found")
        
        conn = get_db_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE execution_suite_plans
                    SET schedule_type = %s, cron_expression = %s, 
                        recurrence_pattern = %s, scheduled_at = %s,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = %s
                    """,
                    (request.schedule_type, request.cron_expression,
                     request.recurrence_pattern, request.scheduled_at, plan_id)
                )
                conn.commit()
                
                # Update scheduler if schedule changed (non-blocking)
                try:
                    from auroqa.Services.ExecutionScheduler import get_scheduler
                    scheduler = get_scheduler()
                    if scheduler and scheduler.scheduler.running:
                        if request.schedule_type in ['recurring', 'cron']:
                            scheduler.schedule_plan(
                                plan_id, 
                                request.schedule_type, 
                                request.cron_expression, 
                                request.recurrence_pattern
                            )
                        else:
                            scheduler.remove_schedule(plan_id)
                    else:
                        logger.warning(f"Scheduler not running, schedule saved to DB only for plan {plan_id}")
                except Exception as sched_err:
                    logger.warning(f"Failed to update scheduler for plan {plan_id}: {sched_err}")
                    # Don't fail the request, schedule is saved in DB
                
                return {
                    "message": "Schedule updated successfully",
                    "plan_id": plan_id,
                    "schedule_type": request.schedule_type
                }
        finally:
            return_db_connection(conn)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating plan schedule: {e}")
        raise HTTPException(status_code=500, detail="Failed to update schedule")
