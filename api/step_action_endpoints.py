"""
Step actions API

GET /api/step_actions - the step actions a user may pick in the UI, with what each one
needs: an element locator, a value, and the value format. The UI builds its action
dropdown and step form from this, so the list cannot drift from the executor.

The catalog lives in Utils/BrowserAutomation/StepActions.py (shared with the validation
agent and the confidence scorer). Only actions that TestRunner.execute_step runs are listed. VALID_ACTIONS also holds
legacy aliases (assert_url_contains, scroll, ...) that the generator maps or that no
executor branch handles; a step saved with one of those would fail at run time.
"""

import logging
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer
from pydantic import BaseModel

from auroqa.models.user import User
from auroqa.Utils.BrowserAutomation.TestRunner import TestRunner
from auroqa.Utils.BrowserAutomation.BrowserAutomation import BrowserAutomation
from auroqa.Utils.BrowserAutomation.StepActions import STEP_ACTIONS

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["step-actions"])

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


class StepAction(BaseModel):
    name: str
    label: str
    group: str
    description: str
    needs_locator: bool            # element_path (XPath) is required
    needs_value: str               # "required", "optional" or "none"
    value_hint: Optional[str] = None       # placeholder / format of the value field
    value_options: Optional[List[str]] = None  # fixed choices for the value, if any
    test_types: List[str]          # test case types the action applies to: "ui", "api"


def _check_against_executor():
    """Drop actions the executor would reject on save, and log what the UI will not offer."""
    valid = TestRunner.VALID_ACTIONS
    listed = {a["name"] for a in STEP_ACTIONS}
    for action in listed - valid:
        logger.error(f"step_actions: '{action}' is not in TestRunner.VALID_ACTIONS and is not offered to the UI")
    hidden = sorted(valid - listed)
    if hidden:
        logger.info(f"step_actions: not offered to the UI (no executor branch or legacy alias): {', '.join(hidden)}")
    return [a for a in STEP_ACTIONS if a["name"] in valid]


_EXPOSED_ACTIONS = _check_against_executor()


@router.get("/step_actions", response_model=List[StepAction])
async def list_step_actions(current_user: User = Depends(get_current_user_from_token)):
    """Step actions for the UI, with locator/value requirements and value hints."""
    sample_files = BrowserAutomation.list_sample_files()
    result = []
    for action in _EXPOSED_ACTIONS:
        item = dict(action)
        if item["name"] == "upload_file":
            item["value_options"] = sample_files
            item["value_hint"] = "Name of a file in sample_files/: " + ", ".join(sample_files)
        result.append(StepAction(**item))
    return result
