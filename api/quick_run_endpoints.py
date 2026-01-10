"""
Quick Run API Endpoints

Provides REST API for manual/quick test execution.
This replaces the direct use of test_executions for new runs.

Features:
- Quick run individual test cases
- Quick run multiple test cases
- Get quick run history
- Get run details
"""

import logging
from typing import Optional, List, Union
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field, validator
from datetime import datetime
from auroqa.Services.QuickRunService import QuickRunService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/quick-run", tags=["quick-run"])

# Initialize service
quick_run_service = QuickRunService()


# ============================================================================
# Pydantic Models
# ============================================================================

class QuickRunTestCaseRequest(BaseModel):
    """Request model for quick running a single test case"""
    client_id: str = Field(..., description="Client UUID")
    project_id: Optional[str] = Field(None, description="Project UUID")
    test_case_id: int = Field(..., description="Test case ID to run")
    suite_id: Optional[int] = Field(None, description="Suite ID if applicable")
    created_by: Optional[Union[str, int]] = Field(None, description="User ID who initiated the run")
    
    @validator('created_by', pre=True, always=True)
    def convert_created_by(cls, v, values):
        # If created_by is not provided or not a valid UUID, use client_id
        if v is None:
            return values.get('client_id')
        v_str = str(v)
        # Check if it looks like a UUID (has dashes and is long enough)
        if len(v_str) >= 20 and '-' in v_str:
            return v_str
        # Not a UUID, use client_id as fallback
        return values.get('client_id', v_str)


class QuickRunMultipleRequest(BaseModel):
    """Request model for quick running multiple test cases"""
    client_id: str = Field(..., description="Client UUID")
    project_id: Optional[str] = Field(None, description="Project UUID")
    test_cases: List[dict] = Field(..., description="List of test cases with test_case_id and optional suite_id")
    name: Optional[str] = Field(None, description="Optional name for the run")
    created_by: Optional[Union[str, int]] = Field(None, description="User ID who initiated the run")
    
    @validator('created_by', pre=True, always=True)
    def convert_created_by(cls, v, values):
        if v is None:
            return values.get('client_id')
        v_str = str(v)
        if len(v_str) >= 20 and '-' in v_str:
            return v_str
        return values.get('client_id', v_str)


class LogTestResultRequest(BaseModel):
    """Request model for logging a test result"""
    run_id: int = Field(..., description="Execution plan run ID")
    test_case_id: int = Field(..., description="Test case ID")
    status: str = Field(..., description="Result status: passed, failed, skipped, error")
    suite_id: Optional[int] = Field(None, description="Suite ID if applicable")
    started_at: Optional[datetime] = Field(None, description="When test started")
    completed_at: Optional[datetime] = Field(None, description="When test completed")
    duration_seconds: Optional[float] = Field(None, description="Test duration")
    error_message: Optional[str] = Field(None, description="Error message if failed")
    screenshot_path: Optional[str] = Field(None, description="Path to screenshot")
    log_path: Optional[str] = Field(None, description="Path to log file")
    retry_count: int = Field(0, description="Number of retries")


class CompleteRunRequest(BaseModel):
    """Request model for completing a run"""
    run_id: int = Field(..., description="Execution plan run ID")
    status: str = Field("completed", description="Final status: completed, failed, cancelled")


class QuickRunResponse(BaseModel):
    """Response model for quick run"""
    plan_id: int
    run_id: int
    test_case_record_id: Optional[int] = None
    status: str


class RunHistoryItem(BaseModel):
    """Response model for run history item"""
    plan_id: int
    name: str
    status: str
    created_at: datetime
    last_executed_at: Optional[datetime]
    run_id: Optional[int]
    run_status: Optional[str]
    total_tests: Optional[int]
    passed_tests: Optional[int]
    failed_tests: Optional[int]
    duration_seconds: Optional[float]


class TestResultItem(BaseModel):
    """Response model for test result"""
    id: int
    test_case_id: int
    suite_id: Optional[int]
    status: str
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    duration_seconds: Optional[float]
    error_message: Optional[str]
    screenshot_path: Optional[str]
    log_path: Optional[str]
    retry_count: int


class RunDetailsResponse(BaseModel):
    """Response model for run details"""
    run_id: int
    plan_id: int
    plan_name: str
    started_at: datetime
    completed_at: Optional[datetime]
    status: str
    total_tests: Optional[int]
    passed_tests: Optional[int]
    failed_tests: Optional[int]
    skipped_tests: Optional[int]
    duration_seconds: Optional[float]
    triggered_by: str
    test_results: List[TestResultItem]


