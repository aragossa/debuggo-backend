"""
Execution Scheduler API Endpoints

Provides REST API for managing scheduled execution of test plans:
- Schedule plans for execution
- Manage scheduled jobs
- View execution schedule
- Pause/resume schedules
"""

import logging
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.security import OAuth2PasswordBearer
from pydantic import BaseModel, Field
from datetime import datetime
from auroqa.models.user import User
from auroqa.Services.ExecutionScheduler import get_scheduler
from auroqa.Services.ExecutionPlanService import ExecutionPlanService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/scheduler", tags=["scheduler"])

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
scheduler = get_scheduler()
plan_service = ExecutionPlanService()


# ============================================================================
# Pydantic Models
# ============================================================================

class SchedulePlanRequest(BaseModel):
    """Request model for scheduling a plan"""
    schedule_type: str = Field(..., description="Schedule type: manual, once, recurring, cron")
    cron_expression: Optional[str] = Field(None, description="Cron expression for cron scheduling")
    recurrence_pattern: Optional[str] = Field(None, description="Recurrence pattern for recurring scheduling")
    scheduled_at: Optional[datetime] = Field(None, description="Scheduled time for one-time execution")


class ScheduledJobResponse(BaseModel):
    """Response model for scheduled job"""
    id: str
    name: str
    next_run_time: Optional[datetime]
    trigger: str


class JobStatusResponse(BaseModel):
    """Response model for job status"""
    plan_id: int
    job_id: Optional[str] = None
    name: Optional[str] = None
    next_run_time: Optional[datetime] = None
    trigger: Optional[str] = None
    scheduled: bool


class ScheduledJobsListResponse(BaseModel):
    """Response model for scheduled jobs list"""
    jobs: List[ScheduledJobResponse]
    total: int


# ============================================================================
# Scheduler Management Endpoints
# ============================================================================

