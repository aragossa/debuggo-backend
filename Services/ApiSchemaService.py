import json
import logging
from typing import Dict, Any, List, Optional
from Utils.AIHelper.AIHelper import AIHelper
from Utils.Connectors.db_utils import get_db_connection_context
from Utils.System import System


class ApiSchemaService:
    """
    Service for analyzing API schemas and generating test cases with steps.
    Supports OpenAPI, Swagger, Postman collections, and custom API schemas.
    """
    
    def __init__(self):
        self.logger = self._setup_logger()
        self.ai_helper = AIHelper()
        self.system = System()
    
    def _setup_logger(self):
        """Setup logger for API schema service."""
        logger = logging.getLogger('ApiSchemaService')
        logger.setLevel(logging.DEBUG)
        
        if not logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            )
            handler.setFormatter(formatter)
            logger.addHandler(handler)
        
        return logger
    
    def generate_test_steps_for_flow(
        self,
        test_case_id: int,
        schema_content: str,
        client_id: str,
        project_id: str
    ) -> bool:
        """
        Generate detailed API test steps for a test case flow using AI.
        
        Args:
            test_case_id: The test case ID to generate steps for
            schema_content: The API schema content (OpenAPI, Swagger, etc.)
            client_id: Client ID for access control
            project_id: Project ID for organization
            
        Returns:
            bool: True if steps were generated successfully
        """
        try:
            self.logger.info(f"Generating API test steps for test case {test_case_id}")
            
            # Get test case details
            with get_db_connection_context() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("""
                        SELECT name, description
                        FROM test_cases
                        WHERE id = %s AND client_id = %s
                    """, (test_case_id, client_id))
                    
                    test_case = cursor.fetchone()
                    if not test_case:
                        self.logger.error(f"Test case {test_case_id} not found")
                        return False
                    
                    test_case_name = test_case[0]
                    test_case_description = test_case[1]
            
            # Generate steps using AI
            prompt = self._create_step_generation_prompt(
                test_case_name,
                test_case_description,
                schema_content
            )
            
            # Use Gemini to generate steps
            response = self.ai_helper.send_request_to_gemini(
                prompt=prompt,
                text_content=schema_content
            )
            
            if not response:
                self.logger.error("Failed to get response from AI")
                return False
            
            # Parse and save steps
            steps = self._parse_ai_response(response)
            self.logger.info(f"📝 Parsed {len(steps)} steps from Gemini response")
            
            if steps:
                # DEBUG: Log step 2 headers
                if len(steps) >= 2:
                    step2_headers = steps[1].get('description', {}).get('headers', {})
                    self.logger.info(f"🔍 Step 2 headers from Gemini: {step2_headers}")
                
                # Validate and fix steps by executing them
                self.logger.info(f"🚀 Starting validation process...")
                validated_steps = self._validate_and_fix_steps(
                    steps, 
                    test_case_id,
                    schema_content,
                    test_case_name,
                    test_case_description
                )
                self.logger.info(f"✅ Validation process completed")
                
                self._save_test_steps(test_case_id, validated_steps)
                self._update_test_case_description(test_case_id, validated_steps, test_case_name)
                self.logger.info(f"Generated and validated {len(validated_steps)} steps for test case {test_case_id}")
                return True
            else:
                self.logger.error("No valid steps generated")
                return False
                
        except Exception as e:
            self.logger.error(f"Error generating test steps: {str(e)}", exc_info=True)
            return False
    
    def _extract_schema_summary(self, schema_content: str) -> str:
        """Extract relevant API endpoints and operations from schema."""
        try:
            import json
            schema = json.loads(schema_content)
            
            # Extract base path from servers or basePath
            base_path = ""
            if 'servers' in schema and len(schema['servers']) > 0:
                # OpenAPI 3.0 format
                server_url = schema['servers'][0].get('url', '')
                # Extract path portion from URL (e.g., http://example.com/api -> /api)
                if server_url:
                    from urllib.parse import urlparse
                    parsed = urlparse(server_url)
                    base_path = parsed.path.rstrip('/')
            elif 'basePath' in schema:
                # Swagger 2.0 format
                base_path = schema['basePath'].rstrip('/')
            
            # If no base path found, check if paths start with /api
            # If not, assume /api prefix is needed
            if not base_path and 'paths' in schema:
                first_path = next(iter(schema['paths'].keys()), '')
                if first_path and not first_path.startswith('/api'):
                    base_path = '/api'
            
            # Extract paths/endpoints
            if 'paths' in schema:
                summary = "Available API Endpoints:\n"
                if base_path:
                    summary += f"(Base path: {base_path})\n"
                summary += "\n"
                
                for path, methods in schema['paths'].items():
                    # Combine base path with endpoint path
                    full_path = f"{base_path}{path}" if base_path else path
                    summary += f"\n{full_path}:\n"
                    
                    for method, details in methods.items():
                        if method.upper() in ['GET', 'POST', 'PUT', 'DELETE', 'PATCH']:
                            summary += f"  {method.upper()}: "
                            
                            # Add summary/description
                            if 'summary' in details:
                                summary += details['summary']
                            elif 'description' in details:
                                summary += details['description'][:100]
                            
                            # Debug: Log what we're processing
                            self.logger.debug(f"Processing {method.upper()} {full_path}")
                            self.logger.debug(f"Has parameters: {'parameters' in details}")
                            self.logger.debug(f"Has requestBody: {'requestBody' in details}")
                            
                            # Check if authentication is required for this endpoint
                            requires_auth = False
                            auth_type = None
                            
                            # Check endpoint-level security
                            if 'security' in details:
                                requires_auth = len(details['security']) > 0
                                if requires_auth and details['security']:
                                    # Get the first security scheme name
                                    first_security = details['security'][0]
                                    if first_security:
                                        auth_type = list(first_security.keys())[0] if first_security else None
                            # Check global security if no endpoint-level security
                            elif 'security' in schema:
                                requires_auth = len(schema['security']) > 0
                                if requires_auth and schema['security']:
                                    first_security = schema['security'][0]
                                    if first_security:
                                        auth_type = list(first_security.keys())[0] if first_security else None
                            
                            # Add authentication requirement indicator
                            if requires_auth:
                                summary += " 🔒 [REQUIRES AUTHENTICATION]"
                                if auth_type:
                                    summary += f" ({auth_type})"
                            
                            # Add parameters info with details
                            if 'parameters' in details:
                                query_params = []
                                path_params = []
                                body_params = []
                                
                                self.logger.debug(f"Parameters for {method.upper()} {full_path}: {details['parameters']}")
                                
                                for param in details['parameters']:
                                    param_name = param.get('name', '')
                                    param_in = param.get('in', '')
                                    param_type = param.get('type', param.get('schema', {}).get('type', 'any'))
                                    param_required = param.get('required', False)
                                    
                                    self.logger.debug(f"  Param: {param_name}, in: {param_in}, type: {param_type}")
                                    
                                    if param_in == 'query':
                                        query_params.append(f"{param_name} ({param_type})")
                                    elif param_in == 'path':
                                        path_params.append(f"{param_name} ({param_type})")
                                    elif param_in == 'body':
                                        body_params.append(param)
                                
                                if query_params:
                                    summary += f"\n    Query Params: {', '.join(query_params)}"
                                if path_params:
                                    summary += f"\n    Path Params: {', '.join(path_params)}"
                                
                                # Handle body parameters (Swagger 2.0 style)
                                if body_params:
                                    for body_param in body_params:
                                        param_schema = body_param.get('schema', {})
                                        
                                        # Handle $ref if present
                                        if '$ref' in param_schema:
                                            ref_path = param_schema['$ref']
                                            self.logger.debug(f"Found body param schema reference: {ref_path}")
                                            # Try to resolve the reference
                                            if ref_path.startswith('#/'):
                                                ref_parts = ref_path[2:].split('/')
                                                resolved_schema = schema
                                                for part in ref_parts:
                                                    resolved_schema = resolved_schema.get(part, {})
                                                param_schema = resolved_schema
                                                self.logger.debug(f"Resolved body param schema: {param_schema}")
                                        
                                        properties = param_schema.get('properties', {})
                                        required_fields = param_schema.get('required', [])
                                        
                                        if properties:
                                            summary += "\n    Request Body:\n"
                                            for prop_name, prop_details in properties.items():
                                                prop_type = prop_details.get('type', 'any')
                                                is_required = prop_name in required_fields
                                                required_marker = " (required)" if is_required else " (optional)"
                                                prop_desc = prop_details.get('description', '')
                                                
                                                summary += f"      - {prop_name}: {prop_type}{required_marker}"
                                                if prop_desc:
                                                    summary += f" - {prop_desc[:50]}"
                                                summary += "\n"
                            
                            # Add request body info with detailed field structure (OpenAPI 3.0 style)
                            if 'requestBody' in details:
                                try:
                                    content = details['requestBody'].get('content', {})
                                    json_content = content.get('application/json', {})
                                    schema_ref = json_content.get('schema', {})
                                    
                                    # Handle $ref if present
                                    if '$ref' in schema_ref:
                                        ref_path = schema_ref['$ref']
                                        self.logger.debug(f"Found schema reference: {ref_path}")
                                        # Try to resolve the reference
                                        if ref_path.startswith('#/'):
                                            ref_parts = ref_path[2:].split('/')
                                            resolved_schema = schema
                                            for part in ref_parts:
                                                resolved_schema = resolved_schema.get(part, {})
                                            schema_ref = resolved_schema
                                            self.logger.debug(f"Resolved schema: {schema_ref}")
                                    
                                    # Extract required fields and properties
                                    required_fields = schema_ref.get('required', [])
                                    properties = schema_ref.get('properties', {})
                                    
                                    if properties:
                                        summary += "\n    Request Body:\n"
                                        for prop_name, prop_details in properties.items():
                                            prop_type = prop_details.get('type', 'any')
                                            is_required = prop_name in required_fields
                                            required_marker = " (required)" if is_required else " (optional)"
                                            prop_desc = prop_details.get('description', '')
                                            
                                            summary += f"      - {prop_name}: {prop_type}{required_marker}"
                                            if prop_desc:
                                                summary += f" - {prop_desc[:50]}"
                                            summary += "\n"
                                    else:
                                        summary += " [has request body]"
                                except Exception as e:
                                    summary += " [has request body]"
                            
                            # Add response schema info for variable extraction
                            if 'responses' in details:
                                try:
                                    success_response = details['responses'].get('200') or details['responses'].get('201')
                                    if success_response:
                                        response_content = success_response.get('content', {})
                                        json_response = response_content.get('application/json', {})
                                        response_schema = json_response.get('schema', {})
                                        response_props = response_schema.get('properties', {})
                                        
                                        if response_props:
                                            summary += "    Response Fields:\n"
                                            for resp_name, resp_details in list(response_props.items())[:10]:
                                                resp_type = resp_details.get('type', 'any')
                                                resp_desc = resp_details.get('description', '')
                                                summary += f"      - {resp_name}: {resp_type}"
                                                if resp_desc:
                                                    summary += f" - {resp_desc[:50]}"
                                                summary += "\n"
                                except Exception:
                                    pass
                            
                            summary += "\n"
                
                # Add authentication info if available
                if 'components' in schema and 'securitySchemes' in schema['components']:
                    summary += "\n\nAuthentication:\n"
                    for scheme_name, scheme_details in schema['components']['securitySchemes'].items():
                        summary += f"  - {scheme_name}: {scheme_details.get('type', 'unknown')}\n"
                
                return summary
            else:
                # If not OpenAPI format, return truncated content
                return schema_content[:3000]
                
        except json.JSONDecodeError:
            # Not valid JSON, return truncated content
            return schema_content[:3000]
        except Exception as e:
            self.logger.warning(f"Error extracting schema summary: {str(e)}")
            return schema_content[:3000]
    
    def _create_step_generation_prompt(
        self,
        test_case_name: str,
        test_case_description: str,
        schema_content: str
    ) -> str:
        """Create AI prompt for generating API test steps."""
        
        # Extract relevant parts from schema (paths and operations)
        schema_summary = self._extract_schema_summary(schema_content)
        
        return f"""
You are an expert API test automation engineer. Generate detailed test steps for the following API test case.

Test Case: {test_case_name}
Description: {test_case_description}

API Schema:
{schema_summary}

Generate a complete sequence of API test steps in JSON format. Each step should include:

1. Authentication step (if needed)
2. Main API operations
3. Validation steps

Return ONLY a JSON array of steps with this exact structure:
[
    {{
        "step_order": 1,
        "action": "api_request",
        "description": {{
            "method": "POST or GET or PUT or DELETE",
            "endpoint": "{{{{base_url}}}}/exact/path/from/schema",
            "headers": {{"Content-Type": "application/json", "Accept": "application/json"}},
            "body": {{"field1": "value1", "field2": "{{{{variable}}}}"}},
            "expected_status": 200,
            "extract_variables": {{"variable_name": "json.path.to.value"}}
        }},
        "summary": "Description of what this step does"
    }}
]

CRITICAL REQUIREMENTS - YOU MUST FOLLOW THESE EXACTLY:

1. **HTTP Methods**:
   - Use the EXACT HTTP method (GET/POST/PUT/PATCH/DELETE) specified in the API schema
   - Check the schema carefully - each endpoint shows its supported method(s)
   - Example: If schema shows "PUT /api/recipient-groups", use "PUT" not "POST"
   - DO NOT assume or change methods - use exactly what the schema specifies

2. **Endpoint Paths**: 
   - Use EXACT endpoint paths from the API schema above
   - Include the COMPLETE path with all prefixes (e.g., /api/auth, NOT /auth)
   - Prepend {{{{base_url}}}} to all endpoints
   - Example: "{{{{base_url}}}}/api/auth" NOT "{{{{base_url}}}}/auth"

3. **Request Body Fields**:
   - Use EXACT field names from the schema's "Request Body" section above
   - Look at the field names listed under "Request Body:" for each endpoint
   - Use the EXACT field names shown (e.g., if it shows "email: string (required)", use "email")
   - DO NOT use generic names like "username" or "login" unless they appear in the schema
   - DO NOT assume field names - ONLY use what's explicitly shown in the Request Body section
   - Map environment variables correctly: {{{{login}}}} should map to the email/username field shown in schema

4. **Variable Substitution**:
   - Use {{{{variable_name}}}} for variable substitution (double curly braces)
   - Available environment variables: {{{{base_url}}}}, {{{{login}}}}, {{{{password}}}}
   - Map {{{{login}}}} to the correct field (email, username, etc.) based on schema
   - Map {{{{password}}}} to the password field

5. **Headers - AUTHENTICATION IS CRITICAL**:
   - Always include "Content-Type": "application/json" for POST/PUT/PATCH requests
   - Always include "Accept": "application/json" for all requests
   - **IMPORTANT**: For endpoints marked with 🔒 [REQUIRES AUTHENTICATION], you MUST include:
     "Authorization": "Bearer {{{{access_token}}}}"
   - If an endpoint shows 🔒 [REQUIRES AUTHENTICATION], it will FAIL without the Authorization header
   - The access_token variable comes from the authentication step (login response)
   - Example for authenticated endpoint:
     "headers": {{
       "Content-Type": "application/json",
       "Accept": "application/json",
       "Authorization": "Bearer {{{{access_token}}}}"
     }}

6. **Response Handling & Variable Extraction - CRITICAL**:
   - The "description" field must be a valid JSON object (not a string)
   - **ALWAYS** include "extract_variables" when a response contains values needed in later steps
   - Common values to extract:
     * Authentication tokens (token, access_token, auth_token)
     * Resource IDs (id, user_id, client_id, group_id, etc.)
     * Any value that will be used in subsequent API calls
   - Use field names from "Response Fields:" section for variable extraction
   - Use JSONPath notation: "$.field" for top-level, "$.object.field" for nested
   - Examples:
     * Token: {{"access_token": "$.token"}}
     * ID: {{"user_id": "$.user.id"}} or {{"client_id": "$.client-id"}}
     * Nested: {{"group_id": "$.recipient-group.id"}}
   - If you create a resource (POST/PUT) and need its ID later, ALWAYS extract it
   - Use "expected_status" to validate response codes
     * GET requests: typically 200
     * POST/PUT create operations: 200 or 201 (both are valid)
     * DELETE requests: 200 or 204
     * Use 200 as default if unsure

7. **Authentication Flow - CRITICAL FOR SUCCESS**:
   - If the API requires authentication, the FIRST step MUST be authentication
   - **MANDATORY**: The authentication step MUST include "extract_variables" to capture the token
   - Look at the "Response Fields:" section of the auth endpoint to find the token field name
   - Common token field names: "token", "access_token", "accessToken", "auth_token"
   - Example authentication step structure:
     {{
       "step_order": 1,
       "action": "api_request",
       "description": {{
         "method": "POST",
         "endpoint": "{{{{base_url}}}}/api/auth",
         "headers": {{"Content-Type": "application/json", "Accept": "application/json"}},
         "body": {{"email": "{{{{login}}}}", "password": "{{{{password}}}}"}},
         "expected_status": 200,
         "extract_variables": {{"access_token": "$.token"}}  // REQUIRED! Extract token from response
       }},
       "summary": "Authenticate and obtain access token"
     }}
   - Without extract_variables, subsequent authenticated requests will FAIL

Generate practical, executable test steps that cover the main flow described in the test case.
"""
    
    def _update_test_case_description(self, test_case_id: int, steps: List[Dict[str, Any]], test_case_name: str):
        """Update test case description with summary of generated steps."""
        try:
            # Build description from steps
            description_parts = [f"Test Case: {test_case_name}\n"]
            description_parts.append(f"Total Steps: {len(steps)}\n\n")
            description_parts.append("Test Flow:\n")
            
            for i, step in enumerate(steps, 1):
                summary = step.get('summary', step.get('expected_result', 'API Request'))
                description_parts.append(f"{i}. {summary}\n")
            
            # Add endpoints covered
            endpoints = set()
            for step in steps:
                description_data = step.get('description', {})
                if isinstance(description_data, dict):
                    endpoint = description_data.get('endpoint', '')
                    if endpoint:
                        # Remove {{base_url}} prefix for cleaner display
                        endpoint = endpoint.replace('{{base_url}}', '').replace('{{{{base_url}}}}', '')
                        endpoints.add(endpoint)
            
            if endpoints:
                description_parts.append(f"\nEndpoints Covered:\n")
                for endpoint in sorted(endpoints):
                    description_parts.append(f"- {endpoint}\n")
            
            full_description = ''.join(description_parts)
            
            # Update database
            with get_db_connection_context() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("""
                        UPDATE test_cases
                        SET description = %s
                        WHERE id = %s
                    """, (full_description, test_case_id))
                    conn.commit()
            
            self.logger.info(f"Updated description for test case {test_case_id}")
            
        except Exception as e:
            self.logger.warning(f"Failed to update test case description: {str(e)}")
            # Don't fail the whole operation if description update fails
    
    def _parse_ai_response(self, response: Any) -> List[Dict[str, Any]]:
        """Parse AI response and extract test steps."""
        try:
            # Handle different response formats
            if isinstance(response, list):
                return response
            elif isinstance(response, dict):
                # Check if response has a 'steps' key
                if 'steps' in response:
                    return response['steps']
                # Otherwise treat the dict as a single step
                return [response]
            elif isinstance(response, str):
                # Try to parse as JSON
                # Remove markdown code blocks if present
                response = response.strip()
                if response.startswith('```'):
                    lines = response.split('\n')
                    response = '\n'.join(lines[1:-1])
                
                parsed = json.loads(response)
                if isinstance(parsed, list):
                    return parsed
                elif isinstance(parsed, dict) and 'steps' in parsed:
                    return parsed['steps']
                else:
                    return [parsed]
            else:
                self.logger.error(f"Unexpected response type: {type(response)}")
                return []
                
        except json.JSONDecodeError as e:
            self.logger.error(f"Failed to parse AI response as JSON: {str(e)}")
            self.logger.debug(f"Response content: {response}")
            return []
        except Exception as e:
            self.logger.error(f"Error parsing AI response: {str(e)}")
            return []
    
    def _save_test_steps(self, test_case_id: int, steps: List[Dict[str, Any]]):
        """Save generated test steps to database incrementally for real-time UI updates."""
        with get_db_connection_context() as conn:
            with conn.cursor() as cursor:
                # Delete existing steps for this test case
                cursor.execute("""
                    DELETE FROM test_steps WHERE test_case_id = %s
                """, (test_case_id,))
                conn.commit()
                
                # Insert steps one by one with immediate commits for real-time updates
                for i, step in enumerate(steps, 1):
                    step_order = step.get('step_order', i)
                    action = step.get('action', 'api_request')
                    
                    # Convert description dict to JSON string
                    description_data = step.get('description', {})
                    
                    if isinstance(description_data, dict):
                        description_json = json.dumps(description_data)
                    else:
                        description_json = str(description_data)
                    
                    summary = step.get('summary', '')
                    
                    cursor.execute("""
                        INSERT INTO test_steps (
                            test_case_id, step_order, action, description, expected_result
                        ) VALUES (%s, %s, %s, %s, %s)
                    """, (
                        test_case_id,
                        step_order,
                        action,
                        description_json,
                        summary
                    ))
                    
                    # Commit each step immediately so frontend can see it
                    conn.commit()
                    self.logger.info(f"Saved step {i}/{len(steps)} for test case {test_case_id}")
                
                self.logger.info(f"Completed saving {len(steps)} steps for test case {test_case_id}")
    
    def _validate_and_fix_steps(
        self, 
        steps: List[Dict[str, Any]], 
        test_case_id: int,
        schema_content: str,
        test_case_name: str,
        test_case_description: str
    ) -> List[Dict[str, Any]]:
        """Validate generated steps by executing them and fix if needed."""
        self.logger.info(f"🔍 Starting validation for test case {test_case_id} with {len(steps)} steps...")
        
        try:
            import requests
            import json
            
            self.logger.info(f"📋 Validation imports successful")
            
            # Get environment for test execution
            with get_db_connection_context() as conn:
                with conn.cursor() as cursor:
                    # Get test case details
                    cursor.execute("""
                        SELECT project_id FROM test_cases WHERE id = %s
                    """, (test_case_id,))
                    row = cursor.fetchone()
                    if not row:
                        self.logger.warning("Test case not found, skipping validation")
                        return steps
                    
                    project_id = row[0]
                    
                    # Get first environment for this project
                    cursor.execute("""
                        SELECT id, base_url, login, password, custom_variables
                        FROM environments
                        WHERE project_id = %s
                        LIMIT 1
                    """, (project_id,))
                    env_row = cursor.fetchone()
                    
                    if not env_row:
                        self.logger.warning("No environment found, skipping validation")
                        return steps
                    
                    environment_vars = {
                        'base_url': env_row[1],
                        'login': env_row[2],
                        'password': env_row[3],
                        'custom_variables': env_row[4] or {}
                    }
            
            # Execute steps and collect failures
            session_variables = {}
            failed_steps = []
            
            for i, step in enumerate(steps):
                try:
                    step_data = step.get('description', {})
                    if not isinstance(step_data, dict):
                        continue
                    
                    # Build request
                    method = step_data.get('method', 'GET').upper()
                    endpoint = step_data.get('endpoint', '')
                    headers = step_data.get('headers', {})
                    body = step_data.get('body')
                    expected_status = step_data.get('expected_status', 200)
                    
                    # Substitute variables in endpoint
                    endpoint = endpoint.replace('{{base_url}}', environment_vars['base_url'])
                    for var, val in session_variables.items():
                        endpoint = endpoint.replace(f'{{{{{var}}}}}', str(val))
                    
                    # Substitute variables in headers
                    headers_copy = {}
                    for key, value in headers.items():
                        header_value = str(value)
                        for var, val in session_variables.items():
                            header_value = header_value.replace(f'{{{{{var}}}}}', str(val))
                        headers_copy[key] = header_value
                    headers = headers_copy
                    
                    # Substitute variables in body
                    if body and isinstance(body, dict):
                        body_str = json.dumps(body)
                        for var, val in session_variables.items():
                            body_str = body_str.replace(f'{{{{{var}}}}}', str(val))
                        body = json.loads(body_str)
                    
                    # Execute request
                    self.logger.info(f"📡 Testing step {i+1}: {method} {endpoint}")
                    response = requests.request(
                        method=method,
                        url=endpoint,
                        headers=headers,
                        json=body,
                        timeout=10
                    )
                    
                    # Check if response matches expectation
                    if response.status_code != expected_status:
                        self.logger.warning(
                            f"❌ Step {i+1} failed: Expected {expected_status}, got {response.status_code}"
                        )
                        failed_steps.append({
                            'step_index': i,
                            'step': step,
                            'request': {
                                'method': method,
                                'url': endpoint,
                                'headers': headers,
                                'body': body
                            },
                            'response': {
                                'status': response.status_code,
                                'headers': dict(response.headers),
                                'body': response.text[:1000]
                            }
                        })
                    else:
                        self.logger.info(f"✅ Step {i+1} passed")
                        
                        # Extract variables for next steps
                        extract_vars = step_data.get('extract_variables', {})
                        if extract_vars and response.status_code < 400:
                            try:
                                response_data = response.json()
                                for var_name, path in extract_vars.items():
                                    if path.startswith('$.'):
                                        path = path[2:]
                                    keys = path.split('.')
                                    value = response_data
                                    for key in keys:
                                        value = value.get(key) if isinstance(value, dict) else None
                                        if value is None:
                                            break
                                    if value is not None:
                                        session_variables[var_name] = value
                            except:
                                pass
                
                except Exception as e:
                    self.logger.error(f"Error validating step {i+1}: {str(e)}")
            
            # If there are failures, ask Gemini to fix them
            if failed_steps:
                self.logger.info(f"🔧 Fixing {len(failed_steps)} failed steps...")
                fixed_steps = self._fix_failed_steps(
                    steps,
                    failed_steps,
                    schema_content,
                    test_case_name,
                    test_case_description
                )
                return fixed_steps
            
            self.logger.info("✅ All steps validated successfully")
            return steps
            
        except Exception as e:
            self.logger.error(f"❌ Error during validation: {str(e)}", exc_info=True)
            self.logger.warning(f"⚠️ Returning original steps without validation due to error")
            # Return original steps if validation fails
            return steps
    
    def _fix_failed_steps(
        self,
        original_steps: List[Dict[str, Any]],
        failed_steps: List[Dict[str, Any]],
        schema_content: str,
        test_case_name: str,
        test_case_description: str
    ) -> List[Dict[str, Any]]:
        """Ask Gemini to fix failed steps based on actual API responses."""
        try:
            # Build correction prompt
            failures_description = []
            for failure in failed_steps:
                step_num = failure['step_index'] + 1
                req = failure['request']
                resp = failure['response']
                
                failures_description.append(f"""
Step {step_num} FAILED:
Request:
  Method: {req['method']}
  URL: {req['url']}
  Headers: {json.dumps(req['headers'], indent=2)}
  Body: {json.dumps(req['body'], indent=2) if req['body'] else 'None'}

Actual Response:
  Status: {resp['status']}
  Body: {resp['body']}

Expected Status: {failure['step'].get('description', {}).get('expected_status', 200)}
""")
            
            correction_prompt = f"""
The following API test steps FAILED when executed against the real API.
Please analyze the actual responses and fix the steps to work correctly.

Test Case: {test_case_name}
Description: {test_case_description}

FAILURES:
{''.join(failures_description)}

Original Steps:
{json.dumps(original_steps, indent=2)}

API Schema:
{self._extract_schema_summary(schema_content)}

**CRITICAL RULES FOR CORRECTIONS**:
1. **PRESERVE HTTP METHODS**: Do NOT change HTTP methods (GET/POST/PUT/PATCH/DELETE) unless the API returns 405 Method Not Allowed
   - If you see 404 errors, the issue is likely the endpoint path, NOT the method
   - Always check the API schema for the correct method for each endpoint
   - Example: If schema shows "PUT /api/recipient-groups", use PUT, not POST

2. **PRESERVE AUTHORIZATION HEADERS**: Do NOT remove Authorization headers from steps
   - If a step has "Authorization": "Bearer {{access_token}}", keep it
   - Authorization headers are REQUIRED for authenticated endpoints
   - Only remove auth headers if API returns 401 Unauthorized

3. **Common issues to fix**:
   - Wrong field names in request body (check schema definitions)
   - Wrong expected status codes (update based on actual response)
     * 200 and 201 are both valid success codes for POST/PUT requests
     * Use the actual status code returned by the API
   - Wrong endpoint paths (verify against schema paths)
   - Missing required fields (add from schema)
   - Wrong variable extraction paths (fix JSONPath expressions)

4. **What NOT to change**:
   - HTTP methods (unless 405 error)
   - Authorization headers (unless 401 error)
   - Authentication flow structure
   - Variable names already extracted

Please return the COMPLETE corrected steps array in JSON format.
Return ONLY the JSON array of corrected steps, no explanation.
"""
            
            self.logger.info("🤖 Asking Gemini to fix failed steps...")
            response = self.ai_helper.send_request_to_gemini(
                prompt=correction_prompt,
                text_content=schema_content
            )
            
            if response:
                fixed_steps = self._parse_ai_response(response)
                if fixed_steps:
                    self.logger.info(f"✅ Gemini provided {len(fixed_steps)} corrected steps")
                    return fixed_steps
            
            self.logger.warning("Failed to get corrections from Gemini, using original steps")
            return original_steps
            
        except Exception as e:
            self.logger.error(f"Error fixing steps: {str(e)}")
            return original_steps
    
    def get_schema_by_id(self, schema_id: int, client_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve API schema by ID."""
        with get_db_connection_context() as conn:
            with conn.cursor() as cursor:
                cursor.execute("""
                    SELECT id, name, content, schema_type, project_id
                    FROM api_schemas
                    WHERE id = %s AND client_id = %s
                """, (schema_id, client_id))
                
                row = cursor.fetchone()
                if row:
                    return {
                        'id': row[0],
                        'name': row[1],
                        'content': row[2],
                        'schema_type': row[3],
                        'project_id': row[4]
                    }
                return None
