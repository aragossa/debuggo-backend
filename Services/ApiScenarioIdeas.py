"""
Ideas for API test scenarios, suggested by the model from the library of API calls.

The baseline tests (Services/ApiBaselineTests.py) cover what follows from the schema alone: a read
check per GET and a create-read-update-delete chain per resource. This asks the model, in one
request, for scenarios beyond those: flows across resources, negative checks, business rules.
Each idea is a test name and a description written the way a person would describe the test.

The user picks the ideas to keep. Each becomes an API test case in the group "<schema>/Scenarios",
and its steps are generated from the description as for any API test (ApiScenarioGenerator),
through the same Kafka queue, one test after another.
"""

import json
import logging
from typing import Any, Dict, List, Optional

from auroqa.Services.ApiBaselineTests import _find_login, _find_or_create_group
from auroqa.Services.ApiOperationLibrary import list_operations
from auroqa.Services.ApiScenarioGenerator import describe_operation
from auroqa.Utils.Connectors.db_utils import get_db_connection_context

logger = logging.getLogger(__name__)

SCENARIOS_GROUP = "Scenarios"
MAX_IDEAS = 20
MAX_CALLS_IN_PROMPT = 120


def _schema(schema_id: int, client_id: str) -> Optional[Dict[str, str]]:
    with get_db_connection_context() as conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT name, project_id FROM api_schemas WHERE id = %s AND client_id = %s",
                           (schema_id, client_id))
            row = cursor.fetchone()
    return {'name': row[0], 'project_id': str(row[1])} if row else None


def _existing_tests(schema_name: str, project_id: str, client_id: str) -> List[str]:
    """Names and descriptions of the API tests already in the schema's group, at any depth."""
    with get_db_connection_context() as conn:
        with conn.cursor() as cursor:
            cursor.execute("""
                WITH RECURSIVE tree AS (
                    SELECT id FROM test_cases
                    WHERE type = 'group' AND name = %s AND parent_id IS NULL AND project_id = %s AND client_id = %s
                    UNION ALL
                    SELECT tc.id FROM test_cases tc JOIN tree ON tc.parent_id = tree.id WHERE tc.type = 'group'
                )
                SELECT name, COALESCE(description, '') FROM test_cases
                WHERE type = 'test' AND parent_id IN (SELECT id FROM tree)
                ORDER BY id
            """, (schema_name, project_id, client_id))
            return [f"- {name}: {description[:160]}" for name, description in cursor.fetchall()]


def build_ideas_prompt(schema_name: str, operations: List[Dict], existing: List[str], count: int,
                       uncovered: Optional[List[str]] = None) -> str:
    login = _find_login(operations)
    calls = '\n'.join(describe_operation(op, login is not None and op['id'] == login['id'])
                      for op in operations[:MAX_CALLS_IN_PROMPT])
    auth_rule = ('Calls marked "auth" are authorized automatically with the login and password of the test '
                 'environment (a regular user, maybe an admin).' if login else
                 'Calls marked "auth" cannot be authorized here: do not suggest scenarios that need them.')
    existing_text = '\n'.join(existing[:200]) or '(none)'
    uncovered_text = (f"\nCALLS NO TEST USES YET (prefer scenarios that use them, where a real scenario exists):\n"
                      f"{', '.join(uncovered[:60])}\n") if uncovered else ''
    return f"""You are a senior API test engineer. Suggest API test scenarios for the API "{schema_name}".

API CALLS (name: METHOD path — what it does | body: example | returns status and response fields):
{calls}

TESTS THAT ALREADY EXIST OR WERE ALREADY SUGGESTED (do not repeat them or suggest variants of them; simple read checks and create-read-update-delete chains of one
resource are already covered):
{existing_text}
{uncovered_text}
Suggest up to {count} scenarios that find real bugs and go beyond those tests:
- flows across several resources, where data created by one call is used by another
  (an item that refers to another one, a list or a search that must show what was just created);
- negative checks: what a call must refuse (missing or invalid fields, a duplicate, a deleted item, no token)
  and the status it must answer with;
- business rules the summaries or fields reveal (totals, states, filters, sorting, limits).

Each scenario must be doable with the calls above only, from an empty state: it creates the data it needs and
deletes what it created when a delete call exists. {auth_rule}
Do not suggest a scenario that needs data the calls cannot create, an email inbox, a file, or another system.

Write each description as a tester would write the test case: the steps in order and what must be checked,
naming the resources as the API names them. Do not put JSON, paths or call names in the description.

Return ONLY this JSON:
{{"scenarios": [{{"name": "short test name, up to 80 characters", "resource": "main resource",
  "kind": "flow | negative | rule", "description": "1. ...\\n2. ...\\n3. Check that ...",
  "calls": ["names of the calls from the list the test uses"]}}]}}"""


