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
            self.logger = self._setup_logger()
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

    def _setup_logger(self):
        logger = logging.getLogger('HtmlAnalyzer')
        logger.setLevel(logging.INFO)

        # Remove any existing handlers to prevent duplicate logging
        if logger.hasHandlers():
            logger.handlers.clear()

        handler = logging.StreamHandler(sys.stdout)
        handler.setLevel(logging.INFO)
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(filename)s:%(lineno)d  - %(message)s')
        handler.setFormatter(formatter)
        logger.addHandler(handler)

        return logger

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
            required_keys = ['element_locator', 'css_selector', 'by_strategy', 'action', 'element_purpose', 'next_step', 'value']
            missing_keys = [k for k in required_keys if k not in response]
            if missing_keys:
                self.logger.warning(f"Missing required keys in response: {missing_keys}")
                # Set default values for missing keys
                for key in missing_keys:
                    if key == 'css_selector':
                        response[key] = ''  # CSS selector is optional fallback
                    else:
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
                'css_selector': response.get('css_selector', ''),  # Get CSS selector
                'by_strategy': response['by_strategy'],
                'value': response['value'],
                'next_step': response['next_step']
            }

            self.add_step_to_history(test_case_id, step_data)

            # Return tuple in the expected order (now includes css_selector)
            return (
                step_data['next_step'],
                step_data['element_purpose'],
                step_data['action'],
                step_data['element_locator'],
                step_data['css_selector'],
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
            required_keys = ['analysis', 'element_locator', 'css_selector', 'by_strategy', 'action', 'element_purpose', 'value', 'next_step']
            missing_keys = [k for k in required_keys if k not in response]
            if missing_keys:
                self.logger.warning(f"Missing required keys in error analysis response: {missing_keys}")
                # Set default values for missing keys
                for key in missing_keys:
                    if key == 'css_selector':
                        response[key] = ''  # CSS selector is optional fallback
                    else:
                        response[key] = ''
            
            # Normalize by_strategy to match database constraints
            if response['by_strategy'].lower() not in ['css', 'xpath']:
                response['by_strategy'] = 'xpath'  # Default to xpath if invalid
            else:
                response['by_strategy'] = response['by_strategy'].lower()
            
            # Log the analysis
            self.logger.info(f"Error analysis: {response['analysis']}")
            
            # Return tuple in the expected order (now includes css_selector)
            return (
                response['next_step'],
                response['element_purpose'],
                response['action'],
                response['element_locator'],
                response.get('css_selector', ''),
                response['by_strategy'],
                response['value']
            )
        else:
            raise ValueError(f"Unsupported AI provider for error analysis: {self.provider}")