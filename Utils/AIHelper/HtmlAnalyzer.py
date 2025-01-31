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


    def save_step(self, test_case_id: int, step_order: int, element_purpose: str, action: str, element_locator: str, value: str, by_strategy: str) -> int:
        try:
            with self.get_db_connection() as connection:
                with connection.cursor() as cursor:
                    insert_query = """
                        INSERT INTO public.test_steps (
                            test_case_id,
                            step_order,
                            description,
                            action,
                            element_path,
                            value,
                            path_type,
                            created_at,
                            updated_at
                        ) VALUES (
                            %s, %s, %s, %s, %s, %s, %s, %s, %s
                        ) RETURNING id;
                    """

                    current_timestamp = datetime.now()

                    cursor.execute(
                        insert_query,
                        (
                            test_case_id,
                            step_order,
                            element_purpose,
                            action,
                            element_locator,
                            value,
                            by_strategy,
                            current_timestamp,
                            current_timestamp
                        )
                    )

                    new_step_id = cursor.fetchone()[0]
                    connection.commit()

                    self.logger.info(f"Successfully saved test step with ID: {new_step_id}")
                    return new_step_id

        except psycopg2.Error as e:
            self.logger.error(f"Database error while saving test step: {str(e)}")
            raise
        except Exception as e:
            self.logger.error(f"Unexpected error while saving test step: {str(e)}")
            raise


    def html_analyzer(self, test_case_id: int, html_code: str, test_name: str, test_description: str, step_order: int, next_prompt: str, prev_step_description: str) -> \
    tuple[Any, Any, Any, Any, Any]:

        self.logger.info("Sending request to AI provider for HTML analysis.")
        prompt = self.get_analyze_html_promt(html_code=html_code,
                                             test_name=test_name,
                                             test_description=test_description,
                                             step_order=step_order,
                                             next_prompt=next_prompt,
                                             prev_step_description=prev_step_description
                                             )


        if self.provider == "gemini":
            ai_response = self.send_request_to_gemini(prompt)
            # todo: implement sending request to chatgpt, claude
            # elif self.provider == "chatgpt":
            #     response = self._mock_response("ChatGPT", html_code, element_purpose)
            # elif self.provider == "claude":
            #     response = self._mock_response("Claude", html_code, element_purpose)

            element_purpose = ai_response['element_purpose']
            action = ai_response['action']
            element_locator = ai_response['element_locator']
            by_strategy = ai_response['by_strategy']
            value = ai_response['value']
            next_step = ai_response['next_step']

            self.save_step(test_case_id=test_case_id,
                           step_order=step_order,
                           element_purpose=element_purpose,
                           action=action,
                           element_locator=element_locator,
                           value=value,
                           by_strategy=by_strategy)
            self.logger.info(f"Received response from {self.provider}: {ai_response}")
            return next_step, element_purpose, action, element_locator, by_strategy
        else:
            raise ValueError(f"Unsupported AI provider: {self.provider}")