# ============================================================================
# Endpoints
# ============================================================================

@router.post("/test-case", response_model=QuickRunResponse)
async def quick_run_test_case(request: QuickRunTestCaseRequest):
    """
    Quick run a single test case.
    Creates an execution plan and prepares for test execution.
    """
    try:
        result = quick_run_service.quick_run_test_case(
            client_id=request.client_id,
            project_id=request.project_id,
            test_case_id=request.test_case_id,
            created_by=request.created_by,
            suite_id=request.suite_id
        )
        
        if 'error' in result:
            raise HTTPException(status_code=500, detail=result['error'])
        
        return QuickRunResponse(**result)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in quick run: {e}")
        raise HTTPException(status_code=500, detail="Failed to create quick run")


@router.post("/multiple", response_model=QuickRunResponse)
async def quick_run_multiple_test_cases(request: QuickRunMultipleRequest):
    """
    Quick run multiple test cases.
    Creates an execution plan with multiple test cases.
    """
    try:
        # Create quick run plan
        plan_name = request.name or f"Quick Run - {len(request.test_cases)} tests"
        plan_id = quick_run_service.create_quick_run_plan(
            client_id=request.client_id,
            project_id=request.project_id,
            name=plan_name,
            created_by=request.created_by,
            auto_delete=False
        )
        
        if not plan_id:
            raise HTTPException(status_code=500, detail="Failed to create quick run plan")
        
        # Add test cases
        success = quick_run_service.add_test_cases_to_plan(plan_id, request.test_cases)
        if not success:
            raise HTTPException(status_code=500, detail="Failed to add test cases to plan")
        
        # Create run
        run_id = quick_run_service.create_plan_run(plan_id, triggered_by='manual')
        if not run_id:
            raise HTTPException(status_code=500, detail="Failed to create plan run")
        
        return QuickRunResponse(
            plan_id=plan_id,
            run_id=run_id,
            status='ready'
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in quick run multiple: {e}")
        raise HTTPException(status_code=500, detail="Failed to create quick run")


@router.post("/log-result")
async def log_test_result(request: LogTestResultRequest):
    """
    Log a test result for a quick run.
    Called by TestRunner after each test case execution.
    """
    try:
        result_id = quick_run_service.log_test_run_result(
            run_id=request.run_id,
            test_case_id=request.test_case_id,
            status=request.status,
            suite_id=request.suite_id,
            started_at=request.started_at,
            completed_at=request.completed_at,
            duration_seconds=request.duration_seconds,
            error_message=request.error_message,
            screenshot_path=request.screenshot_path,
            log_path=request.log_path,
            retry_count=request.retry_count
        )
        
        if not result_id:
            raise HTTPException(status_code=500, detail="Failed to log test result")
        
        return {"success": True, "result_id": result_id}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error logging test result: {e}")
        raise HTTPException(status_code=500, detail="Failed to log test result")


@router.post("/complete")
async def complete_run(request: CompleteRunRequest):
    """
    Complete a quick run and calculate statistics.
    Called after all test cases have been executed.
    """
    try:
        success = quick_run_service.complete_plan_run(
            run_id=request.run_id,
            status=request.status
        )
        
        if not success:
            raise HTTPException(status_code=500, detail="Failed to complete run")
        
        return {"success": True}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error completing run: {e}")
        raise HTTPException(status_code=500, detail="Failed to complete run")


@router.get("/history")
async def get_quick_run_history(
    client_id: str = Query(..., description="Client UUID"),
    project_id: Optional[str] = Query(None, description="Project UUID filter"),
    limit: int = Query(50, ge=1, le=500, description="Maximum results")
):
    """
    Get quick run history for a client.
    """
    try:
        history = quick_run_service.get_quick_run_history(
            client_id=client_id,
            project_id=project_id,
            limit=limit
        )
        
        return {"history": history, "total": len(history)}
    except Exception as e:
        logger.error(f"Error getting quick run history: {e}")
        raise HTTPException(status_code=500, detail="Failed to get quick run history")


@router.get("/run/{run_id}")
async def get_run_details(run_id: int):
    """
    Get detailed results for a specific run.
    """
    try:
        details = quick_run_service.get_run_details(run_id)
        
        if 'error' in details:
            raise HTTPException(status_code=404, detail=details['error'])
        
        return details
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting run details: {e}")
        raise HTTPException(status_code=500, detail="Failed to get run details")
