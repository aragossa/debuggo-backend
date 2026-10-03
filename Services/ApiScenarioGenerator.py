"""
API test scenario from one model request.

The model gets the test description and the calls of the project's API library that fit it
(names, example bodies, response fields - not the whole schema) and answers with the whole test:
which calls, in what order, with what data, and how values pass from one step to the next.
The requests themselves are assembled by code from the library, so a path is never invented.

The plan is then run without AI. The model is asked again only when a step fails, with the
request that was sent and what the API answered. When the plan has run to its end, the test
is complete: that is decided here, not by the model.
"""

import json
import logging
import re
import uuid
from typing import Any, Dict, List, Optional, Tuple

from auroqa.Services.ApiBaselineTests import _UNIQUE_FIELDS, _find_login, _login_step, _singular, _unique_body
from auroqa.Services.ApiOperationLibrary import list_operations, step_request
from auroqa.Utils.Connectors.db_utils import get_db_connection_context
from auroqa.Utils.Environments import api_base_url, load_environment_vars

MAX_REPAIRS = 2          # model requests after the first one, each only after a failed step
MAX_CALLS_IN_PROMPT = 60
_FILTER_FROM = 40        # a smaller library goes to the model whole
_STOP_WORDS = {'the', 'and', 'for', 'with', 'that', 'this', 'from', 'then', 'check', 'test', 'verify', 'api',
               'new', 'all', 'get', 'via', 'into', 'use', 'using', 'should', 'must', 'can', 'not', 'are', 'was',
               'name', 'value', 'create', 'read', 'update', 'delete', 'rename', 'list', 'search', 'item', 'gone'}


def has_library(project_id: str, client_id: str) -> bool:
    """Whether the project has API calls to build a scenario from."""
    with get_db_connection_context() as conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT 1 FROM api_operations WHERE project_id = %s AND client_id = %s LIMIT 1",
                           (project_id, client_id))
            return cursor.fetchone() is not None


def _words(text: str) -> set:
    """Lowercase words of a text, camelCase and paths split, plurals folded."""
    text = re.sub(r'([a-z])([A-Z])', r'\1 \2', text or '')
    return {_singular(word) for word in re.findall(r'[a-z]{3,}', text.lower())} - _STOP_WORDS


def select_operations(operations: List[Dict], text: str) -> List[Dict]:
    """
    The calls worth showing to the model for this test: those of the resources the description
    mentions, plus the login call. A small library, or a description that matches nothing, gives all calls.
    """
    login = _find_login(operations)
    if len(operations) <= _FILTER_FROM:
        return operations
    wanted = _words(text)
    resources = {op['resource'] for op in operations
                 if wanted & (_words(op['resource']) | _words(op['path']))}
    selected = [op for op in operations if op['resource'] in resources]
    if not selected:
        selected = list(operations)
    if login and login not in selected:
        selected.insert(0, login)
    return selected[:MAX_CALLS_IN_PROMPT]


MAX_CALLS_IN_UI_PROMPT = 25


