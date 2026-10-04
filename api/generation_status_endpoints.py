"""
Generation status endpoints

DELETE /api/test_case_generation_error/{test_case_id} - dismiss the stored reason why the last
generation of a test case stopped. The reason itself comes with GET /api/test_case_generation_status/{id}.

GET  /api/test_cases/{test_case_id}/review-notes         - what the generator changed to agree with the API
POST /api/test_cases/{test_case_id}/review-notes/confirm - a person confirms a note (it is cleared)
"""

import logging
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from fastapi.security import OAuth2PasswordBearer

from auroqa.models.user import User
from auroqa.Utils.Connectors.db_utils import get_db_connection_context
from auroqa.Utils.GenerationStatus import clear_generation_error

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["generation-status"])

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


@router.delete("/test_case_generation_error/{test_case_id}")
async def dismiss_generation_error(test_case_id: int, current_user: User = Depends(get_current_user_from_token)):
    """Forget why the last generation of this test case stopped."""
    with get_db_connection_context() as conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT id FROM test_cases WHERE id = %s AND client_id = %s",
                           (test_case_id, str(current_user.client_id)))
            if not cursor.fetchone():
                raise HTTPException(status_code=404, detail="Test case not found")
    clear_generation_error(test_case_id)
    return {"success": True}


def _own_test_case(cursor, test_case_id: int, client_id: str):
    cursor.execute("SELECT review_notes FROM test_cases WHERE id = %s AND client_id = %s", (test_case_id, client_id))
    row = cursor.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Test case not found")
    return row[0]


@router.get("/test_cases/{test_case_id}/review-notes")
async def get_review_notes(test_case_id: int, current_user: User = Depends(get_current_user_from_token)):
    """
    What the generator changed in this test to agree with the API: expected values or statuses of a
    step, and steps it removed. Each note waits for a person to confirm it.
    """
    with get_db_connection_context() as conn:
        with conn.cursor() as cursor:
            case_notes = _own_test_case(cursor, test_case_id, str(current_user.client_id))
            cursor.execute("""
                SELECT id, review_notes FROM test_steps
                WHERE test_case_id = %s AND review_notes IS NOT NULL AND review_notes <> ''
            """, (test_case_id,))
            steps = {str(step_id): notes for step_id, notes in cursor.fetchall()}
    return {"test_case": case_notes or None, "steps": steps}


class ConfirmReviewRequest(BaseModel):
    # The step whose note is confirmed; none = the note of the test case itself; all = every note of the test
    step_id: Optional[int] = None
    all: bool = False


@router.post("/test_cases/{test_case_id}/review-notes/confirm")
async def confirm_review_notes(test_case_id: int, request: ConfirmReviewRequest = None,
                               current_user: User = Depends(get_current_user_from_token)):
    """A person has looked at what the generator changed and accepts it: the note is cleared."""
    request = request or ConfirmReviewRequest()
    with get_db_connection_context() as conn:
        with conn.cursor() as cursor:
            _own_test_case(cursor, test_case_id, str(current_user.client_id))
            if request.all or request.step_id is None:
                cursor.execute("UPDATE test_cases SET review_notes = NULL WHERE id = %s", (test_case_id,))
            if request.all:
                cursor.execute("UPDATE test_steps SET review_notes = NULL WHERE test_case_id = %s", (test_case_id,))
            elif request.step_id is not None:
                cursor.execute("UPDATE test_steps SET review_notes = NULL WHERE id = %s AND test_case_id = %s",
                               (request.step_id, test_case_id))
            conn.commit()
    return {"success": True}
