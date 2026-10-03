"""
Generation status endpoints

DELETE /api/test_case_generation_error/{test_case_id} - dismiss the stored reason why the last
generation of a test case stopped. The reason itself comes with GET /api/test_case_generation_status/{id}.
"""

import logging
from fastapi import APIRouter, Depends, HTTPException
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
