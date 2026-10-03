"""
Coverage of an API schema by the tests of its project, built by code from what is stored.

For every call of the schema (the library of Services/ApiOperationLibrary.py): which test steps send
it, with which expected statuses, and how the step ended in its last run. A step is matched to a
call by method and path: "/brands/%brand_id%" and "/brands/01ABC" are "/brands/{brandId}".

State of a call:
  uncovered - no test step sends it
  basic     - sent, but only one kind of check: success statuses only, or errors only
  full      - both a success status and an error status (401, 404, 422, ...) are checked
  failing   - a step that sends it failed in its last run

Three views of the same calls ("states" of a call, "summary" of the schema):
  api - by the API steps of the tests, as above
  ui  - by what the browser sent during the last run of each UI test (test_run_api_calls): the calls
        of the backend the UI tests really reach; the statuses are those the API answered with
  all - both together

page_coverage() is the same idea for pages: the pages of the application the UI tests were on.
"""

import json
import logging
import re
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

from auroqa.Services.ApiOperationLibrary import list_operations
from auroqa.Utils.Connectors.db_utils import get_db_connection_context

logger = logging.getLogger(__name__)

_METHOD_OF_ACTION = {'api_get': 'GET', 'api_post': 'POST', 'api_put': 'PUT', 'api_delete': 'DELETE',
                     'api_patch': 'PATCH'}


def _path_only(endpoint: str) -> str:
    """The path of an endpoint as a step stores it: no host, no query, no trailing slash."""
    endpoint = (endpoint or '').strip()
    if endpoint.startswith('%') and '%/' in endpoint:  # "%api_url%/brands"
        endpoint = endpoint[endpoint.index('%/') + 1:]
    if re.match(r'https?://', endpoint):
        endpoint = urlparse(endpoint).path
    endpoint = endpoint.split('?')[0].rstrip('/')
    return endpoint or '/'


class OperationMatcher:
    """Finds the call of a schema for a method and a concrete path."""

    def __init__(self, operations: List[Dict]):
        compiled = []
        for op in operations:
            pattern = '/'.join('[^/]+' if part.startswith('{') and part.endswith('}') else re.escape(part)
                               for part in op['path'].rstrip('/').split('/'))
            compiled.append((op['path'].count('{'), op['method'], re.compile(f'^{pattern or "/"}$'), op))
        # "/users/login" must win over "/users/{id}": fewer parameters first
        self._compiled = sorted(compiled, key=lambda item: item[0])
        # API servers are often mounted under a prefix the schema does not repeat ("/api/v1")
        self._paths = {op['path'] for op in operations}

    def match(self, method: str, endpoint: str) -> Optional[Dict]:
        method = (method or '').upper()
        path = _path_only(endpoint)
        segments = path.split('/')
        # Try the path as it is, then without leading segments: "/api/v1/brands" -> "/brands"
        for skip in range(0, max(1, len(segments) - 1)):
            candidate = '/' + '/'.join(segments[1 + skip:]) if skip else path
            for _, op_method, pattern, op in self._compiled:
                if op_method == method and pattern.match(candidate):
                    return op
        return None


def _step_request(action: str, element_path: Optional[str], value: Optional[str],
                  description: Optional[str]) -> Optional[Tuple[str, str, int]]:
    """(method, endpoint, expected status) of an API step, or None when it sends nothing."""
    for text in (value, description):
        if text and text.lstrip().startswith('{'):
            try:
                data = json.loads(text)
            except json.JSONDecodeError:
                continue
            if isinstance(data, dict) and data.get('endpoint'):
                try:
                    status = int(data.get('expected_status') or 200)
                except (TypeError, ValueError):
                    status = 200
                return str(data.get('method') or 'GET').upper(), str(data['endpoint']), status
    if action in _METHOD_OF_ACTION and element_path:
        return _METHOD_OF_ACTION[action], element_path, 200
    return None