def ui_api_context(project_id: str, client_id: str, text: str) -> Optional[Dict[str, Any]]:
    """
    What a UI test generation needs to use the API for test data: the calls of the resources the
    test description mentions, as a prompt block, and the library to build the steps from.
    None when the project has no library or the description points to none of its resources:
    the block goes into the prompt of every step, so it is kept short.
    """
    library = list_operations(project_id, client_id)
    if not library:
        return None
    newest_schema = max(op['schema_id'] for op in library)
    library = [op for op in library if op['schema_id'] == newest_schema]
    login = _find_login(library)
    wanted = _words(text)
    resources = {op['resource'] for op in library if wanted & (_words(op['resource']) | _words(op['path']))}
    # Reading calls prepare nothing: only the calls that change data are offered
    selected = [op for op in library if op['resource'] in resources and op['method'] != 'GET'
                and not (login and op['id'] == login['id'])][:MAX_CALLS_IN_UI_PROMPT]
    if not selected:
        return None

    lines = []
    for op in selected:
        # The body as it will be sent when the step changes nothing: the model reuses these values on the page
        body = (op.get('request') or {}).get('body')
        if isinstance(body, dict) and body:
            body = _unique_body(body, 'upd' if op['method'] in ('PUT', 'PATCH') else '')
        fields = f" | body: {json.dumps(body, separators=(',', ':'))[:340]}" if isinstance(body, dict) and body else ''
        lines.append(f"- {op['name']}: {op['method']} {op['path']} — {(op.get('summary') or '')[:70]}{fields}")
    prompt = (
        "API CALLS OF THIS APPLICATION (action \"api_request\"):\n" + "\n".join(lines) + "\n"
        "Use an API call ONLY to prepare data the test needs before the page is used (a user to log in with, "
        "an item to look at) or to clean up after it. NEVER use the API for the behaviour the test itself "
        "verifies: that must be done through the page.\n"
        "When the test description needs data that does not exist yet (a new or just registered user, a new item, "
        "a precondition), create it with an API call FIRST, before the page steps that use it, and then use the "
        "created data on the page: type the same values you sent in the API body (for example %random_email% and "
        "the password you chose) instead of the environment's %login% and %password%.\n"
        "To use one, return action \"api_request\", element_locator \"N/A\" and \"value\" as JSON: "
        "{\"call\": \"name from the list\", \"body\": {}, \"path_params\": {}, "
        "\"extract_variables\": {\"variable\": \"$.field\"}}. The body shown for a call is valid and is sent as "
        "it is: leave \"body\" empty unless the test needs another value in some field, and then give only that "
        "field. Authorization is added automatically. A placeholder (%random_email%, %unique_name%) is the same "
        "value in every step of this test, so after the call a page step types exactly the values of that body "
        "(the same %random_email%, the same password text). A value from the response is available as %variable% "
        "after extract_variables. Do not repeat an API call that is already among the previous steps."
    )
    return {'prompt': prompt, 'library': library, 'login': login}


def describe_operation(op: Dict, is_login: bool = False) -> str:
    """One line about a call for the prompt."""
    request = op.get('request') or {}
    if is_login:
        # The step logs in with the environment's credentials, not with the example ones of the schema
        request = {**request, 'body': _login_step(op)['request']['body']}
    response = op.get('response') or {}
    parts = [f"- {op['name']}: {op['method']} {op['path']}"]
    if op.get('summary'):
        parts.append(f"— {op['summary'][:80]}")
    if op.get('requires_auth'):
        parts.append("| auth")
    query = [f"{param['name']}{'*' if param.get('required') else ''}" for param in request.get('query_params') or []]
    if query:
        parts.append(f"| query: {', '.join(query)}")
    if request.get('body') is not None:
        parts.append(f"| body: {json.dumps(request['body'], separators=(',', ':'))[:300]}")
    returns = f"| returns {op['expected_status']}"
    if response.get('kind') and response['kind'] != 'none':
        fields = ', '.join(list((response.get('fields') or {}).keys())[:12])
        shape = {'list': '[{%s}]', 'paginated': '{data: [{%s}]}', 'object': '{%s}'}[response['kind']]
        returns += ' ' + shape % fields
    parts.append(returns)
    return ' '.join(parts)


def build_prompt(name: str, description: str, operations: List[Dict], login: Optional[Dict]) -> str:
    has_login = login is not None
    calls = '\n'.join(describe_operation(op, has_login and op['id'] == login['id']) for op in operations)
    login_rule = ('Calls marked "auth" are authorized automatically: a login step with the environment\'s '
                  'credentials is put before the first of them and the Authorization header is added. Do NOT add '
                  'a login step yourself, unless the test itself is about logging in.'
                  if has_login else 'Calls marked "auth" cannot be authorized here: avoid them.')
    return f"""You are an API test engineer. Write ONE API test as a sequence of calls from the list below.

TEST NAME: {name}
WHAT TO TEST: {description or name}

API CALLS YOU MAY USE (name: METHOD path — what it does | body: example | returns status and response fields):
{calls}

RULES
1. Use only calls from the list, referring to each by its name in "call". Never invent a path or a call.
2. This is the only request: return the whole test, every step, in order.
3. Pass data between steps with variables. "extract_variables": {{"brand_id": "$.id"}} takes a value from the
   response (paths: $.field, $.data[0].id, $[0].id); later steps use it as %brand_id%.
4. Fill the {{parameters}} of a path in "path_params", e.g. {{"brandId": "%brand_id%"}}.
5. "body" overrides fields of the call's example body: give only the fields this test changes, null to leave a
   field out. Name-like fields of the example body (name, slug, title, email) are made unique automatically, with
   different values for a create and an update call: leave them alone unless the test needs a specific value.
   For your own unique values use %unique_name% and %random_email%. A placeholder is ONE value for the whole
   test: every %unique_name% is the same text. For a second, different value add a label: %unique_name:second%.
   To check a value later, extract it from the response of the call that set or returned it.
6. {login_rule}
7. "expected_status" only when the step must return something else than the call's normal status
   (a negative check: 404 after a delete, 422 for invalid data, 401 without a token).
8. "expect": expected values in the response, by path, e.g. {{"$.name": "%brand_name%"}}. Use it to verify what
   the test is about; do not compare generated ids or dates.
9. Keep the test to what the description asks. Clean up what the test created when a delete call exists.

Return ONLY this JSON:
{{"steps": [{{"call": "name from the list", "description": "what this step does", "path_params": {{}}, "params": {{}},
  "body": {{}}, "expected_status": 200, "extract_variables": {{}}, "expect": {{}}}}]}}
Leave out the keys a step does not need."""


