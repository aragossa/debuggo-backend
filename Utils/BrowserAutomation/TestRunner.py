import sys
from contextlib import contextmanager
from datetime import datetime
import logging
import os
import redis
from redis.lock import Lock as RedisLock
from threading import Lock
import time
import multiprocessing
from datetime import timedelta
from Utils.AIHelper.HtmlAnalyzer import HtmlAlanyzer
from Utils.BrowserAutomation.BrowserAutomation import BrowserAutomation
from Utils.BrowserAutomation.EnvHelper import EnvHelper
from Utils.Connectors.DbConnector import DbConnector
from Utils.System import System


class TestRunner:
    _instance = None
    _lock = Lock()
    _redis = None
    _redis_lock = None
    _lock_key = "test_runner_lock"
    _lock_timeout = 300  # 5 minutes timeout

    def __new__(cls):
        pid = os.getpid()
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(TestRunner, cls).__new__(cls)
                cls._instance.browser = None
                cls._instance.test_run_id = None
                cls._instance.logger = cls._instance._setup_logger()
                cls._instance.logger.info(f"[PID:{pid}] Creating new TestRunner instance")
                
                # Initialize Redis connection
                system = System()
                try:
                    cls._instance._redis = redis.Redis(
                        host=system.redis_host,
                        port=system.redis_port,
                        decode_responses=True
                    )
                    cls._instance.logger.info(f"[PID:{pid}] Redis connection established")
                    
                    # Create a Redis lock
                    cls._instance._redis_lock = cls._instance._redis.lock(
                        cls._instance._lock_key,
                        timeout=cls._instance._lock_timeout,
                        blocking=True,
                        blocking_timeout=60
                    )
                    cls._instance.logger.info(f"[PID:{pid}] Redis lock created")
                except Exception as e:
                    cls._instance.logger.error(f"[PID:{pid}] Error initializing Redis: {e}")
                    raise
            else:
                cls._instance.logger.info(f"[PID:{pid}] Returning existing TestRunner instance")
            return cls._instance

    def __init__(self):
        """Initialize TestRunner. This will only run once due to singleton pattern."""
        pid = os.getpid()
        if not hasattr(self, '_initialized'):
            self.logger.info(f"[PID:{pid}] Initializing TestRunner")
            self._initialized = True
        else:
            self.logger.info(f"[PID:{pid}] TestRunner already initialized")

    def __del__(self):
        """Cleanup method to ensure browser is closed when TestRunner is destroyed"""
        pid = os.getpid()
        self.logger.info(f"[PID:{pid}] TestRunner instance being destroyed")
        self._cleanup_browser()

    @contextmanager
    def _process_lock(self):
        """Process-safe lock using Redis"""
        pid = os.getpid()
        acquired = False
        try:
            self.logger.info(f"[PID:{pid}] Attempting to acquire Redis lock")
            # Try to acquire lock with blocking
            acquired = self._redis_lock.acquire()
            if not acquired:
                self.logger.error(f"[PID:{pid}] Failed to acquire Redis lock after timeout")
                raise TimeoutError("Could not acquire lock for test execution")
            self.logger.info(f"[PID:{pid}] Successfully acquired Redis lock")
            yield
        finally:
            if acquired:
                try:
                    self._redis_lock.release()
                    self.logger.info(f"[PID:{pid}] Released Redis lock")
                except Exception as e:
                    self.logger.error(f"[PID:{pid}] Error releasing Redis lock: {e}")
            else:
                self.logger.warning(f"[PID:{pid}] No lock to release")

    def _cleanup_browser(self):
        """Helper method to cleanup browser instance"""
        pid = os.getpid()
        if self.browser:
            try:
                self.browser.close()
                self.logger.info(f"[PID:{pid}] Browser closed successfully")
            except Exception as e:
                self.logger.error(f"[PID:{pid}] Error closing browser: {e}")
            finally:
                self.browser = None
                self.logger.info(f"[PID:{pid}] Browser instance set to None")

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
        if action == "click":
            self.browser.click(element_path, by_stategy)
        elif action == 'navigate':
            self.browser.navigate(element_path)
        elif action == "type":
            self.browser.type_text(element_path, value, by_stategy)
        elif action == "wait":
            self.browser.wait_for_element(element_path, by_stategy)
        elif action == "press_key":
            self.browser.press_key(element_path, value, by_stategy)
        elif action == "assert":
            self.browser.assert_element(element_path, value, by_stategy)
        elif action == "hover":
            self.browser.hover(element_path, by_stategy)
        else:
            raise ValueError(f"Unsupported action: {action}")

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

    def run_test_case(self, test_case_id: int):
        """
        Run a complete test case

        Args:
            test_case_id: ID of the test case to run
        """
        pid = os.getpid()
        self.logger.info(f"[PID:{pid}] Starting test case execution for ID: {test_case_id}")
        start_time = datetime.now()
        env = EnvHelper()

        with self._process_lock():
            try:
                # Initialize browser
                self.logger.info(f"[PID:{pid}] Cleaning up any existing browser instance")
                self._cleanup_browser()
                
                self.logger.info(f"[PID:{pid}] Creating new browser instance")
                self.browser = BrowserAutomation(headless=True)
                self.logger.info(f"[PID:{pid}] Browser started successfully")

                # Get and execute test steps
                self.logger.info(f"[PID:{pid}] Retrieving test steps")
                steps = self._get_test_steps(test_case_id)
                
                self.logger.info(f"[PID:{pid}] Navigating to base URL: {env.base_url}")
                self.browser.navigate(url=env.base_url)
                
                self.logger.info(f"[PID:{pid}] Starting test step execution")
                for step in steps:
                    step_id, action, element_path, description, expected_result, value, path_type = step
                    self.logger.info(f"[PID:{pid}] Executing step {step_id}: {action}")
                    self.execute_step(action, element_path, value, path_type)

                # Calculate duration and log success
                duration = (datetime.now() - start_time).total_seconds()
                self._log_test_run(test_case_id, "success", duration=duration)
                self.logger.info(f"[PID:{pid}] Test case completed successfully in {duration} seconds")
                return {"status": "success", "duration": duration}

            except Exception as e:
                duration = (datetime.now() - start_time).total_seconds()
                self.logger.error(f"[PID:{pid}] Test case failed: {str(e)}")
                self._log_test_run(test_case_id, "failure", str(e), duration)
                return {"status": "failure", "error": str(e), "duration": duration}

            finally:
                self.logger.info(f"[PID:{pid}] Cleaning up after test case execution")
                self._cleanup_browser()

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
                try:
                    self.browser.close()
                except:
                    pass
                self.browser = None
