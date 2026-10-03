"""
Library of API calls of a project.

An uploaded OpenAPI 3 / Swagger 2 schema is turned by code, without AI, into one record per
method + path: its name, a request template filled from the schema examples, the success status,
whether it needs authorization, and the fields of the response. The records live in the
api_operations table.

API tests are assembled from these calls, and a UI test inserts one as an api_request step.
A step keeps its own copy of the request (see step_request), so re-uploading a schema never
changes an existing test.
"""

import json
import logging
import re
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

from auroqa.Utils.Connectors.db_utils import get_db_connection_context

logger = logging.getLogger(__name__)

HTTP_METHODS = ('get', 'post', 'put', 'patch', 'delete')
_MAX_DEPTH = 6  # nesting of an example body; also stops self-referencing schemas


def _resolve(node: Any, schema: Dict, seen: Optional[tuple] = None) -> Any:
    """Follow a local "$ref" ("#/components/schemas/X"). A broken or cyclic reference gives {}."""
    seen = seen or ()
    while isinstance(node, dict) and '$ref' in node:
        ref = node['$ref']
        if not isinstance(ref, str) or not ref.startswith('#/') or ref in seen:
            return {}
        seen = seen + (ref,)
        target = schema
        for part in ref[2:].split('/'):
            part = part.replace('~1', '/').replace('~0', '~')
            if not isinstance(target, dict) or part not in target:
                return {}
            target = target[part]
        node = target
    return node


def _merged(node: Dict, schema: Dict) -> Dict:
    """An object schema with allOf folded in; oneOf / anyOf take the first variant."""
    node = _resolve(node, schema)
    if not isinstance(node, dict):
        return {}
    if 'allOf' in node:
        merged = {key: value for key, value in node.items() if key != 'allOf'}
        properties = dict(merged.get('properties') or {})
        required = list(merged.get('required') or [])
        for part in node['allOf']:
            part = _merged(part, schema)
            properties.update(part.get('properties') or {})
            required.extend(part.get('required') or [])
            merged.setdefault('type', part.get('type'))
        merged['properties'] = properties
        merged['required'] = required
        return merged
    for key in ('oneOf', 'anyOf'):
        if node.get(key):
            return _merged(node[key][0], schema)
    return node


def _has_example(node: Any, schema: Dict, depth: int = 0) -> bool:
    """Whether the schema itself gives a value for the node (example, default, enum), at any depth."""
    node = _merged(node, schema)
    if not node or depth >= _MAX_DEPTH:
        return False
    if 'example' in node or 'default' in node or node.get('enum'):
        return True
    if node.get('type') == 'array':
        return _has_example(node.get('items') or {}, schema, depth + 1)
    return any(_has_example(prop, schema, depth + 1) for prop in (node.get('properties') or {}).values())


def _example(node: Any, schema: Dict, depth: int = 0) -> Any:
    """A sample value for a schema node: its own example first, then one made up from the type."""
    node = _merged(node, schema)
    if not node:
        return None
    for key in ('example', 'default'):
        if key in node:
            return node[key]
    if node.get('enum'):
        return node['enum'][0]

    kind = node.get('type') or ('object' if 'properties' in node else None)
    if kind == 'object':
        if depth >= _MAX_DEPTH:
            return {}
        return {name: _example(prop, schema, depth + 1) for name, prop in (node.get('properties') or {}).items()}
    if kind == 'array':
        if depth >= _MAX_DEPTH:
            return []
        return [_example(node.get('items') or {}, schema, depth + 1)]
    if kind == 'integer':
        return 1
    if kind == 'number':
        return 1.0
    if kind == 'boolean':
        return True
    by_format = {'email': '%random_email%', 'uuid': '%random_uuid%', 'date': '2000-01-01',
                 'date-time': '2000-01-01T00:00:00Z', 'uri': 'https://example.com', 'url': 'https://example.com'}
    return by_format.get(node.get('format'), 'string')


def _made_up_fields(node: Any, schema: Dict) -> List[str]:
    """Optional top-level fields of an object schema whose sample value is made up, not taken from the schema."""
    node = _merged(node, schema)
    required = node.get('required') or []
    return [name for name, prop in (node.get('properties') or {}).items()
            if name not in required and not _has_example(prop, schema)]


def _field_types(node: Any, schema: Dict) -> Dict[str, str]:
    """Top-level fields of an object schema with their types."""
    node = _merged(node, schema)
    fields = {}
    for name, prop in (node.get('properties') or {}).items():
        prop = _merged(prop, schema)
        fields[name] = prop.get('type') or ('object' if 'properties' in prop else 'any')
    return fields


