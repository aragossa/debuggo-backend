"""
Execution Management API Endpoints

Provides REST API for executing test plans:
- Execute plans with parallel suite execution
- Track execution progress
- Cancel executions
- Get execution results
"""

import logging
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from datetime import datetime
from auroqa.models.user import User
from auroqa.Services.ParallelExecutionEngine import get_execution_engine
from auroqa.Services.ExecutionPlanService import ExecutionPlanService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/execution", tags=["execution"])

# Initialize services
execution_engine = get_execution_engine()
plan_service = ExecutionPlanService()


# ============================================================================
# Pydantic Models
# ============================================================================

class ExecutePlanRequest(BaseModel):
    """Request model for executing a plan"""
    max_parallel: int = Field(1, description="Maximum parallel suites")


class ExecutionResultResponse(BaseModel):
    """Response model for execution result"""
    plan_id: int
    run_id: int
    status: str
    suite_results: list
    total_suites: int
    passed_suites: int
    failed_suites: int
    skipped_suites: int
    total_tests: int
    passed_tests: int
    failed_tests: int
    skipped_tests: int
    started_at: datetime
    completed_at: Optional[datetime]


class ExecutionStatusResponse(BaseModel):
    """Response model for execution status"""
    id: int
    status: str
    started_at: datetime
    completed_at: Optional[datetime]
    total_suites: int
    passed_suites: int
    failed_suites: int
    total_tests: int
    passed_tests: int
    failed_tests: int


class ExecutionProgressResponse(BaseModel):
    """Response model for execution progress"""
    run_id: int
    status: str
    total_suites: int
    completed_suites: int
    passed_suites: int
    failed_suites: int
    total_tests: int
    completed_tests: int
    passed_tests: int
    failed_tests: int
    progress_percentage: int


# ============================================================================
# Execution Endpoints
# ============================================================================

def _execute_plan_background(plan_id: int, run_id: int, max_parallel: int):
    """Background task to execute plan - runs in separate thread"""
    import threading
    logger.info(f"[Thread {threading.current_thread().name}] Starting background execution for plan {plan_id}, run {run_id}")
    try:
        execution_engine.execute_plan(
            plan_id=plan_id,
            run_id=run_id,
            max_parallel=max_parallel
        )
        logger.info(f"[Thread {threading.current_thread().name}] Completed execution for plan {plan_id}, run {run_id}")
    except Exception as e:
        logger.error(f"[Thread {threading.current_thread().name}] Error executing plan {plan_id}: {e}")


