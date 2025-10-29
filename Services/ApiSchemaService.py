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
        logger.setLevel(logging.INFO)
        
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
        project_id: str,
        generation_context: str = "normal"
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
            
            # Delete all existing test steps before generating new ones
            self.logger.info(f"🗑️ Deleting all existing test steps for test case {test_case_id}")
            with get_db_connection_context() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("""
                        DELETE FROM test_steps 
                        WHERE test_case_id = %s
                    """, (test_case_id,))
                    deleted_count = cursor.rowcount
                    conn.commit()
                    self.logger.info(f"✅ Deleted {deleted_count} existing test steps")
            
            # Generate steps using AI
            prompt = self._create_step_generation_prompt(
                test_case_name,
                test_case_description,
                schema_content,
                generation_context
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
                                            summary += "\n    Request Body Fields:\n"
                                            for prop_name, prop_details in properties.items():
                                                prop_type = prop_details.get('type', 'any')
                                                is_required = prop_name in required_fields
                                                required_marker = " (required)" if is_required else " (optional)"
                                                prop_desc = prop_details.get('description', '')
                                                prop_format = prop_details.get('format', '')
                                                prop_enum = prop_details.get('enum', [])
                                                prop_example = prop_details.get('example', '')
                                                prop_min = prop_details.get('minLength') or prop_details.get('minimum')
                                                prop_max = prop_details.get('maxLength') or prop_details.get('maximum')
                                                
                                                summary += f"      - {prop_name}: {prop_type}{required_marker}"
                                                if prop_format:
                                                    summary += f" [format: {prop_format}]"
                                                if prop_enum:
                                                    summary += f" [enum: {', '.join(map(str, prop_enum[:5]))}]"
                                                if prop_example:
                                                    summary += f" [example: {prop_example}]"
                                                if prop_min is not None or prop_max is not None:
                                                    summary += f" [range: {prop_min or 'any'}-{prop_max or 'any'}]"
                                                if prop_desc:
                                                    summary += f" - {prop_desc[:80]}"
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
                                        summary += "\n    Request Body Fields:\n"
                                        for prop_name, prop_details in properties.items():
                                            prop_type = prop_details.get('type', 'any')
                                            is_required = prop_name in required_fields
                                            required_marker = " (required)" if is_required else " (optional)"
                                            prop_desc = prop_details.get('description', '')
                                            prop_format = prop_details.get('format', '')
                                            prop_enum = prop_details.get('enum', [])
                                            prop_example = prop_details.get('example', '')
                                            prop_min = prop_details.get('minLength') or prop_details.get('minimum')
                                            prop_max = prop_details.get('maxLength') or prop_details.get('maximum')
                                            
                                            summary += f"      - {prop_name}: {prop_type}{required_marker}"
                                            if prop_format:
                                                summary += f" [format: {prop_format}]"
                                            if prop_enum:
                                                summary += f" [enum: {', '.join(map(str, prop_enum[:5]))}]"
                                            if prop_example:
                                                summary += f" [example: {prop_example}]"
                                            if prop_min is not None or prop_max is not None:
                                                summary += f" [range: {prop_min or 'any'}-{prop_max or 'any'}]"
                                            if prop_desc:
                                                summary += f" - {prop_desc[:80]}"
                                            summary += "\n"
                                    else:
                                        summary += " [has request body]"
                                except Exception as e:
                                    summary += " [has request body]"
                            
                            # Add ALL possible response statuses and schemas
                            if 'responses' in details:
                                try:
                                    summary += "\n    Possible Responses:\n"
                                    for status_code, response_details in details['responses'].items():
                                        response_desc = response_details.get('description', '')
                                        summary += f"      {status_code}: {response_desc}\n"
                                        
                                        # Extract response schema if available
                                        response_content = response_details.get('content', {})
                                        json_response = response_content.get('application/json', {})
                                        response_schema = json_response.get('schema', {})
                                        
                                        # Handle $ref in response schema
                                        if '$ref' in response_schema:
                                            ref_path = response_schema['$ref']
                                            if ref_path.startswith('#/'):
                                                ref_parts = ref_path[2:].split('/')
                                                resolved_schema = schema
                                                for part in ref_parts:
                                                    resolved_schema = resolved_schema.get(part, {})
                                                response_schema = resolved_schema
                                        
                                        response_props = response_schema.get('properties', {})
                                        
                                        if response_props:
                                            summary += f"        Response Fields:\n"
                                            for resp_name, resp_details in response_props.items():
                                                resp_type = resp_details.get('type', 'any')
                                                resp_desc = resp_details.get('description', '')
                                                resp_format = resp_details.get('format', '')
                                                resp_example = resp_details.get('example', '')
                                                
                                                summary += f"          - {resp_name}: {resp_type}"
                                                if resp_format:
                                                    summary += f" [format: {resp_format}]"
                                                if resp_example:
                                                    summary += f" [example: {resp_example}]"
                                                if resp_desc:
                                                    summary += f" - {resp_desc[:60]}"
                                                summary += "\n"
                                except Exception as e:
                                    self.logger.debug(f"Error parsing responses: {str(e)}")
                            
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
        schema_content: str,
        generation_context: str = "normal"
    ) -> str:
        """Create AI prompt for generating API test steps."""
        
        # Extract relevant parts from schema (paths and operations)
        schema_summary = self._extract_schema_summary(schema_content)
        
        base_prompt = f"""
You are an expert API test automation engineer. Generate detailed test steps for the following API test case.

⚠️ ⚠️ ⚠️ CRITICAL WARNING - READ THIS FIRST ⚠️ ⚠️ ⚠️

THIS API DOES NOT FOLLOW STANDARD REST CONVENTIONS!
- Some endpoints use PUT for creating resources (not POST)
- Some endpoints use POST for updating resources (not PUT)
- You MUST use the EXACT HTTP method shown in the schema below
- DO NOT assume POST=create or PUT=update
- LOOK at the schema and use the method shown next to each endpoint

Example from this API:
- "/api/clients:" shows "PUT: Create a Client" → USE PUT, NOT POST
- If you see "POST: Update details" → USE POST, NOT PUT

⚠️ ⚠️ ⚠️ END CRITICAL WARNING ⚠️ ⚠️ ⚠️

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

1. **HTTP Methods - CRITICAL - READ CAREFULLY**:
   - Use the EXACT HTTP method (GET/POST/PUT/PATCH/DELETE) specified in the API schema
   - The schema shows the EXACT method for each endpoint - DO NOT ASSUME standard REST conventions
   - Example: If schema shows "PUT: Create a Client", use "PUT" not "POST" (even though POST is typical for create)
   - Example: If schema shows "POST: Update details", use "POST" not "PUT" (even though PUT is typical for update)
   - NEVER assume POST for create or PUT for update - ALWAYS use what the schema explicitly shows
   - Check the schema carefully - each endpoint shows its supported method(s) right after the path
   - Format in schema: "/api/endpoint:" followed by "GET:", "POST:", "PUT:", "PATCH:", or "DELETE:"
   - DO NOT change methods based on REST conventions - use exactly what the schema specifies

2. **Endpoint Paths**: 
   - Use EXACT endpoint paths from the API schema above
   - Include the COMPLETE path with all prefixes (e.g., /api/auth, NOT /auth)
   - Prepend {{{{base_url}}}} to all endpoints
   - Example: "{{{{base_url}}}}/api/auth" NOT "{{{{base_url}}}}/auth"

3. **Request Body Fields - CRITICAL FOR ACCURACY**:
   - Use EXACT field names from the schema's "Request Body Fields:" section above
   - The schema shows EXACT field names with their types, formats, and examples
   - Example: If schema shows "email: string (required) [format: email]", use "email" NOT "login" or "username"
   - Example: If schema shows "username: string (required)", use "username" NOT "email" or "login"
   - Pay attention to [format: ...] hints (email, date-time, uuid, etc.)
   - Pay attention to [example: ...] values for correct data format
   - Pay attention to [enum: ...] for allowed values
   - DO NOT assume or invent field names - ONLY use what's explicitly shown
   - Map environment variables to the correct schema field:
     * If schema has "email" field → use "email": "{{{{login}}}}"
     * If schema has "username" field → use "username": "{{{{login}}}}"
     * If schema has "login" field → use "login": "{{{{login}}}}"

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

6. **Response Status Codes - USE SCHEMA VALUES**:
   - The schema shows "Possible Responses:" section with ALL status codes for each endpoint
   - Use the EXACT status code from the schema for "expected_status"
   - Example: If schema shows "200: Successful response", use "expected_status": 200
   - Example: If schema shows "201: Resource created", use "expected_status": 201
   - Example: If schema shows "204: No content", use "expected_status": 204
   - DO NOT guess status codes - use what the schema specifies
   - For success scenarios, use the success status code shown (200, 201, 204, etc.)
   - For error scenarios, use the error status code shown (400, 401, 403, 404, 422, 500, etc.)

7. **Response Fields & Variable Extraction - CRITICAL**:
   - The "description" field must be a valid JSON object (not a string)
   - **ALWAYS** include "extract_variables" when a response contains values needed in later steps
   - Look at "Response Fields:" under each status code in "Possible Responses:" section
   - Use EXACT field names from the response schema
   - Pay attention to [format: ...] and [example: ...] hints for response fields
   - Common values to extract:
     * Authentication tokens (token, access_token, auth_token)
     * Resource IDs (id, user_id, client_id, group_id, etc.)
     * Any value that will be used in subsequent API calls
   - Use JSONPath notation: "$.field" for top-level, "$.object.field" for nested
   - Examples:
     * Token: {{"access_token": "$.token"}}
     * ID: {{"user_id": "$.user.id"}} or {{"client_id": "$.client-id"}}
     * Nested: {{"group_id": "$.recipient-group.id"}}
   - If you create a resource (POST/PUT) and need its ID later, ALWAYS extract it

8. **Authentication Flow - CRITICAL FOR SUCCESS**:
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

{self._get_context_specific_instructions(generation_context, test_case_name, additional_context)}
"""
        
        return base_prompt
    
    def _get_context_specific_instructions(self, generation_context: str, test_case_name: str, additional_context: str = None) -> str:
        """Generate context-specific instructions for different generation scenarios"""
        if generation_context == "precondition":
            base_precondition = f"""
🔧 **PRECONDITION GENERATION MODE** 🔧

This is a PRECONDITION test case - you are generating setup steps that create data/entities needed for the main UI test.

**⚠️ CRITICAL: READ THE TEST CASE DESCRIPTION CAREFULLY ⚠️**

The test case description above specifies EXACTLY what should be created in preconditions vs main test:

MAIN TEST CASE: {test_case_name}
FULL DESCRIPTION: Look at the "Description:" section above

**PARSE THE DESCRIPTION TO UNDERSTAND**:
- **preconditions:** section = what YOU should create (API setup)  
- **test case:** section = what the UI test will do (not your responsibility)
- **tear down:** section = what cleanup will do (not your responsibility)

**EXAMPLE PARSING**:
If description says "preconditions: create a new client via API. test case: create recipient group"
→ YOU create: CLIENT (via API)
→ UI test creates: RECIPIENT GROUP (via UI)

**🚨 CRITICAL RULES FOR PRECONDITIONS 🚨**:

1. **🚫 NEVER CREATE THE MAIN ENTITY**: 
   - If test case name contains "create recipient group" → DO NOT create recipient group in precondition
   - If test case name contains "create user" → DO NOT create user in precondition
   - If test case name contains "create campaign" → DO NOT create campaign in precondition
   - ONLY create DEPENDENCIES that the main entity needs

2. **READ THE DESCRIPTION CAREFULLY**:
   - Look for "preconditions:" section → This tells you EXACTLY what to create
   - Look for "test case:" section → This is what the UI test will do (NOT YOU!)
   - If preconditions says "create client" → Create ONLY client, nothing else

3. **EXTRACT ALL IDs**: Every create operation MUST extract the created resource ID
   - Example: Create client → extract client_id  
   - Example: Create user → extract user_id

**❌ ABSOLUTELY FORBIDDEN PATTERNS ❌**:
```
Test case name: "create recipient group"
Step 1: Authenticate ✅
Step 2: Create client ✅
Step 3: Create recipient group ❌ WRONG! This is the main action!
```

**✅ CORRECT PATTERN ✅**:
```
Test case name: "create recipient group"
Step 1: Authenticate ✅
Step 2: Create client ✅ (dependency for recipient group)
Step 3: STOP HERE! ✅ (UI test will create the recipient group)
```

**REMEMBER**: Preconditions = Setup dependencies ONLY. Main business action = UI test responsibility!

3. **Use Variable Names That Make Sense**: Extract variables with descriptive names:
   - "user_id", "client_id", "project_id", "organization_id", etc.
   - NOT generic names like "id" or "resource_id"

4. **Authentication First**: Always start with authentication to get proper permissions for creating resources

5. **Keep It Minimal**: Only create what's explicitly mentioned in the preconditions section - don't over-engineer
"""
            
            if additional_context:
                base_precondition = f"""
{base_precondition}

**SPECIFIC CONTEXT FOR THIS PRECONDITION**:
{additional_context}
"""
                return base_precondition
            
            return base_precondition

        elif generation_context == "teardown":
            base_teardown = f"""
🧹 **TEARDOWN GENERATION MODE** 🧹

This is a TEARDOWN test case - you are generating cleanup steps that remove data/entities created during testing.

**⚠️ CRITICAL: READ THE TEST CASE DESCRIPTION CAREFULLY ⚠️**

The test case description above specifies EXACTLY what entities are involved:

MAIN TEST CASE: {test_case_name}  
FULL DESCRIPTION: Look at the "Description:" section above

**PARSE THE DESCRIPTION TO UNDERSTAND WHAT TO DELETE**:
- **preconditions:** section = entities created by API preconditions (need cleanup)
- **test case:** section = entities created by UI test (need cleanup)  
- **tear down:** section = lists what YOU should delete

**EXAMPLE PARSING**:
If description says "preconditions: create a new client via API. test case: create recipient group. tear down: remove created client; remove recipient group"
→ YOU delete: CLIENT (created by precondition) AND RECIPIENT GROUP (created by UI test)

**🚨 CRITICAL RULES FOR TEARDOWN 🚨**:

1. **🚫 ABSOLUTELY NO CREATION OPERATIONS**: 
   - Generate ONLY DELETE operations
   - If you generate ANY PUT or POST operations, you are doing it COMPLETELY WRONG
   - Teardown = Cleanup ONLY, never create anything

2. **DELETE WHAT WAS ALREADY CREATED**:
   - Precondition created: client (has %client_id% variable)
   - Main UI test created: recipient group (has %recipient_group_id% variable)
   - YOU delete: Both of these using their variables

3. **USE VARIABLES FROM PREVIOUS STEPS**:
   - %client_id% - Created by precondition
   - %recipient_group_id% - Created by main UI test
   - %user_id% - Created by precondition (if applicable)
   - These variables are ALREADY AVAILABLE from previous execution

4. **DELETE IN REVERSE ORDER**:
   - Delete child entities first (recipient group)
   - Then delete parent entities (client)
   - This respects foreign key dependencies

**❌ ABSOLUTELY FORBIDDEN PATTERNS ❌**:
```
Step 1: Authenticate ✅
Step 2: Create client ❌ WRONG! Don't create anything!
Step 3: Create recipient group ❌ WRONG! Don't create anything!
Step 4: Delete recipient group ❌ Why create it if you're deleting it?
```

**✅ CORRECT PATTERN ✅**:
```
Step 1: Authenticate ✅
Step 2: Delete recipient group using %recipient_group_id% ✅ (created by UI test)
Step 3: Delete client using %client_id% ✅ (created by precondition)
Step 4: DONE! ✅
```

**REMEMBER**: Teardown = Delete what was created. NEVER create new entities in teardown!

5. **Use Dynamic Variables, NOT hardcoded IDs**: 
   - ✅ GOOD: "endpoint": "%base_url%/api/clients/%client_id%"
   - ❌ BAD: "endpoint": "%base_url%/api/clients/105"

6. **Authentication**: Start with authentication to ensure permissions for deletion

7. **Expected Status Codes for DELETE operations**:
   - 200: Successful deletion (with response body)
   - 204: Successful deletion (no content)  
   - 404: Already deleted (acceptable)

**REMEMBER**: Teardown should ONLY delete what was created, never create new things!
"""
            
            if additional_context:
                base_teardown += f"\n\n**SPECIFIC CONTEXT FOR THIS TEARDOWN**:\n{additional_context}\n"
            
            return base_teardown

        else:  # normal context
            return """
📋 **STANDARD API TEST GENERATION** 📋

Generate a complete API test flow that covers the main functionality described in the test case.
Focus on the primary user journey and include proper authentication, main operations, and validation.
"""
    
    def _update_test_case_description(self, test_case_id: int, steps: List[Dict[str, Any]], test_case_name: str):
        """Update test case description with summary of generated steps."""
        try:
            # Check if description already contains structured context (from CombinedTestGenerationService)
            with get_db_connection_context() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("SELECT description FROM test_cases WHERE id = %s", (test_case_id,))
                    result = cursor.fetchone()
                    if result and result[0]:
                        existing_desc = result[0]
                        # If description contains structured context markers, preserve it and append step summary
                        if "STRUCTURED TEST DESCRIPTION:" in existing_desc or "preconditions:" in existing_desc:
                            self.logger.info(f"Preserving structured context for test case {test_case_id}")
                            # Just append step summary without overwriting structured context
                            step_summary = f"\n\n=== GENERATED STEPS ({len(steps)} total) ===\n"
                            for i, step in enumerate(steps, 1):
                                summary = step.get('summary', step.get('expected_result', 'API Request'))
                                step_summary += f"{i}. {summary}\n"
                            
                            cursor.execute("""
                                UPDATE test_cases
                                SET description = %s
                                WHERE id = %s
                            """, (existing_desc + step_summary, test_case_id))
                            conn.commit()
                            return
            
            # Build description from steps (for cases without structured context)
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