def _describe_response(node: Any, schema: Dict) -> Dict[str, Any]:
    """What a success response looks like: an object, a list, a page of items ({"data": [...]}), or nothing."""
    node = _merged(node, schema)
    if not node:
        return {'kind': 'none', 'fields': {}}
    if node.get('type') == 'array':
        return {'kind': 'list', 'fields': _field_types(node.get('items') or {}, schema)}
    data = _merged((node.get('properties') or {}).get('data') or {}, schema)
    if data.get('type') == 'array':
        return {'kind': 'paginated', 'fields': _field_types(data.get('items') or {}, schema)}
    return {'kind': 'object', 'fields': _field_types(node, schema)}


def _json_schema_of(content_holder: Dict, schema: Dict) -> Any:
    """The body schema of an OpenAPI 3 requestBody / response ("content") or a Swagger 2 one ("schema")."""
    holder = _resolve(content_holder, schema) or {}
    if 'schema' in holder:  # Swagger 2
        return holder['schema']
    content = holder.get('content') or {}
    media = content.get('application/json') or next(iter(content.values()), {})
    return (media or {}).get('schema')


def _base_path(schema: Dict) -> str:
    """Path prefix shared by all endpoints: from the first server URL (OpenAPI 3) or basePath (Swagger 2)."""
    servers = schema.get('servers') or []
    if servers and isinstance(servers[0], dict):
        return urlparse(servers[0].get('url') or '').path.rstrip('/')
    return (schema.get('basePath') or '').rstrip('/')


def build_operations(schema: Dict) -> List[Dict[str, Any]]:
    """Every method + path of an OpenAPI 3 / Swagger 2 schema as a library record (not saved)."""
    if not isinstance(schema, dict) or not isinstance(schema.get('paths'), dict):
        return []

    base_path = _base_path(schema)
    global_auth = bool(schema.get('security'))
    operations = []

    for path, path_item in schema['paths'].items():
        path_item = _resolve(path_item, schema)
        if not isinstance(path_item, dict):
            continue
        shared_params = path_item.get('parameters') or []

        for method in HTTP_METHODS:
            op = path_item.get(method)
            if not isinstance(op, dict):
                continue

            path_params, query_params, header_params, form = [], [], [], {}
            body, content_type, made_up = None, None, []
            for param in shared_params + (op.get('parameters') or []):
                param = _resolve(param, schema)
                if not isinstance(param, dict) or not param.get('name'):
                    continue
                where = param.get('in')
                if where == 'body':  # Swagger 2
                    body, content_type = _example(param.get('schema') or {}, schema), 'application/json'
                    made_up = _made_up_fields(param.get('schema') or {}, schema)
                    continue
                example = param['example'] if 'example' in param else _example(param.get('schema') or param, schema)
                entry = {'name': param['name'], 'required': bool(param.get('required')), 'example': example,
                         'description': param.get('description') or ''}
                if where == 'path':
                    path_params.append(entry)
                elif where == 'query':
                    query_params.append(entry)
                elif where == 'header':
                    header_params.append(entry)
                elif where == 'formData':  # Swagger 2
                    form[param['name']] = example

            if op.get('requestBody'):  # OpenAPI 3
                body_schema = _json_schema_of(op['requestBody'], schema)
                if body_schema is not None:
                    body, content_type = _example(body_schema, schema), 'application/json'
                    made_up = _made_up_fields(body_schema, schema)
            if body is None and form:
                body, content_type = form, 'application/x-www-form-urlencoded'

            responses = op.get('responses') or {}
            success = sorted(int(code) for code in responses if str(code).isdigit() and 200 <= int(code) < 300)
            expected_status = success[0] if success else 200
            success_response = responses.get(str(expected_status)) or responses.get(expected_status) or {}

            security = op['security'] if 'security' in op else None
            tags = op.get('tags') or []
            segments = [part for part in path.split('/') if part and not part.startswith('{')]

            operations.append({
                'method': method.upper(),
                'path': f"{base_path}{path}",
                'name': str(op.get('operationId') or f"{method.upper()} {path}")[:255],
                'summary': (op.get('summary') or op.get('description') or '').strip(),
                'resource': str(tags[0] if tags else (segments[0] if segments else ''))[:255],
                'requires_auth': bool(security) if security is not None else global_auth,
                'expected_status': expected_status,
                'request': {'path_params': path_params, 'query_params': query_params,
                            'header_params': header_params, 'body': body, 'content_type': content_type,
                            # optional body fields with a made-up sample value
                            'made_up_fields': made_up},
                'response': _describe_response(_json_schema_of(success_response, schema), schema),
            })

    return operations