def assemble_request(step: Dict, op: Dict, login: Optional[Dict]) -> Dict[str, Any]:
    """The request of one planned step: the library call with the model's data put in."""
    is_login = login is not None and op['id'] == login['id']
    request = dict(_login_step(op)['request']) if is_login else step_request(op)

    for name, value in (step.get('path_params') or {}).items():
        request['endpoint'] = request['endpoint'].replace(f'%{name}%', str(value))
    if isinstance(step.get('params'), dict) and step['params']:
        request['params'] = {**(request.get('params') or {}), **step['params']}

    body = request.get('body')
    if isinstance(body, dict):
        overrides = step.get('body') if isinstance(step.get('body'), dict) else {}
        if not is_login:
            body = _unique_body(body, 'upd' if op['method'] in ('PUT', 'PATCH') else '')
            # An optional id field with a made-up value stays out unless the test sets it
            for key in (op.get('request') or {}).get('made_up_fields') or []:
                if key.lower().endswith('_id') and key not in overrides:
                    body.pop(key, None)
        # A step that expects an error keeps its data as written; elsewhere a fixed name or slug from
        # the model would make the test fail on its second run, so it gets the unique suffix too
        try:
            negative = int(step.get('expected_status') or 0) >= 400
        except (TypeError, ValueError):
            negative = False
        placeholder = '%unique_name:upd%' if op['method'] in ('PUT', 'PATCH') else '%unique_name%'
        for key, value in overrides.items():
            if value is None:
                body.pop(key, None)
            elif (not is_login and not negative and key.lower() in _UNIQUE_FIELDS
                  and isinstance(value, str) and value and '%' not in value):
                body[key] = f"{value}{'-' if key.lower() == 'slug' else ' '}{placeholder}"
            else:
                body[key] = value
        request['body'] = body
    elif step.get('body') is not None:
        request['body'] = step['body']

    if step.get('expected_status') is not None:
        try:
            request['expected_status'] = int(step['expected_status'])
        except (TypeError, ValueError):
            pass
    extract = dict(request.get('extract_variables') or {})
    if isinstance(step.get('extract_variables'), dict):
        extract.update(step['extract_variables'])
    if extract:
        request['extract_variables'] = extract
    if isinstance(step.get('expect'), dict) and step['expect']:
        request['expect'] = step['expect']
    if not request.get('headers', {}).get('Authorization') and op.get('requires_auth'):
        request.setdefault('headers', {})['Authorization'] = 'Bearer %access_token%'
    return request


