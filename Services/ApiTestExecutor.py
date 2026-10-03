import json
import logging
import re
import requests
from datetime import datetime
from typing import Dict, Any, Optional, List
from auroqa.Utils.Connectors.db_utils import get_db_connection_context
from auroqa.Utils.System import System
from auroqa.Services.VariableManager import VariableManager
from auroqa.Utils.Environments import api_base_url


class ApiTestExecutor:
    """
    Executor for API test cases. Handles authentication, request execution,
    variable substitution, and response validation.
    """
    
    def __init__(self, test_case_id: int, environment_vars: Dict[str, Any] = None, 
                 client_id: Optional[str] = None, project_id: Optional[str] = None, 
                 environment_id: Optional[int] = None):
        self.test_case_id = test_case_id
        self.environment_vars = environment_vars or {}
        self.session_variables = {}  # Store variables extracted during test execution
        self._env_helper = None
        self.test_run_id = None
        self.logger = self._setup_logger()
        self.system = System()
        
        # Phase 1.5: Variable scoping
        self.client_id = client_id
        self.project_id = project_id
        self.environment_id = environment_id
        self.variable_manager = VariableManager()
        self.logger.info(f"VariableManager initialized for scope - Client: {client_id}, Project: {project_id}, Environment: {environment_id}")
        
    def _setup_logger(self):
        """Setup logger for API test execution."""
        logger = logging.getLogger(f'ApiTestExecutor_{self.test_case_id}')
        logger.setLevel(logging.INFO)
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
    
    def execute_test_case(self, execution_id: Optional[int] = None) -> Dict[str, Any]:
        """
        Execute an API test case with all its steps.
        
        Args:
            execution_id: Optional execution ID to link this test run
            
        Returns:
            Dict with execution results
        """
        try:
            self.logger.info(f"Starting API test case execution: {self.test_case_id}")
            
            # Create test run record
            self.test_run_id = self._create_test_run(execution_id)
            
            # Get test steps from database
            steps = self._get_test_steps()
            
            if not steps:
                self.logger.warning(f"No test steps found for test case {self.test_case_id}")
                self._update_test_run('failed', 'No test steps found')
                return {
                    'success': False,
                    'test_run_id': self.test_run_id,
                    'error': 'No test steps found'
                }
            
            # Execute steps sequentially
            results = []
            for step in steps:
                # Track execution time
                import time
                start_time = time.time()
                
                step_result = self._execute_step(step)
                
                # Calculate execution time in milliseconds
                execution_time_ms = int((time.time() - start_time) * 1000)
                step_result['execution_time_ms'] = execution_time_ms
                
                results.append(step_result)
                
                # Save step execution result to database
                self._save_step_result(step, step_result)
                
                if not step_result['success']:
                    self.logger.error(f"Step {step['step_order']} failed: {step_result.get('error')}")
                    self._update_test_run('failed', step_result.get('error'))
                    return {
                        'success': False,
                        'test_run_id': self.test_run_id,
                        'error': step_result.get('error'),
                        'failed_step': step['step_order'],
                        'results': results
                    }
            
            # All steps passed
            self._update_test_run('passed', 'All steps completed successfully')
            self.logger.info(f"API test case {self.test_case_id} completed successfully")
            
            return {
                'success': True,
                'test_run_id': self.test_run_id,
                'results': results
            }
            
        except Exception as e:
            self.logger.error(f"Error executing API test case: {str(e)}", exc_info=True)
            if self.test_run_id:
                self._update_test_run('failed', str(e))
            return {
                'success': False,
                'test_run_id': self.test_run_id,
                'error': str(e)
            }
    
    def _execute_step(self, step: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute a single API test step.
        
        Step data is stored in the description field as JSON with structure:
        {
            "method": "POST",
            "endpoint": "/api/login",
            "headers": {"Content-Type": "application/json"},
            "body": {"username": "{{login}}", "password": "{{password}}"},
            "expected_status": 200,
            "extract_variables": {"access_token": "$.token"}
        }
        """
        try:
            step_order = step['step_order']
            action = step['action']
            
            self.logger.info(f"Executing step {step_order}: {action}")
            
            # The request is JSON in the description (how generated API steps store it) or,
            # when the description is plain text, in the value (the format of api_request steps in UI tests)
            step_data = None
            for field in ('description', 'value'):
                try:
                    parsed = json.loads(step.get(field) or '')
                except (json.JSONDecodeError, TypeError):
                    continue
                if isinstance(parsed, dict):
                    step_data = parsed
                    break
            if step_data is None:
                step_data = {'description': step['description']}
            
            # Handle different action types
            if action == 'api_request' or action == 'navigate':
                return self._execute_api_request(step, step_data)
            elif action == 'wait':
                return self._execute_wait(step, step_data)
            elif action == 'assert':
                return self._execute_assertion(step, step_data)
            else:
                self.logger.warning(f"Unknown action type: {action}, treating as API request")
                return self._execute_api_request(step, step_data)
                
        except Exception as e:
            self.logger.error(f"Error executing step {step.get('step_order')}: {str(e)}")
            return {
                'success': False,
                'step_order': step.get('step_order'),
                'error': str(e)
            }
    
    def _execute_api_request(self, step: Dict[str, Any], step_data: Dict[str, Any]) -> Dict[str, Any]:
        """Execute an HTTP API request."""
        try:
            # Extract request parameters
            method = step_data.get('method', 'GET').upper()
            endpoint = step_data.get('endpoint', step.get('element_path', ''))
            headers = step_data.get('headers', {})
            body = step_data.get('body', step_data.get('payload'))
            expected_status = step_data.get('expected_status', 200)
            extract_variables = step_data.get('extract_variables', {})
            
            # Log available variables before substitution
            self.logger.info(f"🔍 Available session variables: {list(self.session_variables.keys())}")
            if self.session_variables:
                self.logger.info(f"📦 Session variable values: {self.session_variables}")
            
            # Substitute variables in endpoint
            self.logger.info(f"🔧 Original endpoint: {endpoint}")
            endpoint = self._substitute_variables(endpoint)
            self.logger.info(f"🔧 After substitution: {endpoint}")
            
            # Build full URL: a relative endpoint goes to the environment's API address
            base_url = api_base_url(self.environment_vars)
            if not endpoint.startswith('http'):
                url = f"{base_url}{endpoint}"
            else:
                url = endpoint
            
            # Apply authorization headers from environment
            headers = self._apply_authorization_headers(headers)
            
            # Substitute variables in headers
            headers = {k: self._substitute_variables(v) for k, v in headers.items()}
            
            # Substitute variables in body
            if body:
                if isinstance(body, dict):
                    body = self._substitute_variables_in_dict(body)
                elif isinstance(body, str):
                    body = self._substitute_variables(body)
            
            # Get params if they exist
            params = step_data.get('params', {})
            if params:
                params = self._substitute_variables_in_dict(params)
            
            # Log the actual request details
            self.logger.info("=" * 80)
            self.logger.info(f"🌐 API REQUEST - Step {step['step_order']}")
            self.logger.info("=" * 80)
            self.logger.info(f"📍 URL: {url}")
            self.logger.info(f"🔧 Method: {method}")
            self.logger.info(f"📋 Headers: {headers}")
            if params:
                self.logger.info(f"🔗 Query Params: {params}")
            if body:
                self.logger.info(f"📦 Request Body: {body}")
            self.logger.info("=" * 80)
            
            # Make the request
            response = requests.request(
                method=method,
                url=url,
                headers=headers,
                params=params if params else None,
                json=body if isinstance(body, dict) else None,
                data=body if isinstance(body, str) else None,
                timeout=30
            )
            
            # Log response details
            self.logger.info("=" * 80)
            self.logger.info(f"📥 API RESPONSE - Step {step['step_order']}")
            self.logger.info("=" * 80)
            self.logger.info(f"✅ Status Code: {response.status_code}")
            self.logger.info(f"📄 Response Headers: {dict(response.headers)}")
            try:
                response_json = response.json()
                self.logger.info(f"📦 Response Body (JSON): {response_json}")
            except:
                self.logger.info(f"📦 Response Body (Text): {response.text[:500]}")
            self.logger.info("=" * 80)
            
            # Check expected status
            if response.status_code != expected_status:
                return {
                    'success': False,
                    'step_order': step['step_order'],
                    'error': f"Expected status {expected_status}, got {response.status_code}"
                             f" ({self._status_mismatch_hint(expected_status, response.status_code)})",
                    'response_status': response.status_code,
                    'response_body': response.text[:500]
                }
            
            # Compare the response with the values the step expects: {"$.name": "expected"}
            mismatches = self._response_mismatches(response, step_data.get('expect'))
            if mismatches:
                return {
                    'success': False,
                    'step_order': step['step_order'],
                    'error': "Response does not match: " + "; ".join(mismatches),
                    'response_status': response.status_code,
                    'response_body': response.text[:500]
                }
            
            # Extract variables from response
            if extract_variables:
                self._extract_response_variables(response, extract_variables)
            
            return {
                'success': True,
                'step_order': step['step_order'],
                'response_status': response.status_code,
                'response_body': response.text[:500],
                'actual_url': url,
                'method': method,
                'request_headers': headers,
                'request_body': body
            }
            
        except requests.exceptions.RequestException as e:
            self.logger.error(f"Network error: {str(e)}")
            # The usual cause on a local stand: the request leaves from the Debuggo server, not from the
            # user's machine or the test browser, so "localhost" is the server itself
            hint = ''
            if 'url' in locals() and re.match(r'https?://(localhost|127\.0\.0\.1)[:/]', url):
                hint = (" API requests are sent by the Debuggo server, where localhost is the server itself."
                        " Set the environment's API URL to an address the server can reach"
                        " (for an API on this machine: http://host.docker.internal:<port>).")
            return {
                'success': False,
                'step_order': step['step_order'],
                'error': f"Network error: cannot reach {url if 'url' in locals() else 'the API'}.{hint} Details: {str(e)}",
                'actual_url': url if 'url' in locals() else None,
                'method': method if 'method' in locals() else None
            }
        except Exception as e:
            self.logger.error(f"Error executing API request: {str(e)}")
            return {
                'success': False,
                'step_order': step['step_order'],
                'error': str(e),
                'actual_url': url if 'url' in locals() else None,
                'method': method if 'method' in locals() else None
            }
    
    @staticmethod
    def _status_mismatch_hint(expected: int, actual: int) -> str:
        """What an unexpected status most likely means: who has to change, the test or the API description."""
        try:
            expected, actual = int(expected), int(actual)
        except (TypeError, ValueError):
            return "unexpected status"
        if 200 <= actual < 300 and 200 <= expected < 300:
            return "the call succeeded with another success status: the expected status of the step or the API schema is out of date"
        if actual in (401, 403):
            return "not authorized: check the login step and the environment's login, password and role"
        if actual in (400, 422):
            return "the API rejected the request data: fix the body or parameters of the step, see the response"
        if actual == 404:
            return "not found: check the endpoint and the ids passed from earlier steps"
        if actual == 409:
            return "conflict: the item probably exists already, for example left by an earlier failed run"
        if actual >= 500:
            return "server error in the API under test, see the response"
        return "see the response"

    def _execute_wait(self, step: Dict[str, Any], step_data: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a wait step."""
        import time
        wait_seconds = int(step_data.get('seconds', step.get('value', 1)))
        self.logger.info(f"Waiting {wait_seconds} seconds")
        time.sleep(wait_seconds)
        return {
            'success': True,
            'step_order': step['step_order']
        }
    
    def _execute_assertion(self, step: Dict[str, Any], step_data: Dict[str, Any]) -> Dict[str, Any]:
        """Execute an assertion step."""
        # This can be extended for various assertion types
        return {
            'success': True,
            'step_order': step['step_order']
        }
    
    def _apply_authorization_headers(self, headers: Dict[str, str]) -> Dict[str, str]:
        """Apply authorization headers from environment configuration."""
        headers = headers.copy()
        
        # Get authorization headers from environment custom_variables
        custom_vars = self.environment_vars.get('custom_variables', {})
        # Ensure custom_variables is a dict, not a list
        if not isinstance(custom_vars, dict):
            self.logger.warning(f"custom_variables is not a dict, skipping authorization headers")
            return headers
        
        env_auth_headers = custom_vars.get('authorization_headers', [])
        
        if isinstance(env_auth_headers, list):
            for header in env_auth_headers:
                if isinstance(header, dict):
                    header_name = header.get('name', '').strip()
                    header_value = header.get('value', '').strip()
                    
                    # Skip empty headers
                    if not header_name or not header_value:
                        self.logger.warning(f"Skipping empty authorization header")
                        continue
                    
                    # Handle common token variable aliases
                    if '{{auth_token}}' in header_value and 'access_token' in self.session_variables:
                        header_value = header_value.replace('{{auth_token}}', str(self.session_variables['access_token']))
                        self.logger.info(f"Substituted {{{{auth_token}}}} with access_token from session")
                    elif '{{access_token}}' in header_value and 'auth_token' in self.session_variables:
                        header_value = header_value.replace('{{access_token}}', str(self.session_variables['auth_token']))
                    elif '{{token}}' in header_value and 'access_token' in self.session_variables:
                        header_value = header_value.replace('{{token}}', str(self.session_variables['access_token']))
                    
                    headers[header_name] = header_value
                    self.logger.info(f"Applied authorization header: {header_name} = {header_value[:20]}...")
        
        return headers
    
    def _substitute_variables(self, text: str) -> str:
        """Substitute variables in text with values from environment and session."""
        if not isinstance(text, str):
            return text
        
        result = text
        original = text
        
        # First, use EnvHelper to process all %placeholder% variables
        # This handles %random_name%, %random_email%, %unique_name:Type%, etc.
        # One helper per test run: a generated value (%random_email%, %unique_name%) is the same in every step
        if self._env_helper is None:
            from auroqa.Utils.BrowserAutomation.EnvHelper import EnvHelper
            self._env_helper = EnvHelper(self.environment_vars)
        result = self._env_helper.process_variables(result)
        
        # Phase 1.5: Use VariableManager for scoped variable substitution
        if self.variable_manager:
            result = self.variable_manager.substitute_variables(
                text=result,
                client_id=self.client_id,
                project_id=self.project_id,
                environment_id=self.environment_id,
                session_variables=self.session_variables
            )
        
        # Substitute built-in dynamic variables (support {{}} syntax for compatibility)
        import time
        import uuid
        if '{{timestamp}}' in result:
            timestamp = str(int(time.time()))
            result = result.replace('{{timestamp}}', timestamp)
        if '{{datetime}}' in result:
            from datetime import datetime
            dt = datetime.now().isoformat()
            result = result.replace('{{datetime}}', dt)
        if '{{uuid}}' in result:
            uuid_str = str(uuid.uuid4())
            result = result.replace('{{uuid}}', uuid_str)
        if '{{random}}' in result:
            import random
            rand = str(random.randint(1000, 9999))
            result = result.replace('{{random}}', rand)
        
        # Substitute environment variables (support both {{}} and %% syntax)
        for key, value in self.environment_vars.items():
            if key != 'custom_variables' and value is not None:  # Skip the custom_variables dict and unset values
                result = result.replace(f'{{{{{key}}}}}', str(value))
                result = result.replace(f'%{key}%', str(value))
        
        # Substitute session variables (extracted during test execution)
        for key, value in self.session_variables.items():
            result = result.replace(f'{{{{{key}}}}}', str(value))
            result = result.replace(f'%{key}%', str(value))
        
        # Debug log if substitution occurred
        if result != original:
            if '%' in original or '{{' in original:
                self.logger.debug(f"🔄 Variable substitution: '{original[:100]}...' → '{result[:100]}...'")
        
        return result
    
    def _substitute_variables_in_dict(self, data: Dict) -> Dict:
        """Recursively substitute variables in a dictionary."""
        result = {}
        for key, value in data.items():
            if isinstance(value, str):
                result[key] = self._substitute_variables(value)
            elif isinstance(value, dict):
                result[key] = self._substitute_variables_in_dict(value)
            elif isinstance(value, list):
                result[key] = [
                    self._substitute_variables(item) if isinstance(item, str)
                    else self._substitute_variables_in_dict(item) if isinstance(item, dict)
                    else item
                    for item in value
                ]
            else:
                result[key] = value
        return result
    
    def _extract_response_variables(self, response: requests.Response, extract_config: Dict[str, str]):
        """Extract variables from API response using JSONPath or simple key access."""
        try:
            response_data = response.json()
            self.logger.info(f"🔍 Extracting variables from response...")
            self.logger.info(f"📋 Extract config: {extract_config}")
            
            for var_name, path in extract_config.items():
                # Simple implementation - supports basic dot notation
                # For production, consider using jsonpath-ng library
                value = self._get_nested_value(response_data, path)
                if value is not None:
                    self.session_variables[var_name] = value
                    self.logger.info(f"✅ Extracted {var_name} = {str(value)[:50]}...")
                    
                    # Create token aliases for common authentication token names
                    # This ensures {{access_token}}, {{token}}, and {{auth_token}} all work
                    token_names = ['token', 'access_token', 'auth_token', 'accessToken', 'authToken']
                    if var_name in token_names:
                        for alias in token_names:
                            if alias != var_name:
                                self.session_variables[alias] = value
                        self.logger.info(f"🔑 Created token aliases: {', '.join(token_names)}")
                else:
                    self.logger.warning(f"❌ Could not extract {var_name} using path: {path}")
            
            self.logger.info(f"📦 Current session variables: {list(self.session_variables.keys())}")
                    
        except Exception as e:
            self.logger.warning(f"Could not extract variables from response: {str(e)}")
    
    def _response_mismatches(self, response: requests.Response, expect: Any) -> List[str]:
        """Differences between the response and the step's "expect" ({"$.path": value}); empty when it matches."""
        if not isinstance(expect, dict) or not expect:
            return []
        try:
            data = response.json()
        except ValueError:
            return ["the response is not JSON"]
        mismatches = []
        for path, expected in expect.items():
            if isinstance(expected, str):
                expected = self._substitute_variables(expected)
            actual = self._get_nested_value(data, path)
            if actual != expected and str(actual) != str(expected):
                mismatches.append(f"{path} is {json.dumps(actual)}, expected {json.dumps(expected)}")
        return mismatches

    def _get_nested_value(self, data: Any, path: str) -> Any:
        """Get nested value from dict using dot notation or JSONPath."""
        # Remove JSONPath prefix if present
        if path.startswith('$.'):
            path = path[2:]
        
        elif path.startswith('$'):
            path = path[1:]  # "$[0].id": the response is a list
        
        # Dot notation with list indexes: "data[0].id" -> data, 0, id
        keys = [key for key in re.split(r'\.|\[(\d+)\]', path) if key]
        value = data
        
        for key in keys:
            if isinstance(value, dict):
                value = value.get(key)
            elif isinstance(value, list) and key.isdigit() and int(key) < len(value):
                value = value[int(key)]
            else:
                return None
                
            if value is None:
                return None
        
        return value
    
    def _get_test_steps(self) -> List[Dict[str, Any]]:
        """Retrieve test steps from database."""
        with get_db_connection_context() as conn:
            with conn.cursor() as cursor:
                cursor.execute("""
                    SELECT id, test_case_id, step_order, description, action, 
                           element_path, value, expected_result
                    FROM test_steps
                    WHERE test_case_id = %s
                    ORDER BY step_order ASC
                """, (self.test_case_id,))
                
                rows = cursor.fetchall()
                
                steps = []
                for row in rows:
                    steps.append({
                        'id': row[0],
                        'test_case_id': row[1],
                        'step_order': row[2],
                        'description': row[3],
                        'action': row[4],
                        'element_path': row[5],
                        'value': row[6],
                        'expected_result': row[7]
                    })
                
                return steps
    
    def _create_test_run(self, execution_id: Optional[int] = None) -> int:
        """Create a test run record in the database."""
        with get_db_connection_context() as conn:
            with conn.cursor() as cursor:
                cursor.execute("""
                    INSERT INTO test_runs (test_case_id, run_date, result, execution_id)
                    VALUES (%s, %s, %s, %s)
                    RETURNING id
                """, (self.test_case_id, datetime.now(), 'running', execution_id))
                
                test_run_id = cursor.fetchone()[0]
                conn.commit()
                
                self.logger.info(f"Created test run {test_run_id}")
                return test_run_id
    
    def _update_test_run(self, result: str, error_message: Optional[str] = None):
        """Update test run with final result."""
        with get_db_connection_context() as conn:
            with conn.cursor() as cursor:
                cursor.execute("""
                    UPDATE test_runs
                    SET result = %s, exception = %s
                    WHERE id = %s
                """, (result, error_message, self.test_run_id))
                
                conn.commit()
                self.logger.info(f"Updated test run {self.test_run_id} with result: {result}")
    
    def _save_step_result(self, step: Dict[str, Any], step_result: Dict[str, Any]):
        """Save individual step execution result to database."""
        try:
            with get_db_connection_context() as conn:
                with conn.cursor() as cursor:
                    # Get step_id from the step
                    step_id = step.get('id')
                    if not step_id:
                        self.logger.warning(f"No step ID found for step {step.get('step_order')}")
                        return
                    
                    # Prepare result data
                    result_status = 'passed' if step_result.get('success') else 'failed'
                    error_message = step_result.get('error')
                    response_status = step_result.get('response_status')
                    response_body = step_result.get('response_body', '')
                    
                    # Truncate response body if too long (keep first 5000 chars)
                    if len(response_body) > 5000:
                        response_body = response_body[:5000] + '... (truncated)'
                    
                    # Prepare additional_info with actual URL and request details
                    import json
                    additional_info = {
                        'actual_url': step_result.get('actual_url'),
                        'method': step_result.get('method'),
                        'request_headers': step_result.get('request_headers'),
                        'request_body': step_result.get('request_body'),
                        'response_status': response_status,
                        'response_body': response_body
                    }
                    
                    # Get execution time
                    execution_time_ms = step_result.get('execution_time_ms')
                    
                    # Save to test_step_execution_results table
                    cursor.execute("""
                        INSERT INTO test_step_execution_results (
                            test_run_id, test_step_id, step_order, status, error_message, 
                            screenshot_path, additional_info, execution_time_ms
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    """, (
                        self.test_run_id,
                        step_id,
                        step.get('step_order', 1),
                        result_status,
                        f"Status: {response_status}\n\nResponse:\n{response_body}" if response_status else error_message,
                        None,  # No screenshot for API tests
                        json.dumps(additional_info),
                        execution_time_ms
                    ))
                    
                    conn.commit()
                    self.logger.debug(f"Saved step result for step {step_id}")
                    
        except Exception as e:
            self.logger.error(f"Error saving step result: {str(e)}")
            # Don't fail the test execution if saving result fails
            pass


def run_api_test_case(test_case_id: int, environment_vars: Optional[Dict[str, Any]] = None,
                      environment_id: Optional[int] = None, execution_id: Optional[int] = None,
                      quick_run_id: Optional[int] = None, suite_id: Optional[int] = None) -> Dict[str, Any]:
    """
    Run an API test case and, when it is part of a quick run or a plan run, log its result there.

    The single entry point for running an API test: the run endpoint and the plan engine both use it,
    so an API test behaves the same alone and inside a suite.
    """
    started_at = datetime.now()
    if not environment_vars:
        # Without a base URL every relative endpoint would fail with an unreadable network error
        result = {'success': False, 'test_run_id': None, 'error': 'API tests require an environment'}
    else:
        # In an API test %base_url% means the API: an environment that has a separate API address
        # (base_url is then the UI) must not send the requests to the UI
        environment_vars = {**environment_vars, 'base_url': api_base_url(environment_vars)}
        executor = ApiTestExecutor(test_case_id=test_case_id, environment_vars=environment_vars,
                                   environment_id=environment_id)
        result = executor.execute_test_case(execution_id=execution_id)

    if quick_run_id:
        try:
            from auroqa.Services.QuickRunService import QuickRunService
            completed_at = datetime.now()
            QuickRunService().log_test_run_result(
                run_id=quick_run_id,
                test_case_id=test_case_id,
                status='passed' if result.get('success') else 'failed',
                suite_id=suite_id,
                started_at=started_at,
                completed_at=completed_at,
                duration_seconds=(completed_at - started_at).total_seconds(),
                error_message=result.get('error')
            )
        except Exception as e:
            logging.getLogger('ApiTestExecutor').error(f"Failed to log API test {test_case_id} to run {quick_run_id}: {e}")

    return result
