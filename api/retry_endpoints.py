"""
Retry Management API Endpoints

Provides REST API for managing test retry logic:
- Get retry statistics
- Get retry history
- Configure retry policies
- Monitor retry attempts
"""

import logging
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from datetime import datetime
from auroqa.models.user import User
from auroqa.Services.RetryManager import get_retry_manager

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/retry", tags=["retry"])

# Initialize services
retry_manager = get_retry_manager()


# ============================================================================
# Pydantic Models
# ============================================================================

class RetryStatisticsResponse(BaseModel):
    """Response model for retry statistics"""
    suite_run_id: int
    total_retries: int
    successful_retries: int
    failed_retries: int
    last_retry_at: Optional[datetime]


class RetryHistoryItemResponse(BaseModel):
    """Response model for retry history item"""
    id: int
    retry_number: int
    attempted_at: datetime
    completed_at: Optional[datetime]
    status: str
    passed_tests: int
    failed_tests: int
    error_message: Optional[str]


class RetryHistoryListResponse(BaseModel):
    """Response model for retry history list"""
    suite_run_id: int
    history: List[RetryHistoryItemResponse]
    total: int


class RetryDelayCalculationRequest(BaseModel):
    """Request model for retry delay calculation"""
    retry_count: int = Field(..., description="Current retry attempt number (0-indexed)")
    base_delay: int = Field(5, description="Base delay in seconds")
    backoff_multiplier: float = Field(2.0, description="Exponential backoff multiplier")
    max_delay: int = Field(300, description="Maximum delay in seconds")


class RetryDelayCalculationResponse(BaseModel):
    """Response model for retry delay calculation"""
    retry_count: int
    calculated_delay: int
    base_delay: int
    backoff_multiplier: float
    max_delay: int


# ============================================================================
# Retry Statistics Endpoints
# ============================================================================

@router.get("/suite-runs/{suite_run_id}/statistics", response_model=RetryStatisticsResponse)
async def get_retry_statistics(
    suite_run_id: int,
    current_user: User = Depends(lambda: None)  # Placeholder for auth
):
    """Get retry statistics for a suite run"""
    try:
        stats = retry_manager.get_retry_statistics(suite_run_id)
        
        if not stats:
            raise HTTPException(status_code=404, detail="Suite run not found")
        
        return RetryStatisticsResponse(**stats)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting retry statistics: {e}")
        raise HTTPException(status_code=500, detail="Failed to get retry statistics")


@router.get("/suite-runs/{suite_run_id}/history", response_model=RetryHistoryListResponse)
async def get_retry_history(
    suite_run_id: int,
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(lambda: None)  # Placeholder for auth
):
    """Get retry history for a suite run"""
    try:
        history = retry_manager.get_retry_history(suite_run_id, limit, offset)
        
        return RetryHistoryListResponse(
            suite_run_id=suite_run_id,
            history=[RetryHistoryItemResponse(**item) for item in history],
            total=len(history)
        )
    except Exception as e:
        logger.error(f"Error getting retry history: {e}")
        raise HTTPException(status_code=500, detail="Failed to get retry history")


# ============================================================================
# Retry Decision Endpoints
# ============================================================================

@router.post("/should-retry/{suite_run_id}")
async def should_retry(
    suite_run_id: int,
    current_retry_count: int = Query(..., description="Current retry count"),
    max_retries: int = Query(..., description="Maximum retries allowed"),
    current_user: User = Depends(lambda: None)  # Placeholder for auth
):
    """Determine if a suite should be retried"""
    try:
        should_retry_result = retry_manager.should_retry(
            suite_run_id=suite_run_id,
            current_retry_count=current_retry_count,
            max_retries=max_retries
        )
        
        return {
            "suite_run_id": suite_run_id,
            "should_retry": should_retry_result,
            "current_retry_count": current_retry_count,
            "max_retries": max_retries
        }
    except Exception as e:
        logger.error(f"Error determining retry eligibility: {e}")
        raise HTTPException(status_code=500, detail="Failed to determine retry eligibility")


