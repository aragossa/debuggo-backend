"""
Baseline API tests built from the library of API calls, without AI.

For one uploaded schema this creates, by code:
  - a read check for every GET that needs no path parameter: the call answers with its success status;
  - a chain per resource - create, read, update, delete - where the schema has those calls,
    with the id of the created item passed on through extract_variables.

A call that needs authorization gets a login step first; the login uses the environment's
%login% and %password%. The tests land in a group named after the schema (inside "API Tests"),
one subgroup per resource. A test that already exists there is left alone, so the generation
can be repeated after a schema update without duplicates and without touching edited tests.
"""

import json
import logging
import re
from typing import Any, Dict, List, Optional

from auroqa.Services.ApiOperationLibrary import list_operations, step_request
from auroqa.Utils.Connectors.db_utils import get_db_connection_context

logger = logging.getLogger(__name__)

# Body fields whose example value would collide on a second run
_UNIQUE_FIELDS = ('name', 'slug', 'title', 'code', 'username')
_LOGIN_FIELDS = ('email', 'username', 'login', 'user', 'user_name')


def _singular(word: str) -> str:
    word = word.lower()
    if word.endswith('ies'):
        return word[:-3] + 'y'
    if word.endswith('ses') or word.endswith('xes'):
        return word[:-2]
    return word[:-1] if word.endswith('s') else word


def _path_params(path: str) -> List[str]:
    return re.findall(r'\{([^}]+)\}', path)


def _find_login(operations: List[Dict]) -> Optional[Dict]:
    """The call that returns a token: a POST with "login" (or similar) in its path."""
    for marker in ('login', 'signin', 'sign-in', 'auth', 'token'):
        for op in operations:
            fields = (op.get('response') or {}).get('fields') or {}
            if (op['method'] == 'POST' and marker in op['path'].lower() and not _path_params(op['path'])
                    and any('token' in name.lower() for name in fields)):
                return op
    return None


def _login_step(login: Dict) -> Dict[str, Any]:
    """Login with the environment's credentials; the token goes to %access_token%."""
    request = step_request(login)
    body = dict(request.get('body') or {})
    for key in body:
        if key.lower() in _LOGIN_FIELDS:
            body[key] = '%login%'
        elif key.lower() == 'password':
            body[key] = '%password%'
    request['body'] = body
    fields = list(((login.get('response') or {}).get('fields') or {}).keys())
    token = next((name for name in ('access_token', 'token') if name in fields),
                 next(name for name in fields if 'token' in name.lower()))
    request['extract_variables'] = {'access_token': f'$.{token}'}
    return {'description': "Log in with the environment's login and password", 'request': request}


def _unique_body(body: Any, label: str = '') -> Any:
    """
    The example body with values that must differ between runs replaced by placeholders.

    %unique_name% is one value for the whole run; a label (%unique_name:upd%) gives another one,
    so an update does not send the values the create step already used.
    """
    if not isinstance(body, dict):
        return body
    result = dict(body)
    placeholder = f"%unique_name:{label}%" if label else "%unique_name%"
    for key, value in body.items():
        if not isinstance(value, str) or '%' in value:
            continue
        if key.lower() == 'email':
            result[key] = '%random_email%'
        elif key.lower() in _UNIQUE_FIELDS:
            joiner = '-' if key.lower() == 'slug' else ' '
            result[key] = f"{value}{joiner}{placeholder}"
    return result