@router.post("/plans/{plan_id}/schedule")
async def schedule_plan(
    plan_id: int,
    request: SchedulePlanRequest,
    current_user: User = Depends(get_current_user_from_token)  # Placeholder for auth
):
    """Schedule a plan for execution"""
    try:
        # Verify plan exists
        plan = plan_service.get_execution_plan(plan_id)
        if not plan:
            raise HTTPException(status_code=404, detail="Plan not found")
        
        # Schedule the plan
        success = scheduler.schedule_plan(
            plan_id=plan_id,
            schedule_type=request.schedule_type,
            cron_expression=request.cron_expression,
            recurrence_pattern=request.recurrence_pattern
        )
        
        if not success:
            raise HTTPException(status_code=400, detail="Failed to schedule plan")
        
        # Get job status
        status = scheduler.get_job_status(plan_id)
        
        return {
            "status": "success",
            "message": f"Plan {plan_id} scheduled successfully",
            "job": status
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error scheduling plan: {e}")
        raise HTTPException(status_code=500, detail="Failed to schedule plan")


@router.delete("/plans/{plan_id}/schedule")
async def remove_schedule(
    plan_id: int,
    current_user: User = Depends(get_current_user_from_token)  # Placeholder for auth
):
    """Remove schedule for a plan"""
    try:
        # Verify plan exists
        plan = plan_service.get_execution_plan(plan_id)
        if not plan:
            raise HTTPException(status_code=404, detail="Plan not found")
        
        # Remove schedule
        success = scheduler.remove_schedule(plan_id)
        
        if not success:
            raise HTTPException(status_code=400, detail="Plan is not scheduled")
        
        return {
            "status": "success",
            "message": f"Schedule removed for plan {plan_id}"
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error removing schedule: {e}")
        raise HTTPException(status_code=500, detail="Failed to remove schedule")


@router.get("/plans/{plan_id}/status", response_model=JobStatusResponse)
async def get_schedule_status(
    plan_id: int,
    current_user: User = Depends(get_current_user_from_token)  # Placeholder for auth
):
    """Get schedule status for a plan"""
    try:
        # Verify plan exists
        plan = plan_service.get_execution_plan(plan_id)
        if not plan:
            raise HTTPException(status_code=404, detail="Plan not found")
        
        # Get job status
        status = scheduler.get_job_status(plan_id)
        
        if not status:
            raise HTTPException(status_code=500, detail="Failed to get job status")
        
        return JobStatusResponse(**status)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting schedule status: {e}")
        raise HTTPException(status_code=500, detail="Failed to get schedule status")


@router.post("/plans/{plan_id}/pause")
async def pause_schedule(
    plan_id: int,
    current_user: User = Depends(get_current_user_from_token)  # Placeholder for auth
):
    """Pause schedule for a plan"""
    try:
        # Verify plan exists
        plan = plan_service.get_execution_plan(plan_id)
        if not plan:
            raise HTTPException(status_code=404, detail="Plan not found")
        
        # Pause schedule
        success = scheduler.pause_schedule(plan_id)
        
        if not success:
            raise HTTPException(status_code=400, detail="Plan is not scheduled")
        
        return {
            "status": "success",
            "message": f"Schedule paused for plan {plan_id}"
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error pausing schedule: {e}")
        raise HTTPException(status_code=500, detail="Failed to pause schedule")


@router.post("/plans/{plan_id}/resume")
async def resume_schedule(
    plan_id: int,
    current_user: User = Depends(get_current_user_from_token)  # Placeholder for auth
):
    """Resume schedule for a plan"""
    try:
        # Verify plan exists
        plan = plan_service.get_execution_plan(plan_id)
        if not plan:
            raise HTTPException(status_code=404, detail="Plan not found")
        
        # Resume schedule
        success = scheduler.resume_schedule(plan_id)
        
        if not success:
            raise HTTPException(status_code=400, detail="Plan is not scheduled")
        
        return {
            "status": "success",
            "message": f"Schedule resumed for plan {plan_id}"
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error resuming schedule: {e}")
        raise HTTPException(status_code=500, detail="Failed to resume schedule")


# ============================================================================
# Scheduler Status Endpoints
# ============================================================================

@router.get("/jobs", response_model=ScheduledJobsListResponse)
async def list_scheduled_jobs(
    current_user: User = Depends(get_current_user_from_token)  # Placeholder for auth
):
    """List all scheduled jobs"""
    try:
        jobs = scheduler.get_scheduled_jobs()
        
        return ScheduledJobsListResponse(
            jobs=[ScheduledJobResponse(**job) for job in jobs],
            total=len(jobs)
        )
    except Exception as e:
        logger.error(f"Error listing scheduled jobs: {e}")
        raise HTTPException(status_code=500, detail="Failed to list scheduled jobs")


@router.get("/status")
async def get_scheduler_status(
    current_user: User = Depends(get_current_user_from_token)  # Placeholder for auth
):
    """Get scheduler status"""
    try:
        jobs = scheduler.get_scheduled_jobs()
        
        return {
            "status": "running" if scheduler.scheduler.running else "stopped",
            "total_jobs": len(jobs),
            "jobs": jobs
        }
    except Exception as e:
        logger.error(f"Error getting scheduler status: {e}")
        raise HTTPException(status_code=500, detail="Failed to get scheduler status")


# ============================================================================
# Scheduler Control Endpoints
# ============================================================================

@router.post("/start")
async def start_scheduler_endpoint(
    current_user: User = Depends(get_current_user_from_token)  # Placeholder for auth
):
    """Start the scheduler"""
    try:
        if not scheduler.scheduler.running:
            scheduler.start()
            return {
                "status": "success",
                "message": "Scheduler started"
            }
        else:
            return {
                "status": "info",
                "message": "Scheduler is already running"
            }
    except Exception as e:
        logger.error(f"Error starting scheduler: {e}")
        raise HTTPException(status_code=500, detail="Failed to start scheduler")


@router.post("/stop")
async def stop_scheduler_endpoint(
    current_user: User = Depends(get_current_user_from_token)  # Placeholder for auth
):
    """Stop the scheduler"""
    try:
        if scheduler.scheduler.running:
            scheduler.stop()
            return {
                "status": "success",
                "message": "Scheduler stopped"
            }
        else:
            return {
                "status": "info",
                "message": "Scheduler is already stopped"
            }
    except Exception as e:
        logger.error(f"Error stopping scheduler: {e}")
        raise HTTPException(status_code=500, detail="Failed to stop scheduler")


# ============================================================================
# Trigger Endpoints
# ============================================================================

@router.post("/plans/{plan_id}/trigger")
async def trigger_plan_execution(
    plan_id: int,
    current_user: User = Depends(get_current_user_from_token)  # Placeholder for auth
):
    """Manually trigger a scheduled plan execution immediately"""
    try:
        # Check if plan exists
        plan = plan_service.get_execution_plan(plan_id)
        if not plan:
            raise HTTPException(status_code=404, detail="Plan not found")
        
        # Execute the plan immediately in background
        import threading
        from auroqa.Services.ParallelExecutionEngine import ParallelExecutionEngine
        
        run_id = plan_service.create_plan_run(
            plan_id=plan_id,
            triggered_by='manual'
        )
        
        if not run_id:
            raise HTTPException(status_code=500, detail="Failed to create execution run")
        
        engine = ParallelExecutionEngine()
        max_parallel = plan.get('max_parallel_suites', 1)
        
        def run_execution():
            try:
                engine.execute_plan(plan_id=plan_id, run_id=run_id, max_parallel=max_parallel)
            except Exception as ex:
                logger.error(f"Triggered execution error for plan {plan_id}: {ex}")
        
        thread = threading.Thread(
            target=run_execution,
            name=f"TriggeredExec-{plan_id}-{run_id}",
            daemon=True
        )
        thread.start()
        
        return {
            "status": "triggered",
            "message": f"Plan {plan_id} execution triggered",
            "run_id": run_id
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error triggering plan execution: {e}")
        raise HTTPException(status_code=500, detail="Failed to trigger execution")


# ============================================================================
# Schedule Calculation Endpoints
# ============================================================================

@router.post("/calculate-next-execution")
async def calculate_next_execution(
    request: SchedulePlanRequest,
    current_user: User = Depends(get_current_user_from_token)  # Placeholder for auth
):
    """Calculate next execution time for a schedule"""
    try:
        next_execution = scheduler.calculate_next_execution(
            schedule_type=request.schedule_type,
            cron_expression=request.cron_expression,
            recurrence_pattern=request.recurrence_pattern,
            scheduled_at=request.scheduled_at
        )
        
        if not next_execution:
            raise HTTPException(status_code=400, detail="Invalid schedule configuration")
        
        return {
            "next_execution": next_execution,
            "schedule_type": request.schedule_type
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error calculating next execution: {e}")
        raise HTTPException(status_code=500, detail="Failed to calculate next execution")
