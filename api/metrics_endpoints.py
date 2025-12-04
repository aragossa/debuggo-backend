"""
Metrics & Analytics API Endpoints

Provides REST API for test execution metrics:
- Execution statistics
- Trend analysis
- Performance metrics
- Failure analysis
- Comparison analysis
- Dashboard summaries
"""

import logging
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.security import OAuth2PasswordBearer
from pydantic import BaseModel, Field
from datetime import datetime, timedelta
from auroqa.models.user import User
from auroqa.Services.MetricsService import get_metrics_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/metrics", tags=["metrics"])

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
metrics_service = get_metrics_service()


# ============================================================================
# Pydantic Models
# ============================================================================

class ExecutionStatsResponse(BaseModel):
    """Response model for execution statistics"""
    plan_id: int
    total_runs: int
    passed_runs: int
    failed_runs: int
    pass_rate: float
    avg_duration_seconds: float
    min_duration_seconds: float
    max_duration_seconds: float
    total_tests: int
    total_passed_tests: int
    total_failed_tests: int
    overall_pass_rate: float


class TrendDataPoint(BaseModel):
    """Response model for trend data point"""
    date: str
    total_runs: int
    passed_runs: int
    failed_runs: int
    pass_rate: float
    avg_duration_seconds: float
    total_tests: int
    total_passed_tests: int
    total_failed_tests: int
    test_pass_rate: float


class SuitePerformanceResponse(BaseModel):
    """Response model for suite performance"""
    suite_id: int
    total_runs: int
    avg_duration_seconds: float
    max_duration_seconds: float
    passed_runs: int
    failed_runs: int
    pass_rate: float


class SuiteFlakinessResponse(BaseModel):
    """Response model for suite flakiness"""
    suite_id: int
    total_runs: int
    passed_runs: int
    failed_runs: int
    pass_rate: float
    duration_stddev: float
    avg_duration_seconds: float
    flakiness_score: float


class FailureAnalysisResponse(BaseModel):
    """Response model for failure analysis"""
    plan_id: int
    total_failures: int
    suites_with_failures: int
    total_failed_tests: int
    failure_rate: float
    avg_failures_per_run: float


class RunComparison(BaseModel):
    """Response model for run comparison"""
    id: int
    status: str
    total_tests: int
    passed_tests: int
    failed_tests: int
    duration_seconds: float
    pass_rate: float


class ComparisonDifferences(BaseModel):
    """Response model for comparison differences"""
    test_count_change: int
    passed_tests_change: int
    failed_tests_change: int
    duration_change_seconds: float
    pass_rate_change: float


class ComparisonResponse(BaseModel):
    """Response model for plan run comparison"""
    plan_id: int
    run_1: RunComparison
    run_2: RunComparison
    differences: ComparisonDifferences


class DashboardSummaryResponse(BaseModel):
    """Response model for dashboard summary"""
    plan_id: int
    execution_stats: ExecutionStatsResponse
    failure_analysis: FailureAnalysisResponse
    slowest_suites: List[SuitePerformanceResponse]
    flaky_suites: List[SuiteFlakinessResponse]
    recent_trend: List[TrendDataPoint]
    generated_at: datetime


# ============================================================================
# Execution Statistics Endpoints
# ============================================================================

@router.get("/plans/{plan_id}/stats", response_model=ExecutionStatsResponse)
async def get_plan_stats(
    plan_id: int,
    current_user: User = Depends(get_current_user_from_token)  # Placeholder for auth
):
    """Get execution statistics for a plan"""
    try:
        stats = metrics_service.get_plan_execution_stats(plan_id)
        
        if not stats:
            raise HTTPException(status_code=404, detail="Plan not found or no executions")
        
        return ExecutionStatsResponse(**stats)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting plan stats: {e}")
        raise HTTPException(status_code=500, detail="Failed to get plan statistics")


@router.get("/suites/{suite_id}/stats", response_model=ExecutionStatsResponse)
async def get_suite_stats(
    suite_id: int,
    current_user: User = Depends(get_current_user_from_token)  # Placeholder for auth
):
    """Get execution statistics for a suite"""
    try:
        stats = metrics_service.get_suite_execution_stats(suite_id)
        
        if not stats:
            raise HTTPException(status_code=404, detail="Suite not found or no executions")
        
        return ExecutionStatsResponse(**stats)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting suite stats: {e}")
        raise HTTPException(status_code=500, detail="Failed to get suite statistics")


# ============================================================================
# Trend Analysis Endpoints
# ============================================================================