def step_request(operation: Dict[str, Any]) -> Dict[str, Any]:
    """
    The request of an operation in the form a step stores and ApiTestExecutor runs.

    The endpoint is relative: the executor sends it to the environment's API address. Path
    parameters become %name% variables, to be set by an earlier step or replaced by hand.
    """
    request = operation.get('request') or {}
    endpoint = re.sub(r'\{([^}]+)\}', r'%\1%', operation['path'])
    step = {'method': operation['method'], 'endpoint': endpoint}

    headers = {param['name']: str(param['example']) for param in request.get('header_params') or [] if param.get('required')}
    if operation.get('requires_auth'):
        headers['Authorization'] = 'Bearer %access_token%'
    if headers:
        step['headers'] = headers
    params = {param['name']: param['example'] for param in request.get('query_params') or [] if param.get('required')}
    if params:
        step['params'] = params
    if request.get('body') is not None:
        step['body'] = request['body']
    step['expected_status'] = operation.get('expected_status', 200)
    return step


def sync_operations(schema_id: int) -> int:
    """
    Rebuild the library of one uploaded schema. Calls that are still in the schema keep their ids,
    calls that are gone are removed. Returns the number of calls; 0 for a schema that cannot be
    parsed (a Postman collection, a custom format).
    """
    with get_db_connection_context() as conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT project_id, client_id, content FROM api_schemas WHERE id = %s", (schema_id,))
            row = cursor.fetchone()
            if not row:
                return 0
            project_id, client_id, content = row

            try:
                operations = build_operations(json.loads(content))
            except (json.JSONDecodeError, TypeError) as e:
                logger.warning(f"API schema {schema_id} is not JSON, no calls extracted: {e}")
                operations = []

            for op in operations:
                cursor.execute("""
                    INSERT INTO api_operations (schema_id, project_id, client_id, method, path, name, summary,
                                                resource, requires_auth, expected_status, request, response)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (schema_id, method, path) DO UPDATE SET
                        name = EXCLUDED.name, summary = EXCLUDED.summary, resource = EXCLUDED.resource,
                        requires_auth = EXCLUDED.requires_auth, expected_status = EXCLUDED.expected_status,
                        request = EXCLUDED.request, response = EXCLUDED.response, updated_at = CURRENT_TIMESTAMP
                """, (schema_id, str(project_id), str(client_id), op['method'], op['path'], op['name'], op['summary'],
                      op['resource'], op['requires_auth'], op['expected_status'],
                      json.dumps(op['request']), json.dumps(op['response'])))

            keep = [(op['method'], op['path']) for op in operations]
            cursor.execute("SELECT id, method, path FROM api_operations WHERE schema_id = %s", (schema_id,))
            stale = [row[0] for row in cursor.fetchall() if (row[1], row[2]) not in keep]
            if stale:
                cursor.execute("DELETE FROM api_operations WHERE id = ANY(%s)", (stale,))
            conn.commit()

    logger.info(f"API schema {schema_id}: {len(operations)} calls in the library")
    return len(operations)


def list_operations(project_id: str, client_id: str, schema_id: Optional[int] = None) -> List[Dict[str, Any]]:
    """The library of a project, ordered by resource and path. Each call carries its ready step request."""
    with get_db_connection_context() as conn:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT o.id, o.schema_id, s.name, o.method, o.path, o.name, o.summary, o.resource,
                       o.requires_auth, o.expected_status, o.request, o.response
                FROM api_operations o
                JOIN api_schemas s ON s.id = o.schema_id
                WHERE o.project_id = %s AND o.client_id = %s AND (%s::int IS NULL OR o.schema_id = %s)
                ORDER BY o.schema_id DESC, o.resource, o.path, o.method
            """, (project_id, client_id, schema_id, schema_id))
            rows = cursor.fetchall()

    operations = []
    for row in rows:
        operation = {
            'id': row[0], 'schema_id': row[1], 'schema_name': row[2], 'method': row[3], 'path': row[4],
            'name': row[5], 'summary': row[6], 'resource': row[7], 'requires_auth': row[8],
            'expected_status': row[9], 'request': row[10] or {}, 'response': row[11] or {},
        }
        operation['step_request'] = step_request(operation)
        operations.append(operation)
    return operations