def _api_steps(project_id: str, client_id: str) -> List[Dict[str, Any]]:
    """API steps of the project's tests with the status of each step in its last run."""
    with get_db_connection_context() as conn:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT s.id, s.action, s.element_path, s.value, s.description,
                       tc.id, tc.name, tc.test_type,
                       (SELECT r.status FROM test_step_execution_results r
                        WHERE r.test_step_id = s.id ORDER BY r.id DESC LIMIT 1)
                FROM test_steps s
                JOIN test_cases tc ON tc.id = s.test_case_id
                WHERE tc.project_id = %s AND tc.client_id = %s AND tc.type = 'test'
                  AND (s.action = 'api_request' OR s.action LIKE 'api\\_%%')
                ORDER BY tc.id, s.step_order
            """, (project_id, client_id))
            rows = cursor.fetchall()
    steps = []
    for step_id, action, element_path, value, description, test_id, test_name, test_type, status in rows:
        request = _step_request(action, element_path, value, description)
        if request:
            steps.append({'step_id': step_id, 'method': request[0], 'endpoint': request[1],
                          'expected_status': request[2], 'test_id': test_id, 'test_name': test_name,
                          'test_type': test_type or 'ui', 'last_status': status})
    return steps


def _ui_calls(project_id: str, client_id: str) -> List[Dict[str, Any]]:
    """The requests the browser sent in the last traced run of each test of the project."""
    with get_db_connection_context() as conn:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT c.method, c.url, c.status, c.hits, tc.id, tc.name
                FROM test_run_api_calls c
                JOIN test_cases tc ON tc.id = c.test_case_id
                WHERE tc.project_id = %s AND tc.client_id = %s
                  AND c.test_run_id = (SELECT MAX(test_run_id) FROM test_run_api_calls WHERE test_case_id = tc.id)
            """, (project_id, client_id))
            return [{'method': row[0], 'url': row[1], 'status': row[2], 'hits': row[3],
                     'test_id': row[4], 'test_name': row[5]} for row in cursor.fetchall()]


def _state(statuses: List[int], failing: bool) -> str:
    if not statuses:
        return 'uncovered'
    if failing:
        return 'failing'
    return 'full' if any(s < 400 for s in statuses) and any(s >= 400 for s in statuses) else 'basic'


def schema_coverage(schema_id: int, client_id: str) -> Dict[str, Any]:
    """Coverage of one schema: a summary and, per resource, its calls with their state and tests."""
    with get_db_connection_context() as conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT name, project_id FROM api_schemas WHERE id = %s AND client_id = %s",
                           (schema_id, client_id))
            row = cursor.fetchone()
    if not row:
        raise ValueError("API schema not found")
    schema_name, project_id = row[0], str(row[1])

    operations = list_operations(project_id, client_id, schema_id)
    matcher = OperationMatcher(operations)
    by_operation: Dict[int, Dict[str, Any]] = {op['id']: {'statuses': [], 'failing': False, 'tests': {}}
                                               for op in operations}
    unmatched = 0
    for step in _api_steps(project_id, client_id):
        op = matcher.match(step['method'], step['endpoint'])
        if not op:
            unmatched += 1
            continue
        entry = by_operation[op['id']]
        entry['statuses'].append(step['expected_status'])
        failed = step['last_status'] == 'failed'
        entry['failing'] = entry['failing'] or failed
        test = entry['tests'].setdefault(step['test_id'], {
            'id': step['test_id'], 'name': step['test_name'], 'test_type': step['test_type'],
            'statuses': [], 'last_status': None})
        if step['expected_status'] not in test['statuses']:
            test['statuses'].append(step['expected_status'])
        # One failed step makes the test's use of this call failed
        if failed or (step['last_status'] and test['last_status'] != 'failed'):
            test['last_status'] = step['last_status']

    # What the browser of the UI tests sent
    ui_by_operation: Dict[int, Dict[str, Any]] = {op['id']: {'statuses': [], 'tests': {}} for op in operations}
    for call in _ui_calls(project_id, client_id):
        op = matcher.match(call['method'], call['url'])
        if not op:
            continue  # a request to something else: analytics, another backend
        entry = ui_by_operation[op['id']]
        if call['status']:
            entry['statuses'].append(call['status'])
        test = entry['tests'].setdefault(call['test_id'], {
            'id': call['test_id'], 'name': call['test_name'], 'test_type': 'ui', 'statuses': [], 'hits': 0})
        test['hits'] += call['hits']
        if call['status'] and call['status'] not in test['statuses']:
            test['statuses'].append(call['status'])

    resources: Dict[str, List[Dict]] = {}
    empty = {'total': len(operations), 'uncovered': 0, 'basic': 0, 'full': 0, 'failing': 0}
    summary = {'api': dict(empty), 'ui': dict(empty), 'all': dict(empty)}
    for op in operations:
        entry, ui = by_operation[op['id']], ui_by_operation[op['id']]
        # A call the browser sent is covered even when the status was not caught
        ui_statuses = ui['statuses'] or ([200] if ui['tests'] else [])
        states = {'api': _state(entry['statuses'], entry['failing']),
                  'ui': _state(ui_statuses, False),
                  'all': _state(entry['statuses'] + ui_statuses, entry['failing'])}
        for view, state in states.items():
            summary[view][state] += 1
        resources.setdefault(op['resource'] or 'Other', []).append({
            'id': op['id'], 'method': op['method'], 'path': op['path'], 'name': op['name'],
            'summary': op['summary'], 'requires_auth': op['requires_auth'], 'states': states,
            'statuses': sorted(set(entry['statuses'])), 'tests': list(entry['tests'].values()),
            'ui_statuses': sorted(set(ui['statuses'])), 'ui_tests': list(ui['tests'].values()),
        })
    for view in summary.values():
        view['covered'] = view['total'] - view['uncovered']
    return {'schema_id': schema_id, 'schema_name': schema_name, 'project_id': project_id,
            'summary': summary, 'unmatched_steps': unmatched,
            'resources': [{'name': name, 'operations': calls} for name, calls in sorted(resources.items())]}


