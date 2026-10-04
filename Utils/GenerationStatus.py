"""
Why the last step generation of a test case stopped.

A generation runs in the background; when it fails (the AI quota is used up, no environment,
a step that cannot be made to pass) the only trace was the backend log. The reason is kept
here, in Redis, for the UI to show on the test case: it is set when a generation fails,
cleared when the next one starts or when the user dismisses it, and expires by itself.
"""

import logging
import re
from typing import Optional

import redis

from auroqa.Utils.System import System

logger = logging.getLogger(__name__)

_TTL_SECONDS = 24 * 3600
_MAX_LENGTH = 1000


def _client():
    system = System()
    return redis.Redis(host=system.redis_host, port=system.redis_port, db=0, decode_responses=True)


def _key(test_case_id: int) -> str:
    return f"test_case_generation_error:{test_case_id}"


def set_generation_error(test_case_id: int, message: str) -> None:
    try:
        _client().setex(_key(test_case_id), _TTL_SECONDS, (str(message) or "Generation failed")[:_MAX_LENGTH])
    except Exception as e:
        logger.error(f"Could not store the generation error of test case {test_case_id}: {e}")


def clear_generation_error(test_case_id: int) -> None:
    try:
        _client().delete(_key(test_case_id))
    except Exception as e:
        logger.error(f"Could not clear the generation error of test case {test_case_id}: {e}")


def get_generation_error(test_case_id: int) -> Optional[str]:
    try:
        return _client().get(_key(test_case_id))
    except Exception as e:
        logger.error(f"Could not read the generation error of test case {test_case_id}: {e}")
        return None


# ---- the daily quota of a model ---------------------------------------------------------------
# Once the provider says the quota of a model is used up, every further request fails the same way
# until it resets. The tests still in the queue are not sent to the model: they get this reason.

def _quota_key(model_name: Optional[str]) -> str:
    return f"ai_quota_exhausted:{model_name or 'default'}"


def note_quota_exhausted(model_name: Optional[str], message: str) -> bool:
    """Remember that the quota of the model is used up, when the error says so. True if it does."""
    match = re.search(r'quota exhausted.*?retry in about (\d+) min', message or '', re.IGNORECASE)
    if not match:
        return False
    minutes = max(1, min(int(match.group(1)), 24 * 60))
    try:
        _client().setex(_quota_key(model_name), minutes * 60, message[:_MAX_LENGTH])
    except Exception as e:
        logger.error(f"Could not store the quota state of {model_name}: {e}")
    return True


def quota_exhausted(model_name: Optional[str]) -> Optional[str]:
    """Why the model cannot be asked now, with the minutes left; None when it can."""
    try:
        client = _client()
        message = client.get(_quota_key(model_name))
        if not message:
            return None
        minutes = max(1, (client.ttl(_quota_key(model_name)) + 59) // 60)
        return re.sub(r'retry in about \d+ min', f'retry in about {minutes} min', message)
    except Exception as e:
        logger.error(f"Could not read the quota state of {model_name}: {e}")
        return None