@router.get("/plans/{plan_id}/trend")
async def get_execution_trend(
    plan_id: int,
    days: int = Query(30, ge=1, le=365),
    current_user: User = Depends(get_current_user_from_token)  # Placeholder for auth
):
    """Get execution trend over time"""
    try:
        trend = metrics_service.get_execution_trend(plan_id, days)
        
        return {
            "plan_id": plan_id,
            "days": days,
            "trend": [TrendDataPoint(**item) for item in trend],
            "total_data_points": len(trend)
        }
    except Exception as e:
        logger.error(f"Error getting execution trend: {e}")
        raise HTTPException(status_code=500, detail="Failed to get execution trend")


# ============================================================================
# Performance Analysis Endpoints
# ============================================================================

@router.get("/plans/{plan_id}/slowest-suites")
async def get_slowest_suites(
    plan_id: int,
    limit: int = Query(10, ge=1, le=100),
    current_user: User = Depends(get_current_user_from_token)  # Placeholder for auth
):
    """Get slowest performing suites"""
    try:
        slowest = metrics_service.get_slowest_suites(plan_id, limit)
        
        return {
            "plan_id": plan_id,
            "limit": limit,
            "slowest_suites": [SuitePerformanceResponse(**item) for item in slowest],
            "total": len(slowest)
        }
    except Exception as e:
        logger.error(f"Error getting slowest suites: {e}")
        raise HTTPException(status_code=500, detail="Failed to get slowest suites")


@router.get("/plans/{plan_id}/flaky-suites")
async def get_flaky_suites(
    plan_id: int,
    limit: int = Query(10, ge=1, le=100),
    current_user: User = Depends(get_current_user_from_token)  # Placeholder for auth
):
    """Get most flaky (inconsistent) suites"""
    try:
        flaky = metrics_service.get_most_flaky_suites(plan_id, limit)
        
        return {
            "plan_id": plan_id,
            "limit": limit,
            "flaky_suites": [SuiteFlakinessResponse(**item) for item in flaky],
            "total": len(flaky)
        }
    except Exception as e:
        logger.error(f"Error getting flaky suites: {e}")
        raise HTTPException(status_code=500, detail="Failed to get flaky suites")


# ============================================================================
# Failure Analysis Endpoints
# ============================================================================

@router.get("/plans/{plan_id}/failure-analysis", response_model=FailureAnalysisResponse)
async def get_failure_analysis(
    plan_id: int,
    current_user: User = Depends(get_current_user_from_token)  # Placeholder for auth
):
    """Get failure analysis for a plan"""
    try:
        analysis = metrics_service.get_failure_analysis(plan_id)
        
        if not analysis:
            raise HTTPException(status_code=404, detail="Plan not found")
        
        return FailureAnalysisResponse(**analysis)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting failure analysis: {e}")
        raise HTTPException(status_code=500, detail="Failed to get failure analysis")


# ============================================================================
# Comparison Analysis Endpoints
# ============================================================================

@router.get("/plans/{plan_id}/compare-runs", response_model=ComparisonResponse)
async def compare_plan_runs(
    plan_id: int,
    run_id_1: int = Query(..., description="First run ID"),
    run_id_2: int = Query(..., description="Second run ID"),
    current_user: User = Depends(get_current_user_from_token)  # Placeholder for auth
):
    """Compare two plan runs"""
    try:
        comparison = metrics_service.compare_plan_runs(plan_id, run_id_1, run_id_2)
        
        if not comparison:
            raise HTTPException(status_code=404, detail="Runs not found")
        
        return ComparisonResponse(**comparison)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error comparing plan runs: {e}")
        raise HTTPException(status_code=500, detail="Failed to compare plan runs")


# ============================================================================
# Dashboard Endpoints
# ============================================================================

@router.get("/plans/{plan_id}/dashboard")
async def get_dashboard_summary(
    plan_id: int,
    current_user: User = Depends(get_current_user_from_token)  # Placeholder for auth
):
    """Get comprehensive dashboard summary for a plan"""
    try:
        summary = metrics_service.get_dashboard_summary(plan_id)
        
        if not summary:
            raise HTTPException(status_code=404, detail="Plan not found or no executions")
        
        return DashboardSummaryResponse(**summary)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting dashboard summary: {e}")
        raise HTTPException(status_code=500, detail="Failed to get dashboard summary")


# ============================================================================
# Health Check Endpoints
# ============================================================================

@router.get("/health")
async def metrics_health_check(
    current_user: User = Depends(get_current_user_from_token)  # Placeholder for auth
):
    """Health check for metrics service"""
    return {
        "status": "healthy",
        "service": "metrics",
        "timestamp": datetime.now()
    }
