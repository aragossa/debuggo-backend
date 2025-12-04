"""
Variable Management API Endpoints

Provides REST API for managing variables with scope support:
- Global variables
- Client-scoped variables
- Project-scoped variables
- Environment-scoped variables

Also provides audit logging endpoints for variable substitutions and extractions.
"""

import logging
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.security import OAuth2PasswordBearer
from pydantic import BaseModel, Field
from datetime import datetime
from auroqa.models.user import User
from auroqa.Services.VariableManager import VariableManager
from auroqa.Utils.Connectors.db_utils import get_db_connection, return_db_connection

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/variables", tags=["variables"])

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

# Initialize VariableManager
variable_manager = VariableManager()


# ============================================================================
# Pydantic Models
# ============================================================================

class VariableCreate(BaseModel):
    """Request model for creating a variable"""
    name: str = Field(..., description="Variable name")
    value: str = Field(..., description="Variable value")
    scope: str = Field("global", description="Variable scope: global, client, project, environment")
    client_id: Optional[str] = Field(None, description="Client ID (required for client scope)")
    project_id: Optional[str] = Field(None, description="Project ID (required for project scope)")
    environment_id: Optional[int] = Field(None, description="Environment ID (required for environment scope)")
    is_secret: bool = Field(False, description="Whether the variable is secret")
    description: Optional[str] = Field(None, description="Variable description")


class VariableUpdate(BaseModel):
    """Request model for updating a variable"""
    value: Optional[str] = Field(None, description="New variable value")
    description: Optional[str] = Field(None, description="New variable description")
    is_secret: Optional[bool] = Field(None, description="Update is_secret flag")


class VariableResponse(BaseModel):
    """Response model for a variable"""
    id: int
    name: str
    value: str
    scope: str
    client_id: Optional[str]
    project_id: Optional[str]
    environment_id: Optional[int]
    is_secret: bool
    description: Optional[str]
    created_at: datetime
    updated_at: datetime


class VariableListResponse(BaseModel):
    """Response model for variable list"""
    variables: List[VariableResponse]
    total: int


class SubstitutionLogEntry(BaseModel):
    """Response model for substitution log entry"""
    id: int
    test_run_id: int
    test_step_id: int
    variable_name: str
    variable_scope: str
    original_value: str
    substituted_value: str
    created_at: datetime


class ExtractionLogEntry(BaseModel):
    """Response model for extraction log entry"""
    id: int
    test_run_id: int
    test_step_id: int
    variable_name: str
    extracted_value: str
    extraction_path: str
    created_at: datetime


# ============================================================================
# Helper Functions
# ============================================================================