def _related_steps(body: Any, operations: List[Dict], own_path: str, made_up: List[str]) -> List[Dict[str, Any]]:
    """
    For a body field like brand_id: a step that reads the list of that resource and takes the id
    of its first item, so the request refers to something that exists. The body is changed in place.

    An optional id field with a made-up value that points to nothing we can read (a parent_id)
    is removed from the body: "string" there breaks a request that is valid without the field.
    """
    steps = []
    if not isinstance(body, dict):
        return steps
    for key in list(body.keys()):
        if not key.lower().endswith('_id'):
            continue
        prefix = key[:-3].lower()
        resolved = False
        for op in operations:
            response = op.get('response') or {}
            segments = [part for part in op['path'].split('/') if part]
            if (op['method'] != 'GET' or _path_params(op['path']) or not segments or op['path'] == own_path
                    or response.get('kind') not in ('list', 'paginated') or 'id' not in (response.get('fields') or {})):
                continue
            target = _singular(segments[-1])
            if prefix == target or prefix.endswith('_' + target):
                request = step_request(op)
                request['extract_variables'] = {key: '$[0].id' if response['kind'] == 'list' else '$.data[0].id'}
                steps.append({'description': f"Take an existing {target} for {key}", 'request': request})
                body[key] = f'%{key}%'
                resolved = True
                break
        if not resolved and key in made_up:
            del body[key]
    return steps


def build_baseline_tests(operations: List[Dict]) -> List[Dict[str, Any]]:
    """Test definitions (not saved): resource, name, description, steps [{description, request}]."""
    login = _find_login(operations)
    by_path: Dict[str, Dict[str, Dict]] = {}
    for op in operations:
        by_path.setdefault(op['path'], {})[op['method']] = op

    def with_login(steps: List[Dict], needed: bool) -> Optional[List[Dict]]:
        if not needed:
            return steps
        return ([_login_step(login)] + steps) if login else None  # no way to authorize: no test

    tests = []

    # Read checks
    for op in operations:
        if op['method'] != 'GET' or _path_params(op['path']) or op is login:
            continue
        steps = with_login([{'description': op.get('summary') or f"GET {op['path']}", 'request': step_request(op)}],
                           op['requires_auth'])
        if steps:
            tests.append({
                'resource': op['resource'] or 'Other',
                'name': f"GET {op['path']}",
                'description': f"{op.get('summary') or op['name']}: the call answers {op['expected_status']}.",
                'steps': steps,
            })

    # Create, read, update, delete chains
    for path, methods in by_path.items():
        create = methods.get('POST')
        if not create or _path_params(path) or create is login:
            continue
        item_path = next((other for other in by_path if re.fullmatch(re.escape(path) + r'/\{[^/}]+\}', other)), None)
        if not item_path or 'id' not in ((create.get('response') or {}).get('fields') or {}):
            continue
        item = by_path[item_path]
        id_var = _path_params(item_path)[0]
        update = item.get('PUT') or item.get('PATCH')
        used = [op for op in (create, item.get('GET'), update, item.get('DELETE')) if op]
        if len(used) < 2:
            continue

        steps, verbs = [], ['create']
        create_request = step_request(create)
        create_request['body'] = _unique_body(create_request.get('body'))
        related = _related_steps(create_request.get('body'), operations, path,
                                 (create.get('request') or {}).get('made_up_fields') or [])
        related_vars = [name for step in related for name in step['request']['extract_variables']]
        steps.extend(related)
        create_request['extract_variables'] = {id_var: '$.id'}
        steps.append({'description': create.get('summary') or f"POST {path}", 'request': create_request})
        if item.get('GET'):
            verbs.append('read')
            steps.append({'description': item['GET'].get('summary') or f"GET {item_path}", 'request': step_request(item['GET'])})
        if update:
            verbs.append('update')
            update_request = step_request(update)
            update_request['body'] = _unique_body(update_request.get('body'), 'upd')
            if isinstance(update_request.get('body'), dict):
                for key in list(update_request['body'].keys()):
                    if key in related_vars:  # the ids taken before the create step
                        update_request['body'][key] = f'%{key}%'
                    elif key.lower().endswith('_id') and key in ((update.get('request') or {}).get('made_up_fields') or []):
                        del update_request['body'][key]
            steps.append({'description': update.get('summary') or f"{update['method']} {item_path}", 'request': update_request})
        if item.get('DELETE'):
            verbs.append('delete')
            steps.append({'description': item['DELETE'].get('summary') or f"DELETE {item_path}", 'request': step_request(item['DELETE'])})

        steps = with_login(steps, any(op['requires_auth'] for op in used))
        if steps:
            tests.append({
                'resource': create['resource'] or 'Other',
                'name': f"{create['resource'] or path}: {', '.join(verbs)}",
                'description': f"Chain on {path}: {', '.join(verbs)}. The id of the created item is passed to the next calls.",
                'steps': steps,
            })

    return tests