@router.post("/plans/{plan_id}/execute")
async def execute_plan(
    plan_id: int,
    request: Optional[ExecutePlanRequest] = None,
    current_user: User = Depends(lambda: None)  # Placeholder for auth
):
    """Execute a plan with parallel suite execution (async - returns immediately)"""
    import threading
    try:
        # Verify plan exists
        plan = plan_service.get_execution_plan(plan_id)
        if not plan:
            raise HTTPException(status_code=404, detail="Plan not found")
        
        # Use default max_parallel if no request body
        max_parallel = request.max_parallel if request else plan.get('max_parallel_suites', 1)
        
        # Create execution run
        run_id = plan_service.create_plan_run(
            plan_id=plan_id,
            triggered_by='api',
            triggered_by_user_id=str(current_user.id) if current_user else None
        )
        
        if not run_id:
            raise HTTPException(status_code=500, detail="Failed to create execution run")
        
        # Start execution in background thread (non-blocking)
        thread = threading.Thread(
            target=_execute_plan_background,
            args=(plan_id, run_id, max_parallel),
            name=f"ExecutePlan-{plan_id}-{run_id}",
            daemon=True
        )
        thread.start()
        
        # Return immediately with run_id for tracking
        return {
            "status": "started",
            "message": "Execution started in background",
            "run_id": run_id,
            "plan_id": plan_id
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error executing plan: {e}")
        raise HTTPException(status_code=500, detail="Failed to execute plan")


@router.get("/runs/{run_id}/status", response_model=ExecutionStatusResponse)
async def get_execution_status(
    run_id: int,
    current_user: User = Depends(lambda: None)  # Placeholder for auth
):
    """Get execution status"""
    try:
        status = execution_engine.get_execution_status(run_id)
        
        if not status:
            raise HTTPException(status_code=404, detail="Execution run not found")
        
        return ExecutionStatusResponse(**status)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting execution status: {e}")
        raise HTTPException(status_code=500, detail="Failed to get execution status")


@router.get("/runs/{run_id}/progress", response_model=ExecutionProgressResponse)
async def get_execution_progress(
    run_id: int,
    current_user: User = Depends(lambda: None)  # Placeholder for auth
):
    """Get execution progress"""
    try:
        progress = execution_engine.get_execution_progress(run_id)
        
        if not progress:
            raise HTTPException(status_code=404, detail="Execution run not found")
        
        return ExecutionProgressResponse(**progress)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting execution progress: {e}")
        raise HTTPException(status_code=500, detail="Failed to get execution progress")


@router.post("/runs/{run_id}/cancel")
async def cancel_execution(
    run_id: int,
    current_user: User = Depends(lambda: None)  # Placeholder for auth
):
    """Cancel an ongoing execution"""
    try:
        success = execution_engine.cancel_execution(run_id)
        
        if not success:
            raise HTTPException(status_code=400, detail="Could not cancel execution")
        
        return {
            "status": "success",
            "message": f"Execution {run_id} cancelled"
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error cancelling execution: {e}")
        raise HTTPException(status_code=500, detail="Failed to cancel execution")


# ============================================================================
# Execution Results Endpoints
# ============================================================================

@router.get("/runs/{run_id}/results")
async def get_execution_results(
    run_id: int,
    current_user: User = Depends(lambda: None)  # Placeholder for auth
):
    """Get detailed execution results"""
    try:
        status = execution_engine.get_execution_status(run_id)
        
        if not status:
            raise HTTPException(status_code=404, detail="Execution run not found")
        
        return {
            "run_id": run_id,
            "status": status['status'],
            "started_at": status['started_at'],
            "completed_at": status['completed_at'],
            "statistics": {
                "suites": {
                    "total": status['total_suites'],
                    "passed": status['passed_suites'],
                    "failed": status['failed_suites']
                },
                "tests": {
                    "total": status['total_tests'],
                    "passed": status['passed_tests'],
                    "failed": status['failed_tests']
                }
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting execution results: {e}")
        raise HTTPException(status_code=500, detail="Failed to get execution results")


@router.get("/runs/{run_id}/suite-results")
async def get_suite_execution_results(
    run_id: int,
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(lambda: None)  # Placeholder for auth
):
    """Get suite-level execution results"""
    try:
        from auroqa.Utils.Connectors.db_utils import get_db_connection, return_db_connection
        
        conn = get_db_connection()
        try:
            with conn.cursor() as cursor:
                # Get total count
                cursor.execute(
                    "SELECT COUNT(*) FROM execution_suite_plan_suite_runs WHERE execution_suite_plan_run_id = %s",
                    (run_id,)
                )
                total = cursor.fetchone()[0]
                
                # Get paginated results
                cursor.execute(
                    """
                    SELECT id, test_suite_id, status, started_at, completed_at,
                           total_tests, passed_tests, failed_tests, duration_seconds
                    FROM execution_suite_plan_suite_runs
                    WHERE execution_suite_plan_run_id = %s
                    ORDER BY started_at DESC
                    LIMIT %s OFFSET %s
                    """,
                    (run_id, limit, offset)
                )
                
                suite_results = []
                for row in cursor.fetchall():
                    suite_results.append({
                        'id': row[0],
                        'suite_id': row[1],
                        'status': row[2],
                        'started_at': row[3],
                        'completed_at': row[4],
                        'total_tests': row[5],
                        'passed_tests': row[6],
                        'failed_tests': row[7],
                        'duration_seconds': row[8]
                    })
                
                return {
                    "run_id": run_id,
                    "suite_results": suite_results,
                    "total": total
                }
        finally:
            return_db_connection(conn)
    except Exception as e:
        logger.error(f"Error getting suite results: {e}")
        raise HTTPException(status_code=500, detail="Failed to get suite results")