@router.post("/should-retry-by-threshold/{suite_run_id}")
async def should_retry_by_threshold(
    suite_run_id: int,
    failure_percentage_threshold: float = Query(10.0, description="Failure percentage threshold"),
    current_user: User = Depends(lambda: None)  # Placeholder for auth
):
    """Determine if suite should be retried based on failure percentage"""
    try:
        should_retry_result = retry_manager.should_retry_based_on_threshold(
            suite_run_id=suite_run_id,
            failure_percentage_threshold=failure_percentage_threshold
        )
        
        return {
            "suite_run_id": suite_run_id,
            "should_retry": should_retry_result,
            "failure_percentage_threshold": failure_percentage_threshold
        }
    except Exception as e:
        logger.error(f"Error determining retry by threshold: {e}")
        raise HTTPException(status_code=500, detail="Failed to determine retry by threshold")


# ============================================================================
# Retry Delay Calculation Endpoints
# ============================================================================

@router.post("/calculate-delay", response_model=RetryDelayCalculationResponse)
async def calculate_retry_delay(
    request: RetryDelayCalculationRequest,
    current_user: User = Depends(lambda: None)  # Placeholder for auth
):
    """Calculate retry delay with exponential backoff"""
    try:
        delay = retry_manager.calculate_retry_delay(
            retry_count=request.retry_count,
            base_delay=request.base_delay,
            backoff_multiplier=request.backoff_multiplier,
            max_delay=request.max_delay
        )
        
        return RetryDelayCalculationResponse(
            retry_count=request.retry_count,
            calculated_delay=delay,
            base_delay=request.base_delay,
            backoff_multiplier=request.backoff_multiplier,
            max_delay=request.max_delay
        )
    except Exception as e:
        logger.error(f"Error calculating retry delay: {e}")
        raise HTTPException(status_code=500, detail="Failed to calculate retry delay")


# ============================================================================
# Retry Policy Endpoints
# ============================================================================

@router.get("/policies/default")
async def get_default_retry_policy(
    current_user: User = Depends(lambda: None)  # Placeholder for auth
):
    """Get default retry policy"""
    return {
        "max_retries": 3,
        "base_delay_seconds": 5,
        "backoff_multiplier": 2.0,
        "max_delay_seconds": 300,
        "failure_percentage_threshold": 10.0,
        "description": "Default retry policy with exponential backoff"
    }


@router.get("/policies/aggressive")
async def get_aggressive_retry_policy(
    current_user: User = Depends(lambda: None)  # Placeholder for auth
):
    """Get aggressive retry policy (more retries, shorter delays)"""
    return {
        "max_retries": 5,
        "base_delay_seconds": 2,
        "backoff_multiplier": 1.5,
        "max_delay_seconds": 60,
        "failure_percentage_threshold": 20.0,
        "description": "Aggressive retry policy with more attempts and shorter delays"
    }


@router.get("/policies/conservative")
async def get_conservative_retry_policy(
    current_user: User = Depends(lambda: None)  # Placeholder for auth
):
    """Get conservative retry policy (fewer retries, longer delays)"""
    return {
        "max_retries": 2,
        "base_delay_seconds": 10,
        "backoff_multiplier": 3.0,
        "max_delay_seconds": 600,
        "failure_percentage_threshold": 5.0,
        "description": "Conservative retry policy with fewer attempts and longer delays"
    }


@router.get("/policies/no-retry")
async def get_no_retry_policy(
    current_user: User = Depends(lambda: None)  # Placeholder for auth
):
    """Get no-retry policy"""
    return {
        "max_retries": 0,
        "base_delay_seconds": 0,
        "backoff_multiplier": 1.0,
        "max_delay_seconds": 0,
        "failure_percentage_threshold": 0.0,
        "description": "No retry policy - fail immediately"
    }
