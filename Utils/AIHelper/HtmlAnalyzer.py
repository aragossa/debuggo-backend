import sys

import psycopg2
import threading
from datetime import datetime
from typing import Dict, Any, Tuple

from Utils.AIHelper.AIHelper import AIHelper
from Utils.System import System
from contextlib import contextmanager
import logging

class HtmlAnalyzer(AIHelper):
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(HtmlAnalyzer, cls).__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self):
        if not self._initialized:
            super().__init__()
            self.system = System()
            self._initialized = True

    @contextmanager
    def get_db_connection(self):
        """Context manager for database connections."""
        connection = None
        try:
            connection = System.get_db_connection()
            yield connection
        finally:
            if connection:
                System._pool.putconn(connection)


    def add_step_to_history(self, test_case_id: int, step_data: dict):
        """Add a step to the test case history."""
        if test_case_id not in self._step_history:
            self._step_history[test_case_id] = []
        self._step_history[test_case_id].append(step_data)

    def get_step_history(self, test_case_id: int) -> list:
        """Get the step history for a test case."""
        return self._step_history.get(test_case_id, [])

    def clear_step_history(self, test_case_id: int):
        """Clear the step history for a test case."""
        if test_case_id in self._step_history:
            del self._step_history[test_case_id]
    
    def _parse_json_response(self, response):
        """
        Parse JSON response from AI, handling various formats.
        
        Args:
            response: The AI response string or already parsed object
            
        Returns:
            Parsed JSON object/array
        """
        import json
        import re
        
        # If it's already parsed (list/dict), return it as-is
        if isinstance(response, (list, dict)):
            return response
        
        # If it's not a string, convert it to string (but this should not happen in normal cases)
        if not isinstance(response, str):
            self.logger.warning(f"Response is not string or dict/list, converting from {type(response)}")
            response = str(response)
        
        # Check if it's a string representation of a Python list/dict (from str(list) or str(dict))
        if response.startswith("[{") or response.startswith("{"):
            try:
                # Try to evaluate as Python literal (safe for lists/dicts)
                import ast
                parsed_response = ast.literal_eval(response)
                return parsed_response
            except (ValueError, SyntaxError):
                pass
        
        try:
            # Try direct JSON parsing first
            return json.loads(response)
        except json.JSONDecodeError:
            # Try to extract JSON from code blocks
            json_match = re.search(r'```(?:json)?\s*(\{.*?\}|\[.*?\])\s*```', response, re.DOTALL)
            if json_match:
                try:
                    return json.loads(json_match.group(1))
                except json.JSONDecodeError:
                    pass
            
            # Try to find JSON-like content without code blocks
            json_match = re.search(r'(\{.*?\}|\[.*?\])', response, re.DOTALL)
            if json_match:
                try:
                    return json.loads(json_match.group(1))
                except json.JSONDecodeError:
                    pass
            
            # If all else fails, raise an error
            raise ValueError(f"Could not parse JSON from response: {response[:200]}...")
        
        except Exception as e:
            self.logger.error(f"Error parsing JSON response: {e}")
            raise e

    def html_analyzer(self, test_case_id: int, html_code: str, test_name: str, test_description: str, step_order: int,
                      next_prompt: str, prev_step_description: str, screenshot_path: str = None) -> tuple[str, str, str, str, str, str]:
        self.logger.info("Sending request to AI provider for HTML analysis.")
        prompt = self.get_analyze_html_prompt(
            html_code=html_code,
            test_name=test_name,
            test_description=test_description,
            step_order=step_order,
            next_prompt=next_prompt,
            prev_step_description=prev_step_description,
            attached_screenshot=screenshot_path
        )
        self.logger.info(f"The screenshot path {screenshot_path}")
        image = False
        if screenshot_path:
            self.logger.info(f"Reading the screenshot {screenshot_path}")
            image = self.read_img(screenshot_path)

        if self.provider == "gemini":
            if image:
                self.logger.info("Sending request to Gemini with image")
                response = self.send_request_to_gemini(prompt, image)
            else:
                self.logger.info("Sending request to Gemini without image")
                response = self.send_request_to_gemini(prompt)
            self.logger.info("=== HTML ANALYZER RESPONSE START ===")

            # Validate required keys
            required_keys = ['element_locator', 'by_strategy', 'action', 'element_purpose', 'next_step', 'value']
            missing_keys = [k for k in required_keys if k not in response]
            if missing_keys:
                self.logger.warning(f"Missing required keys in response: {missing_keys}")
                # Set default values for missing keys
                for key in missing_keys:
                    response[key] = ''

            # Normalize by_strategy to match database constraints
            if response['by_strategy'].lower() not in ['css', 'xpath']:
                response['by_strategy'] = 'xpath'  # Default to xpath if invalid
            else:
                response['by_strategy'] = response['by_strategy'].lower()

            # Add step to history
            step_data = {
                'element_purpose': response['element_purpose'],
                'action': response['action'],
                'element_locator': response['element_locator'],
                'by_strategy': response['by_strategy'],
                'value': response['value'],
                'next_step': response['next_step']
            }

            self.add_step_to_history(test_case_id, step_data)

            # Return tuple in the expected order
            return (
                step_data['next_step'],
                step_data['element_purpose'],
                step_data['action'],
                step_data['element_locator'],
                step_data['by_strategy'],
                step_data['value']
            )
        elif self.provider == "claude":
            # Mock response for now
            return "Stop", "Mock purpose", "click", "#mock", "css", ""
        elif self.provider == "deepseek":
            # Mock response for now
            return "Stop", "Mock purpose", "click", "#mock", "css", ""
        else:
            raise ValueError(f"Unsupported AI provider: {self.provider}")

    def analyze_error(self, test_case_id: int, html_code: str, test_name: str, test_description: str, 
                     step_history: list, failed_step: dict, error_message: str, 
                     previous_attempts: list = None, screenshot_path: str = None) -> tuple[str, str, str, str, str, str]:
        """
        Analyze a test step failure and suggest a fix.
        
        Args:
            test_case_id: ID of the test case
            html_code: The HTML of the page when the error occurred
            test_name: The name of the test case
            test_description: The description of the test case
            step_history: List of previously executed steps
            failed_step: The step that failed
            error_message: The error message from the failed step
            previous_attempts: List of previous recovery attempts and their errors
            screenshot_path: Path to the screenshot of the failure state
            
        Returns:
            A tuple containing (next_step, element_purpose, action, element_locator, by_strategy, value)
        """
        self.logger.info("Sending request to AI provider for error analysis.")
        prompt = self.get_error_analysis_prompt(
            html_code=html_code,
            error_message=error_message,
            test_name=test_name,
            test_description=test_description,
            step_history=step_history,
            failed_step=failed_step,
            previous_attempts=previous_attempts,
            screenshot_path=screenshot_path
        )
        
        image = False
        if screenshot_path:
            self.logger.info(f"Reading the error screenshot {screenshot_path}")
            image = self.read_img(screenshot_path)
        
        if self.provider == "gemini":
            if image:
                self.logger.info("Sending error analysis request to Gemini with image")
                response = self.send_request_to_gemini(prompt, image)
            else:
                self.logger.info("Sending error analysis request to Gemini without image")
                response = self.send_request_to_gemini(prompt)
            
            self.logger.info("=== ERROR ANALYSIS RESPONSE START ===")
            
            # Validate required keys
            required_keys = ['analysis', 'element_locator', 'by_strategy', 'action', 'element_purpose', 'value', 'next_step']
            missing_keys = [k for k in required_keys if k not in response]
            if missing_keys:
                self.logger.warning(f"Missing required keys in error analysis response: {missing_keys}")
                # Set default values for missing keys
                for key in missing_keys:
                    response[key] = ''
            
            # Normalize by_strategy to match database constraints
            if response['by_strategy'].lower() not in ['css', 'xpath']:
                response['by_strategy'] = 'xpath'  # Default to xpath if invalid
            else:
                response['by_strategy'] = response['by_strategy'].lower()
            
            # Log the analysis
            self.logger.info(f"Error analysis: {response['analysis']}")
            
            # Return tuple in the expected order
            return (
                response['next_step'],
                response['element_purpose'],
                response['action'],
                response['element_locator'],
                response['by_strategy'],
                response['value']
            )
        else:
            raise ValueError(f"Unsupported AI provider for error analysis: {self.provider}")

    def check_preconditions_needed(self, test_case_name, test_case_description, force_preconditions=False):
        """
        Use Gemini to determine if a UI test case needs API preconditions
        """
        if force_preconditions:
            return {
                "needs_preconditions": True,
                "reason": "User explicitly requested preconditions"
            }
        
        prompt = f"""
        Analyze this UI test case and determine if it needs API preconditions (data setup) before testing:

        Test Case Name: {test_case_name}
        Test Case Description: {test_case_description or "No description provided"}

        Consider these scenarios that typically need preconditions:
        1. Testing features that require existing data (viewing lists, editing records, etc.)
        2. Testing user-specific functionality (user profiles, dashboards, etc.) 
        3. Testing workflows that depend on pre-existing entities
        4. Testing pages that show dynamic content based on database data

        Scenarios that typically DON'T need preconditions:
        1. Testing login/registration flows
        2. Testing static pages or landing pages
        3. Testing form validation without submission
        4. Testing navigation or UI elements

        Respond in JSON format:
        {{
            "needs_preconditions": true/false,
            "reason": "Brief explanation of why preconditions are or are not needed",
            "suggested_entities": ["entity1", "entity2"] // Only if needs_preconditions is true
        }}

        Be conservative - only return true if preconditions are clearly needed.
        """
        
        try:
            response = self.get_ai_response(prompt)
            return self._parse_json_response(response)
        except Exception as e:
            self.logger.error(f"Error checking preconditions: {e}")
            return {
                "needs_preconditions": False,
                "reason": f"Error during analysis: {str(e)}"
            }

    def analyze_page_elements(self, page_source: str, page_url: str = None) -> list:
        """
        Analyze HTML page source and generate test steps.
        This method is called by CombinedTestGenerationService for UI test generation.
        
        Args:
            page_source: HTML source code of the page
            page_url: URL of the page (optional)
            
        Returns:
            list: List of test step dictionaries in database format
        """
        try:
            # Create a prompt for AI to analyze the page and generate UI test steps
            prompt = f"""
            Analyze this HTML page source and generate UI test steps for automation testing.
            
            Page URL: {page_url or 'Unknown'}
            
            HTML Content:
            {page_source[:5000]}  # Limit to first 5000 chars to avoid token limits
            
            Generate 3-5 meaningful UI test steps that would verify this page works correctly.
            Focus on key interactive elements like forms, buttons, links, and important content.
            
            VERIFICATION REQUIREMENTS:
            - Each workflow should include verification steps (assert_text_contains)
            - Form submissions should verify success messages or result pages
            - Navigation should verify correct page/section loaded
            - Interactive elements should verify expected responses
            
            Return a JSON array of steps, each with:
            - action: The action to perform. Valid actions: click, type, select, hover, wait, assert_text_contains, scroll, clear, navigate, press_key
            - target: CSS selector or element identifier 
            - element_path: Same as target
            - value: Text to enter (for type actions) or expected text (for assert_text_contains actions)
            - description: Human readable description including verification aspect
            - order: Step number (1, 2, 3, etc.)
            
            Example format:
            [
                {{
                    "action": "navigate",
                    "target": "{page_url or 'current_page'}",
                    "element_path": "{page_url or 'current_page'}",
                    "value": "",
                    "description": "Navigate to the page",
                    "order": 1
                }},
                {{
                    "action": "click",
                    "target": "button[type='submit']",
                    "element_path": "button[type='submit']",
                    "value": "",
                    "description": "Click the submit button",
                    "order": 2
                }},
                {{
                    "action": "assert_text_contains",
                    "target": "h1",
                    "element_path": "h1",
                    "value": "Welcome",
                    "description": "Verify page title contains 'Welcome'",
                    "order": 3
                }}
            ]
            """
            
            try:
                # Use the AI to generate meaningful test steps
                response = self.get_ai_response(prompt)
                parsed_response = self._parse_json_response(response)
                
                if isinstance(parsed_response, list) and len(parsed_response) > 0:
                    # Ensure each step has required fields
                    steps = []
                    for i, step in enumerate(parsed_response, 1):
                        if isinstance(step, dict):
                            # Map invalid actions to valid ones
                            action = step.get('action', 'click')
                            if action == 'verify':
                                action = 'assert_text_contains'
                            elif action == 'check':
                                action = 'assert'
                            elif action == 'validate':
                                action = 'assert'
                            
                            formatted_step = {
                                'step_number': i,
                                'action': action,
                                'target': step.get('target', ''),
                                'element_path': step.get('element_path', step.get('target', '')),
                                'value': step.get('value', ''),
                                'description': step.get('description', f'Step {i}'),
                                'order': step.get('order', i)
                            }
                            steps.append(formatted_step)
                    
                    if steps:
                        self.logger.info(f"Generated {len(steps)} UI test steps using AI analysis")
                        return steps
                        
            except Exception as ai_error:
                self.logger.warning(f"AI analysis failed: {ai_error}, falling back to basic step")
            
            # Fallback: create a basic navigation step if AI fails
            step = {
                'step_number': 1,
                'action': 'navigate',
                'target': page_url or 'current_page',
                'element_path': page_url or 'current_page', 
                'value': '',
                'description': f'Navigate to page: {page_url or "current page"}',
                'order': 1
            }
            
            return [step]
            
        except Exception as e:
            self.logger.error(f"Error in analyze_page_elements: {str(e)}")
            return []