def _find_or_create_group(cursor, name: str, parent_id: Optional[int], project_id: str, client_id: str) -> int:
    cursor.execute("""
        SELECT id FROM test_cases
        WHERE type = 'group' AND name = %s AND project_id = %s AND client_id = %s
          AND parent_id IS NOT DISTINCT FROM %s
        ORDER BY id LIMIT 1
    """, (name, project_id, client_id, parent_id))
    row = cursor.fetchone()
    if row:
        return row[0]
    cursor.execute("""
        INSERT INTO test_cases (name, description, parent_id, type, "order", client_id, project_id, test_type)
        VALUES (%s, %s, %s, 'group', 1, %s, %s, 'api')
        RETURNING id
    """, (name, '', parent_id, client_id, project_id))
    return cursor.fetchone()[0]


def generate_baseline_tests(schema_id: int, client_id: str) -> Dict[str, Any]:
    """
    Create the baseline API tests of a schema. Existing tests (same name in the same resource group)
    are skipped. Returns what was created and what was skipped.
    """
    with get_db_connection_context() as conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT name, project_id FROM api_schemas WHERE id = %s AND client_id = %s",
                           (schema_id, client_id))
            row = cursor.fetchone()
    if not row:
        raise ValueError("API schema not found")
    schema_name, project_id = row[0], str(row[1])

    operations = list_operations(project_id, client_id, schema_id)
    tests = build_baseline_tests(operations)
    created, skipped = [], []

    with get_db_connection_context() as conn:
        with conn.cursor() as cursor:
            root_id = _find_or_create_group(cursor, schema_name, None, project_id, client_id) if tests else None
            groups: Dict[str, int] = {}
            for test in tests:
                if test['resource'] not in groups:
                    groups[test['resource']] = _find_or_create_group(cursor, test['resource'], root_id, project_id, client_id)
                group_id = groups[test['resource']]

                cursor.execute("SELECT id FROM test_cases WHERE type = 'test' AND parent_id = %s AND name = %s",
                               (group_id, test['name']))
                existing = cursor.fetchone()
                if existing:
                    skipped.append({'id': existing[0], 'name': test['name'], 'resource': test['resource']})
                    continue

                cursor.execute("""
                    INSERT INTO test_cases (name, description, parent_id, type, "order", client_id, project_id, test_type)
                    VALUES (%s, %s, %s, 'test', 1, %s, %s, 'api')
                    RETURNING id
                """, (test['name'], test['description'], group_id, client_id, project_id))
                test_case_id = cursor.fetchone()[0]
                for order, step in enumerate(test['steps'], 1):
                    request = step['request']
                    cursor.execute("""
                        INSERT INTO test_steps (test_case_id, step_order, description, action, element_path, value,
                                                path_type, expected_result, created_at, updated_at)
                        VALUES (%s, %s, %s, 'api_request', NULL, %s, 'xpath', %s, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                    """, (test_case_id, order, step['description'], json.dumps(request),
                          f"Status {request.get('expected_status', 200)}"))
                created.append({'id': test_case_id, 'name': test['name'], 'resource': test['resource'],
                                'steps': len(test['steps'])})
            conn.commit()

    logger.info(f"Baseline API tests for schema {schema_id}: {len(created)} created, {len(skipped)} already existed")
    return {'schema_id': schema_id, 'group_id': root_id, 'operations': len(operations),
            'created': created, 'skipped': skipped}