⚠️ ⚠️ ⚠️ CRITICAL WARNING - READ THIS FIRST ⚠️ ⚠️ ⚠️

THIS API DOES NOT FOLLOW STANDARD REST CONVENTIONS!
- Some endpoints use PUT for creating resources (not POST)
- Some endpoints use POST for updating resources (not PUT)
- If you see a 404 error, check if you're using the WRONG HTTP METHOD
- Example: "POST /api/clients" returns 404 because it should be "PUT /api/clients"
- ALWAYS check the schema below for the correct method

⚠️ ⚠️ ⚠️ END CRITICAL WARNING ⚠️ ⚠️ ⚠️

Test Case: {test_case_name}
Description: {test_case_description}

FAILURES:
{''.join(failures_description)}

Original Steps:
{json.dumps(original_steps, indent=2)}

API Schema:
{self._extract_schema_summary(schema_content)}

**CRITICAL RULES FOR CORRECTIONS**:
1. **CHECK HTTP METHODS AGAINST SCHEMA**: 
   - If you see 404 errors, check BOTH the endpoint path AND the HTTP method against the schema
   - The schema shows EXACT methods for each endpoint - DO NOT ASSUME standard REST conventions
   - If the schema shows "PUT: Create a Client" but the step uses POST, change it to PUT
   - If the schema shows "POST: Update details" but the step uses PUT, change it to POST
   - 404 errors can be caused by WRONG METHOD or WRONG PATH - check the schema carefully
   - Only preserve the method if it EXACTLY matches what the schema shows for that endpoint
   - Example: If schema shows "PUT /api/clients" but step uses "POST /api/clients", change to PUT

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
   - Authorization headers (unless 401 error indicates they're wrong)
   - Authentication flow structure
   - Variable names already extracted
   - Endpoint paths (unless schema shows different path)

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
    
    def generate_test_steps_iteratively(
        self,
        test_case_id: int,
        schema_content: str,
        client_id: str,
        project_id: str,
        environment_id: int = None,
        generation_context: str = "normal",
        additional_context: str = None
    ) -> bool:
        """
        Generate API test steps iteratively - one step at a time with real execution feedback.
        
        New flow:
        1. Generate first step (authentication if needed)
        2. Execute the step
        3. Collect request/response
        4. Send to Gemini to generate expected result + next step
        5. Repeat until test flow is complete
        
        Args:
            test_case_id: The test case ID to generate steps for
            schema_content: The API schema content
            client_id: Client ID for access control
            project_id: Project ID for organization
            environment_id: Environment ID for API configuration
            generation_context: Context for generation - "normal", "precondition", or "teardown"
            
        Returns:
            bool: True if steps were generated successfully
        """
        try:
            from Services.ApiTestExecutor import ApiTestExecutor
            
            self.logger.info(f"🔄 Starting iterative step generation for test case {test_case_id}")
            
            # Get test case details and user_id
            with get_db_connection_context() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("""
                        SELECT tc.name, tc.description
                        FROM test_cases tc
                        WHERE tc.id = %s AND tc.client_id = %s
                    """, (test_case_id, client_id))
                    
                    test_case = cursor.fetchone()
                    if not test_case:
                        self.logger.error(f"Test case {test_case_id} not found")
                        return False
                    
                    test_case_name = test_case[0]
                    test_case_description = test_case[1]
                    
                    # Get a user_id from this client (for conflict notifications)
                    cursor.execute("""
                        SELECT id FROM users 
                        WHERE client_id = %s 
                        ORDER BY id ASC 
                        LIMIT 1
                    """, (client_id,))
                    
                    user_row = cursor.fetchone()
                    user_id = user_row[0] if user_row else None
                    
                    if not user_id:
                        self.logger.warning(f"No user found for client {client_id}, conflict notifications will be disabled")
                        user_id = 1  # Fallback to admin user
            
            # Extract schema summary
            schema_summary = self._extract_schema_summary(schema_content)
            
            # Check if we're resuming from an approved conflict
            conflict_resolution = self._check_conflict_resolution(test_case_id)
            resuming_from_conflict = False
            
            # Only delete existing steps if this is a NEW generation, not a resume
            if not conflict_resolution or conflict_resolution['status'] != 'approved':
                self.logger.info(f"🗑️ Deleting all existing test steps for test case {test_case_id}")
                with get_db_connection_context() as conn:
                    with conn.cursor() as cursor:
                        cursor.execute("""
                            DELETE FROM test_steps 
                            WHERE test_case_id = %s
                        """, (test_case_id,))
                        deleted_count = cursor.rowcount
                        conn.commit()
                        self.logger.info(f"✅ Deleted {deleted_count} existing test steps")
            else:
                self.logger.info(f"♻️ Resuming from conflict - keeping existing steps")
            
            # Initialize variables for iteration
            step_order = 1
            generated_steps = []
            execution_history = []
            extracted_variables = {}  # Track variables extracted from responses
            max_steps = 20  # Safety limit
            first_step = None
            
            if conflict_resolution and conflict_resolution['status'] == 'approved':
                # Resume from saved state
                self.logger.info(f"✅ Resuming generation from approved conflict resolution...")
                saved_state = conflict_resolution['generation_state']
                if saved_state:
                    execution_history = saved_state.get('execution_history', [])
                    extracted_variables = saved_state.get('extracted_variables', {})
                    step_order = saved_state.get('step_order', 1)
                    
                    # IMPORTANT: Increment step_order to move to NEXT step after conflict
                    step_order += 1
                    
                    resuming_from_conflict = True
                    self.logger.info(f"📍 Resuming from step {step_order} (conflict resolved on step {step_order - 1}) with {len(execution_history)} previous steps")
                    
                    # CRITICAL: Save the conflicted step(s) to database now that conflict is resolved
                    self.logger.info(f"🔍 Checking {len(execution_history)} history items for conflicts...")
                    for hist_item in execution_history:
                        self.logger.info(f"🔍 History item: step_order={hist_item.get('step_order')}, has_conflict={hist_item.get('conflict', False)}")
                        if hist_item.get('conflict'):
                            # This step had a conflict that's now resolved - save it to database
                            conflicted_step = hist_item['step']
                            conflicted_step['step_order'] = hist_item['step_order']
                            
                            # CRITICAL: Apply the corrected expected status from user's approval
                            if 'corrected_expected_status' in conflict_resolution:
                                old_status = conflicted_step.get('description', {}).get('expected_status', 'unknown')
                                new_status = conflict_resolution['corrected_expected_status']
                                self.logger.info(f"🔧 Applying correction: expected_status {old_status} → {new_status}")
                                if 'description' not in conflicted_step:
                                    conflicted_step['description'] = {}
                                conflicted_step['description']['expected_status'] = new_status
                            
                            # Apply corrected expected response if available
                            if 'corrected_expected_response' in conflict_resolution and conflict_resolution['corrected_expected_response']:
                                self.logger.info(f"🔧 Applying corrected expected response")
                                conflicted_step['description']['expected_response'] = conflict_resolution['corrected_expected_response']
                            
                            self.logger.info(f"💾 Saving conflicted step {hist_item['step_order']} to database...")
                            self._save_single_step(test_case_id, conflicted_step, client_id)
                            generated_steps.append(conflicted_step)
                            self.logger.info(f"✅ Saved previously conflicted step {hist_item['step_order']} to database")
                    
                    # Update test case description immediately so steps appear in UI
                    if generated_steps:
                        self.logger.info(f"📝 Updating test case description with {len(generated_steps)} steps after conflict resolution")
                        self._update_test_case_description(test_case_id, generated_steps, test_case_name)
                    
                    # Mark notification as processed
                    with get_db_connection_context() as conn:
                        cursor = conn.cursor()
                        cursor.execute(
                            "UPDATE api_conflict_notifications SET status = 'processed' WHERE id = %s",
                            (conflict_resolution['notification_id'],)
                        )
                        conn.commit()
            
            # Generate first step only if not resuming
            if not resuming_from_conflict:
                self.logger.info("📝 Generating first step...")
                first_step = self._generate_first_step(
                    test_case_name,
                    test_case_description,
                    schema_summary,
                    generation_context,
                    additional_context
                )
                
                if not first_step:
                    self.logger.error("Failed to generate first step")
                    return False
            
            # Iterative generation loop
            max_retries_per_step = 3
            retry_count = 0
            
            while step_order <= max_steps:
                # Check if there's a pending conflict resolution
                conflict_resolution = self._check_conflict_resolution(test_case_id)
                if conflict_resolution:
                    if conflict_resolution['status'] == 'waiting':
                        self.logger.info(f"⏸️ Test generation paused - waiting for user to resolve conflict notification {conflict_resolution['notification_id']}")
                        return "paused"  # Pause generation, don't clear Redis flag
                    elif conflict_resolution['status'] == 'approved':
                        # Resume from saved state
                        self.logger.info(f"✅ User approved conflict resolution, resuming generation...")
                        saved_state = conflict_resolution['generation_state']
                        if saved_state:
                            execution_history = saved_state.get('execution_history', execution_history)
                            extracted_variables = saved_state.get('extracted_variables', extracted_variables)
                            step_order = saved_state.get('step_order', step_order)
                            # NOTE: step_order already incremented in pre-loop check, don't increment again!
                            self.logger.info(f"📍 Continuing from step {step_order} after conflict resolution")
                        # Save any conflicted steps from history that weren't saved yet
                        for hist_item in execution_history:
                            if hist_item.get('conflict') and hist_item['step_order'] not in [s.get('step_order') for s in generated_steps]:
                                conflicted_step = hist_item['step']
                                conflicted_step['step_order'] = hist_item['step_order']
                                
                                # Apply corrections from conflict resolution
                                if 'corrected_expected_status' in conflict_resolution:
                                    if 'description' not in conflicted_step:
                                        conflicted_step['description'] = {}
                                    conflicted_step['description']['expected_status'] = conflict_resolution['corrected_expected_status']
                                
                                if 'corrected_expected_response' in conflict_resolution and conflict_resolution['corrected_expected_response']:
                                    conflicted_step['description']['expected_response'] = conflict_resolution['corrected_expected_response']
                                
                                self.logger.info(f"💾 Saving in-loop conflicted step {hist_item['step_order']}...")
                                self._save_single_step(test_case_id, conflicted_step, client_id)
                                generated_steps.append(conflicted_step)
                        
                        # Update description if we saved steps
                        if generated_steps:
                            self.logger.info(f"📝 Updating test case description with {len(generated_steps)} steps (in-loop)")
                            self._update_test_case_description(test_case_id, generated_steps, test_case_name)
                        
                        # Mark notification as processed
                        with get_db_connection_context() as conn:
                            cursor = conn.cursor()
                            cursor.execute(
                                "UPDATE api_conflict_notifications SET status = 'processed' WHERE id = %s",
                                (conflict_resolution['notification_id'],)
                            )
                            conn.commit()
                
                self.logger.info(f"🔄 Processing step {step_order}... (retry: {retry_count}/{max_retries_per_step})")
                
                # Determine current step
                if step_order == 1 and first_step:
                    # Use first step only if we have it (not resuming)
                    current_step = first_step
                else:
                    # Generate next step based on previous execution
                    current_step = self._generate_next_step(
                        test_case_name,
                        test_case_description,
                        schema_summary,
                        execution_history,
                        extracted_variables
                    )
                    
                    if not current_step:
                        self.logger.info(f"✅ Test flow complete after {step_order - 1} steps")
                        break
                
                # Execute the step FIRST (before saving) to get corrected extraction paths
                self.logger.info(f"▶️ Executing step {step_order}...")
                execution_result = self._execute_step_for_feedback(
                    test_case_id,
                    current_step,
                    project_id,
                    client_id,
                    extracted_variables,
                    environment_id
                )
                
                if not execution_result:
                    self.logger.error(f"Failed to execute step {step_order}")
                    break
                
                # Check if execution resulted in an error (4xx/5xx status)
                if execution_result.get('error'):
                    self.logger.warning(f"⚠️ Step {step_order} returned error status: {execution_result['response']['status']}")
                    self.logger.warning(f"Error message: {execution_result.get('error_message')}")
                    
                    # Check for documentation conflict BEFORE retrying
                    if retry_count == 0:  # Only check on first error
                        conflict_details = self._detect_documentation_conflict(
                            test_case_id,
                            current_step,
                            execution_result,
                            schema_content
                        )
                        
                        if conflict_details:
                            # IMPORTANT: Add current step to execution history BEFORE saving state
                            # so AI has context when resuming
                            execution_history.append({
                                'step_order': step_order,
                                'step': current_step,
                                'request': execution_result['request'],
                                'response': execution_result['response'],
                                'conflict': True  # Mark this step had a conflict
                            })
                            
                            # Create notification and pause generation
                            generation_state = {
                                'execution_history': execution_history,
                                'extracted_variables': extracted_variables,
                                'step_order': step_order,
                                'current_step': current_step
                            }
                            
                            notification_id = self._create_conflict_notification(
                                test_case_id,
                                client_id,
                                user_id,
                                step_order,
                                current_step,
                                execution_result,
                                conflict_details,
                                generation_state
                            )
                            
                            if notification_id:
                                self.logger.info(f"🚨 Test generation PAUSED - conflict notification {notification_id} created")
                                self.logger.info(f"⏸️ Waiting for user decision to continue...")
                                return "paused"  # Pause generation, don't clear Redis flag
                    
                    # Check retry limit
                    if retry_count >= max_retries_per_step:
                        self.logger.error(f"❌ Max retries ({max_retries_per_step}) reached for step {step_order}, moving to next step")
                        # Save the failed step anyway so user can see what was attempted
                        current_step['step_order'] = step_order
                        self._save_single_step(test_case_id, current_step, client_id)
                        generated_steps.append(current_step)
                        # Reset retry counter and move to next step
                        retry_count = 0
                        step_order += 1
                        continue
                    
                    # Increment retry counter
                    retry_count += 1
                    
                    # Add error result to history so Gemini can see it
                    execution_history.append({
                        'step_order': step_order,
                        'step': current_step,
                        'request': execution_result['request'],
                        'response': execution_result['response'],
                        'error': True
                    })
                    
                    # Ask Gemini to retry with a corrected request
                    self.logger.info(f"🔄 Asking Gemini to fix the error and retry (attempt {retry_count}/{max_retries_per_step})...")
                    retry_step = self._generate_next_step(
                        test_case_name,
                        test_case_description,
                        schema_summary,
                        execution_history,
                        extracted_variables
                    )
                    
                    if retry_step:
                        # Use the retry step instead
                        current_step = retry_step
                        self.logger.info(f"✅ Gemini generated corrected step, retrying...")
                        # Continue to execute the corrected step (don't increment step_order yet)
                        continue
                    else:
                        self.logger.error(f"❌ Gemini couldn't generate a fix, stopping generation")
                        break
                
                # Update step with corrected extraction paths (if any)
                if 'corrected_extract_variables' in execution_result:
                    corrected_paths = execution_result['corrected_extract_variables']
                    if 'description' in current_step and 'extract_variables' in current_step['description']:
                        current_step['description']['extract_variables'] = corrected_paths
                        self.logger.info(f"🔧 Updated step with corrected extraction paths: {corrected_paths}")
                
                # NOW save step to database with corrected paths (only if successful)
                current_step['step_order'] = step_order
                self._save_single_step(test_case_id, current_step, client_id)
                generated_steps.append(current_step)
                
                # Extract variables from response if specified
                if 'extracted_vars' in execution_result:
                    extracted_variables.update(execution_result['extracted_vars'])
                    self.logger.info(f"📦 Extracted variables: {list(execution_result['extracted_vars'].keys())}")
                
                # Add to execution history
                execution_history.append({
                    'step_order': step_order,
                    'step': current_step,
                    'request': execution_result['request'],
                    'response': execution_result['response']
                })
                
                self.logger.info(f"✅ Step {step_order} executed: {execution_result['response']['status']}")
                
                # Reset retry counter on success
                retry_count = 0
                
                # Check if this should be the last step
                if self._is_test_flow_complete(execution_history, test_case_description):
                    self.logger.info(f"✅ Test flow complete after {step_order} steps")
                    break
                
                step_order += 1
            
            # Update test case description with summary (final update)
            if generated_steps:
                self.logger.info(f"📝 Final update: test case description with {len(generated_steps)} total steps")
                self._update_test_case_description(test_case_id, generated_steps, test_case_name)
            else:
                self.logger.warning(f"⚠️ No steps generated to update description")
            
            self.logger.info(f"✅ Iterative generation complete: {len(generated_steps)} steps generated")
            return True
            
        except Exception as e:
            self.logger.error(f"❌ Error in iterative generation: {str(e)}", exc_info=True)
            return False
    
    def _generate_first_step(self, test_case_name: str, test_case_description: str, schema_summary: str, generation_context: str = "normal", additional_context: str = None) -> dict:
        """Generate the first step (usually authentication if required)."""
        
        example_json = '''{
    "action": "api_request",
    "description": {
        "method": "POST or GET or PUT or DELETE",
        "endpoint": "%base_url%/exact/path/from/schema",
        "headers": {"Content-Type": "application/json", "Accept": "application/json"},
        "body": {"email": "%login%", "password": "%password%"},
        "expected_status": 200,
        "extract_variables": {"auth_token": "$.token"}
    },
    "summary": "What this step does"
}'''
        
        prompt = f"""
⚠️ ⚠️ ⚠️ CRITICAL WARNING - READ THIS FIRST ⚠️ ⚠️ ⚠️

THIS API DOES NOT FOLLOW STANDARD REST CONVENTIONS!
- Some endpoints use PUT for creating resources (not POST)
- Some endpoints use POST for updating resources (not PUT)
- You MUST use the EXACT HTTP method shown in the schema below
- DO NOT assume POST=create or PUT=update

⚠️ ⚠️ ⚠️ END CRITICAL WARNING ⚠️ ⚠️ ⚠️

You are generating API test steps ONE AT A TIME with real execution feedback.

Test Case: {test_case_name}
Description: {test_case_description}

API Schema:
{schema_summary}

Generate ONLY THE FIRST STEP for this test case.

Rules:
1. If the API requires authentication (look for 🔒 [REQUIRES AUTHENTICATION] markers), the first step MUST be authentication
2. If no authentication is needed, generate the first main operation step
3. Use EXACT HTTP methods from the schema (check carefully - PUT vs POST)
4. Use EXACT field names from "Request Body Fields:" section
5. **CRITICAL - EXTRACT VARIABLES BASED ON EXPECTED RESPONSE STRUCTURE**:
   - Look at the schema to understand the response structure
   - If response will be {{"client": {{"id": 49}}}}, use "$.client.id"
   - If response will be {{"token": "abc"}}, use "$.token"
   - If response will be {{"data": {{"user": {{"id": 1}}}}}}, use "$.data.user.id"
   - ALWAYS match the actual nested structure from the API response
6. **CRITICAL**: NEVER use hardcoded values - use variables:
   - Authentication: use %login% and %password%, NOT "user@example.com"
   - IDs will be extracted in next steps, NOT hardcoded

Available variables:
- %base_url% - API base URL
- %login% - Username/email from environment
- %password% - Password from environment

EXAMPLES FOR VARIABLE EXTRACTION:
Expected response: {{"client": {{"id": 49, "name": "Test"}}}}
✅ CORRECT: "extract_variables": {{"client_id": "$.client.id"}}
❌ WRONG: "extract_variables": {{"client_id": "$.id"}}

Expected response: {{"token": "eyJ0eXAi..."}}
✅ CORRECT: "extract_variables": {{"auth_token": "$.token"}}

{self._get_context_specific_instructions(generation_context, test_case_name, additional_context)}

Return ONLY a single JSON object (not an array) with this structure:
{example_json}

Return ONLY the JSON object, no explanation.
"""
        
        response = self.ai_helper.send_request_to_gemini(
            prompt=prompt,
            text_content=schema_summary
        )
        
        if not response:
            return None
        
        # Parse response
        step = self._parse_single_step_response(response)
        return step
    
    def _generate_next_step(
        self,
        test_case_name: str,
        test_case_description: str,
        schema_summary: str,
        execution_history: list,
        extracted_variables: dict = None
    ) -> dict:
        """Generate the next step based on previous execution results."""
        
        # Build execution history summary (completely outside f-string to avoid format issues)
        history_parts = []
        for i, exec_result in enumerate(execution_history, 1):
            req = exec_result['request']
            resp = exec_result['response']
            
            # Build history text using string concatenation, not f-strings
            part = "\nStep " + str(i) + ":\n"
            part += "  Request:\n"
            part += "    Method: " + str(req['method']) + "\n"
            part += "    URL: " + str(req['url']) + "\n"
            part += "    Headers: " + json.dumps(req['headers'], indent=4) + "\n"
            part += "    Body: " + (json.dumps(req['body'], indent=4) if req['body'] else 'None') + "\n"
            part += "  \n"
            part += "  Response:\n"
            part += "    Status: " + str(resp['status']) + "\n"
            part += "    Headers: " + json.dumps(resp['headers'], indent=4) + "\n"
            part += "    Body: " + (json.dumps(resp['body'], indent=4) if resp['body'] else 'None') + "\n"
            
            # Mark if this step had an error
            if exec_result.get('error'):
                part += "  ⚠️ ERROR: This request failed! " + exec_result.get('error_message', '') + "\n"
                part += "  ⚠️ You MUST fix this request before continuing!\n"
            
            history_parts.append(part)
        
        history_text = ''.join(history_parts)
        
        # Build list of available variables
        available_vars = ["- %base_url% - API base URL", "- %login% - Username/email from environment", "- %password% - Password from environment"]
        if extracted_variables:
            for var_name in extracted_variables.keys():
                available_vars.append(f"- %{var_name}% - Extracted from previous step")
        available_vars_text = '\n'.join(available_vars)
        
        # Build prompt with string concatenation to avoid f-string format issues
        prompt = """
⚠️ ⚠️ ⚠️ CRITICAL WARNING ⚠️ ⚠️ ⚠️
THIS API DOES NOT FOLLOW STANDARD REST CONVENTIONS!
- Check the schema for EXACT HTTP methods (PUT vs POST)
- "/api/clients:" shows "PUT: Create a Client" → USE PUT, NOT POST
⚠️ ⚠️ ⚠️ END WARNING ⚠️ ⚠️ ⚠️

You are generating API test steps ONE AT A TIME with real execution feedback.

Test Case: """ + test_case_name + """
Description: """ + test_case_description + """

API Schema:
""" + schema_summary + """

EXECUTION HISTORY (steps already executed):
""" + history_text + """

Based on the execution history above, generate the NEXT STEP to continue the test flow.

⚠️ **IF THE LAST STEP FAILED (marked with ERROR above)**:
- DO NOT continue to the next step
- ANALYZE the error response to understand what went wrong
- GENERATE A CORRECTED VERSION of the failed request
- Common errors:
  - 500 "Name should contain only alphabetic characters" → Remove spaces/special chars from name field
  - 400 "Missing required field" → Add the missing field to request body
  - 401 "Unauthorized" → Check authentication token is included
  - 404 "Not found" → Check the URL path and ID are correct

Available variables (use these EXACT variable names in your step):
""" + available_vars_text + """

IMPORTANT: Use the EXACT variable names listed above (e.g., %auth_token%, NOT %token%)

Rules:
1. **IF LAST STEP FAILED**: Fix the error and retry the same operation (don't move to next step)
2. Use variables extracted from previous steps (e.g., %auth_token%, %client_id%)
3. Use EXACT HTTP methods from the schema
4. Use EXACT field names from "Request Body Fields:" section
5. If the test flow is complete, return {"complete": true} instead of a step
6. **CRITICAL - EXTRACT VARIABLES FROM ACTUAL RESPONSE STRUCTURE**:
   - Look at the "Response Body" in execution history to see the EXACT JSON structure
   - If response is {"client": {"id": 49}}, use "$.client.id" NOT "$.id"
   - If response is {"token": "abc"}, use "$.token"
   - If response is {"data": {"user": {"id": 1}}}, use "$.data.user.id"
   - ALWAYS match the actual nested structure from the response body
6. **CRITICAL - NO HARDCODED IDs**: 
   - ❌ WRONG: "/api/clients/42" or {"client_id": 123}
   - ✅ CORRECT: "/api/clients/%client_id%" or {"client_id": "%client_id%"}
   - ALWAYS use variables from previous steps, NEVER hardcode IDs or values
   - Check execution history to see what variables are available

Return ONLY a single JSON object in this EXACT format:

If more steps needed:
{
  "action": "api_request",
  "description": {
    "method": "PUT or POST or GET or DELETE",
    "endpoint": "%base_url%/exact/path/%client_id%",
    "headers": {"Content-Type": "application/json", "Authorization": "Bearer %auth_token%"},
    "body": {"field": "value", "id": "%client_id%"},
    "extract_variables": {"variable_name": "$.actual.path.from.response.body"}
  },
  "summary": "What this step does"
}

EXAMPLES FOR VARIABLE EXTRACTION:
Response: {"client": {"id": 49, "name": "Test"}}
✅ CORRECT: "extract_variables": {"client_id": "$.client.id"}
❌ WRONG: "extract_variables": {"client_id": "$.id"}

Response: {"token": "eyJ0eXAi..."}
✅ CORRECT: "extract_variables": {"auth_token": "$.token"}

Response: {"data": {"user": {"id": 123}}}
✅ CORRECT: "extract_variables": {"user_id": "$.data.user.id"}

EXAMPLES FOR VARIABLE USAGE:
✅ CORRECT: "endpoint": "%base_url%/api/clients/%client_id%"
❌ WRONG: "endpoint": "%base_url%/api/clients/42"
✅ CORRECT: "body": {"client_id": "%client_id%"}
❌ WRONG: "body": {"client_id": 42}

If test complete:
{"complete": true}

No explanation, just JSON.
"""
        
        response = self.ai_helper.send_request_to_gemini(
            prompt=prompt,
            text_content=schema_summary
        )
        
        if not response:
            return None
        
        # Parse response
        step = self._parse_single_step_response(response)
        
        # Check if test is complete
        if isinstance(step, dict) and step.get('complete'):
            return None
        
        return step
    
    def _parse_single_step_response(self, response) -> dict:
        """Parse a single step from Gemini response."""
        try:
            # AIHelper already returns parsed dict, not string
            if isinstance(response, dict):
                return response
            
            # If it's a string, parse it
            if isinstance(response, str):
                response = response.strip()
                if response.startswith('```'):
                    lines = response.split('\n')
                    response = '\n'.join(lines[1:-1])
                
                step = json.loads(response)
                return step
            
            self.logger.error(f"Unexpected response type: {type(response)}")
            return None
            
        except Exception as e:
            self.logger.error(f"Error parsing step response: {str(e)}")
            self.logger.debug(f"Response was: {response}")
            return None
    
    def _execute_step_for_feedback(
        self,
        test_case_id: int,
        step: dict,
        project_id: str,
        client_id: str,
        extracted_variables: dict = None,
        environment_id: int = None
    ) -> dict:
        """Execute a step and return request/response for feedback to Gemini."""
        import requests
        
        try:
            # Get environment variables
            with get_db_connection_context() as conn:
                with conn.cursor() as cursor:
                    # Use specific environment if provided, otherwise get first one
                    if environment_id:
                        cursor.execute("""
                            SELECT base_url, login, password, custom_variables
                            FROM environments
                            WHERE id = %s AND project_id = %s
                        """, (environment_id, project_id))
                    else:
                        cursor.execute("""
                            SELECT base_url, login, password, custom_variables
                            FROM environments
                            WHERE project_id = %s
                            LIMIT 1
                        """, (project_id,))
                    
                    env = cursor.fetchone()
                    if not env:
                        env_msg = f"environment ID {environment_id}" if environment_id else "any environment"
                        self.logger.error(f"No {env_msg} found for project {project_id}")
                        return None
                    
                    base_url = env[0]
                    login = env[1]
                    password = env[2]
                    custom_vars = env[3] or {}
            
            # Build variable context
            variables = {
                'base_url': base_url,
                'login': login,
                'password': password,
                **custom_vars
            }
            
            # Merge previously extracted variables
            if extracted_variables:
                variables.update(extracted_variables)
            
            # Prepare request - handle multiple formats
            # Format 1: {"action": "api_request", "description": {...}}
            # Format 2: {"step": {"request": {...}}}
            # Format 3: {"api_request": {"method": "PUT", "url": "...", ...}}
            # Format 4: {"step": "name", "method": "PUT", "url": "...", ...} (flat structure)
            if 'method' in step and 'url' in step:
                # Format 4 - flat structure (newest)
                method = step.get('method', 'GET')
                endpoint = step.get('url', '')
                headers = step.get('headers', {})
                body = step.get('body')
            elif 'api_request' in step:
                # Format 3
                request_data = step['api_request']
                method = request_data.get('method', 'GET')
                endpoint = request_data.get('url', '')
                headers = request_data.get('headers', {})
                body = request_data.get('body')
            elif 'step' in step and 'request' in step['step']:
                # Format 2
                request_data = step['step']['request']
                method = request_data.get('method', 'GET')
                endpoint = request_data.get('url', '')
                headers = request_data.get('headers', {})
                body = request_data.get('body')
            else:
                # Format 1 - old format
                description = step.get('description', {})
                method = description.get('method', 'GET')
                endpoint = description.get('endpoint', '')
                headers = description.get('headers', {})
                body = description.get('body')
            
            # Substitute variables in endpoint
            for var_name, var_value in variables.items():
                endpoint = endpoint.replace(f'%{var_name}%', str(var_value))
            
            # Substitute variables in headers
            headers_str = json.dumps(headers)
            for var_name, var_value in variables.items():
                headers_str = headers_str.replace(f'%{var_name}%', str(var_value))
            headers = json.loads(headers_str)
            
            # Substitute variables in body
            if body:
                body_str = json.dumps(body)
                for var_name, var_value in variables.items():
                    body_str = body_str.replace(f'%{var_name}%', str(var_value))
                body = json.loads(body_str)
            
            # Execute request
            self.logger.info(f"🌐 Executing: {method} {endpoint}")
            if body:
                self.logger.debug(f"Request body: {json.dumps(body, indent=2)}")
            
            # Disable SSL warnings for testing
            import urllib3
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
            
            response = requests.request(
                method=method,
                url=endpoint,
                headers=headers,
                json=body,
                timeout=30,
                verify=False  # For testing
            )
            
            self.logger.info(f"📥 Response: {response.status_code}")
            
            # Parse response body
            try:
                response_body = response.json() if response.text else None
            except:
                response_body = response.text
            
            # Check if response status is 4xx or 5xx - need to validate if it's expected
            expected_status = step.get('description', {}).get('expected_status', 200)
            if response.status_code >= 400:
                self.logger.warning(f"⚠️ Received error status {response.status_code}")
                self.logger.info(f"Response body: {response_body}")
                
                # Ask Gemini if this error is expected for this test case
                is_expected = self._validate_error_response(
                    test_case_id,
                    step,
                    response.status_code,
                    response_body
                )
                
                if not is_expected:
                    # Unexpected error - need to fix the request
                    self.logger.error(f"❌ Error status {response.status_code} is NOT expected for this test case")
                    return {
                        'request': {
                            'method': method,
                            'url': endpoint,
                            'headers': headers,
                            'body': body
                        },
                        'response': {
                            'status': response.status_code,
                            'headers': dict(response.headers),
                            'body': response_body
                        },
                        'error': True,
                        'error_message': f"Unexpected error status {response.status_code}"
                    }
                else:
                    # Expected error (negative testing) - this is success!
                    self.logger.info(f"✅ Error status {response.status_code} is EXPECTED for this test case (negative testing)")
                    # Continue to save this as a successful step
            
            # Extract variables if specified in step
            new_extracted_vars = {}
            # Handle multiple formats
            if 'extract' in step:
                extract_spec = step['extract']
                if isinstance(extract_spec, list):
                    # Format 3: {"extract": [{"name": "client_id", "from": "body", "path": "id"}]}
                    extract_variables = {}
                    for item in extract_spec:
                        var_name = item.get('name')
                        path = item.get('path', '')
                        if var_name and path:
                            extract_variables[var_name] = f'$.{path}'
                elif isinstance(extract_spec, dict):
                    # Format 4: {"extract": {"client_id": "id"}} - convert to JSONPath
                    extract_variables = {}
                    for var_name, path in extract_spec.items():
                        if not path.startswith('$.'):
                            extract_variables[var_name] = f'$.{path}'
                        else:
                            extract_variables[var_name] = path
                else:
                    extract_variables = extract_spec
            elif 'step' in step and 'extract' in step['step']:
                # Format 2
                extract_variables = step['step']['extract']
            else:
                # Format 1
                extract_variables = step.get('description', {}).get('extract_variables', {})
            
            if extract_variables and isinstance(response_body, dict):
                for var_name, json_path in extract_variables.items():
                    try:
                        # Simple JSONPath extraction ($.field or $.nested.field)
                        if json_path.startswith('$.'):
                            path_parts = json_path[2:].split('.')
                            value = response_body
                            for part in path_parts:
                                if isinstance(value, dict):
                                    value = value.get(part)
                                else:
                                    value = None
                                    break
                            
                            if value is not None:
                                new_extracted_vars[var_name] = value
                                self.logger.info(f"✓ Extracted {var_name} = {value}")
                            else:
                                # AUTO-CORRECTION: If extraction failed, try to find the value intelligently
                                self.logger.warning(f"⚠️ Path {json_path} failed, attempting auto-correction...")
                                corrected_value, corrected_path = self._find_value_in_response(
                                    response_body, 
                                    path_parts[-1],  # Last part of path (e.g., "id" from "$.id")
                                    var_name
                                )
                                if corrected_value is not None:
                                    new_extracted_vars[var_name] = corrected_value
                                    # Update the extract_variables with corrected path for database storage
                                    extract_variables[var_name] = corrected_path
                                    self.logger.info(f"✅ AUTO-CORRECTED: {var_name} = {corrected_value} (path: {corrected_path})")
                                else:
                                    self.logger.error(f"❌ Could not find value for {var_name} in response")
                    except Exception as e:
                        self.logger.warning(f"Failed to extract {var_name}: {str(e)}")
            
            # Return execution result
            result = {
                'request': {
                    'method': method,
                    'url': endpoint,
                    'headers': headers,
                    'body': body
                },
                'response': {
                    'status': response.status_code,
                    'headers': dict(response.headers),
                    'body': response_body
                }
            }
            
            if new_extracted_vars:
                result['extracted_vars'] = new_extracted_vars
            
            # Return corrected extraction paths (if any were auto-corrected)
            if extract_variables:
                result['corrected_extract_variables'] = extract_variables
            
            return result
            
        except Exception as e:
            self.logger.error(f"Error executing step: {str(e)}", exc_info=True)
            return None
    
    def _save_single_step(self, test_case_id: int, step: dict, client_id: str):
        """Save a single step to the database."""
        try:
            with get_db_connection_context() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("""
                        INSERT INTO test_steps (
                            test_case_id, step_order, action, description,
                            expected_result
                        ) VALUES (%s, %s, %s, %s, %s)
                    """, (
                        test_case_id,
                        step['step_order'],
                        step.get('action', 'api_request'),
                        json.dumps(step.get('description', {})),
                        step.get('summary', '')
                    ))
                conn.commit()
                
        except Exception as e:
            self.logger.error(f"Error saving step: {str(e)}")
    
    def _validate_error_response(self, test_case_id: int, step: dict, status_code: int, response_body) -> bool:
        """
        Ask Gemini if an error response (4xx/5xx) is expected for this test case.
        
        Args:
            test_case_id: The test case ID
            step: The current step being executed
            status_code: The HTTP status code received
            response_body: The response body
            
        Returns:
            bool: True if error is expected (negative testing), False if unexpected
        """
        try:
            # Get test case details from database
            with get_db_connection_context() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT name, description 
                    FROM test_cases 
                    WHERE id = %s
                """, (test_case_id,))
                result = cursor.fetchone()
                
                if not result:
                    self.logger.warning(f"Could not find test case {test_case_id}, assuming error is unexpected")
                    return False
                
                test_case_name = result[0]
                test_case_description = result[1] or ""
            
            # Build prompt for Gemini
            prompt = f"""You are analyzing an API test execution to determine if an error response is expected.

TEST CASE INFORMATION:
Name: {test_case_name}
Description: {test_case_description}

CURRENT STEP:
Summary: {step.get('summary', 'N/A')}
Request Method: {step.get('description', {}).get('method', 'N/A')}
Request Endpoint: {step.get('description', {}).get('endpoint', 'N/A')}
Request Body: {json.dumps(step.get('description', {}).get('body', {}), indent=2)}

ACTUAL RESPONSE:
Status Code: {status_code}
Response Body: {json.dumps(response_body, indent=2) if isinstance(response_body, dict) else str(response_body)}

QUESTION:
Based on the test case name and description, is this error response EXPECTED?

Consider:
- Negative testing scenarios (testing invalid inputs, unauthorized access, etc.)
- Test case names containing: "invalid", "unauthorized", "error", "fail", "negative", "wrong"
- Test descriptions mentioning expected errors or validation

Answer with a single JSON object:
{{
  "is_expected": true/false,
  "reason": "Brief explanation why this error is/isn't expected",
  "expected_status": <the status code that should be expected for this step>
}}

Return ONLY the JSON object, no explanation."""

            # Call Gemini
            response = self.ai_helper.send_request_to_gemini(
                prompt=prompt,
                image=None,
                text_content=None
            )
            
            if not response:
                self.logger.warning("Gemini did not respond, assuming error is unexpected")
                return False
            
            # Parse response
            try:
                # AIHelper already returns parsed dict, check if it's already a dict
                if isinstance(response, dict):
                    validation_result = response
                else:
                    # If it's a string, try to extract JSON from response
                    import re
                    json_match = re.search(r'\{.*\}', response, re.DOTALL)
                    if json_match:
                        validation_result = json.loads(json_match.group())
                    else:
                        self.logger.warning("Could not parse Gemini response, assuming error is unexpected")
                        return False
                
                is_expected = validation_result.get('is_expected', False)
                reason = validation_result.get('reason', 'No reason provided')
                expected_status = validation_result.get('expected_status', 200)
                
                self.logger.info(f"🤖 Gemini validation: is_expected={is_expected}, reason={reason}")
                
                # Update step with expected status if error is expected
                if is_expected and 'description' in step:
                    step['description']['expected_status'] = expected_status
                
                return is_expected
                    
            except Exception as e:
                self.logger.warning(f"Error parsing Gemini validation response: {str(e)}")
                return False
                
        except Exception as e:
            self.logger.error(f"Error validating error response: {str(e)}")
            return False
    
    def _find_value_in_response(self, response_body: dict, field_name: str, var_name: str, current_path: str = "$") -> tuple:
        """
        Intelligently search for a field in the response body and return (value, corrected_path).
        
        This handles cases where Gemini generates wrong paths like:
        - Generated: $.id but actual structure is $.client.id
        - Generated: $.token but actual structure is $.data.token
        
        Args:
            response_body: The API response dictionary
            field_name: The field to search for (e.g., "id", "token")
            var_name: The variable name being extracted (e.g., "client_id", "auth_token")
            current_path: Current JSONPath being built (default: "$")
            
        Returns:
            tuple: (value, corrected_path) or (None, None) if not found
        """
        # Strategy 1: Look for exact field name match at current level
        if field_name in response_body:
            value = response_body[field_name]
            corrected_path = f"{current_path}.{field_name}"
            self.logger.debug(f"Found {field_name} at {corrected_path}")
            return (value, corrected_path)
        
        # Strategy 2: Look for field in nested objects
        # Common patterns: {client: {id: X}}, {data: {user: {id: X}}}, etc.
        for key, value in response_body.items():
            if isinstance(value, dict):
                # Recursively search nested objects
                found_value, found_path = self._find_value_in_response(
                    value, 
                    field_name, 
                    var_name, 
                    f"{current_path}.{key}"
                )
                if found_value is not None:
                    return (found_value, found_path)
        
        # Strategy 3: Smart matching based on variable name
        # If looking for "client_id", prioritize paths containing "client"
        # If looking for "user_id", prioritize paths containing "user"
        if '_' in var_name:
            prefix = var_name.split('_')[0]  # e.g., "client" from "client_id"
            if prefix in response_body and isinstance(response_body[prefix], dict):
                if field_name in response_body[prefix]:
                    value = response_body[prefix][field_name]
                    corrected_path = f"{current_path}.{prefix}.{field_name}"
                    self.logger.debug(f"Smart match: {var_name} → {corrected_path}")
                    return (value, corrected_path)
        
        return (None, None)
    
    def _is_test_flow_complete(self, execution_history: list, test_case_description: str) -> bool:
        """Determine if the test flow is complete based on execution history."""
        # Simple heuristic: if last step was a DELETE or verification GET, might be complete
        if not execution_history:
            return False
        
        last_step = execution_history[-1]
        last_method = last_step['request']['method']
        last_status = last_step['response']['status']
        
        # If it's a DELETE with 200/204, likely cleanup step (last step)
        if last_method == 'DELETE' and last_status in [200, 204]:
            return True
        
        # If we have 5+ steps, might be complete
        if len(execution_history) >= 5:
            return True
        
        return False
    
    def _detect_documentation_conflict(
        self,
        test_case_id: int,
        step: dict,
        execution_result: dict,
        schema_content: str
    ) -> Optional[dict]:
        """
        Detect conflicts between API documentation and actual API behavior.
        Uses Gemini to analyze if the request was correct according to documentation
        but the response doesn't match expectations.
        
        Returns conflict details if detected, None otherwise.
        """
        try:
            actual_status = execution_result['response']['status']
            actual_response = execution_result['response']['body']
            request_details = execution_result['request']
            
            # Only check for conflicts on error statuses (4xx/5xx)
            if actual_status < 400:
                return None
            
            # Ask Gemini to analyze if this is a documentation conflict
            prompt = f"""You are analyzing an API test execution to detect conflicts between API documentation and actual behavior.

**API Documentation (relevant excerpt):**
{schema_content[:3000]}

**Test Step Request:**
- Method: {request_details['method']}
- Endpoint: {request_details['url']}
- Headers: {json.dumps(request_details.get('headers', {}), indent=2)}
- Body: {json.dumps(request_details.get('body', {}), indent=2)}

**Actual Response:**
- Status Code: {actual_status}
- Response Body: {json.dumps(actual_response, indent=2)}

**Analysis Required:**
1. Is the request correctly formed according to the API documentation?
2. What status code and response does the documentation specify for this scenario?
3. Does the actual response match the documentation?
4. If there's a mismatch, is this a documentation conflict (doc says one thing, API does another)?

**IMPORTANT:** Only report a conflict if:
- The request is correct according to documentation
- The documentation explicitly specifies a different status code or response format
- This is NOT just a test case expecting an error (like testing invalid credentials)

Return a JSON object:
{{
  "is_conflict": true/false,
  "conflict_type": "status_mismatch" | "schema_mismatch" | "none",
  "documented_status": <single integer status code from documentation, e.g. 400 or 401, NOT "400 or 401">,
  "documented_response": <expected response structure from docs>,
  "conflict_description": "Detailed explanation of the conflict",
  "suggested_resolution": "What should be the corrected expected result",
  "corrected_expected_status": <single integer - the status that should be expected based on reality>,
  "corrected_expected_response": <the response structure that should be expected>
}}

IMPORTANT: documented_status and corrected_expected_status must be single integers (e.g., 400), not strings or ranges.

Return ONLY the JSON object."""

            response = self.ai_helper.send_request_to_gemini(
                prompt=prompt,
                image=None,
                text_content=None
            )
            
            if not response:
                return None
            
            # Response is already a dict from AIHelper
            conflict_data = response
            
            if conflict_data.get('is_conflict', False):
                self.logger.warning(f"🚨 DOCUMENTATION CONFLICT DETECTED: {conflict_data.get('conflict_description')}")
                
                # Parse documented_status - handle cases where Gemini returns strings like "400 or 401"
                documented_status = conflict_data.get('documented_status')
                if isinstance(documented_status, str):
                    # Extract first number from string like "400 or 401"
                    import re
                    match = re.search(r'\d+', documented_status)
                    documented_status = int(match.group()) if match else None
                elif documented_status is not None:
                    documented_status = int(documented_status)
                
                return {
                    'conflict_type': conflict_data.get('conflict_type', 'status_mismatch'),
                    'documented_status': documented_status,
                    'documented_response': conflict_data.get('documented_response'),
                    'conflict_description': conflict_data.get('conflict_description'),
                    'suggested_resolution': conflict_data.get('suggested_resolution'),
                    'corrected_expected_status': conflict_data.get('corrected_expected_status', actual_status),
                    'corrected_expected_response': conflict_data.get('corrected_expected_response', actual_response)
                }
            
            return None
            
        except Exception as e:
            self.logger.error(f"Error detecting documentation conflict: {str(e)}")
            return None
    
    def _create_conflict_notification(
        self,
        test_case_id: int,
        client_id: str,
        user_id: int,
        step_number: int,
        step: dict,
        execution_result: dict,
        conflict_details: dict,
        generation_state: dict
    ) -> Optional[int]:
        """
        Create a conflict notification in the database that requires user intervention.
        
        Returns notification ID if created successfully, None otherwise.
        """
        try:
            with get_db_connection_context() as conn:
                cursor = conn.cursor()
                
                request = execution_result['request']
                response = execution_result['response']
                
                insert_query = """
                    INSERT INTO api_conflict_notifications (
                        test_case_id, client_id, user_id, step_number, conflict_type,
                        request_method, request_endpoint, request_body, request_headers,
                        expected_status, actual_status, expected_response, actual_response,
                        conflict_description, suggested_resolution,
                        corrected_expected_status, corrected_expected_response,
                        generation_state, status
                    ) VALUES (
                        %s, %s, %s, %s, %s,
                        %s, %s, %s, %s,
                        %s, %s, %s, %s,
                        %s, %s,
                        %s, %s,
                        %s, 'pending'
                    ) RETURNING id
                """
                
                cursor.execute(insert_query, (
                    test_case_id,
                    client_id,
                    user_id,
                    step_number,
                    conflict_details['conflict_type'],
                    request['method'],
                    request['url'],
                    json.dumps(request.get('body')),
                    json.dumps(request.get('headers')),
                    conflict_details.get('documented_status'),
                    response['status'],
                    json.dumps(conflict_details.get('documented_response')),
                    json.dumps(response['body']),
                    conflict_details['conflict_description'],
                    conflict_details['suggested_resolution'],
                    conflict_details['corrected_expected_status'],
                    json.dumps(conflict_details['corrected_expected_response']),
                    json.dumps(generation_state)
                ))
                
                notification_id = cursor.fetchone()[0]
                conn.commit()
                
                self.logger.info(f"✅ Created conflict notification {notification_id} for test case {test_case_id}")
                return notification_id
                
        except Exception as e:
            self.logger.error(f"Error creating conflict notification: {str(e)}")
            return None
    
    def _check_conflict_resolution(self, test_case_id: int) -> Optional[dict]:
        """
        Check if there's a pending conflict notification for this test case.
        Returns None if no pending conflict, or resolution details if resolved.
        """
        try:
            with get_db_connection_context() as conn:
                cursor = conn.cursor()
                
                # Check for active conflict (pending or approved only)
                # Ignore old processed/rejected/cancelled notifications from previous runs
                cursor.execute("""
                    SELECT id, status, generation_state, corrected_expected_status, 
                           corrected_expected_response, user_decision
                    FROM api_conflict_notifications
                    WHERE test_case_id = %s
                      AND status IN ('pending', 'approved')
                    ORDER BY created_at DESC
                    LIMIT 1
                """, (test_case_id,))
                
                result = cursor.fetchone()
                if not result:
                    return None
                
                notification_id, status, generation_state, corrected_status, corrected_response, user_decision = result
                
                if status == 'pending':
                    # Still waiting for user decision
                    return {'status': 'waiting', 'notification_id': notification_id}
                elif status == 'approved':
                    # User approved the correction
                    # Note: JSONB fields are already dicts, no need to json.loads()
                    return {
                        'status': 'approved',
                        'notification_id': notification_id,
                        'generation_state': generation_state if generation_state else {},
                        'corrected_expected_status': corrected_status,
                        'corrected_expected_response': corrected_response if corrected_response else {}
                    }
                
                # Should not reach here since we filter for pending/approved only
                return None
                
        except Exception as e:
            self.logger.error(f"Error checking conflict resolution: {str(e)}")
            return None