def _parse(response: Any) -> List[Dict]:
    if isinstance(response, str):
        text = response.strip()
        if text.startswith('```'):
            text = '\n'.join(text.split('\n')[1:-1])
        try:
            response = json.loads(text)
        except json.JSONDecodeError:
            logger.error(f"Scenario ideas: the model did not return JSON: {text[:300]}")
            return []
    ideas = response.get('scenarios') if isinstance(response, dict) else response
    return [idea for idea in ideas if isinstance(idea, dict)] if isinstance(ideas, list) else []


def suggest_scenarios(schema_id: int, client_id: str, model_name: Optional[str] = None,
                      count: int = 10, exclude: Optional[List[Dict]] = None) -> Dict[str, Any]:
    """
    Ideas for API test scenarios of a schema: [{name, description, resource, kind, calls}].
    exclude: ideas already shown to the user ({name, description}), for "suggest more": not repeated.
    """
    schema = _schema(schema_id, client_id)
    if not schema:
        raise ValueError("API schema not found")
    operations = list_operations(schema['project_id'], client_id, schema_id)
    if not operations:
        raise ValueError("The schema has no API calls")
    count = max(1, min(int(count or 10), MAX_IDEAS))
    existing = _existing_tests(schema['name'], schema['project_id'], client_id)
    existing += [f"- {str(idea.get('name') or '')[:120]}: {str(idea.get('description') or '')[:160]}"
                 for idea in exclude or [] if idea.get('name')]
    from auroqa.Services.ApiCoverage import uncovered_operations
    prompt = build_ideas_prompt(schema['name'], operations, existing, count,
                                uncovered_operations(schema_id, client_id))
    logger.info(f"Scenario ideas for schema {schema_id}: {len(operations)} calls, {len(existing)} existing tests, "
                f"prompt {len(prompt)} chars")

    from auroqa.Utils.AIHelper.AIHelper import AIHelper
    response = AIHelper().send_request_to_gemini(
        prompt=prompt, request_type='api_test', request_context='api_scenario_ideas',
        client_id=client_id, model_name=model_name)

    names = {op['name'] for op in operations}
    taken = {line[2:].split(':')[0].strip().lower() for line in existing}
    ideas, dropped = [], 0
    for idea in _parse(response):
        name = str(idea.get('name') or '').strip()[:120]
        description = str(idea.get('description') or '').strip()
        calls = [str(call) for call in idea.get('calls') or [] if str(call) in names]
        # An idea that names no real call cannot be built from this API; a repeated name is not a new test
        if not name or not description or not calls or name.lower() in taken:
            dropped += 1
            continue
        taken.add(name.lower())
        ideas.append({'name': name, 'description': description, 'calls': calls,
                      'resource': str(idea.get('resource') or '').strip()[:80],
                      'kind': str(idea.get('kind') or '').strip()[:20]})
    if dropped:
        logger.info(f"Scenario ideas for schema {schema_id}: {dropped} dropped (no known call, empty or repeated)")
    return {'schema_id': schema_id, 'scenarios': ideas[:count]}