def get_variable_from_db(variable_id: int) -> dict:
    """Get variable from database"""
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT id, name, value, scope, client_id, project_id, environment_id,
                       is_secret, description, created_at, updated_at
                FROM test_variables
                WHERE id = %s AND is_active = TRUE
                """,
                (variable_id,)
            )
            result = cursor.fetchone()
            if not result:
                return None
            
            return {
                'id': result[0],
                'name': result[1],
                'value': result[2],
                'scope': result[3],
                'client_id': result[4],
                'project_id': result[5],
                'environment_id': result[6],
                'is_secret': result[7],
                'description': result[8],
                'created_at': result[9],
                'updated_at': result[10]
            }
    finally:
        return_db_connection(conn)


def get_variables_from_db(
    scope: Optional[str] = None,
    client_id: Optional[str] = None,
    project_id: Optional[str] = None,
    environment_id: Optional[int] = None,
    limit: int = 100,
    offset: int = 0
) -> tuple:
    """Get variables from database with optional filtering"""
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            # Build WHERE clause
            where_clauses = ["is_active = TRUE"]
            params = []
            
            if scope:
                where_clauses.append("scope = %s")
                params.append(scope)
            if client_id:
                where_clauses.append("client_id = %s")
                params.append(client_id)
            if project_id:
                where_clauses.append("project_id = %s")
                params.append(project_id)
            if environment_id:
                where_clauses.append("environment_id = %s")
                params.append(environment_id)
            
            where_clause = " AND ".join(where_clauses)
            
            # Get total count
            cursor.execute(f"SELECT COUNT(*) FROM test_variables WHERE {where_clause}", params)
            total = cursor.fetchone()[0]
            
            # Get paginated results
            params.extend([limit, offset])
            cursor.execute(
                f"""
                SELECT id, name, value, scope, client_id, project_id, environment_id,
                       is_secret, description, created_at, updated_at
                FROM test_variables
                WHERE {where_clause}
                ORDER BY created_at DESC
                LIMIT %s OFFSET %s
                """,
                params
            )
            
            variables = []
            for row in cursor.fetchall():
                variables.append({
                    'id': row[0],
                    'name': row[1],
                    'value': row[2],
                    'scope': row[3],
                    'client_id': row[4],
                    'project_id': row[5],
                    'environment_id': row[6],
                    'is_secret': row[7],
                    'description': row[8],
                    'created_at': row[9],
                    'updated_at': row[10]
                })
            
            return variables, total
    finally:
        return_db_connection(conn)


def get_substitution_logs(
    test_run_id: Optional[int] = None,
    test_step_id: Optional[int] = None,
    variable_name: Optional[str] = None,
    limit: int = 100,
    offset: int = 0
) -> tuple:
    """Get variable substitution logs"""
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            # Build WHERE clause
            where_clauses = []
            params = []
            
            if test_run_id:
                where_clauses.append("test_run_id = %s")
                params.append(test_run_id)
            if test_step_id:
                where_clauses.append("test_step_id = %s")
                params.append(test_step_id)
            if variable_name:
                where_clauses.append("variable_name = %s")
                params.append(variable_name)
            
            where_clause = " AND ".join(where_clauses) if where_clauses else "1=1"
            
            # Get total count
            cursor.execute(f"SELECT COUNT(*) FROM variable_substitution_log WHERE {where_clause}", params)
            total = cursor.fetchone()[0]
            
            # Get paginated results
            params.extend([limit, offset])
            cursor.execute(
                f"""
                SELECT id, test_run_id, test_step_id, variable_name, variable_scope,
                       original_value, substituted_value, created_at
                FROM variable_substitution_log
                WHERE {where_clause}
                ORDER BY created_at DESC
                LIMIT %s OFFSET %s
                """,
                params
            )
            
            logs = []
            for row in cursor.fetchall():
                logs.append({
                    'id': row[0],
                    'test_run_id': row[1],
                    'test_step_id': row[2],
                    'variable_name': row[3],
                    'variable_scope': row[4],
                    'original_value': row[5],
                    'substituted_value': row[6],
                    'created_at': row[7]
                })
            
            return logs, total
    finally:
        return_db_connection(conn)


def get_extraction_logs(
    test_run_id: Optional[int] = None,
    test_step_id: Optional[int] = None,
    variable_name: Optional[str] = None,
    limit: int = 100,
    offset: int = 0
) -> tuple:
    """Get variable extraction logs"""
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            # Build WHERE clause
            where_clauses = []
            params = []
            
            if test_run_id:
                where_clauses.append("test_run_id = %s")
                params.append(test_run_id)
            if test_step_id:
                where_clauses.append("test_step_id = %s")
                params.append(test_step_id)
            if variable_name:
                where_clauses.append("variable_name = %s")
                params.append(variable_name)
            
            where_clause = " AND ".join(where_clauses) if where_clauses else "1=1"
            
            # Get total count
            cursor.execute(f"SELECT COUNT(*) FROM variable_extraction_log WHERE {where_clause}", params)
            total = cursor.fetchone()[0]
            
            # Get paginated results
            params.extend([limit, offset])
            cursor.execute(
                f"""
                SELECT id, test_run_id, test_step_id, variable_name,
                       extracted_value, extraction_path, created_at
                FROM variable_extraction_log
                WHERE {where_clause}
                ORDER BY created_at DESC
                LIMIT %s OFFSET %s
                """,
                params
            )
            
            logs = []
            for row in cursor.fetchall():
                logs.append({
                    'id': row[0],
                    'test_run_id': row[1],
                    'test_step_id': row[2],
                    'variable_name': row[3],
                    'extracted_value': row[4],
                    'extraction_path': row[5],
                    'created_at': row[6]
                })
            
            return logs, total
    finally:
        return_db_connection(conn)


# ============================================================================
# Variable Management Endpoints
# ============================================================================

@router.get("", response_model=VariableListResponse)
async def list_variables(
    scope: Optional[str] = Query(None, description="Filter by scope"),
    client_id: Optional[str] = Query(None, description="Filter by client ID"),
    project_id: Optional[str] = Query(None, description="Filter by project ID"),
    environment_id: Optional[int] = Query(None, description="Filter by environment ID"),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(get_current_user_from_token)  # Placeholder for auth
):
    """
    List variables with optional filtering.
    
    Query Parameters:
    - scope: Filter by scope (global, client, project, environment)
    - client_id: Filter by client ID
    - project_id: Filter by project ID
    - environment_id: Filter by environment ID
    - limit: Number of results per page (default: 100)
    - offset: Number of results to skip (default: 0)
    """
    try:
        variables, total = get_variables_from_db(
            scope=scope,
            client_id=client_id,
            project_id=project_id,
            environment_id=environment_id,
            limit=limit,
            offset=offset
        )
        
        return VariableListResponse(
            variables=[VariableResponse(**var) for var in variables],
            total=total
        )
    except Exception as e:
        logger.error(f"Error listing variables: {e}")
        raise HTTPException(status_code=500, detail="Failed to list variables")


@router.get("/{variable_id}", response_model=VariableResponse)
async def get_variable(
    variable_id: int,
    current_user: User = Depends(get_current_user_from_token)  # Placeholder for auth
):
    """Get a specific variable by ID"""
    try:
        variable = get_variable_from_db(variable_id)
        if not variable:
            raise HTTPException(status_code=404, detail="Variable not found")
        
        return VariableResponse(**variable)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting variable: {e}")
        raise HTTPException(status_code=500, detail="Failed to get variable")


@router.post("", response_model=VariableResponse)
async def create_variable(
    request: VariableCreate,
    current_user: User = Depends(get_current_user_from_token)  # Placeholder for auth
):
    """Create a new variable"""
    try:
        # Validate scope requirements
        if request.scope == 'client' and not request.client_id:
            raise HTTPException(status_code=400, detail="client_id required for client scope")
        if request.scope == 'project' and not request.project_id:
            raise HTTPException(status_code=400, detail="project_id required for project scope")
        if request.scope == 'environment' and not request.environment_id:
            raise HTTPException(status_code=400, detail="environment_id required for environment scope")
        
        # Create variable using VariableManager
        var_id = variable_manager.create_variable(
            name=request.name,
            value=request.value,
            scope=request.scope,
            client_id=request.client_id,
            project_id=request.project_id,
            environment_id=request.environment_id,
            is_secret=request.is_secret,
            description=request.description
        )
        
        if not var_id:
            raise HTTPException(status_code=500, detail="Failed to create variable")
        
        # Retrieve and return the created variable
        variable = get_variable_from_db(var_id)
        return VariableResponse(**variable)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating variable: {e}")
        raise HTTPException(status_code=500, detail="Failed to create variable")


@router.put("/{variable_id}", response_model=VariableResponse)
async def update_variable(
    variable_id: int,
    request: VariableUpdate,
    current_user: User = Depends(get_current_user_from_token)  # Placeholder for auth
):
    """Update an existing variable"""
    try:
        # Check if variable exists
        variable = get_variable_from_db(variable_id)
        if not variable:
            raise HTTPException(status_code=404, detail="Variable not found")
        
        # Update variable using VariableManager
        success = variable_manager.update_variable(
            variable_id=variable_id,
            value=request.value,
            description=request.description,
            is_secret=request.is_secret
        )
        
        if not success:
            raise HTTPException(status_code=500, detail="Failed to update variable")
        
        # Retrieve and return the updated variable
        variable = get_variable_from_db(variable_id)
        return VariableResponse(**variable)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating variable: {e}")
        raise HTTPException(status_code=500, detail="Failed to update variable")


@router.delete("/{variable_id}")
async def delete_variable(
    variable_id: int,
    current_user: User = Depends(get_current_user_from_token)  # Placeholder for auth
):
    """Delete a variable"""
    try:
        # Check if variable exists
        variable = get_variable_from_db(variable_id)
        if not variable:
            raise HTTPException(status_code=404, detail="Variable not found")
        
        # Delete variable using VariableManager
        success = variable_manager.delete_variable(variable_id)
        
        if not success:
            raise HTTPException(status_code=500, detail="Failed to delete variable")
        
        return {"status": "success", "message": "Variable deleted"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting variable: {e}")
        raise HTTPException(status_code=500, detail="Failed to delete variable")


# ============================================================================
# Scope-Specific Endpoints
# ============================================================================

@router.get("/scope/project/{project_id}", response_model=VariableListResponse)
async def list_project_variables(
    project_id: str,
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(get_current_user_from_token)  # Placeholder for auth
):
    """List variables for a specific project"""
    try:
        variables, total = get_variables_from_db(
            project_id=project_id,
            limit=limit,
            offset=offset
        )
        
        return VariableListResponse(
            variables=[VariableResponse(**var) for var in variables],
            total=total
        )
    except Exception as e:
        logger.error(f"Error listing project variables: {e}")
        raise HTTPException(status_code=500, detail="Failed to list project variables")


@router.get("/scope/environment/{environment_id}", response_model=VariableListResponse)
async def list_environment_variables(
    environment_id: int,
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(get_current_user_from_token)  # Placeholder for auth
):
    """List variables for a specific environment"""
    try:
        variables, total = get_variables_from_db(
            environment_id=environment_id,
            limit=limit,
            offset=offset
        )
        
        return VariableListResponse(
            variables=[VariableResponse(**var) for var in variables],
            total=total
        )
    except Exception as e:
        logger.error(f"Error listing environment variables: {e}")
        raise HTTPException(status_code=500, detail="Failed to list environment variables")


# ============================================================================
# Audit Logging Endpoints
# ============================================================================

@router.get("/logs/substitution", response_model=dict)
async def get_substitution_logs_endpoint(
    test_run_id: Optional[int] = Query(None),
    test_step_id: Optional[int] = Query(None),
    variable_name: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(get_current_user_from_token)  # Placeholder for auth
):
    """Get variable substitution logs"""
    try:
        logs, total = get_substitution_logs(
            test_run_id=test_run_id,
            test_step_id=test_step_id,
            variable_name=variable_name,
            limit=limit,
            offset=offset
        )
        
        return {
            "logs": [SubstitutionLogEntry(**log) for log in logs],
            "total": total
        }
    except Exception as e:
        logger.error(f"Error getting substitution logs: {e}")
        raise HTTPException(status_code=500, detail="Failed to get substitution logs")


@router.get("/logs/extraction", response_model=dict)
async def get_extraction_logs_endpoint(
    test_run_id: Optional[int] = Query(None),
    test_step_id: Optional[int] = Query(None),
    variable_name: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(get_current_user_from_token)  # Placeholder for auth
):
    """Get variable extraction logs"""
    try:
        logs, total = get_extraction_logs(
            test_run_id=test_run_id,
            test_step_id=test_step_id,
            variable_name=variable_name,
            limit=limit,
            offset=offset
        )
        
        return {
            "logs": [ExtractionLogEntry(**log) for log in logs],
            "total": total
        }
    except Exception as e:
        logger.error(f"Error getting extraction logs: {e}")
        raise HTTPException(status_code=500, detail="Failed to get extraction logs")
