"""
Loading of a test environment for a run.

One place that turns an environments row into the dictionary the executors take:
base_url (the UI address), api_url (the API address, None when the environment has none),
login, password and custom_variables.
"""

import os
import re
from typing import Any, Dict, Optional

from auroqa.Utils.Connectors.db_utils import get_db_connection_context


def with_scheme(url: Optional[str]) -> Optional[str]:
    """An address typed without a scheme ("host:8091") as a URL: http:// is assumed. Empty stays None."""
    url = (url or '').strip()
    if not url:
        return None
    return url if re.match(r'^[a-zA-Z][a-zA-Z0-9+.-]*://', url) else f"http://{url}"


def load_environment_vars(environment_id: Optional[int], client_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """
    Variables of an environment, or None when it does not exist.

    With client_id the environment must belong to a project of that client.
    """
    if not environment_id:
        return None
    with get_db_connection_context() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT e.base_url, e.login, e.password, e.custom_variables, e.api_url
                FROM environments e
                JOIN projects p ON e.project_id = p.id
                WHERE e.id = %s AND (%s::text IS NULL OR p.client_id::text = %s)
                """,
                (environment_id, client_id, client_id)
            )
            row = cursor.fetchone()
    if not row:
        return None
    return {
        "base_url": row[0],
        "login": row[1],
        "password": row[2],
        "custom_variables": row[3] or {},
        "api_url": with_scheme(row[4]),
    }


def api_base_url(environment_vars: Optional[Dict[str, Any]]) -> str:
    """Where relative API endpoints go: the environment's API address, or its base_url when it has none."""
    environment_vars = environment_vars or {}
    return (with_scheme(environment_vars.get("api_url") or environment_vars.get("base_url")) or "").rstrip("/")


def reachable_url(url: str) -> str:
    """
    The URL as the backend has to call it.

    API requests are sent by the backend. When it runs in a container, "localhost" in an
    environment's address means the user's machine, not the container: LOCALHOST_ALIAS names the
    host that stands for that machine (host.docker.internal in the local Docker stand) and is
    put in place of localhost / 127.0.0.1. Without the variable the URL is used as it is.
    """
    alias = os.getenv('LOCALHOST_ALIAS', '').strip()
    if not alias or not isinstance(url, str):
        return url
    return re.sub(r'^(https?://)(localhost|127\.0\.0\.1)(?=[:/]|$)', lambda m: m.group(1) + alias, url, flags=re.IGNORECASE)