def create_scenario_tests(schema_id: int, client_id: str, scenarios: List[Dict]) -> Dict[str, Any]:
    """
    Create the API test cases of the chosen scenarios in "<schema>/Scenarios", without steps.
    A test with the same name there is left as it is. Returns the created and the skipped tests.
    """
    schema = _schema(schema_id, client_id)
    if not schema:
        raise ValueError("API schema not found")
    project_id = schema['project_id']
    created, skipped = [], []
    with get_db_connection_context() as conn:
        with conn.cursor() as cursor:
            root_id = _find_or_create_group(cursor, schema['name'], None, project_id, client_id)
            group_id = _find_or_create_group(cursor, SCENARIOS_GROUP, root_id, project_id, client_id)
            for scenario in scenarios:
                name = str(scenario.get('name') or '').strip()[:120]
                description = str(scenario.get('description') or '').strip()
                if not name or not description:
                    continue
                cursor.execute("SELECT id FROM test_cases WHERE type = 'test' AND parent_id = %s AND name = %s",
                               (group_id, name))
                existing = cursor.fetchone()
                if existing:
                    skipped.append({'id': existing[0], 'name': name})
                    continue
                cursor.execute("""
                    INSERT INTO test_cases (name, description, parent_id, type, "order", client_id, project_id, test_type)
                    VALUES (%s, %s, %s, 'test', 1, %s, %s, 'api')
                    RETURNING id
                """, (name, description, group_id, client_id, project_id))
                created.append({'id': cursor.fetchone()[0], 'name': name})
            conn.commit()
    logger.info(f"Scenario tests for schema {schema_id}: {len(created)} created, {len(skipped)} already existed")
    return {'schema_id': schema_id, 'project_id': project_id, 'group_id': group_id,
            'created': created, 'skipped': skipped}


def scenario_tests_without_steps(schema_id: int, client_id: str) -> Dict[str, Any]:
    """The tests of "<schema>/Scenarios" that have no steps yet: created, but their generation did not finish."""
    schema = _schema(schema_id, client_id)
    if not schema:
        raise ValueError("API schema not found")
    with get_db_connection_context() as conn:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT tc.id, tc.name FROM test_cases tc
                JOIN test_cases scenarios ON scenarios.id = tc.parent_id
                JOIN test_cases root ON root.id = scenarios.parent_id
                WHERE tc.type = 'test' AND scenarios.type = 'group' AND scenarios.name = %s
                  AND root.type = 'group' AND root.name = %s AND root.parent_id IS NULL
                  AND root.project_id = %s AND root.client_id = %s
                  AND NOT EXISTS (SELECT 1 FROM test_steps s WHERE s.test_case_id = tc.id)
                ORDER BY tc.id
            """, (SCENARIOS_GROUP, schema['name'], schema['project_id'], client_id))
            tests = [{'id': row[0], 'name': row[1]} for row in cursor.fetchall()]
    return {'schema_id': schema_id, 'project_id': schema['project_id'], 'tests': tests}


def queue_generation(test_case_id: int, client_id: str, project_id: str,
                     environment_id: Optional[int], model_name: Optional[str]) -> None:
    """Queue the step generation of an API test, the same message the Generate button sends."""
    import redis
    from kafka import KafkaProducer
    from auroqa.Utils.GenerationStatus import clear_generation_error
    from auroqa.Utils.System import System

    system = System()
    producer = KafkaProducer(bootstrap_servers=f"{system.kafka_host}:{system.kafka_port}",
                             value_serializer=lambda v: json.dumps(v).encode('utf-8'))
    try:
        clear_generation_error(test_case_id)
        producer.send('user_requests', value={
            'request_type': 'generate_api_test_steps',
            'test_case_id': test_case_id,
            # Not read when the project has a library of calls, but the consumer requires it
            'schema_content': 'library',
            'client_id': client_id,
            'project_id': project_id,
            'environment_id': environment_id,
            'model_name': model_name,
        })
        producer.flush()
    finally:
        producer.close()
    try:
        # Shown as "generating" in the UI; long enough for the tests queued before it
        redis.Redis(host=system.redis_host, port=system.redis_port, db=0, decode_responses=True) \
            .setex(f"api_test_generating:{test_case_id}", 1800, str(test_case_id))
    except Exception as e:
        logger.error(f"Could not mark test case {test_case_id} as generating: {e}")
