"""
Requirements Traceability API Endpoints

Provides REST API for:
- Requirement CRUD operations
- Test-to-requirement mapping
- Coverage analysis
- Traceability matrix
"""

import logging
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from datetime import datetime
from auroqa.models.user import User
from auroqa.Services.RequirementsService import get_requirements_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/requirements", tags=["requirements"])

# Initialize service
requirements_service = get_requirements_service()


# ============================================================================
# Pydantic Models
# ============================================================================

class RequirementCreate(BaseModel):
    """Request model for creating a requirement"""
    client_id: str
    project_id: str
    requirement_id: str = Field(..., description="Unique requirement ID like REQ-001")
    title: str
    description: Optional[str] = None
    requirement_type: str = Field(default='functional', description="functional, non-functional, etc.")
    priority: str = Field(default='medium', description="low, medium, high, critical")
    status: str = Field(default='draft', description="draft, approved, implemented, verified, deprecated")


class RequirementUpdate(BaseModel):
    """Request model for updating a requirement"""
    title: Optional[str] = None
    description: Optional[str] = None
    requirement_type: Optional[str] = None
    priority: Optional[str] = None
    status: Optional[str] = None


class RequirementResponse(BaseModel):
    """Response model for a requirement"""
    id: int
    client_id: str
    project_id: Optional[str]
    requirement_id: str
    title: str
    description: Optional[str]
    requirement_type: str
    priority: str
    status: str
    created_at: Optional[datetime]
    updated_at: Optional[datetime]


class TestMappingRequest(BaseModel):
    """Request model for mapping test to requirement"""
    test_case_id: int
    coverage_type: str = Field(default='full', description="full, partial, exploratory")


class TestMappingResponse(BaseModel):
    """Response model for test mapping"""
    test_case_id: int
    name: str
    description: Optional[str]
    type: Optional[str]
    coverage_type: str


class CoverageSummaryResponse(BaseModel):
    """Response model for coverage summary"""
    total_requirements: int
    covered_requirements: int
    uncovered_requirements: int
    coverage_percentage: float
    by_status: dict
    by_priority: dict
    by_coverage_type: dict


class TraceabilityMatrixItem(BaseModel):
    """Response model for traceability matrix item"""
    id: int
    requirement_id: str
    title: str
    priority: str
    status: str
    test_count: int
    test_names: str
    is_covered: bool


# ============================================================================
# Requirement CRUD Endpoints
# ============================================================================

