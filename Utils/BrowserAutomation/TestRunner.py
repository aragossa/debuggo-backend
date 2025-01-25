import sys
from contextlib import contextmanager
from datetime import datetime
import logging

from Utils.AIHelper.HtmlAnalyzer import HtmlAlanyzer
from Utils.BrowserAutomation.BrowserAutomation import BrowserAutomation
from Utils.BrowserAutomation.EnvHelper import EnvHelper
from Utils.Connectors.DbConnector import DbConnector
from Utils.System import System


class TestRunner:
    def __init__(self):
        """
        Initialize TestRunner with database configuration

        Args:
            db_config: Dictionary containing database connection parameters
                      (host, database, user, password, port)
        """
        self.browser = None
        self.test_run_id = None
        self.logger = self._setup_logger()

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
        logger = logging.getLogger('TestRunner')
        logger.setLevel(logging.INFO)

        handler = logging.StreamHandler(sys.stdout)
        handler.setLevel(logging.INFO)
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(filename)s:%(lineno)d  - %(message)s')
        handler.setFormatter(formatter)
        logger.addHandler(handler)

        return logger

    def _connect_db(self):
        """Create database connection"""
        db = DbConnector()
        return db.get_connection()

    def _log_test_run(self, test_case_id: int, result: str, exception: str = None,
                      duration: float = None, stdout: str = None, stderr: str = None):
        """Log test run results to database"""
        with self.get_db_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute("""
                    INSERT INTO test_runs 
                    (test_case_id, result, exception, duration, stdout, stderr)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    RETURNING id
                """, (test_case_id, result, exception, duration, stdout, stderr))
                self.test_run_id = cursor.fetchone()[0]
                connection.commit()

    def _get_test_steps(self, test_case_id: int):
        """Retrieve test steps from database"""
        with self.get_db_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute("""
                    SELECT id, action, element_path, description, expected_result, value, path_type
                    FROM test_steps
                    WHERE test_case_id = %s
                    ORDER BY step_order
                """, (test_case_id,))
                return cursor.fetchall()

    def _get_test_case(self, test_case_id: int):
        with self.get_db_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute("""
                    SELECT name, description
                    FROM test_cases
                    WHERE id = %s
                """, (test_case_id,))
                return cursor.fetchone()

    def execute_step(self, action: str, element_path: str = None, value: str = None, by_stategy: str = None):
        """
        'select', 'hover', 'assert', 'scroll', 'clear'
        """
        if action == "navigate":
            self.browser.navigate(element_path)
        elif action == "click":
            self.browser.click(element_path, by_stategy)
        elif action == "type":
            self.browser.type_text(element_path, value, by_stategy)
        elif action == "wait":
            self.browser.wait_for_element(element_path, by_stategy)
        elif action == "press_key":
            self.browser.press_key(element_path, value, by_stategy)
        elif action == 'assert':
            self.browser.assert_element(element_path, value, by_stategy)
        else:
            raise ValueError(f"Unsupported action: {action}")

    def run_test_case(self, test_case_id: int):
        """
        Run a complete test case

        Args:
            test_case_id: ID of the test case to run
        """
        start_time = datetime.now()
        env = EnvHelper()

        try:
            # Initialize browser

            self.browser = BrowserAutomation(headless=True)

            # Get and execute test steps
            steps = self._get_test_steps(test_case_id)
            self.browser.navigate(url=env.base_url)
            for step in steps:
                step_id, action, element_path, description, expected_result, value, path_type = step
                self.execute_step(action, element_path, value, path_type)

            # Calculate duration and log success
            duration = (datetime.now() - start_time).total_seconds()
            self._log_test_run(
                test_case_id=test_case_id,
                result="success",
                duration=duration
            )
            result = '{"result": "Success"}'

        except Exception as e:
            # Log failure
            duration = (datetime.now() - start_time).total_seconds()
            self._log_test_run(
                test_case_id=test_case_id,
                result="failure",
                exception=str(e),
                duration=duration
            )
            result = '{"result": "Failed"}'
            raise

        finally:
            if self.browser:
                self.browser.close()
            return result


    def generate_test_steps(self, test_case_id: int):
        try:
            system = System()
            env = EnvHelper()
            html_analyzer = HtmlAlanyzer()
            self.browser = BrowserAutomation(headless=True)
            test_case_data = self._get_test_case(test_case_id=test_case_id)
            test_name = test_case_data[0]
            test_description = test_case_data[1]

            self.browser.navigate(url=env.base_url)
            step_order = 0
            page_source = self.browser.get_page_source()
            prev_step_description = ''
            next_prompt = ''
            while next_prompt != 'Stop':
                self.logger.info(f"next_prompt: {next_prompt}, condition: {next_prompt != 'Stop'}")
                next_step, element_purpose, action, element_locator, by_strategy = html_analyzer.html_analyzer(
                                            test_case_id=test_case_id,
                                            html_code=page_source,
                                            test_name=test_name,
                                            test_description=test_description,
                                            step_order=step_order,
                                            next_prompt=next_prompt,
                                            prev_step_description=prev_step_description
                )
                next_prompt = next_step
                prev_step_description = test_description
                self.execute_step(action, element_locator, "", by_strategy)
                self.logger.info(f"next_step: {next_prompt}, element_purpose: {element_purpose}, action: {action}, element_locator: {element_locator}, by_strategy: {by_strategy}, next_prompt: {next_prompt}")


                page_source = self.browser.get_page_source()
                step_order += 1


        except Exception as e:
            self.logger.error(e)

        finally:
            if self.browser:
                self.browser.close()
