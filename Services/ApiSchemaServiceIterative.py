"""
Helper methods for iterative API test step generation.
These methods are added to ApiSchemaService class.
"""

def _generate_first_step(self, test_case_name: str, test_case_description: str, schema_summary: str) -> dict:
    """Generate the first step (usually authentication if required)."""
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
5. Include extract_variables to capture values needed for next steps

Return ONLY a single JSON object (not an array) with this structure:
{{
    "action": "api_request",
    "description": {{
        "method": "POST or GET or PUT or DELETE",
        "endpoint": "{{{{base_url}}}}/exact/path/from/schema",
        "headers": {{"Content-Type": "application/json", "Accept": "application/json"}},
        "body": {{"field1": "value1"}},
        "expected_status": 200,
        "extract_variables": {{"variable_name": "$.json.path"}}
    }},
    "summary": "What this step does"
}}

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
    execution_history: list
) -> dict:
    """Generate the next step based on previous execution results."""
    
    # Build execution history summary
    history_text = []
    for i, exec_result in enumerate(execution_history, 1):
        req = exec_result['request']
        resp = exec_result['response']
        
        history_text.append(f"""
Step {i}:
  Request:
    Method: {req['method']}
    URL: {req['url']}
    Headers: {json.dumps(req['headers'], indent=4)}
    Body: {json.dumps(req['body'], indent=4) if req['body'] else 'None'}
  
  Response:
    Status: {resp['status']}
    Headers: {json.dumps(resp['headers'], indent=4)}
    Body: {json.dumps(resp['body'], indent=4) if resp['body'] else 'None'}
""")
    
    prompt = f"""
⚠️ ⚠️ ⚠️ CRITICAL WARNING ⚠️ ⚠️ ⚠️
THIS API DOES NOT FOLLOW STANDARD REST CONVENTIONS!
- Check the schema for EXACT HTTP methods (PUT vs POST)
- "/api/clients:" shows "PUT: Create a Client" → USE PUT, NOT POST
⚠️ ⚠️ ⚠️ END WARNING ⚠️ ⚠️ ⚠️

You are generating API test steps ONE AT A TIME with real execution feedback.

Test Case: {test_case_name}
Description: {test_case_description}

API Schema:
{schema_summary}

EXECUTION HISTORY (steps already executed):
{''.join(history_text)}

Based on the execution history above, generate the NEXT STEP to continue the test flow.

Rules:
1. Use variables extracted from previous steps (e.g., {{{{access_token}}}}, {{{{client_id}}}})
2. Use EXACT HTTP methods from the schema
3. Use EXACT field names from "Request Body Fields:" section
4. If the test flow is complete, return {{"complete": true}} instead of a step
5. Extract any IDs or values needed for subsequent steps

Return ONLY a single JSON object:
- If more steps needed: return step object like before
- If test complete: return {{"complete": true}}

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


def _parse_single_step_response(self, response: str) -> dict:
    """Parse a single step from Gemini response."""
    import json
    
    try:
        # Remove markdown code blocks if present
        response = response.strip()
        if response.startswith('```'):
            lines = response.split('\n')
            response = '\n'.join(lines[1:-1])
        
        # Parse JSON
        step = json.loads(response)
        return step
        
    except Exception as e:
        self.logger.error(f"Error parsing step response: {str(e)}")
        self.logger.debug(f"Response was: {response}")
        return None


def _execute_step_for_feedback(
    self,
    test_case_id: int,
    step: dict,
    project_id: str,
    client_id: str
) -> dict:
    """Execute a step and return request/response for feedback to Gemini."""
    import requests
    from Services.ApiTestExecutor import ApiTestExecutor
    
    try:
        # Get environment variables
        with get_db_connection_context() as conn:
            with conn.cursor() as cursor:
                cursor.execute("""
                    SELECT base_url, username, password, custom_variables
                    FROM project_environments
                    WHERE project_id = %s
                    LIMIT 1
                """, (project_id,))
                
                env = cursor.fetchone()
                if not env:
                    self.logger.error(f"No environment found for project {project_id}")
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
        
        # Get previously extracted variables from execution history
        with get_db_connection_context() as conn:
            with conn.cursor() as cursor:
                cursor.execute("""
                    SELECT description
                    FROM test_steps
                    WHERE test_case_id = %s
                    ORDER BY step_order
                """, (test_case_id,))
                
                # This is a simplified version - in reality we'd need to track
                # extracted variables from previous executions
                # For now, we'll just execute the step
        
        # Prepare request
        description = step.get('description', {})
        method = description.get('method', 'GET')
        endpoint = description.get('endpoint', '')
        headers = description.get('headers', {})
        body = description.get('body')
        
        # Substitute variables in endpoint
        for var_name, var_value in variables.items():
            endpoint = endpoint.replace(f'{{{{{var_name}}}}}', str(var_value))
        
        # Substitute variables in body
        if body:
            body_str = json.dumps(body)
            for var_name, var_value in variables.items():
                body_str = body_str.replace(f'{{{{{var_name}}}}}', str(var_value))
            body = json.loads(body_str)
        
        # Execute request
        self.logger.info(f"Executing: {method} {endpoint}")
        
        response = requests.request(
            method=method,
            url=endpoint,
            headers=headers,
            json=body,
            timeout=30
        )
        
        # Return execution result
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
                'body': response.json() if response.text else None
            }
        }
        
    except Exception as e:
        self.logger.error(f"Error executing step: {str(e)}")
        return None


def _save_single_step(self, test_case_id: int, step: dict, client_id: str):
    """Save a single step to the database."""
    try:
        with get_db_connection_context() as conn:
            with conn.cursor() as cursor:
                cursor.execute("""
                    INSERT INTO test_steps (
                        test_case_id, step_order, action, description,
                        expected_result, client_id
                    ) VALUES (%s, %s, %s, %s, %s, %s)
                """, (
                    test_case_id,
                    step['step_order'],
                    step.get('action', 'api_request'),
                    json.dumps(step.get('description', {})),
                    step.get('summary', ''),
                    client_id
                ))
            conn.commit()
            
    except Exception as e:
        self.logger.error(f"Error saving step: {str(e)}")


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