@router.post("", response_model=dict)
async def create_requirement(
    request: RequirementCreate,
    current_user: User = Depends(lambda: None)
):
    """Create a new requirement"""
    try:
        req_id = requirements_service.create_requirement(
            client_id=request.client_id,
            project_id=request.project_id,
            requirement_id=request.requirement_id,
            title=request.title,
            description=request.description,
            requirement_type=request.requirement_type,
            priority=request.priority,
            status=request.status,
            created_by=current_user.id if current_user else None
        )
        
        if not req_id:
            raise HTTPException(status_code=500, detail="Failed to create requirement")
        
        return {"id": req_id, "message": "Requirement created successfully"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating requirement: {e}")
        raise HTTPException(status_code=500, detail="Failed to create requirement")


@router.get("", response_model=dict)
async def list_requirements(
    client_id: str = Query(...),
    project_id: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    priority: Optional[str] = Query(None),
    requirement_type: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(lambda: None)
):
    """List requirements with filters"""
    try:
        requirements, total = requirements_service.list_requirements(
            client_id=client_id,
            project_id=project_id,
            status=status,
            priority=priority,
            requirement_type=requirement_type,
            limit=limit,
            offset=offset
        )
        
        return {
            "requirements": requirements,
            "total": total,
            "limit": limit,
            "offset": offset
        }
    except Exception as e:
        logger.error(f"Error listing requirements: {e}")
        raise HTTPException(status_code=500, detail="Failed to list requirements")


@router.get("/{requirement_id}", response_model=RequirementResponse)
async def get_requirement(
    requirement_id: int,
    current_user: User = Depends(lambda: None)
):
    """Get a requirement by ID"""
    try:
        requirement = requirements_service.get_requirement(requirement_id)
        if not requirement:
            raise HTTPException(status_code=404, detail="Requirement not found")
        
        return RequirementResponse(**requirement)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting requirement: {e}")
        raise HTTPException(status_code=500, detail="Failed to get requirement")


@router.put("/{requirement_id}", response_model=dict)
async def update_requirement(
    requirement_id: int,
    request: RequirementUpdate,
    current_user: User = Depends(lambda: None)
):
    """Update a requirement"""
    try:
        success = requirements_service.update_requirement(
            requirement_db_id=requirement_id,
            title=request.title,
            description=request.description,
            requirement_type=request.requirement_type,
            priority=request.priority,
            status=request.status
        )
        
        if not success:
            raise HTTPException(status_code=404, detail="Requirement not found")
        
        return {"message": "Requirement updated successfully"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating requirement: {e}")
        raise HTTPException(status_code=500, detail="Failed to update requirement")


@router.delete("/{requirement_id}", response_model=dict)
async def delete_requirement(
    requirement_id: int,
    current_user: User = Depends(lambda: None)
):
    """Delete a requirement"""
    try:
        success = requirements_service.delete_requirement(requirement_id)
        if not success:
            raise HTTPException(status_code=404, detail="Requirement not found")
        
        return {"message": "Requirement deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting requirement: {e}")
        raise HTTPException(status_code=500, detail="Failed to delete requirement")


# ============================================================================
# Test Mapping Endpoints
# ============================================================================

@router.post("/{requirement_id}/tests", response_model=dict)
async def map_test_to_requirement(
    requirement_id: int,
    request: TestMappingRequest,
    current_user: User = Depends(lambda: None)
):
    """Map a test case to a requirement"""
    try:
        mapping_id = requirements_service.map_test_to_requirement(
            test_case_id=request.test_case_id,
            requirement_db_id=requirement_id,
            coverage_type=request.coverage_type
        )
        
        if not mapping_id:
            raise HTTPException(status_code=500, detail="Failed to map test to requirement")
        
        return {"mapping_id": mapping_id, "message": "Test mapped to requirement"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error mapping test to requirement: {e}")
        raise HTTPException(status_code=500, detail="Failed to map test to requirement")


@router.delete("/{requirement_id}/tests/{test_case_id}", response_model=dict)
async def unmap_test_from_requirement(
    requirement_id: int,
    test_case_id: int,
    current_user: User = Depends(lambda: None)
):
    """Remove a test mapping from a requirement"""
    try:
        success = requirements_service.unmap_test_from_requirement(
            test_case_id=test_case_id,
            requirement_db_id=requirement_id
        )
        
        if not success:
            raise HTTPException(status_code=404, detail="Mapping not found")
        
        return {"message": "Test unmapped from requirement"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error unmapping test: {e}")
        raise HTTPException(status_code=500, detail="Failed to unmap test")


@router.get("/{requirement_id}/tests", response_model=dict)
async def get_tests_for_requirement(
    requirement_id: int,
    current_user: User = Depends(lambda: None)
):
    """Get all tests mapped to a requirement"""
    try:
        tests = requirements_service.get_tests_for_requirement(requirement_id)
        return {"requirement_id": requirement_id, "tests": tests, "count": len(tests)}
    except Exception as e:
        logger.error(f"Error getting tests for requirement: {e}")
        raise HTTPException(status_code=500, detail="Failed to get tests")


# ============================================================================
# Coverage & Traceability Endpoints
# ============================================================================

@router.get("/coverage/summary", response_model=CoverageSummaryResponse)
async def get_coverage_summary(
    client_id: str = Query(...),
    project_id: Optional[str] = Query(None),
    current_user: User = Depends(lambda: None)
):
    """Get requirements coverage summary"""
    try:
        summary = requirements_service.get_coverage_summary(
            client_id=client_id,
            project_id=project_id
        )
        return CoverageSummaryResponse(**summary)
    except Exception as e:
        logger.error(f"Error getting coverage summary: {e}")
        raise HTTPException(status_code=500, detail="Failed to get coverage summary")


@router.get("/traceability/matrix", response_model=dict)
async def get_traceability_matrix(
    client_id: str = Query(...),
    project_id: Optional[str] = Query(None),
    current_user: User = Depends(lambda: None)
):
    """Get traceability matrix"""
    try:
        matrix = requirements_service.get_traceability_matrix(
            client_id=client_id,
            project_id=project_id
        )
        return {"matrix": matrix, "total": len(matrix)}
    except Exception as e:
        logger.error(f"Error getting traceability matrix: {e}")
        raise HTTPException(status_code=500, detail="Failed to get traceability matrix")


@router.get("/coverage/uncovered", response_model=dict)
async def get_uncovered_requirements(
    client_id: str = Query(...),
    project_id: Optional[str] = Query(None),
    current_user: User = Depends(lambda: None)
):
    """Get requirements without test coverage"""
    try:
        uncovered = requirements_service.get_uncovered_requirements(
            client_id=client_id,
            project_id=project_id
        )
        return {"uncovered": uncovered, "count": len(uncovered)}
    except Exception as e:
        logger.error(f"Error getting uncovered requirements: {e}")
        raise HTTPException(status_code=500, detail="Failed to get uncovered requirements")
