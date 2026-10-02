import json
import logging
import os
import uuid
from typing import Dict, Any, List, Optional
from auroqa.Utils.Connectors.db_utils import get_db_connection_context
from auroqa.Utils.System import System
from auroqa.Utils.BrowserAutomation.EnvHelper import EnvHelper
from auroqa.Services.ValidationAgent import ValidationAgent
from auroqa.Services.ConfidenceScorer import ConfidenceScorer
from auroqa.Services.PlanningCollector import PlanningCollector

# Phase 3 Integration: Use wrapper if enabled
if os.getenv('USE_PHASE3', 'true').lower() == 'true':
    from auroqa.Utils.AIHelper.EnhancedAIHelper import EnhancedAIHelper as AIHelper
else:
    from auroqa.Utils.AIHelper.AIHelper import AIHelper


class ApiSchemaService:
    """
    Service for analyzing API schemas and generating test cases with steps.
    Supports OpenAPI, Swagger, Postman collections, and custom API schemas.
    """
    
    def __init__(self):
        self.logger = self._setup_logger()
        self.ai_helper = AIHelper()
        self.system = System()
        # Phase 1: Initialize validation and scoring services
        self.validator = ValidationAgent()
        self.scorer = ConfidenceScorer()
        # Planning & Reasoning: Initialize planning collector
        self.planning_collector = PlanningCollector(
            redis_host=self.system.redis_host,
            redis_port=self.system.redis_port
        )
    
    def _setup_logger(self):
        """Setup logger for API schema service."""
        logger = logging.getLogger('ApiSchemaService')
        logger.setLevel(logging.DEBUG)
        # The app configures root logging (main.py); an own handler here would print every line twice
        if logging.getLogger().handlers:
            return logger
        
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
            # Generate unique job ID for tracking all AI requests in this test generation
            generation_job_id = str(uuid.uuid4())
            self.logger.info(f"Generating API test steps for test case {test_case_id} (Job ID: {generation_job_id})")
            
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
                schema_content
            )
            
            # Use Gemini to generate steps
            response = self.ai_helper.send_request_to_gemini(
                prompt=prompt,
                text_content=schema_content,
                request_type='api_test',
                request_context=f'test_case_{test_case_id}',
                client_id=client_id,
                generation_job_id=generation_job_id
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
                    test_case_description,
                    client_id,
                    generation_job_id
                )
                self.logger.info(f"✅ Validation process completed")
                
                self._save_test_steps(test_case_id, validated_steps)
                # Don't update description - preserve user's original input
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
    
    # ==================== PHASE 1: SCHEMA ANALYSIS METHODS ====================
    
    def _extract_endpoints_from_schema(self, schema_content: str) -> List[Dict[str, Any]]:
        """
        Парсит API схему и извлекает все endpoints.
        
        Args:
            schema_content: JSON строка с API схемой
            
        Returns:
            List[Dict]: Список endpoints с методами, путями, параметрами и ответами
            
        Example:
            [
                {
                    "method": "POST",
                    "path": "/auth",
                    "description": "Authenticate user",
                    "body_fields": ["email", "password"],
                    "response_fields": ["token"],
                    "requires_auth": False
                },
                {
                    "method": "GET",
                    "path": "/resources/{id}",
                    "description": "Get resource",
                    "path_params": ["id"],
                    "response_fields": ["id", "name"],
                    "requires_auth": True
                }
            ]
        """
        try:
            import json
            schema = json.loads(schema_content)
            endpoints = []
            
            if 'paths' not in schema:
                self.logger.warning("No 'paths' found in schema")
                return endpoints
            
            # Extract base path
            base_path = ""
            if 'servers' in schema and len(schema['servers']) > 0:
                server_url = schema['servers'][0].get('url', '')
                if server_url:
                    from urllib.parse import urlparse
                    parsed = urlparse(server_url)
                    base_path = parsed.path.rstrip('/')
            elif 'basePath' in schema:
                base_path = schema['basePath'].rstrip('/')
            
            # Iterate through all paths and methods
            for path, methods in schema['paths'].items():
                full_path = f"{base_path}{path}" if base_path else path
                
                for method, details in methods.items():
                    if method.upper() not in ['GET', 'POST', 'PUT', 'DELETE', 'PATCH']:
                        continue
                    
                    endpoint = {
                        "method": method.upper(),
                        "path": full_path,
                        "description": details.get('summary', details.get('description', '')),
                        "body_fields": [],
                        "path_params": [],
                        "query_params": [],
                        "response_fields": [],
                        "requires_auth": False,
                        "auth_type": None
                    }
                    
                    # Check authentication requirement
                    requires_auth = False
                    auth_type = None
                    
                    if 'security' in details:
                        requires_auth = len(details['security']) > 0
                        if requires_auth and details['security']:
                            first_security = details['security'][0]
                            if first_security:
                                auth_type = list(first_security.keys())[0]
                    elif 'security' in schema:
                        requires_auth = len(schema['security']) > 0
                        if requires_auth and schema['security']:
                            first_security = schema['security'][0]
                            if first_security:
                                auth_type = list(first_security.keys())[0]
                    
                    endpoint["requires_auth"] = requires_auth
                    endpoint["auth_type"] = auth_type
                    
                    # Extract parameters
                    if 'parameters' in details:
                        for param in details['parameters']:
                            param_name = param.get('name', '')
                            param_in = param.get('in', '')
                            param_type = param.get('type', param.get('schema', {}).get('type', 'string'))
                            
                            if param_in == 'path':
                                endpoint["path_params"].append({
                                    "name": param_name,
                                    "type": param_type,
                                    "required": param.get('required', False)
                                })
                            elif param_in == 'query':
                                endpoint["query_params"].append({
                                    "name": param_name,
                                    "type": param_type,
                                    "required": param.get('required', False)
                                })
                    
                    # Extract request body fields (Swagger 2.0 style)
                    if 'parameters' in details:
                        for param in details['parameters']:
                            if param.get('in') == 'body':
                                param_schema = param.get('schema', {})
                                if '$ref' in param_schema:
                                    ref_path = param_schema['$ref']
                                    if ref_path.startswith('#/'):
                                        ref_parts = ref_path[2:].split('/')
                                        resolved_schema = schema
                                        for part in ref_parts:
                                            resolved_schema = resolved_schema.get(part, {})
                                        param_schema = resolved_schema
                                
                                properties = param_schema.get('properties', {})
                                for prop_name in properties.keys():
                                    endpoint["body_fields"].append(prop_name)
                    
                    # Extract request body fields (OpenAPI 3.0 style)
                    if 'requestBody' in details:
                        try:
                            content = details['requestBody'].get('content', {})
                            json_content = content.get('application/json', {})
                            schema_ref = json_content.get('schema', {})
                            
                            if '$ref' in schema_ref:
                                ref_path = schema_ref['$ref']
                                if ref_path.startswith('#/'):
                                    ref_parts = ref_path[2:].split('/')
                                    resolved_schema = schema
                                    for part in ref_parts:
                                        resolved_schema = resolved_schema.get(part, {})
                                    schema_ref = resolved_schema
                            
                            properties = schema_ref.get('properties', {})
                            for prop_name in properties.keys():
                                endpoint["body_fields"].append(prop_name)
                        except Exception as e:
                            self.logger.debug(f"Error extracting request body: {str(e)}")
                    
                    # Extract response fields
                    if 'responses' in details:
                        try:
                            for status_code, response_details in details['responses'].items():
                                if status_code.startswith('2'):  # Success responses
                                    response_content = response_details.get('content', {})
                                    json_response = response_content.get('application/json', {})
                                    response_schema = json_response.get('schema', {})
                                    
                                    if '$ref' in response_schema:
                                        ref_path = response_schema['$ref']
                                        if ref_path.startswith('#/'):
                                            ref_parts = ref_path[2:].split('/')
                                            resolved_schema = schema
                                            for part in ref_parts:
                                                resolved_schema = resolved_schema.get(part, {})
                                            response_schema = resolved_schema
                                    
                                    response_props = response_schema.get('properties', {})
                                    for prop_name in response_props.keys():
                                        if prop_name not in endpoint["response_fields"]:
                                            endpoint["response_fields"].append(prop_name)
                        except Exception as e:
                            self.logger.debug(f"Error extracting response fields: {str(e)}")
                    
                    endpoints.append(endpoint)
            
            self.logger.info(f"✅ Extracted {len(endpoints)} endpoints from schema")
            return endpoints
            
        except json.JSONDecodeError as e:
            self.logger.error(f"Invalid JSON in schema: {str(e)}")
            return []
        except Exception as e:
            self.logger.error(f"Error extracting endpoints: {str(e)}")
            return []
    
    def _check_if_auth_required(self, schema_content: str) -> Dict[str, Any]:
        """
        Проверяет требуется ли аутентификация для API.
        
        Args:
            schema_content: JSON строка с API схемой
            
        Returns:
            Dict: {
                "required": bool,
                "type": str (Bearer, API Key, OAuth, etc.),
                "endpoint": str (путь к endpoint аутентификации),
                "description": str
            }
        """
        try:
            import json
            schema = json.loads(schema_content)
            
            # Check global security
            if 'security' in schema and len(schema['security']) > 0:
                first_security = schema['security'][0]
                if first_security:
                    auth_type = list(first_security.keys())[0]
                    
                    # Try to find auth endpoint
                    auth_endpoint = None
                    if 'paths' in schema:
                        for path in schema['paths'].keys():
                            if 'auth' in path.lower() or 'login' in path.lower():
                                auth_endpoint = path
                                break
                    
                    result = {
                        "required": True,
                        "type": auth_type,
                        "endpoint": auth_endpoint or "/auth",
                        "description": f"API requires {auth_type} authentication"
                    }
                    
                    self.logger.info(f"✅ Auth required: {auth_type}")
                    return result
            
            # Check if any endpoint requires auth
            if 'paths' in schema:
                for path, methods in schema['paths'].items():
                    for method, details in methods.items():
                        if 'security' in details and len(details['security']) > 0:
                            first_security = details['security'][0]
                            if first_security:
                                auth_type = list(first_security.keys())[0]
                                result = {
                                    "required": True,
                                    "type": auth_type,
                                    "endpoint": None,
                                    "description": f"Some endpoints require {auth_type} authentication"
                                }
                                self.logger.info(f"✅ Auth required: {auth_type}")
                                return result
            
            self.logger.info("✅ No authentication required")
            return {
                "required": False,
                "type": None,
                "endpoint": None,
                "description": "No authentication required"
            }
            
        except json.JSONDecodeError:
            self.logger.warning("Invalid JSON in schema")
            return {"required": False, "type": None, "endpoint": None, "description": "Could not parse schema"}
        except Exception as e:
            self.logger.error(f"Error checking auth requirement: {str(e)}")
            return {"required": False, "type": None, "endpoint": None, "description": "Error checking auth"}
    
    def _analyze_endpoint_complexity(self, endpoint: Dict[str, Any]) -> Dict[str, Any]:
        """
        Анализирует сложность одного endpoint.
        
        Args:
            endpoint: Dict с информацией об endpoint (из _extract_endpoints_from_schema)
            
        Returns:
            Dict: {
                "complexity": str (low/medium/high),
                "risks": List[str],
                "modifies_data": bool,
                "requires_id": bool,
                "nested": bool
            }
        """
        try:
            complexity = "low"
            risks = []
            
            method = endpoint.get("method", "GET")
            path = endpoint.get("path", "")
            body_fields = endpoint.get("body_fields", [])
            path_params = endpoint.get("path_params", [])
            query_params = endpoint.get("query_params", [])
            
            # Determine if data is modified
            modifies_data = method in ["POST", "PUT", "PATCH", "DELETE"]
            
            # Check if requires ID
            requires_id = len(path_params) > 0 or "{id}" in path or "{ID}" in path
            
            # Check if nested resource
            nested = path.count("/") > 2
            
            # Calculate complexity
            field_count = len(body_fields) + len(path_params) + len(query_params)
            
            if modifies_data:
                if field_count > 5:
                    complexity = "high"
                elif field_count > 2:
                    complexity = "medium"
                else:
                    complexity = "low"
            else:
                if field_count > 3:
                    complexity = "medium"
                else:
                    complexity = "low"
            
            if nested:
                complexity = "high" if complexity == "low" else "high"
            
            # Identify risks
            if method == "DELETE":
                risks.extend(["Data loss", "Cascading deletes"])
            elif method == "PUT" or method == "PATCH":
                risks.extend(["Partial update", "Concurrent modification"])
            elif method == "POST":
                risks.extend(["Duplicate creation", "Data validation"])
            
            if requires_id:
                risks.append("Invalid ID")
            
            if query_params:
                risks.append("Complex filtering errors")
            
            return {
                "complexity": complexity,
                "risks": risks,
                "modifies_data": modifies_data,
                "requires_id": requires_id,
                "nested": nested
            }
            
        except Exception as e:
            self.logger.error(f"Error analyzing endpoint complexity: {str(e)}")
            return {
                "complexity": "medium",
                "risks": [],
                "modifies_data": False,
                "requires_id": False,
                "nested": False
            }
    
    def _extract_response_structure(self, endpoint: Dict[str, Any]) -> Dict[str, Any]:
        """
        Анализирует структуру ответа endpoint.
        
        Args:
            endpoint: Dict с информацией об endpoint
            
        Returns:
            Dict: {
                "fields": List[str],
                "nested": bool,
                "depth": int,
                "complexity": str (low/medium/high)
            }
        """
        try:
            response_fields = endpoint.get("response_fields", [])
            
            # Estimate nesting and depth
            nested = len(response_fields) > 5
            depth = 1
            
            # Simple heuristic: if many fields, likely nested
            if len(response_fields) > 10:
                depth = 3
                complexity = "high"
            elif len(response_fields) > 5:
                depth = 2
                complexity = "medium"
            else:
                depth = 1
                complexity = "low"
            
            return {
                "fields": response_fields,
                "nested": nested,
                "depth": depth,
                "complexity": complexity
            }
            
        except Exception as e:
            self.logger.error(f"Error extracting response structure: {str(e)}")
            return {
                "fields": [],
                "nested": False,
                "depth": 1,
                "complexity": "low"
            }
    
    def _check_for_pagination(self, schema_content: str) -> Dict[str, Any]:
        """
        Проверяет есть ли pagination в API.
        
        Args:
            schema_content: JSON строка с API схемой
            
        Returns:
            Dict: {
                "has_pagination": bool,
                "type": str (offset_limit, cursor, page, etc.),
                "parameters": List[str],
                "default_limit": int
            }
        """
        try:
            import json
            schema = json.loads(schema_content)
            
            pagination_indicators = {
                "offset": ["offset", "skip"],
                "limit": ["limit", "take", "per_page"],
                "page": ["page", "page_number"],
                "cursor": ["cursor", "next_token", "continuation_token"]
            }
            
            found_params = []
            pagination_type = None
            
            if 'paths' in schema:
                for path, methods in schema['paths'].items():
                    for method, details in methods.items():
                        if 'parameters' in details:
                            for param in details['parameters']:
                                param_name = param.get('name', '').lower()
                                
                                for pag_type, indicators in pagination_indicators.items():
                                    if param_name in indicators:
                                        if param_name not in found_params:
                                            found_params.append(param_name)
                                        if not pagination_type:
                                            pagination_type = pag_type
            
            has_pagination = len(found_params) > 0
            
            result = {
                "has_pagination": has_pagination,
                "type": pagination_type or "unknown",
                "parameters": found_params,
                "default_limit": 20
            }
            
            if has_pagination:
                self.logger.info(f"✅ Pagination detected: {pagination_type}, params: {found_params}")
            else:
                self.logger.info("✅ No pagination detected")
            
            return result
            
        except json.JSONDecodeError:
            self.logger.warning("Invalid JSON in schema")
            return {
                "has_pagination": False,
                "type": None,
                "parameters": [],
                "default_limit": 20
            }
        except Exception as e:
            self.logger.error(f"Error checking pagination: {str(e)}")
            return {
                "has_pagination": False,
                "type": None,
                "parameters": [],
                "default_limit": 20
            }
    
    # ==================== END PHASE 1 METHODS ====================
    
    # ==================== PHASE 2: DYNAMIC DATA CREATION METHODS ====================
    
    def _create_dynamic_requirement_analysis(self, schema_content: str, test_description: str) -> Dict[str, Any]:
        """
        Создает ДИНАМИЧЕСКУЮ requirement_analysis на основе анализа схемы.
        
        Args:
            schema_content: JSON строка с API схемой
            test_description: Описание тестового случая
            
        Returns:
            Dict: {
                "complexity_score": int (0-100),
                "factors": List[str],
                "description": str
            }
        """
        try:
            # Используем методы Фазы 1 для анализа
            endpoints = self._extract_endpoints_from_schema(schema_content)
            auth_info = self._check_if_auth_required(schema_content)
            pagination_info = self._check_for_pagination(schema_content)
            
            endpoint_count = len(endpoints)
            
            # Определяем complexity_score ДИНАМИЧЕСКИ
            if endpoint_count > 5:
                complexity_score = 85  # Высокая сложность
            elif endpoint_count > 2:
                complexity_score = 65  # Средняя сложность
            else:
                complexity_score = 40  # Низкая сложность
            
            # Определяем factors ДИНАМИЧЕСКИ
            factors = []
            
            # Анализируем методы HTTP
            methods = [ep.get("method") for ep in endpoints]
            if "POST" in methods or "PUT" in methods or "DELETE" in methods:
                factors.append("Data modification")
            if "GET" in methods:
                factors.append("Data retrieval")
            
            # Анализируем аутентификацию
            if auth_info["required"]:
                factors.append(f"Authentication ({auth_info['type']})")
            
            # Анализируем pagination
            if pagination_info["has_pagination"]:
                factors.append(f"Pagination ({pagination_info['type']})")
            
            # Анализируем вложенность ресурсов
            has_nested = any(ep.get("path", "").count("/") > 2 for ep in endpoints)
            if has_nested:
                factors.append("Nested resources")
            
            # Анализируем параметры
            has_complex_params = any(
                len(ep.get("path_params", [])) > 1 or 
                len(ep.get("query_params", [])) > 2 
                for ep in endpoints
            )
            if has_complex_params:
                factors.append("Complex parameters")
            
            # Анализируем DELETE операции
            if "DELETE" in methods:
                factors.append("Data deletion")
            
            # Если нет факторов, добавляем базовый
            if not factors:
                factors.append("API testing")
            
            # Создаем description
            description = f"Analyzing {endpoint_count} API endpoints with {len(factors)} complexity factors: {', '.join(factors[:3])}"
            
            result = {
                "complexity_score": complexity_score,
                "factors": factors,
                "description": description
            }
            
            self.logger.info(f"✅ Dynamic requirement analysis: score={complexity_score}, factors={len(factors)}")
            return result
            
        except Exception as e:
            self.logger.error(f"Error creating dynamic requirement analysis: {str(e)}")
            # Fallback to safe defaults
            return {
                "complexity_score": 50,
                "factors": ["API testing"],
                "description": "API test case analysis"
            }
    
    def _create_dynamic_decomposition(self, schema_content: str, test_description: str) -> Dict[str, Any]:
        """
        Создает ДИНАМИЧЕСКУЮ decomposition на основе endpoints в схеме.
        
        Args:
            schema_content: JSON строка с API схемой
            test_description: Описание тестового случая
            
        Returns:
            Dict: {
                "strategy": str,
                "total_steps": int,
                "subtasks": List[Dict]
            }
        """
        try:
            endpoints = self._extract_endpoints_from_schema(schema_content)
            auth_info = self._check_if_auth_required(schema_content)
            
            subtasks = []
            step_order = 1
            
            # Шаг 1: Аутентификация (если требуется)
            if auth_info["required"]:
                auth_endpoint = auth_info.get("endpoint", "/auth")
                subtasks.append({
                    "order": step_order,
                    "task": f"Authenticate with API ({auth_info['type']})",
                    "type": "setup",
                    "endpoint": auth_endpoint,
                    "description": f"Obtain {auth_info['type']} authentication token"
                })
                step_order += 1
            
            # Шаги 2+: Основные операции (в порядке: POST, PUT, PATCH, DELETE, GET)
            # Сначала POST (создание)
            for endpoint in endpoints:
                if endpoint["method"] == "POST" and "auth" not in endpoint["path"].lower():
                    subtasks.append({
                        "order": step_order,
                        "task": f"Create via {endpoint['path']}",
                        "type": "execution",
                        "endpoint": endpoint["path"],
                        "method": "POST",
                        "description": endpoint.get("description", "Create resource")
                    })
                    step_order += 1
            
            # Потом PUT (обновление)
            for endpoint in endpoints:
                if endpoint["method"] == "PUT":
                    subtasks.append({
                        "order": step_order,
                        "task": f"Update via {endpoint['path']}",
                        "type": "execution",
                        "endpoint": endpoint["path"],
                        "method": "PUT",
                        "description": endpoint.get("description", "Update resource")
                    })
                    step_order += 1
            
            # Потом PATCH (частичное обновление)
            for endpoint in endpoints:
                if endpoint["method"] == "PATCH":
                    subtasks.append({
                        "order": step_order,
                        "task": f"Patch via {endpoint['path']}",
                        "type": "execution",
                        "endpoint": endpoint["path"],
                        "method": "PATCH",
                        "description": endpoint.get("description", "Partially update resource")
                    })
                    step_order += 1
            
            # Потом DELETE (удаление)
            for endpoint in endpoints:
                if endpoint["method"] == "DELETE":
                    subtasks.append({
                        "order": step_order,
                        "task": f"Delete via {endpoint['path']}",
                        "type": "execution",
                        "endpoint": endpoint["path"],
                        "method": "DELETE",
                        "description": endpoint.get("description", "Delete resource")
                    })
                    step_order += 1
            
            # Потом GET (чтение/проверка)
            for endpoint in endpoints:
                if endpoint["method"] == "GET":
                    subtasks.append({
                        "order": step_order,
                        "task": f"Verify via {endpoint['path']}",
                        "type": "validation",
                        "endpoint": endpoint["path"],
                        "method": "GET",
                        "description": endpoint.get("description", "Retrieve and verify resource")
                    })
                    step_order += 1
            
            # Если нет subtasks (только auth), добавляем fallback
            if len(subtasks) == 0:
                subtasks.append({
                    "order": 1,
                    "task": "Execute API test",
                    "type": "execution",
                    "endpoint": "/",
                    "description": "Execute API test"
                })
            
            # Создаем strategy
            strategy = " → ".join([s["task"] for s in subtasks])
            
            result = {
                "strategy": strategy,
                "total_steps": len(subtasks),
                "subtasks": subtasks
            }
            
            self.logger.info(f"✅ Dynamic decomposition: {len(subtasks)} steps, strategy: {strategy[:80]}...")
            return result
            
        except Exception as e:
            self.logger.error(f"Error creating dynamic decomposition: {str(e)}")
            # Fallback
            return {
                "strategy": "Execute API test",
                "total_steps": 1,
                "subtasks": [{
                    "order": 1,
                    "task": "Execute API test",
                    "type": "execution",
                    "endpoint": "/"
                }]
            }
    
    def _create_dynamic_dependencies(self, schema_content: str, test_description: str) -> Dict[str, Any]:
        """
        Создает ДИНАМИЧЕСКИЕ dependencies на основе endpoints и аутентификации.
        
        Args:
            schema_content: JSON строка с API схемой
            test_description: Описание тестового случая
            
        Returns:
            Dict: {
                "data_dependencies": List[Dict],
                "state_dependencies": List[Dict]
            }
        """
        try:
            endpoints = self._extract_endpoints_from_schema(schema_content)
            auth_info = self._check_if_auth_required(schema_content)
            
            data_dependencies = [
                {
                    "variable": "base_url",
                    "source": "environment",
                    "description": "API base URL from environment"
                }
            ]
            
            state_dependencies = []
            
            # Если требуется аутентификация
            if auth_info["required"]:
                data_dependencies.append({
                    "variable": "auth_token",
                    "source": "response",
                    "description": f"Authentication token from {auth_info.get('endpoint', '/auth')} endpoint"
                })
                state_dependencies.append({
                    "state": "authenticated",
                    "required_for": "protected_endpoints",
                    "description": "Must authenticate before accessing protected endpoints"
                })
            
            # Если есть POST (создание ресурсов)
            has_post = any(ep["method"] == "POST" for ep in endpoints)
            if has_post:
                data_dependencies.append({
                    "variable": "resource_id",
                    "source": "response",
                    "description": "Resource ID from POST response"
                })
                state_dependencies.append({
                    "state": "resource_created",
                    "required_for": "update_delete",
                    "description": "Resource must be created before update/delete operations"
                })
            
            # Если есть вложенные ресурсы
            has_nested = any(ep["path"].count("/") > 2 for ep in endpoints)
            if has_nested:
                data_dependencies.append({
                    "variable": "parent_id",
                    "source": "response",
                    "description": "Parent resource ID for nested operations"
                })
                state_dependencies.append({
                    "state": "parent_resource_exists",
                    "required_for": "nested_operations",
                    "description": "Parent resource must exist for nested operations"
                })
            
            # Анализируем path параметры
            all_path_params = set()
            for ep in endpoints:
                for param in ep.get("path_params", []):
                    all_path_params.add(param.get("name"))
            
            for param_name in all_path_params:
                if param_name not in ["id"]:  # id уже добавлен как resource_id
                    data_dependencies.append({
                        "variable": param_name,
                        "source": "response",
                        "description": f"Parameter {param_name} from previous response"
                    })
            
            result = {
                "data_dependencies": data_dependencies,
                "state_dependencies": state_dependencies
            }
            
            self.logger.info(f"✅ Dynamic dependencies: {len(data_dependencies)} data, {len(state_dependencies)} state")
            return result
            
        except Exception as e:
            self.logger.error(f"Error creating dynamic dependencies: {str(e)}")
            # Fallback
            return {
                "data_dependencies": [
                    {"variable": "base_url", "source": "environment", "description": "API base URL"}
                ],
                "state_dependencies": []
            }
    
    def _create_dynamic_risk_assessment(self, schema_content: str, test_description: str) -> Dict[str, Any]:
        """
        Создает ДИНАМИЧЕСКУЮ risk_assessment на основе endpoints и методов HTTP.
        
        Args:
            schema_content: JSON строка с API схемой
            test_description: Описание тестового случая
            
        Returns:
            Dict: {
                "identified_risks": List[Dict]
            }
        """
        try:
            endpoints = self._extract_endpoints_from_schema(schema_content)
            auth_info = self._check_if_auth_required(schema_content)
            
            risks = []
            
            # Анализируем методы HTTP
            methods = [ep["method"] for ep in endpoints]
            
            # Риск для GET
            if "GET" in methods:
                risks.append({
                    "risk": "Rate limiting on read operations",
                    "severity": "medium",
                    "probability": 0.25,
                    "mitigation": "Add delays between requests or implement caching"
                })
                risks.append({
                    "risk": "Timeout on large responses",
                    "severity": "medium",
                    "probability": 0.15,
                    "mitigation": "Implement pagination or filtering"
                })
            
            # Риск для POST
            if "POST" in methods:
                risks.append({
                    "risk": "Data validation errors",
                    "severity": "medium",
                    "probability": 0.35,
                    "mitigation": "Validate request data before sending"
                })
                risks.append({
                    "risk": "Duplicate resource creation",
                    "severity": "low",
                    "probability": 0.15,
                    "mitigation": "Use unique identifiers or idempotency keys"
                })
            
            # Риск для PUT/PATCH
            if "PUT" in methods or "PATCH" in methods:
                risks.append({
                    "risk": "Concurrent modification conflicts",
                    "severity": "high",
                    "probability": 0.2,
                    "mitigation": "Use version control, timestamps, or optimistic locking"
                })
                risks.append({
                    "risk": "Partial update inconsistency",
                    "severity": "medium",
                    "probability": 0.15,
                    "mitigation": "Validate all fields after partial updates"
                })
            
            # Риск для DELETE
            if "DELETE" in methods:
                risks.append({
                    "risk": "Accidental data loss",
                    "severity": "high",
                    "probability": 0.1,
                    "mitigation": "Implement soft deletes or backup mechanisms"
                })
                risks.append({
                    "risk": "Cascading deletes affecting related data",
                    "severity": "high",
                    "probability": 0.15,
                    "mitigation": "Check for related resources before deletion"
                })
            
            # Риск для аутентификации
            if auth_info["required"]:
                risks.append({
                    "risk": "Authentication token expiration",
                    "severity": "medium",
                    "probability": 0.3,
                    "mitigation": "Refresh token before expiration or handle 401 responses"
                })
                risks.append({
                    "risk": "Insufficient permissions",
                    "severity": "medium",
                    "probability": 0.2,
                    "mitigation": "Verify user has required permissions for each operation"
                })
            
            # Анализируем параметры
            has_complex_params = any(
                len(ep.get("path_params", [])) > 1 or 
                len(ep.get("query_params", [])) > 2 
                for ep in endpoints
            )
            if has_complex_params:
                risks.append({
                    "risk": "Complex parameter validation errors",
                    "severity": "low",
                    "probability": 0.2,
                    "mitigation": "Test with various parameter combinations"
                })
            
            # Анализируем вложенность
            has_nested = any(ep["path"].count("/") > 2 for ep in endpoints)
            if has_nested:
                risks.append({
                    "risk": "Nested resource access control issues",
                    "severity": "high",
                    "probability": 0.15,
                    "mitigation": "Verify access control at each nesting level"
                })
            
            # Если нет рисков, добавляем базовый
            if not risks:
                risks.append({
                    "risk": "API schema mismatch",
                    "severity": "medium",
                    "probability": 0.2,
                    "mitigation": "Compare actual responses with schema documentation"
                })
            
            result = {
                "identified_risks": risks
            }
            
            self.logger.info(f"✅ Dynamic risk assessment: {len(risks)} risks identified")
            return result
            
        except Exception as e:
            self.logger.error(f"Error creating dynamic risk assessment: {str(e)}")
            # Fallback
            return {
                "identified_risks": [{
                    "risk": "API schema mismatch",
                    "severity": "medium",
                    "probability": 0.2,
                    "mitigation": "Compare actual responses with schema documentation"
                }]
            }
    
    # ==================== END PHASE 2 METHODS ====================
    
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
        test_case_description: str,
        client_id: str,
        generation_job_id: str
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
                    test_case_description,
                    test_case_id,
                    client_id,
                    generation_job_id
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
        test_case_description: str,
        test_case_id: int,
        client_id: str,
        generation_job_id: str
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
                text_content=schema_content,
                request_type='api_test',
                request_context=f'test_case_{test_case_id}_correction',
                client_id=client_id,
                generation_job_id=generation_job_id
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
        environment_id: int = None
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
            
        Returns:
            bool: True if steps were generated successfully
        """
        try:
            from auroqa.Services.ApiTestExecutor import ApiTestExecutor
            
            # Generate unique job ID for tracking all AI requests in this test generation
            generation_job_id = str(uuid.uuid4())
            self.logger.info(f"🔄 Starting iterative step generation for test case {test_case_id} (Job ID: {generation_job_id})")
            
            # ==================== PHASE 1: STRATEGIC PLANNING ====================
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
            
            # ==================== PHASE 2: DYNAMIC PLANNING (PHASE 2 INTEGRATION) ====================
            # Create dynamic requirement analysis
            req_analysis = self._create_dynamic_requirement_analysis(schema_content, test_case_description)
            self.planning_collector.set_requirement_analysis(
                test_case_id=test_case_id,
                complexity_score=req_analysis["complexity_score"],
                factors=req_analysis["factors"],
                description=req_analysis["description"]
            )
            self.logger.info(f"✅ Dynamic requirement analysis: score={req_analysis['complexity_score']}, factors={len(req_analysis['factors'])}")
            
            # Create dynamic decomposition
            decomposition = self._create_dynamic_decomposition(schema_content, test_case_description)
            self.planning_collector.set_decomposition(
                test_case_id=test_case_id,
                strategy=decomposition["strategy"],
                subtasks=decomposition["subtasks"]
            )
            self.logger.info(f"✅ Dynamic decomposition: {decomposition['total_steps']} steps")
            
            # Create dynamic dependencies
            dependencies = self._create_dynamic_dependencies(schema_content, test_case_description)
            self.planning_collector.set_dependencies(
                test_case_id=test_case_id,
                data_dependencies=dependencies["data_dependencies"],
                state_dependencies=dependencies["state_dependencies"]
            )
            self.logger.info(f"✅ Dynamic dependencies: {len(dependencies['data_dependencies'])} data, {len(dependencies['state_dependencies'])} state")
            
            # Create dynamic risk assessment
            risk_assessment = self._create_dynamic_risk_assessment(schema_content, test_case_description)
            self.planning_collector.set_risk_assessment(
                test_case_id=test_case_id,
                identified_risks=risk_assessment["identified_risks"]
            )
            self.logger.info(f"✅ Dynamic risk assessment: {len(risk_assessment['identified_risks'])} risks identified")
            
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
            max_steps = 100  # Safety limit (increased to support large test flows)
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
                    
                    # Don't update description - preserve user's original input
                    if generated_steps:
                        self.logger.info(f"📝 Saved {len(generated_steps)} steps after conflict resolution (description preserved)")
                    
                    # Mark notification as processed
                    with get_db_connection_context() as conn:
                        cursor = conn.cursor()
                        cursor.execute(
                            "UPDATE api_conflict_notifications SET status = 'processed' WHERE id = %s",
                            (conflict_resolution['notification_id'],)
                        )
                        conn.commit()
                    
                    # ==================== RECOVERY STATISTICS ====================
                    # Track successful recovery
                    self.planning_collector.set_recovery_statistics(
                        test_case_id=test_case_id,
                        total_failures=1,
                        automated_recoveries=0,
                        escalations=1,
                        recovery_rate=100.0  # User approved the resolution
                    )
            
            # Generate first step only if not resuming
            if not resuming_from_conflict:
                self.logger.info("📝 Generating first step...")
                first_step = self._generate_first_step(
                    test_case_name,
                    test_case_description,
                    schema_summary,
                    client_id,
                    generation_job_id
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
                        
                        # Don't update description - preserve user's original input
                        if generated_steps:
                            self.logger.info(f"📝 Saved {len(generated_steps)} steps (in-loop, description preserved)")
                        
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
                        extracted_variables,
                        client_id,
                        generation_job_id
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
                    
                    # Skip conflict detection for obvious data validation errors
                    # Check both error_message and response body
                    error_message = execution_result.get('error_message', '').lower()
                    response_body = execution_result.get('response', {}).get('body', {})
                    response_text = json.dumps(response_body).lower() if response_body else ''
                    
                    validation_patterns = [
                        'should contain only alphabetic',
                        'should contain only',
                        'should be in',
                        'invalid format',
                        'field is required',
                        'must be',
                        'cannot be empty',
                        'validation',
                        'invalid',
                        'format'
                    ]
                    is_validation_error = any(pattern in error_message for pattern in validation_patterns) or \
                                        any(pattern in response_text for pattern in validation_patterns)
                    
                    if is_validation_error:
                        self.logger.info(f"🔧 Data validation error detected in response: {response_body}")
                        self.logger.info(f"🔧 This is NOT a conflict - will retry with corrected data")
                    
                    # Check for documentation conflict BEFORE retrying (but skip for validation errors)
                    if retry_count == 0 and not is_validation_error:  # Only check on first error, skip validation errors
                        conflict_details = self._detect_documentation_conflict(
                            test_case_id,
                            current_step,
                            execution_result,
                            schema_content
                        )
                        
                        if conflict_details:
                            # ==================== ERROR RECOVERY TRACKING ====================
                            # Track failure analysis
                            self.planning_collector.set_failure_analysis(
                                test_case_id=test_case_id,
                                failures=[
                                    {
                                        "step": step_order,
                                        "type": "documentation_conflict",
                                        "description": conflict_details.get('description', 'Schema/documentation mismatch detected'),
                                        "expected": conflict_details.get('expected', 'Unknown'),
                                        "actual": conflict_details.get('actual', 'Unknown'),
                                        "root_cause": "API documentation does not match actual behavior"
                                    }
                                ],
                                summary=f"Documentation conflict detected at step {step_order}: {conflict_details.get('description', 'Schema mismatch')}"
                            )
                            
                            # Track recovery strategies
                            self.planning_collector.set_recovery_strategies(
                                test_case_id=test_case_id,
                                automated=[
                                    {
                                        "strategy": "User approval",
                                        "description": "Wait for user to review and approve the corrected expected value",
                                        "success_rate": 0.95
                                    }
                                ],
                                escalation=[
                                    {
                                        "action": "Manual review",
                                        "reason": "User must decide if schema or test expectation is correct",
                                        "priority": "high"
                                    }
                                ]
                            )
                            
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
                
                # Phase 1: Validate the step
                validation_result = self.validator.validate_step(current_step)
                if not validation_result.is_valid:
                    self.logger.warning(f"⚠️ Step {step_order} validation failed: {validation_result.errors}")
                else:
                    self.logger.info(f"✓ Step {step_order} validation passed (confidence: {validation_result.confidence:.1f}%)")
                
                # Save validation result
                self.validator.save_validation_result(test_case_id, current_step.get('id', step_order), validation_result)
                
                # Phase 1: Score confidence
                confidence_score = self.scorer.score_step(current_step)
                self.logger.info(f"📊 Step {step_order} confidence: {confidence_score.overall_confidence:.1f}% ({confidence_score.risk_level} risk)")
                
                # Save confidence score
                self.scorer.save_confidence_score(test_case_id, confidence_score)
                
                # Log recommendations if any
                if confidence_score.recommendations:
                    for rec in confidence_score.recommendations:
                        self.logger.info(f"💡 Recommendation: {rec}")
                
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
            
            # Don't update description - preserve user's original input
            if generated_steps:
                self.logger.info(f"📝 Final: {len(generated_steps)} total steps saved (description preserved)")
            else:
                self.logger.warning(f"⚠️ No steps generated")
            
            # ==================== PHASE 2: MULTI-TURN REASONING ====================
            # Add reasoning traces for debugging
            # Build step details string
            step_details = []
            for i, s in enumerate(generated_steps, 1):
                step_order = s.get('step_order', i)
                method = s.get('description', {}).get('method', 'unknown')
                endpoint = s.get('description', {}).get('endpoint', 'unknown')
                step_details.append(f"Step {step_order}: {method} {endpoint}")
            
            self.planning_collector.add_reasoning_trace(
                test_case_id=test_case_id,
                message=f"Generated {len(generated_steps)} API test steps",
                trace_type="success",
                details=f"Steps: {', '.join(step_details)}"
            )
            
            # Add tool usage for schema analysis
            self.planning_collector.add_tool_usage(
                test_case_id=test_case_id,
                tool_name="SchemaAnalyzer",
                description="Analyzed API schema to identify endpoints and operations",
                status="completed",
                result=f"Identified {len(schema_summary.split('Endpoint:'))} endpoints"
            )
            
            # Add tool usage for test generation
            self.planning_collector.add_tool_usage(
                test_case_id=test_case_id,
                tool_name="GeminiAI",
                description="Generated test steps using AI analysis",
                status="completed",
                result=f"Generated {len(generated_steps)} test steps with validation"
            )
            
            # ==================== PHASE 3: PLAN SUMMARY ====================
            # Calculate average confidence from generated steps
            avg_confidence = 0
            if generated_steps:
                total_confidence = sum([s.get('confidence', 75) for s in generated_steps])
                avg_confidence = total_confidence / len(generated_steps)
            
            # Set plan summary
            self.planning_collector.set_plan_summary(
                test_case_id=test_case_id,
                total_steps=len(generated_steps),
                estimated_duration=f"{len(generated_steps) * 2}-{len(generated_steps) * 5} seconds",
                test_type="api",
                execution_plan=f"Execute {len(generated_steps)} API test steps sequentially with request/response validation. Average confidence: {avg_confidence:.1f}%"
            )
            
            self.logger.info(f"✅ Iterative generation complete: {len(generated_steps)} steps generated")
            return True
            
        except Exception as e:
            self.logger.error(f"❌ Error in iterative generation: {str(e)}", exc_info=True)
            return False
    
    def _generate_first_step(self, test_case_name: str, test_case_description: str, schema_summary: str, client_id: str = None, generation_job_id: str = None) -> dict:
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
6. **CRITICAL - DYNAMIC DATA PLACEHOLDERS**: NEVER use hardcoded values - use dynamic placeholders:
   
   A. ENVIRONMENT VARIABLES:
      - %base_url% - API base URL
      - %login% - Username/email from environment
      - %password% - Password from environment
      - %auth_token% - Extracted authentication token
   
   B. UNIQUE IDENTIFIERS (cached per test run):
      - %unique_name% - Random unique ID (e.g., "a7b3c9d2")
      - %unique_name:Client% - With prefix (e.g., "Client_a7b3c9d2")
      - %timestamp_name% - Timestamp-based (e.g., "20250129_143052")
   
   C. REALISTIC PERSONAL DATA:
      - %random_name% - Full name (e.g., "John Smith")
      - %random_first_name% - First name (e.g., "John")
      - %random_last_name% - Last name (e.g., "Smith")
      - %random_email% - Email (e.g., "john.smith@example.com")
      - %random_username% - Username (e.g., "john_smith_123")
      - %random_phone% - Phone number (e.g., "+1-555-234-5678")
   
   D. REALISTIC LOCATION DATA:
      - %random_address% - Street address
      - %random_city% - City name
      - %random_country% - Country name
   
   E. REALISTIC BUSINESS DATA:
      - %random_company% - Company name (e.g., "Acme Corporation")
      - %random_job_title% - Job title (e.g., "Software Engineer")
   
   F. TECHNICAL DATA:
      - %random_string% - Alphanumeric string (10 chars)
      - %random_number% - Number (1-10000)
      - %random_url% - URL
      - %random_uuid% - Full UUID
      - %random_date% - Date (YYYY-MM-DD)
      - %random_boolean% - true/false
   
   USAGE EXAMPLES FOR API REQUESTS:
      ❌ WRONG: {{"name": "Test Client", "email": "test@test.com", "phone": "555-1234"}}
      ✅ CORRECT: {{"name": "%random_company%", "email": "%random_email%", "phone": "%random_phone%"}}
      
      ❌ WRONG: {{"firstName": "John", "lastName": "Doe", "city": "New York"}}
      ✅ CORRECT: {{"firstName": "%random_first_name%", "lastName": "%random_last_name%", "city": "%random_city%"}}
      
      ❌ WRONG: {{"username": "testuser", "password": "pass123"}}
      ✅ CORRECT: {{"username": "%random_username%", "password": "%random_string%"}}
   
   WHEN TO USE:
      - For "name" fields (clients, companies, groups): Use %random_company% (generates "Acme Corporation" - alphabetic only)
      - For entity names needing consistency across steps: Use %unique_name:Type% (but may contain underscores/numbers)
      - For email fields: Use %random_email%
      - For phone fields: Use %random_phone%
      - For address fields: Use %random_address%, %random_city%, %random_country%
      - IDs will be extracted from responses, NOT hardcoded
      
      ⚠️ IMPORTANT: If API requires "alphabetic characters only", use %random_company% NOT %unique_name%

EXAMPLES FOR VARIABLE EXTRACTION:
Expected response: {{"client": {{"id": 49, "name": "Test"}}}}
✅ CORRECT: "extract_variables": {{"client_id": "$.client.id"}}
❌ WRONG: "extract_variables": {{"client_id": "$.id"}}

Expected response: {{"token": "eyJ0eXAi..."}}
✅ CORRECT: "extract_variables": {{"auth_token": "$.token"}}

Return ONLY a single JSON object (not an array) with this structure:
{example_json}

Return ONLY the JSON object, no explanation.
"""
        
        response = self.ai_helper.send_request_to_gemini(
            prompt=prompt,
            text_content=schema_summary,
            request_type='api_test',
            request_context='test_case_first_step_generation',
            client_id=client_id,
            generation_job_id=generation_job_id
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
        extracted_variables: dict = None,
        client_id: str = None,
        generation_job_id: str = None
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

**CRITICAL - HOW TO FIX DATA VALIDATION ERRORS:**

1. "only alphabetic characters" ERROR:
   ❌ WRONG: "name": "TestClient%random_first_name%"  → "TestClientJohn" (mixed chars!)
   ❌ WRONG: "name": "%unique_name:Client%"  → "Client_a7b3c9d2" (underscore/numbers!)
   ✅ CORRECT: "name": "%random_company%"  → "AcmeCorporation" (letters only, no spaces/hyphens!)

2. "international number format" ERROR:
   ❌ WRONG: Leave phone as is → Will fail again
   ✅ CORRECT: Use %random_phone% placeholder → Generates "+12025551234" (E.164 format - clean digits only)
   
3. Other validation errors:
   - If ANY field validation fails → Use the appropriate %random_*% placeholder
   - Don't try to fix data manually, use placeholders that generate correct format

Other common errors:
  - 400 "Missing required field" → Add the missing field to request body
  - 401 "Unauthorized" → Check authentication token is included
  - 404 "Not found" → Check the URL path and ID are correct

Available variables (use these EXACT variable names in your step):
""" + available_vars_text + """

IMPORTANT: Use the EXACT variable names listed above (e.g., %auth_token%, NOT %token%)

**DYNAMIC DATA PLACEHOLDERS** - Use these for realistic test data:

A. UNIQUE IDENTIFIERS (cached per test run):
   - %unique_name% - Random unique ID (e.g., "a7b3c9d2")
   - %unique_name:Client% - With prefix (e.g., "Client_a7b3c9d2")
   - %timestamp_name% - Timestamp-based (e.g., "20250129_143052")

B. REALISTIC PERSONAL DATA:
   - %random_name% - Full name (e.g., "John Smith")
   - %random_first_name% - First name (e.g., "John")
   - %random_last_name% - Last name (e.g., "Smith")
   - %random_email% - Email (e.g., "john.smith@example.com")
   - %random_username% - Username (e.g., "john_smith_123")
   - %random_phone% - Phone number (e.g., "+1-555-234-5678")

C. REALISTIC LOCATION DATA:
   - %random_address% - Street address
   - %random_city% - City name
   - %random_country% - Country name

D. REALISTIC BUSINESS DATA:
   - %random_company% - Company name (e.g., "Acme Corporation")
   - %random_job_title% - Job title (e.g., "Software Engineer")

E. TECHNICAL DATA:
   - %random_string% - Alphanumeric string (10 chars)
   - %random_number% - Number (1-10000)
   - %random_url% - URL
   - %random_uuid% - Full UUID
   - %random_date% - Date (YYYY-MM-DD)
   - %random_boolean% - true/false

USAGE EXAMPLES:
   ❌ WRONG: {"name": "Test Client", "email": "test@test.com"}
   ✅ CORRECT: {"name": "%random_company%", "email": "%random_email%"}

⚠️ CRITICAL - PLACEHOLDER SELECTION:
   - For "name" fields that must be ALPHABETIC ONLY → Use %random_company% (generates "Acme Corporation")
   - For "name" fields that allow special chars → Use %unique_name:Client% (generates "Client_a7b3c9d2")
   - For email fields → Use %random_email% (generates "john.smith@example.com")
   - For phone fields → Use %random_phone% (generates "+1-555-234-5678")
   - For address fields → Use %random_address%, %random_city%, %random_country%
   
   IF API REJECTS with "only alphabetic characters" error:
   ✅ FIX: Change %unique_name:Client% to %random_company%

Rules:
1. **IF LAST STEP FAILED**: Fix the error and retry the same operation (don't move to next step)
2. Use variables extracted from previous steps (e.g., %auth_token%, %client_id%)
3. Use EXACT HTTP methods from the schema
4. Use EXACT field names from "Request Body Fields:" section
5. **FOLLOW THE ENTIRE DESCRIPTION**: Compare the execution history against the test description above. Count how many steps from the description have been completed. If ALL steps from the description are done, return {"complete": true}. Otherwise, generate the NEXT step from the description.
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
            text_content=schema_summary,
            request_type='api_test',
            request_context=f'test_case_step_generation',
            client_id=client_id,
            generation_job_id=generation_job_id
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
                    custom_vars_raw = env[3] or {}
            
            # Build variable context
            # Ensure custom_variables is a dict before unpacking
            # It might be a list or have authorization_headers at top level
            if isinstance(custom_vars_raw, dict):
                # If it has authorization_headers, extract only the custom variables (not the headers array)
                custom_vars = {k: v for k, v in custom_vars_raw.items() if k != 'authorization_headers' and not isinstance(v, list)}
            else:
                self.logger.warning(f"custom_variables is not a dict (type: {type(custom_vars_raw)}), using empty dict")
                custom_vars = {}
            
            variables = {
                'base_url': base_url,
                'login': login,
                'password': password,
                **custom_vars
            }
            
            # Merge previously extracted variables
            if extracted_variables:
                variables.update(extracted_variables)
            
            # Initialize EnvHelper for placeholder processing
            env_helper = EnvHelper(environment_vars={
                'base_url': base_url,
                'login': login,
                'password': password
            })
            
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
            
            # First, use EnvHelper to process ALL placeholders (including dynamic ones like %random_company%)
            endpoint = env_helper.process_variables(endpoint)
            
            # Then substitute extracted variables (like %auth_token%, %client_id%)
            for var_name, var_value in variables.items():
                endpoint = endpoint.replace(f'%{var_name}%', str(var_value))
            
            # Process headers
            headers_str = json.dumps(headers)
            headers_str = env_helper.process_variables(headers_str)  # Process dynamic placeholders first
            for var_name, var_value in variables.items():
                headers_str = headers_str.replace(f'%{var_name}%', str(var_value))
            headers = json.loads(headers_str)
            
            # Process body
            if body:
                body_str = json.dumps(body)
                body_str = env_helper.process_variables(body_str)  # Process dynamic placeholders first
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
                    response_body,
                    client_id
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
            # ==================== PHASE 2: MULTI-TURN REASONING ====================
            # Record ReAct trace for this step
            self.planning_collector.add_react_trace(
                test_case_id=test_case_id,
                thought=f"Generating step {step['step_order']}: {step.get('summary', 'API request')}",
                action="generate_api_step",
                action_params={
                    "method": step.get('description', {}).get('method', 'GET'),
                    "endpoint": step.get('description', {}).get('endpoint', ''),
                    "step_order": step['step_order']
                },
                observation=f"Generated {step.get('action', 'api_request')} step",
                reflection="Step generated and ready for execution"
            )
            
            # Record tool usage
            self.planning_collector.add_tool_usage(
                test_case_id=test_case_id,
                tool_name="generate_api_step",
                description="Generates API test steps from schema",
                status="completed",
                result=f"Step {step['step_order']} generated successfully"
            )
            
            # Record reasoning trace
            self.planning_collector.add_reasoning_trace(
                test_case_id=test_case_id,
                message=f"Generated step {step['step_order']}: {step.get('action', 'api_request')}",
                trace_type="success",
                details=f"Method: {step.get('description', {}).get('method', 'GET')}"
            )
            
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
            # Record error in planning
            self.planning_collector.add_reasoning_trace(
                test_case_id=test_case_id,
                message=f"Error saving step: {str(e)}",
                trace_type="error",
                details=str(e)
            )
    
    def _validate_error_response(self, test_case_id: int, step: dict, status_code: int, response_body, client_id: str = None) -> bool:
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
                text_content=None,
                request_type='api_execution',
                request_context=f'test_case_{test_case_id}_error_validation',
                client_id=client_id  # client_id is a UUID string, not int
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
        """Determine if the test flow is complete by asking Gemini to compare execution against description."""
        if not execution_history:
            return False
        
        # Build execution summary
        summary_parts = []
        for i, exec_result in enumerate(execution_history, 1):
            summary = exec_result.get('step', {}).get('summary', 'API Request')
            status = exec_result['response']['status']
            summary_parts.append(f"{i}. {summary} (Status: {status})")
        
        execution_summary = '\n'.join(summary_parts)
        
        # Ask Gemini if all steps from description are complete
        prompt = f"""Compare the test description against what has been executed.

Test Description:
{test_case_description}

Steps Executed So Far:
{execution_summary}

Question: Have ALL steps described in the test description been completed?
- Count the steps in the description
- Count the steps executed
- Compare if they match

Answer ONLY with "COMPLETE" if all steps are done, or "CONTINUE" if more steps are needed.
Just one word, nothing else."""

        try:
            # Call Gemini directly for raw text response (not JSON)
            import google.generativeai as genai
            genai.configure(api_key=self.ai_helper.gemini_api_key)
            model_id = self.ai_helper._get_model_id()
            model = genai.GenerativeModel(model_id)
            
            response = model.generate_content(prompt)
            
            if response and response.text:
                answer = response.text.strip().upper()
                self.logger.info(f"🤖 Gemini completion check: {answer}")
                return "COMPLETE" in answer
        except Exception as e:
            self.logger.warning(f"Failed to check completion with Gemini: {str(e)}")
        
        # Fallback: never assume complete, keep generating
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

**IMPORTANT - DO NOT REPORT AS CONFLICT:**
❌ Data validation errors that can be fixed by changing the request data:
   - "Name should contain only alphabetic characters" → NOT a conflict, fix by using better data
   - "Country should contain only alphabetic characters" → NOT a conflict, fix by using better data
   - "Email format is invalid" → NOT a conflict, fix by using valid email
   - "Field is required" → NOT a conflict, fix by adding the field
   - ANY validation error about data format/content → NOT a conflict

✅ ONLY report as conflict if:
   - The request data is VALID according to documentation requirements
   - The documentation explicitly specifies a different status code or response format
   - The API behavior contradicts what the documentation says it should do
   - This is NOT a test case expecting an error (like testing invalid credentials)
   
Example of TRUE conflict: Documentation says "returns 404 if not found" but API returns 500
Example of NOT conflict: API returns 500 "Name should contain only alphabetic characters" - this is a data validation issue

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
                text_content=None,
                request_type='api_execution',
                request_context=f'test_case_{test_case_id}_conflict_detection'
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
