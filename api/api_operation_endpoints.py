"""
API call library endpoints

GET  /api/projects/{project_id}/api-operations      - the API calls of a project, from its uploaded schemas
POST /api/api-schemas/{schema_id}/operations/sync   - rebuild the calls of one schema

POST /api/api-schemas/{schema_id}/baseline-tests    - create the baseline API tests of one schema, without AI
GET  /api/api-schemas/{schema_id}/scenario-tests/pending  - scenario tests that have no steps yet
POST /api/api-schemas/{schema_id}/scenario-tests/generate - generate the steps of those tests
GET  /api/api-schemas/{schema_id}/coverage          - which calls of a schema the tests send, and how well
POST /api/api-schemas/{schema_id}/scenario-ideas    - ask the model for more complex test scenarios of a schema
POST /api/api-schemas/{schema_id}/scenario-tests    - create the chosen scenarios as API tests and generate their steps

The library is built by code in Services/ApiOperationLibrary.py when a schema is uploaded.
Each call comes with "step_request": the JSON an api_request step stores.
"""

import logging
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException
from fastapi.concurrency import run_in_threadpool
from fastapi.security import OAuth2PasswordBearer
from pydantic import BaseModel

from auroqa.models.user import User
from auroqa.Services.ApiOperationLibrary import list_operations, sync_operations
from auroqa.Services.ApiBaselineTests import generate_baseline_tests
from auroqa.Services.ApiCoverage import schema_coverage
from auroqa.Services.ApiScenarioIdeas import (create_scenario_tests, queue_generation, scenario_tests_without_steps,
                                              suggest_scenarios)
from auroqa.Utils.GenerationStatus import quota_exhausted
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



def _model_name(ai_model_id: Optional[int], user_id) -> Optional[str]:
    """The model picked in the request, else the user's preferred one, else None (the default)."""
    with get_db_connection_context() as conn:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT m.model_id FROM ai_models m
                WHERE m.is_active = TRUE AND m.id = COALESCE(
                    %s, (SELECT ai_model_id FROM user_ai_models WHERE user_id = %s LIMIT 1))
            """, (ai_model_id, user_id))
            row = cursor.fetchone()
    return row[0] if row else None


class Scenario(BaseModel):
    name: str
    description: str


class ScenarioIdeasRequest(BaseModel):
    count: Optional[int] = 10
    ai_model_id: Optional[int] = None
    # Ideas already shown: "suggest more" asks for others
    exclude: List[Scenario] = []


class ScenarioTestsRequest(BaseModel):
    scenarios: List[Scenario]
    environment_id: Optional[int] = None
    ai_model_id: Optional[int] = None


@router.post("/api-schemas/{schema_id}/scenario-ideas")
async def get_scenario_ideas(
    schema_id: int,
    request: ScenarioIdeasRequest = None,
    current_user: User = Depends(get_current_user_from_token)
):
    """
    Ask the model, in one request, for API test scenarios beyond the baseline tests. Nothing is saved:
    the user picks the ideas to keep and sends them to /scenario-tests.
    """
    request = request or ScenarioIdeasRequest()
    client_id = str(current_user.client_id)
    found = _schema_ids(client_id, schema_id=schema_id)
    if not found:
        raise HTTPException(status_code=404, detail="API schema not found or access denied")
    try:
        if found[0][1] == 0:
            sync_operations(schema_id)
        model_name = _model_name(request.ai_model_id, current_user.id)
        result = await run_in_threadpool(suggest_scenarios, schema_id, client_id, model_name, request.count,
                                         [idea.dict() for idea in request.exclude])
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error suggesting API test scenarios: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to suggest API test scenarios: {str(e)}")
    if not result['scenarios']:
        raise HTTPException(status_code=502, detail="The model suggested no usable scenarios. Try again.")
    return {"success": True, **result}


@router.post("/api-schemas/{schema_id}/scenario-tests")
async def create_scenario_api_tests(
    schema_id: int,
    request: ScenarioTestsRequest,
    current_user: User = Depends(get_current_user_from_token)
):
    """
    Create the chosen scenarios as API tests in "<schema>/Scenarios" and queue the generation of
    their steps, one test after another. Tests that already exist there are left as they are.
    """
    client_id = str(current_user.client_id)
    if not _schema_ids(client_id, schema_id=schema_id):
        raise HTTPException(status_code=404, detail="API schema not found or access denied")
    if not request.scenarios:
        raise HTTPException(status_code=400, detail="No scenarios chosen")
    try:
        result = create_scenario_tests(schema_id, client_id, [s.dict() for s in request.scenarios])
        model_name = _model_name(request.ai_model_id, current_user.id)
        for test in result['created']:
            queue_generation(test['id'], client_id, result['project_id'], request.environment_id, model_name)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error creating API scenario tests: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to create API scenario tests: {str(e)}")
    return {"success": True, **result}


@router.get("/api-schemas/{schema_id}/coverage")
async def get_schema_coverage(
    schema_id: int,
    current_user: User = Depends(get_current_user_from_token)
):
    """
    Coverage of a schema by the tests of its project: per call, the tests that send it, the statuses
    they expect and whether the last run passed. Built by code, no AI.
    """
    client_id = str(current_user.client_id)
    found = _schema_ids(client_id, schema_id=schema_id)
    if not found:
        raise HTTPException(status_code=404, detail="API schema not found or access denied")
    try:
        if found[0][1] == 0:
            sync_operations(schema_id)
        return await run_in_threadpool(schema_coverage, schema_id, client_id)
    except Exception as e:
        logger.error(f"Error building API coverage: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to build API coverage: {str(e)}")


@router.get("/api-schemas/{schema_id}/scenario-tests/pending")
async def get_pending_scenario_tests(
    schema_id: int,
    current_user: User = Depends(get_current_user_from_token)
):
    """Scenario tests of the schema that were created but have no steps (their generation did not finish)."""
    client_id = str(current_user.client_id)
    if not _schema_ids(client_id, schema_id=schema_id):
        raise HTTPException(status_code=404, detail="API schema not found or access denied")
    return scenario_tests_without_steps(schema_id, client_id)


class GeneratePendingRequest(BaseModel):
    environment_id: Optional[int] = None
    ai_model_id: Optional[int] = None


@router.post("/api-schemas/{schema_id}/scenario-tests/generate")
async def generate_pending_scenario_tests(
    schema_id: int,
    request: GeneratePendingRequest = None,
    current_user: User = Depends(get_current_user_from_token)
):
    """Queue the step generation of every scenario test of the schema that has no steps."""
    request = request or GeneratePendingRequest()
    client_id = str(current_user.client_id)
    if not _schema_ids(client_id, schema_id=schema_id):
        raise HTTPException(status_code=404, detail="API schema not found or access denied")
    model_name = _model_name(request.ai_model_id, current_user.id)
    no_quota = quota_exhausted(model_name)
    if no_quota:
        raise HTTPException(status_code=429, detail=no_quota)
    try:
        pending = scenario_tests_without_steps(schema_id, client_id)
        for test in pending['tests']:
            queue_generation(test['id'], client_id, pending['project_id'], request.environment_id, model_name)
    except Exception as e:
        logger.error(f"Error queuing scenario tests: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to queue the scenario tests: {str(e)}")
    return {"success": True, "queued": pending['tests']}
