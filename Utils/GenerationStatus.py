"""
Why the last step generation of a test case stopped.

A generation runs in the background; when it fails (the AI quota is used up, no environment,
a step that cannot be made to pass) the only trace was the backend log. The reason is kept
here, in Redis, for the UI to show on the test case: it is set when a generation fails,
cleared when the next one starts or when the user dismisses it, and expires by itself.
"""

import logging
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
