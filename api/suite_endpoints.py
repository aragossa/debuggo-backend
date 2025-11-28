"""
Test Suite API Endpoints
Provides CRUD operations and execution management for test suites
"""

from fastapi import APIRouter, HTTPException, Depends, Query
from fastapi.security import OAuth2PasswordBearer
from pydantic import BaseModel, UUID4
from typing import List, Optional
from datetime import datetime
import logging
from auroqa.Services.SuiteService import SuiteService
from auroqa.models.user import User
from auroqa.Utils.System import System

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/suites", tags=["test-suites"])

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


# ============================================================================
# PYDANTIC MODELS
# ============================================================================

class CreateSuiteRequest(BaseModel):
    """Create suite request"""
    name: str
    suite_type: str = 'static'  # 'static', 'dynamic', 'smart'
    project_id: Optional[UUID4] = None
    description: Optional[str] = None
    parent_suite_id: Optional[int] = None
    default_environment_id: Optional[int] = None


class UpdateSuiteRequest(BaseModel):
    """Update suite request"""
    name: Optional[str] = None
    description: Optional[str] = None
    default_environment_id: Optional[int] = None
    parent_suite_id: Optional[int] = None
    suite_type: Optional[str] = None


class AddTestToSuiteRequest(BaseModel):
    """Add test to suite request"""
    test_case_id: int
    execution_order: int = 0
    environment_override_id: Optional[int] = None


class AddMultipleTestsRequest(BaseModel):
    """Add multiple tests to suite"""
    test_case_ids: List[int]


class SuiteResponse(BaseModel):
    """Suite response model"""
    id: int
    client_id: UUID4
    project_id: Optional[UUID4]
    name: str
    description: Optional[str]
    parent_suite_id: Optional[int]
    suite_type: str
    default_environment_id: Optional[int]
    created_by: Optional[int]
    created_at: datetime
    updated_at: datetime
    test_count: int


class SuiteTestResponse(BaseModel):
    """Test in suite response"""
    id: int
    test_case_id: int
    test_name: str
    test_type: str
    description: Optional[str]
    execution_order: int
    environment_override_id: Optional[int]


class SuiteStatisticsResponse(BaseModel):
    """Suite statistics response"""
    total_tests: int
    ui_tests: int
    api_tests: int
    total_runs: Optional[int]
    passed_runs: Optional[int]
    failed_runs: Optional[int]
    avg_duration_seconds: Optional[float]


# ============================================================================
# ENDPOINTS
# ============================================================================

@router.post("", response_model=SuiteResponse)
async def create_suite(
    request: CreateSuiteRequest,
    current_user: User = Depends(get_current_user_from_token)
):
    """Create a new test suite"""
    try:
        system = System()
        conn = system.get_db_connection()
        
        suite_service = SuiteService(conn)
        suite_id = suite_service.create_suite(
            client_id=str(current_user.client_id),
            name=request.name,
            suite_type=request.suite_type,
            project_id=str(request.project_id) if request.project_id else None,
            description=request.description,
            parent_suite_id=request.parent_suite_id,
            default_environment_id=request.default_environment_id,
            created_by=current_user.id
        )
        
        suite = suite_service.get_suite(suite_id)
        system.return_connection(conn)
        
        return SuiteResponse(
            id=suite.id,
            client_id=suite.client_id,
            project_id=suite.project_id,
            name=suite.name,
            description=suite.description,
            parent_suite_id=suite.parent_suite_id,
            suite_type=suite.suite_type,
            default_environment_id=suite.default_environment_id,
            created_by=suite.created_by,
            created_at=suite.created_at,
            updated_at=suite.updated_at,
            test_count=suite.test_count
        )
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error creating suite: {e}")
        raise HTTPException(status_code=500, detail="Failed to create suite")


@router.get("", response_model=List[SuiteResponse])
async def list_suites(
    project_id: Optional[UUID4] = Query(None),
    parent_suite_id: Optional[int] = Query(None),
    current_user: User = Depends(get_current_user_from_token)
):
    """List test suites"""
    try:
        system = System()
        conn = system.get_db_connection()
        
        suite_service = SuiteService(conn)
        suites = suite_service.list_suites(
            client_id=str(current_user.client_id),
            project_id=str(project_id) if project_id else None,
            parent_suite_id=parent_suite_id
        )
        
        system.return_connection(conn)
        
        return [SuiteResponse(
            id=s.id,
            client_id=s.client_id,
            project_id=s.project_id,
            name=s.name,
            description=s.description,
            parent_suite_id=s.parent_suite_id,
            suite_type=s.suite_type,
            default_environment_id=s.default_environment_id,
            created_by=s.created_by,
            created_at=s.created_at,
            updated_at=s.updated_at,
            test_count=s.test_count
        ) for s in suites]
        
    except Exception as e:
        logger.error(f"Error listing suites: {e}")
        raise HTTPException(status_code=500, detail="Failed to list suites")


