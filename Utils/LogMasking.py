"""
Secrets must not reach the log: the password of an environment, access tokens, API keys.

mask_secrets() returns a copy of what is about to be logged with such values replaced by ***.
It works by key name in dicts (password, token, authorization, ...) and by shape in text
(a JWT, a "Bearer ..." header, "password": "..." inside a JSON string).
"""

import re
from typing import Any

MASK = '***'
_SECRET_KEY = re.compile(r'pass(word|wd)?|secret|token|authori[sz]ation|api[_-]?key|cookie', re.IGNORECASE)
_JWT = re.compile(r'eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]*')
_BEARER = re.compile(r'(Bearer\s+)(?!%)[^\s"\',}]+', re.IGNORECASE)
_KEY_VALUE = re.compile(
    r'''(["']?[\w-]*(?:pass(?:word|wd)?|secret|token|api[_-]?key)[\w-]*["']?\s*[:=]\s*)(["'])(?!%)(.*?)\2''',
    re.IGNORECASE)


def mask_secrets(value: Any) -> Any:
    """A copy of value that is safe to log. %placeholders% are kept: they name a variable, not its value."""
    if isinstance(value, dict):
        return {key: (MASK if isinstance(key, str) and _SECRET_KEY.search(key) and item not in (None, '')
                      and not _is_placeholder(item) else mask_secrets(item))
                for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [mask_secrets(item) for item in value]
    if isinstance(value, str):
        text = _KEY_VALUE.sub(lambda m: f"{m.group(1)}{m.group(2)}{MASK}{m.group(2)}", value)
        text = _BEARER.sub(lambda m: m.group(1) + MASK, text)
        return _JWT.sub(MASK, text)
    return value


def _is_placeholder(item: Any) -> bool:
    return isinstance(item, str) and bool(re.fullmatch(r'(Bearer\s+)?%[\w:.-]+%', item.strip()))