def page_coverage(project_id: str, client_id: str) -> Dict[str, Any]:
    """
    The pages of the application the UI tests of a project were on, in the last traced run of each
    test: per page, the tests that visited it. Only visited pages are known: there is no list of
    all pages to compare with.
    """
    with get_db_connection_context() as conn:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT p.page, tc.id, tc.name, MIN(p.url), MAX(p.created_at)
                FROM test_run_pages p
                JOIN test_cases tc ON tc.id = p.test_case_id
                WHERE tc.project_id = %s AND tc.client_id = %s
                  AND p.test_run_id = (SELECT MAX(test_run_id) FROM test_run_pages WHERE test_case_id = tc.id)
                GROUP BY p.page, tc.id, tc.name
                ORDER BY p.page, tc.id
            """, (project_id, client_id))
            rows = cursor.fetchall()
            cursor.execute("""
                SELECT COUNT(*) FROM test_cases tc
                WHERE tc.project_id = %s AND tc.client_id = %s AND tc.type = 'test'
                  AND COALESCE(tc.test_type, 'ui') = 'ui'
            """, (project_id, client_id))
            ui_tests = cursor.fetchone()[0]
    pages: Dict[str, Dict[str, Any]] = {}
    traced = set()
    for page, test_id, test_name, url, visited_at in rows:
        entry = pages.setdefault(page, {'page': page, 'example_url': url, 'tests': [], 'last_visit': None})
        entry['tests'].append({'id': test_id, 'name': test_name})
        stamp = visited_at.isoformat() if visited_at else None
        entry['last_visit'] = max(filter(None, [entry['last_visit'], stamp]), default=None)
        traced.add(test_id)
    return {'project_id': project_id, 'ui_tests': ui_tests, 'traced_tests': len(traced),
            'pages': sorted(pages.values(), key=lambda item: (len(item['tests']), item['page']))}


def uncovered_operations(schema_id: int, client_id: str) -> List[str]:
    """Names of the calls no test sends, for the scenario ideas: they are suggested first."""
    try:
        coverage = schema_coverage(schema_id, client_id)
    except Exception as e:
        logger.error(f"Coverage of schema {schema_id} could not be built: {e}")
        return []
    return [call['name'] for resource in coverage['resources'] for call in resource['operations']
            if call['states']['api'] == 'uncovered']
