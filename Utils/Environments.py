"""
Loading of a test environment for a run.

One place that turns an environments row into the dictionary the executors take:
base_url (the UI address), api_url (the API address, None when the environment has none),
login, password and custom_variables.
"""

from typing import Any, Dict, Optional

from auroqa.Utils.Connectors.db_utils import get_db_connection_context


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
        "api_url": row[4] or None,
    }


def api_base_url(environment_vars: Optional[Dict[str, Any]]) -> str:
    """Where relative API endpoints go: the environment's API address, or its base_url when it has none."""
    environment_vars = environment_vars or {}
    return (environment_vars.get("api_url") or environment_vars.get("base_url") or "").rstrip("/")
