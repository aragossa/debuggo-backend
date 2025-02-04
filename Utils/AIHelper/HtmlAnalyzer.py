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
            self.logger = logging.getLogger(__name__)
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

    def html_analyzer(self, test_case_id: int, html_code: str, test_name: str, test_description: str, step_order: int,
                      next_prompt: str, prev_step_description: str) -> tuple[str, str, str, str, str, str]:
        self.logger.info("Sending request to AI provider for HTML analysis.")
        prompt = self.get_analyze_html_prompt(
            html_code=html_code,
            test_name=test_name,
            test_description=test_description,
            step_order=step_order,
            next_prompt=next_prompt,
            prev_step_description=prev_step_description
        )


        if self.provider == "gemini":
            self.logger.info("Sending request to Gemini")
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