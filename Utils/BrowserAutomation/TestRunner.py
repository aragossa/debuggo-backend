from datetime import datetime

from Utils.BrowserAutomation.BrowserAutomation import BrowserAutomation
from Utils.DbConnector import DbConnector


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

    def _connect_db(self):
        """Create database connection"""
        db = DbConnector()
        return db.get_connection()

    def _log_test_run(self, test_case_id: int, result: str, exception: str = None,
                      duration: float = None, stdout: str = None, stderr: str = None):
        """Log test run results to database"""
        with self._connect_db() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO test_runs 
                    (test_case_id, result, exception, duration, stdout, stderr)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    RETURNING id
                """, (test_case_id, result, exception, duration, stdout, stderr))
                self.test_run_id = cur.fetchone()[0]
                conn.commit()

    def _get_test_steps(self, test_case_id: int):
        """Retrieve test steps from database"""
        with self._connect_db() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT id, action, element_path, description, expected_result, value, path_type
                    FROM test_steps
                    WHERE test_case_id = %s
                    ORDER BY step_order
                """, (test_case_id,))
                return cur.fetchall()

    def execute_step(self, action: str, element_path: str = None, value: str = None, by_stategy: str = None):
        """
        'select', 'hover', 'assert', 'scroll', 'clear''
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
        else:
            raise ValueError(f"Unsupported action: {action}")

    def run_test_case(self, test_case_id: int):
        """
        Run a complete test case

        Args:
            test_case_id: ID of the test case to run
        """
        start_time = datetime.now()

        try:
            # Initialize browser

            self.browser = BrowserAutomation(headless=False)

            # Get and execute test steps
            steps = self._get_test_steps(test_case_id)
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

        except Exception as e:
            # Log failure
            duration = (datetime.now() - start_time).total_seconds()
            self._log_test_run(
                test_case_id=test_case_id,
                result="failure",
                exception=str(e),
                duration=duration
            )
            raise

        finally:
            if self.browser:
                self.browser.close()



if __name__ == "__main__":
    runner = TestRunner()
    runner.run_test_case(385)