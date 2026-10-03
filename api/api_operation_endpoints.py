"""
API call library endpoints

GET  /api/projects/{project_id}/api-operations      - the API calls of a project, from its uploaded schemas
POST /api/api-schemas/{schema_id}/operations/sync   - rebuild the calls of one schema

POST /api/api-schemas/{schema_id}/baseline-tests    - create the baseline API tests of one schema, without AI

The library is built by code in Services/ApiOperationLibrary.py when a schema is uploaded.
Each call comes with "step_request": the JSON an api_request step stores.
"""

import logging
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer

from auroqa.models.user import User
from auroqa.Services.ApiOperationLibrary import list_operations, sync_operations
from auroqa.Services.ApiBaselineTests import generate_baseline_tests
from auroqa.Utils.Connectors.db_utils import get_db_connection_context

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["api-operations"])

# This will be set by main.py during app initialization
_current_user_func = None
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/login")


def set_get_current_user(func):
    """Set the get_current_user dependency function"""
    global _current_user_func
    _current_user_func = func


async def get_current_user_from_token(token: str = Depends(oauth2_scheme)) -> User:
    if _current_user_func is None:
        raise HTTPException(status_code=500, detail="Authentication not configured")
    return await _current_user_func(token)


def _schema_ids(client_id: str, project_id: Optional[str] = None, schema_id: Optional[int] = None):
    """Ids of the client's schemas, with the number of calls each has in the library."""
    with get_db_connection_context() as conn:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT s.id, (SELECT COUNT(*) FROM api_operations o WHERE o.schema_id = s.id)
                FROM api_schemas s
                WHERE s.client_id = %s
                  AND (%s::text IS NULL OR s.project_id::text = %s)
                  AND (%s::int IS NULL OR s.id = %s)
            """, (client_id, project_id, project_id, schema_id, schema_id))
            return cursor.fetchall()


@router.get("/projects/{project_id}/api-operations")
async def get_project_api_operations(
    project_id: str,
    schema_id: Optional[int] = None,
    current_user: User = Depends(get_current_user_from_token)
):
    """The API calls of a project, optionally of one schema."""
    try:
        client_id = str(current_user.client_id)
        # A schema uploaded before the library existed has no calls yet: build them on first use
        for found_id, count in _schema_ids(client_id, project_id=project_id, schema_id=schema_id):
            if count == 0:
                sync_operations(found_id)
        operations = list_operations(project_id, client_id, schema_id)
        return {"operations": operations, "total": len(operations)}
    except Exception as e:
        logger.error(f"Error listing API operations: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to list API operations: {str(e)}")


@router.post("/api-schemas/{schema_id}/operations/sync")
async def sync_schema_operations(
    schema_id: int,
    current_user: User = Depends(get_current_user_from_token)
):
    """Rebuild the calls of one schema from its stored content."""
    if not _schema_ids(str(current_user.client_id), schema_id=schema_id):
        raise HTTPException(status_code=404, detail="API schema not found or access denied")
    try:
        return {"success": True, "schema_id": schema_id, "operations_count": sync_operations(schema_id)}
    except Exception as e:
        logger.error(f"Error syncing API operations: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to sync API operations: {str(e)}")


@router.post("/api-schemas/{schema_id}/baseline-tests")
async def create_baseline_tests(
    schema_id: int,
    current_user: User = Depends(get_current_user_from_token)
):
    """
    Create the baseline API tests of a schema from its calls: read checks and
    create-read-update-delete chains. No AI. Tests that already exist are skipped.
    """
    client_id = str(current_user.client_id)
    found = _schema_ids(client_id, schema_id=schema_id)
    if not found:
        raise HTTPException(status_code=404, detail="API schema not found or access denied")
    try:
        if found[0][1] == 0:
            sync_operations(schema_id)
        result = generate_baseline_tests(schema_id, client_id)
        return {"success": True, **result}
    except Exception as e:
        logger.error(f"Error creating baseline API tests: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to create baseline API tests: {str(e)}")