@router.get("/{suite_id}", response_model=SuiteResponse)
async def get_suite(
    suite_id: int,
    current_user: User = Depends(get_current_user_from_token)
):
    """Get suite details"""
    try:
        system = System()
        conn = system.get_db_connection()
        
        suite_service = SuiteService(conn)
        suite = suite_service.get_suite(suite_id)
        
        if not suite:
            system.return_connection(conn)
            raise HTTPException(status_code=404, detail="Suite not found")
        
        # Verify user's client matches suite's client
        if str(suite.client_id) != str(current_user.client_id):
            system.return_connection(conn)
            raise HTTPException(status_code=403, detail="Access denied")
        
        system.return_connection(conn)
        
        return SuiteResponse(
            id=suite.id,
            client_id=suite.client_id,
            project_id=suite.project_id,
            name=suite.name,
            description=suite.description,
            parent_suite_id=suite.parent_suite_id,
            suite_type=suite.suite_type,
            default_environment_id=suite.default_environment_id,
            created_by=suite.created_by,
            created_at=suite.created_at,
            updated_at=suite.updated_at,
            test_count=suite.test_count
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting suite: {e}")
        raise HTTPException(status_code=500, detail="Failed to get suite")


@router.put("/{suite_id}", response_model=SuiteResponse)
async def update_suite(
    suite_id: int,
    request: UpdateSuiteRequest,
    current_user: User = Depends(get_current_user_from_token)
):
    """Update suite"""
    try:
        system = System()
        conn = system.get_db_connection()
        
        suite_service = SuiteService(conn)
        
        # Verify ownership
        suite = suite_service.get_suite(suite_id)
        if not suite or str(suite.client_id) != str(current_user.client_id):
            system.return_connection(conn)
            raise HTTPException(status_code=403, detail="Access denied")
        
        # Update
        update_data = {k: v for k, v in request.dict().items() if v is not None}
        suite_service.update_suite(suite_id, **update_data)
        
        # Return updated suite
        suite = suite_service.get_suite(suite_id)
        system.return_connection(conn)
        
        return SuiteResponse(
            id=suite.id,
            client_id=suite.client_id,
            project_id=suite.project_id,
            name=suite.name,
            description=suite.description,
            parent_suite_id=suite.parent_suite_id,
            suite_type=suite.suite_type,
            default_environment_id=suite.default_environment_id,
            created_by=suite.created_by,
            created_at=suite.created_at,
            updated_at=suite.updated_at,
            test_count=suite.test_count
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating suite: {e}")
        raise HTTPException(status_code=500, detail="Failed to update suite")


@router.delete("/{suite_id}")
async def delete_suite(
    suite_id: int,
    current_user: User = Depends(get_current_user_from_token)
):
    """Delete suite"""
    try:
        system = System()
        conn = system.get_db_connection()
        
        suite_service = SuiteService(conn)
        
        # Verify ownership
        suite = suite_service.get_suite(suite_id)
        if not suite or str(suite.client_id) != str(current_user.client_id):
            system.return_connection(conn)
            raise HTTPException(status_code=403, detail="Access denied")
        
        # Delete
        suite_service.delete_suite(suite_id)
        system.return_connection(conn)
        
        return {"status": "success", "message": "Suite deleted"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting suite: {e}")
        raise HTTPException(status_code=500, detail="Failed to delete suite")


@router.post("/{suite_id}/tests", response_model=dict)
async def add_test_to_suite(
    suite_id: int,
    request: AddTestToSuiteRequest,
    current_user: User = Depends(get_current_user_from_token)
):
    """Add test case to suite"""
    try:
        system = System()
        conn = system.get_db_connection()
        
        suite_service = SuiteService(conn)
        
        # Verify ownership
        suite = suite_service.get_suite(suite_id)
        if not suite or str(suite.client_id) != str(current_user.client_id):
            system.return_connection(conn)
            raise HTTPException(status_code=403, detail="Access denied")
        
        # Add test
        stc_id = suite_service.add_test_to_suite(
            suite_id=suite_id,
            test_case_id=request.test_case_id,
            execution_order=request.execution_order,
            environment_override_id=request.environment_override_id
        )
        
        system.return_connection(conn)
        
        return {
            "status": "success",
            "message": "Test added to suite",
            "suite_test_case_id": stc_id
        }
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error adding test to suite: {e}")
        raise HTTPException(status_code=500, detail="Failed to add test")


@router.post("/{suite_id}/tests/bulk", response_model=dict)
async def add_multiple_tests_to_suite(
    suite_id: int,
    request: AddMultipleTestsRequest,
    current_user: User = Depends(get_current_user_from_token)
):
    """Add multiple test cases to suite"""
    try:
        system = System()
        conn = system.get_db_connection()
        
        suite_service = SuiteService(conn)
        
        # Verify ownership
        suite = suite_service.get_suite(suite_id)
        if not suite or str(suite.client_id) != str(current_user.client_id):
            system.return_connection(conn)
            raise HTTPException(status_code=403, detail="Access denied")
        
        # Add tests
        added_count = 0
        failed_count = 0
        
        for idx, test_case_id in enumerate(request.test_case_ids):
            try:
                suite_service.add_test_to_suite(
                    suite_id=suite_id,
                    test_case_id=test_case_id,
                    execution_order=idx
                )
                added_count += 1
            except Exception as e:
                logger.warning(f"Failed to add test {test_case_id}: {e}")
                failed_count += 1
        
        system.return_connection(conn)
        
        return {
            "status": "success",
            "added_count": added_count,
            "failed_count": failed_count,
            "message": f"Added {added_count} tests to suite"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error adding multiple tests: {e}")
        raise HTTPException(status_code=500, detail="Failed to add tests")


@router.delete("/{suite_id}/tests/{test_case_id}")
async def remove_test_from_suite(
    suite_id: int,
    test_case_id: int,
    current_user: User = Depends(get_current_user_from_token)
):
    """Remove test case from suite"""
    try:
        system = System()
        conn = system.get_db_connection()
        
        suite_service = SuiteService(conn)
        
        # Verify ownership
        suite = suite_service.get_suite(suite_id)
        if not suite or str(suite.client_id) != str(current_user.client_id):
            system.return_connection(conn)
            raise HTTPException(status_code=403, detail="Access denied")
        
        # Remove test
        suite_service.remove_test_from_suite(suite_id, test_case_id)
        system.return_connection(conn)
        
        return {"status": "success", "message": "Test removed from suite"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error removing test from suite: {e}")
        raise HTTPException(status_code=500, detail="Failed to remove test")


@router.get("/{suite_id}/tests", response_model=List[SuiteTestResponse])
async def get_suite_tests(
    suite_id: int,
    current_user: User = Depends(get_current_user_from_token)
):
    """Get all tests in a suite"""
    try:
        system = System()
        conn = system.get_db_connection()
        
        suite_service = SuiteService(conn)
        
        # Verify ownership
        suite = suite_service.get_suite(suite_id)
        if not suite or str(suite.client_id) != str(current_user.client_id):
            system.return_connection(conn)
            raise HTTPException(status_code=403, detail="Access denied")
        
        # Get tests
        tests = suite_service.get_suite_tests(suite_id)
        system.return_connection(conn)
        
        return [SuiteTestResponse(**test) for test in tests]
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting suite tests: {e}")
        raise HTTPException(status_code=500, detail="Failed to get tests")


@router.get("/{suite_id}/statistics", response_model=SuiteStatisticsResponse)
async def get_suite_statistics(
    suite_id: int,
    current_user: User = Depends(get_current_user_from_token)
):
    """Get suite statistics"""
    try:
        system = System()
        conn = system.get_db_connection()
        
        suite_service = SuiteService(conn)
        
        # Verify ownership
        suite = suite_service.get_suite(suite_id)
        if not suite or str(suite.client_id) != str(current_user.client_id):
            system.return_connection(conn)
            raise HTTPException(status_code=403, detail="Access denied")
        
        # Get statistics
        stats = suite_service.get_suite_statistics(suite_id)
        system.return_connection(conn)
        
        return SuiteStatisticsResponse(**stats)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting suite statistics: {e}")
        raise HTTPException(status_code=500, detail="Failed to get statistics")


@router.get("/{suite_id}/hierarchy", response_model=dict)
async def get_suite_hierarchy(
    suite_id: int,
    current_user: User = Depends(get_current_user_from_token)
):
    """Get suite hierarchy starting from given suite"""
    try:
        system = System()
        conn = system.get_db_connection()
        
        suite_service = SuiteService(conn)
        
        # Verify ownership
        suite = suite_service.get_suite(suite_id)
        if not suite or str(suite.client_id) != str(current_user.client_id):
            system.return_connection(conn)
            raise HTTPException(status_code=403, detail="Access denied")
        
        # Get hierarchy
        hierarchy = suite_service.get_suite_hierarchy(
            client_id=str(current_user.client_id),
            project_id=str(suite.project_id) if suite.project_id else None
        )
        
        system.return_connection(conn)
        
        return {
            "status": "success",
            "suites": hierarchy
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting suite hierarchy: {e}")
        raise HTTPException(status_code=500, detail="Failed to get hierarchy")