class ApiScenarioGenerator:
    def __init__(self):
        self.logger = logging.getLogger('ApiScenarioGenerator')
        self._ai_helper = None
        self.last_error: Optional[str] = None  # why generate() returned False, for the UI

    @property
    def ai_helper(self):
        if self._ai_helper is None:
            from auroqa.Utils.AIHelper.AIHelper import AIHelper
            self._ai_helper = AIHelper()
        return self._ai_helper

    # ---- model -----------------------------------------------------------------------------

    def _ask(self, prompt: str, client_id: str, job_id: str, model_name: Optional[str], context: str) -> Optional[List[Dict]]:
        response = self.ai_helper.send_request_to_gemini(
            prompt=prompt, request_type='api_test', request_context=context,
            client_id=client_id, generation_job_id=job_id, model_name=model_name)
        if isinstance(response, str):
            text = response.strip()
            if text.startswith('```'):
                text = '\n'.join(text.split('\n')[1:-1])
            try:
                response = json.loads(text)
            except json.JSONDecodeError:
                self.logger.error(f"The model did not return JSON: {text[:300]}")
                return None
        steps = response.get('steps') if isinstance(response, dict) else response
        if not isinstance(steps, list) or not steps:
            self.logger.error(f"The model returned no steps: {str(response)[:300]}")
            return None
        return [step for step in steps if isinstance(step, dict)]

    # ---- plan -> requests -> run -----------------------------------------------------------------

    def _to_requests(self, plan: List[Dict], operations: List[Dict], login: Optional[Dict]) -> Tuple[List[Dict], Optional[str]]:
        """Planned steps as executable steps [{description, request}], or what is wrong with the plan."""
        by_name = {op['name']: op for op in operations}
        by_route = {f"{op['method']} {op['path']}": op for op in operations}
        steps = []
        logged_in, needs_login = False, False
        for index, step in enumerate(plan, 1):
            call = str(step.get('call') or '')
            op = by_name.get(call) or by_route.get(call)
            if not op:
                return [], f"step {index} uses the call \"{call}\", which is not in the list"
            if login is not None and op['id'] == login['id']:
                logged_in = True
            elif op.get('requires_auth') and not logged_in:
                needs_login = True
            steps.append({'description': str(step.get('description') or op.get('summary') or call)[:500],
                          'request': assemble_request(step, op, login)})
        # Authorization is mechanical: a call that needs a token gets the login step, whatever the model planned
        if needs_login and login is not None:
            steps.insert(0, _login_step(login))
        return steps, None

    def _run(self, steps: List[Dict], test_case_id: int, environment_vars: Dict) -> Optional[Dict[str, Any]]:
        """Run the steps in order. None when all passed, else the failure: index, request, status, response."""
        from auroqa.Services.ApiTestExecutor import ApiTestExecutor
        executor = ApiTestExecutor(test_case_id=test_case_id, environment_vars=environment_vars)
        for index, step in enumerate(steps):
            self._progress(test_case_id, f"Running step {index + 1} of {len(steps)}: {step['description']}")
            request = step['request']
            result = executor._execute_api_request({'step_order': index + 1, 'element_path': ''}, request)
            error = None if result.get('success') else (result.get('error') or 'failed')
            if error is None:
                missing = [f"{name} ({path})" for name, path in (request.get('extract_variables') or {}).items()
                           if name not in executor.session_variables]
                if missing:
                    error = "not found in the response: " + ", ".join(missing)
            if error:
                return {'index': index, 'error': error, 'status': result.get('response_status'),
                        'response': result.get('response_body'), 'url': result.get('actual_url')}
        return None

    def _progress(self, test_case_id: int, text: str):
        """What the UI shows while the test is being generated."""
        try:
            import redis
            from auroqa.Utils.System import System
            system = System()
            redis.Redis(host=system.redis_host, port=system.redis_port, db=0).setex(
                f"test_case_current_step:{test_case_id}", 300, text[:200])
        except Exception:
            pass

    def _save(self, test_case_id: int, steps: List[Dict]):
        """Replace the steps of the test case with the generated ones."""
        with get_db_connection_context() as conn:
            with conn.cursor() as cursor:
                cursor.execute("DELETE FROM test_steps WHERE test_case_id = %s", (test_case_id,))
                for order, step in enumerate(steps, 1):
                    request = step['request']
                    cursor.execute("""
                        INSERT INTO test_steps (test_case_id, step_order, description, action, element_path, value,
                                                path_type, expected_result, created_at, updated_at)
                        VALUES (%s, %s, %s, 'api_request', NULL, %s, 'xpath', %s, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                    """, (test_case_id, order, step['description'], json.dumps(request),
                          f"Status {request.get('expected_status', 200)}"))
                conn.commit()

    # ---- entry point ----------------------------------------------------------------------------------

    def generate(self, test_case_id: int, client_id: str, project_id: str,
                 environment_id: Optional[int] = None, model_name: Optional[str] = None) -> bool:
        """
        Generate the steps of an API test case. Returns True when the saved test ran to its end
        during generation, False when it was saved with a failing step or could not be planned.
        """
        job_id = str(uuid.uuid4())
        with get_db_connection_context() as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT name, description FROM test_cases WHERE id = %s AND client_id = %s",
                               (test_case_id, client_id))
                row = cursor.fetchone()
                if not row:
                    self.logger.error(f"Test case {test_case_id} not found")
                    self.last_error = "Test case not found."
                    return False
                name, description = row[0], row[1] or ''
                if not environment_id:
                    cursor.execute("SELECT id FROM environments WHERE project_id = %s ORDER BY id LIMIT 1", (project_id,))
                    first = cursor.fetchone()
                    environment_id = first[0] if first else None

        environment_vars = load_environment_vars(environment_id)
        if not environment_vars:
            self.logger.error(f"Test case {test_case_id}: no environment to run the generated steps on")
            self.last_error = "No environment to run the generated steps on: select an environment and generate again."
            return False
        environment_vars = {**environment_vars, 'base_url': api_base_url(environment_vars)}

        library = list_operations(project_id, client_id)
        newest_schema = max(op['schema_id'] for op in library)
        library = [op for op in library if op['schema_id'] == newest_schema]
        login = _find_login(library)
        operations = select_operations(library, f"{name} {description}")
        prompt = build_prompt(name, description, operations, login)
        self.logger.info(f"Test case {test_case_id}: scenario from {len(operations)} of {len(library)} calls, "
                         f"prompt {len(prompt)} chars (job {job_id})")

        self._progress(test_case_id, "Planning the test")
        plan = self._ask(prompt, client_id, job_id, model_name, 'api_scenario_plan')
        steps: List[Dict] = []
        for attempt in range(MAX_REPAIRS + 1):
            if not plan:
                break
            steps, plan_error = self._to_requests(plan, library, login)
            failure = None if plan_error else self._run(steps, test_case_id, environment_vars)
            if not plan_error and failure is None:
                self._save(test_case_id, steps)
                self.logger.info(f"Test case {test_case_id}: {len(steps)} steps, passed, {attempt + 1} model request(s)")
                return True
            self.logger.info(f"Test case {test_case_id}: attempt {attempt + 1} failed: "
                             f"{plan_error or 'step %d: %s' % (failure['index'] + 1, failure['error'])}")
            if attempt == MAX_REPAIRS:
                break

            if plan_error:
                problem = f"The plan cannot be used: {plan_error}."
            else:
                failed = steps[failure['index']]
                problem = (f"Steps 1-{failure['index']} passed. Step {failure['index'] + 1} "
                           f"(\"{failed['description']}\") failed.\n"
                           f"Request sent: {json.dumps(failed['request'])[:1500]}\n"
                           f"Result: {failure['error']}\n"
                           f"Response status: {failure['status']}\nResponse body: {str(failure['response'])[:1500]}")
            self._progress(test_case_id, f"Fixing the test after a failed step (attempt {attempt + 1})")
            plan = self._ask(
                f"{prompt}\n\nYOUR PREVIOUS ANSWER:\n{json.dumps({'steps': plan})[:6000]}\n\n"
                f"WHAT HAPPENED WHEN IT WAS RUN AGAINST THE REAL API:\n{problem}\n\n"
                "Return the corrected whole test in the same JSON format. Fix the data or the order of the calls. "
                "If the API answers with another success status than the list says (201 instead of 200), set "
                "\"expected_status\" to what the API really returns. Data created by the failed run may still exist: "
                "keep unique values unique.",
                client_id, job_id, model_name, 'api_scenario_repair')

        if steps:
            # Keep the last plan: the user sees which step fails and can fix it
            self._save(test_case_id, steps)
            self.logger.warning(f"Test case {test_case_id}: saved {len(steps)} steps, but the test does not pass yet")
            reason = plan_error or f"step {failure['index'] + 1} fails: {failure['error']}"
            self.last_error = (f"The test was generated, but it does not pass yet ({reason}). "
                               f"The {len(steps)} steps are saved: fix the failing step or generate again.")
        else:
            self.logger.error(f"Test case {test_case_id}: no usable plan from the model")
            self.last_error = "The model returned no usable test plan. Make the description more specific or try another model."
        return False
