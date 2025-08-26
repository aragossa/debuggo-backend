import sys
from contextlib import contextmanager
from datetime import datetime
import logging
import os
import psycopg2
import redis
from redis.lock import Lock as RedisLock
from threading import Lock
import time
import multiprocessing
from datetime import timedelta
import base64
import os.path
from Utils.AIHelper.HtmlAnalyzer import HtmlAnalyzer
from Utils.BrowserAutomation.BrowserAutomation import BrowserAutomation
from Utils.BrowserAutomation.EnvHelper import EnvHelper
from Utils.System import System
import io
from Utils.Connectors.db_utils import get_db_connection, return_db_connection


class TestRunner:
    _instances = {}
    _lock = Lock()  # Local threading lock as fallback
    _redis = None
    _lock_timeout = 300  # 5 minutes timeout

    def __new__(cls, user_id=None, test_case_id=None):
        pid = os.getpid()
        # Create a unique key for this user and test case
        instance_key = f"{user_id}_{test_case_id}" if user_id and test_case_id else "default"
        
        with cls._lock:
            # If no instance exists for this key, create one
            if instance_key not in cls._instances:
                instance = super(TestRunner, cls).__new__(cls)
                instance.browser = None
                instance.test_run_id = None
                instance.user_id = user_id
                instance.test_case_id = test_case_id
                instance.instance_key = instance_key
                instance.logger = instance._setup_logger()
                instance.html_analyzer = None  # Initialize HTML analyzer as None
                instance.logger.info(f"[PID:{pid}] Creating new TestRunner instance for user:{user_id}, test:{test_case_id}")
                
                # Initialize Redis connection (shared across instances)
                if not hasattr(cls, '_redis_initialized'):
                    system = System()
                    try:
                        cls._redis = redis.Redis(
                            host=system.redis_host,
                            port=system.redis_port,
                            decode_responses=True
                        )
                        instance.logger.info(f"[PID:{pid}] Redis connection established")
                        cls._redis_initialized = True
                        # No need to create a global Redis lock on initialization
                        # We'll create test-specific locks when needed
                        instance.logger.info(f"[PID:{pid}] Redis connection ready for test-specific locks")
                    except Exception as e:
                        instance.logger.error(f"[PID:{pid}] Error initializing Redis: {e}")
                        raise
                
                cls._instances[instance_key] = instance
                return instance
            else:
                cls._instances[instance_key].logger.info(f"[PID:{pid}] Returning existing TestRunner instance for user:{user_id}, test:{test_case_id}")
                return cls._instances[instance_key]

    def __init__(self, user_id=None, test_case_id=None):
        """Initialize TestRunner for a specific user and test case"""
        self.logger = self._setup_logger()
        self.pid = os.getpid()
        self.user_id = user_id
        self.test_case_id = test_case_id
        
        if not hasattr(self, '_initialized'):
            self.logger.info(f"[PID:{self.pid}] Initializing TestRunner for user:{user_id}, test:{test_case_id}")
            self._initialized = True
            # Initialize HTML analyzer
            self.html_analyzer = HtmlAnalyzer()
            self.logger.info(f"[PID:{self.pid}] HTML Analyzer initialized")
            
            # Each instance will have its own browser
            # But we'll create it on demand when needed rather than at initialization time
            self.browser = None
            self.logger.info(f"[PID:{self.pid}] Browser will be initialized when needed")
        else:
            self.logger.info(f"[PID:{self.pid}] TestRunner already initialized for user:{user_id}, test:{test_case_id}")

    def __del__(self):
        """Cleanup method to ensure browser is closed when TestRunner is destroyed"""
        pid = os.getpid()
        self.logger.info(f"[PID:{pid}] TestRunner instance being destroyed for user:{self.user_id}, test:{self.test_case_id}")
        self._cleanup_browser()
        
        # Remove this instance from the instances dictionary
        if hasattr(self, 'instance_key') and self.instance_key in self.__class__._instances:
            del self.__class__._instances[self.instance_key]

    @contextmanager
    def _test_case_lock(self, test_case_id):
        """Process-safe lock specific to a test case using Redis or threading lock as fallback"""
        pid = os.getpid()
        lock_key = f"test_case_lock:{test_case_id}"
        acquired = False
        redis_error = None
        redis_lock = None
        
        try:
            self.logger.info(f"[PID:{pid}] Attempting to acquire lock for test case {test_case_id}")
            
            # First try Redis lock if available
            if self._redis:
                try:
                    self.logger.info(f"[PID:{pid}] Creating test-specific Redis lock for test case {test_case_id}")
                    redis_lock = self._redis.lock(
                        lock_key,
                        timeout=self._lock_timeout,
                        blocking=True,
                        blocking_timeout=5
                    )
                    
                    acquired = redis_lock.acquire(blocking=True, blocking_timeout=5)
                    if acquired:
                        self.logger.info(f"[PID:{pid}] Successfully acquired Redis lock for test case {test_case_id}")
                        redis_error = None
                    else:
                        self.logger.warning(f"[PID:{pid}] Failed to acquire Redis lock for test case {test_case_id}, falling back to threading lock")
                        redis_error = "Failed to acquire Redis lock after timeout"
                except Exception as e:
                    self.logger.warning(f"[PID:{pid}] Redis error: {str(e)}, falling back to threading lock")
                    redis_error = str(e)
            else:
                self.logger.info(f"[PID:{pid}] Redis not available")
                redis_error = "Redis not initialized"
            
            # If Redis failed, use threading lock
            if redis_error:
                try:
                    self._lock.acquire()
                    acquired = True
                    self.logger.info(f"[PID:{pid}] Successfully acquired threading lock for test case {test_case_id}")
                except Exception as e:
                    self.logger.error(f"[PID:{pid}] Failed to acquire threading lock for test case {test_case_id}: {str(e)}")
                    raise TimeoutError(f"Could not acquire any lock for test case {test_case_id} execution: {str(e)}")
            
            yield
        finally:
            if acquired:
                try:
                    # Release the appropriate lock
                    if redis_error is None and redis_lock:
                        redis_lock.release()
                        self.logger.info(f"[PID:{pid}] Released Redis lock for test case {test_case_id}")
                    else:
                        self._lock.release()
                        self.logger.info(f"[PID:{pid}] Released threading lock for test case {test_case_id}")
                except Exception as e:
                    self.logger.error(f"[PID:{pid}] Error releasing lock for test case {test_case_id}: {str(e)}")
            else:
                self.logger.warning(f"[PID:{pid}] No lock to release for test case {test_case_id}")
    
    @contextmanager
    def _no_lock(self):
        """A context manager that doesn't apply any locks - for operations that don't need locking"""
        try:
            yield
        finally:
            pass

    def _ensure_browser_initialized(self):
        """Ensure the browser is initialized if it's not already"""
        pid = os.getpid()
        if not self.browser:
            self.logger.info(f"[PID:{pid}] Initializing browser for user:{self.user_id}, test:{self.test_case_id}")
            try:
                self.browser = BrowserAutomation(headless=False)
                self.logger.info(f"[PID:{pid}] Browser initialized successfully")
            except Exception as e:
                self.logger.error(f"[PID:{pid}] Failed to initialize browser: {str(e)}")
                raise
        return self.browser

    def _cleanup_browser(self):
        """Cleanup method to close the browser"""
        pid = os.getpid()
        if hasattr(self, 'browser') and self.browser:
            self.logger.info(f"[PID:{pid}] Cleaning up browser for user:{self.user_id}, test:{self.test_case_id}")
            try:
                self.browser.close()
                self.browser = None
                self.logger.info(f"[PID:{pid}] Browser closed successfully")
            except Exception as e:
                self.logger.error(f"[PID:{pid}] Error closing browser: {str(e)}")
            finally:
                self.browser = None
                self.logger.info(f"[PID:{pid}] Browser instance set to None")

    def _setup_logger(self):
        logger = logging.getLogger('TestRunner')
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

    def _connect_db(self):
        """Create database connection"""
        return get_db_connection()

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
        """
        Get test case details from database.
        
        Args:
            test_case_id: ID of the test case
            
        Returns:
            Tuple containing (name, description) of the test case
        """
        with self.get_db_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute("""
                    SELECT name, description
                    FROM test_cases
                    WHERE id = %s
                """, (test_case_id,))
                result = cursor.fetchone()
                if not result:
                    self.logger.error(f"Test case with ID {test_case_id} not found")
                    return ("Unknown Test Case", "No description available")
                return result

    def _save_step(self, test_case_id: int, step_order: int, element_purpose: str, action: str, element_locator: str, value: str, by_strategy: str) -> int:
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
                            updated_at,
                            screenshot_path
                        ) VALUES (
                            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
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
                            current_timestamp,
                            None  # Initially set screenshot_path to None, will be updated later
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

    def execute_step(self, action: str, element_path: str = None, value: str = None, by_strategy: str = None, env_helper=None):
        """
        Execute a test step with the given action.
        
        Args:
            action (str): The action to perform (click, type, wait, etc.)
            element_path (str): The path to the element to interact with
            value (str): The value to use for the action (e.g., text to type)
            by_strategy (str): The strategy to locate elements (xpath or css)
            env_helper (EnvHelper): Optional environment helper for variable processing
        """
        try:
            # Process variables in element_path and value using the EnvHelper
            if env_helper:
                if element_path:
                    element_path = env_helper.process_variables(element_path)
                if value:
                    value = env_helper.process_variables(value)
            
            # Handle None or empty by_strategy
            if not by_strategy:
                # Try to auto-detect the strategy
                if element_path and (element_path.startswith('//') or element_path.startswith('(')):
                    by_strategy = 'xpath'
                else:
                    by_strategy = 'css'
            
            self.logger.info(f"[PID:{self.pid}] Executing {action} with path '{element_path}' using {by_strategy}")

            if action == "click":
                self.browser.click(element_path, by_strategy)
            elif action == 'navigate':
                # For navigate action, if element_path is 'N/A', use the value field instead
                if element_path == 'N/A' or not element_path:
                    if value:
                        self.logger.info(f"[PID:{self.pid}] Navigating to URL from value field: {value}")
                        self.browser.navigate(value)
                    else:
                        raise ValueError("Navigate action requires either a valid element_path or value containing the URL")
                else:
                    self.browser.navigate(element_path)
            elif action == "type":
                self.logger.info(f"[PID:{self.pid}] with value {value}")
                self.browser.type_text(element_path, value, by_strategy)
            elif action == "wait":
                self.browser.wait_for_element(element_path, by_strategy)
            elif action == "press_key":
                self.browser.press_key(element_path, value, by_strategy)
            elif action == "assert":
                self.browser.assert_element(element_path, value, by_strategy)
            elif action == "assert_text_contains":
                self.browser.assert_text_contains(element_path, value, by_strategy)
            elif action == "hover":
                self.browser.hover(element_path, by_strategy)
            elif action == "select":
                self.browser.select(element_path, value, by_strategy)
            elif action == "clear":
                self.browser.clear(element_path, by_strategy)
            else:
                raise ValueError(f"Unsupported action: {action}")
                
            # Only add a 5-second wait if the page has been reloaded
            if action in ['click', 'navigate', 'submit']:
                # Check if the page has been reloaded
                self.logger.info(f"[PID:{self.pid}] Checking if page has been reloaded after {action}")
                if self.browser.wait_for_page_changes():
                    self.logger.info(f"[PID:{self.pid}] Page was reloaded, waiting 5 seconds for it to stabilize")
                    time.sleep(1)
                else:
                    self.logger.info(f"[PID:{self.pid}] No page reload detected after {action}")
            
        except Exception as e:
            self.logger.error(f"[PID:{self.pid}] Failed to execute step: {action} on {element_path}")
            self.logger.error(f"[PID:{self.pid}] Error details: {str(e)}")
            # Log the actual selector strategy being used
            if by_strategy:
                self.logger.error(f"[PID:{self.pid}] Selector strategy: {by_strategy}")
            # Log the stack trace for better debugging
            import traceback
            self.logger.error(f"[PID:{self.pid}] Stack trace: {traceback.format_exc()}")
            
            # Take a screenshot to help with debugging
            try:
                screenshot_path = self.browser.take_screenshot(f"error_{action}")
                self.logger.error(f"[PID:{self.pid}] Error screenshot saved to: {screenshot_path}")
                
                # Log current page information
                url = self.browser.driver.current_url
                title = self.browser.driver.title
                self.logger.error(f"[PID:{self.pid}] Page at time of error: {url} (Title: {title})")
            except Exception as screenshot_error:
                self.logger.error(f"[PID:{self.pid}] Failed to capture error screenshot: {str(screenshot_error)}")
                
            raise

    @contextmanager
    def get_db_connection(self):
        """Context manager for database connections."""
        connection = None
        try:
            connection = get_db_connection()
            yield connection
        finally:
            if connection:
                return_db_connection(connection)

    def run_test_case(self, test_case_id: int, environment_vars=None):
        """
        Run a complete test case with step-by-step result tracking

        Args:
            test_case_id: ID of the test case to run
            environment_vars: Optional dictionary with environment variables (base_url, login, password)
        """
        pid = os.getpid()
        self.logger.info(f"[PID:{pid}] Starting test case execution for ID: {test_case_id}")
        start_time = datetime.now()
        
        # Initialize environment helper with provided variables
        env = EnvHelper(environment_vars)
        
        # Log environment variables for debugging
        if environment_vars:
            self.logger.info(f"[PID:{pid}] Using environment variables: {environment_vars}")
        else:
            self.logger.warning(f"[PID:{pid}] No environment variables provided")
        
        # Set running flag in Redis
        try:
            if self._redis:
                # Clear any existing stop flag
                self._redis.delete(f"test_case_stop_execution:{test_case_id}")
                # Set running flag
                self._redis.set(f"test_case_running:{test_case_id}", "1", ex=3600)  # Expire after 1 hour
                self.logger.info(f"[PID:{pid}] Set running status in Redis for test case {test_case_id}")
        except Exception as e:
            self.logger.error(f"[PID:{pid}] Failed to set running status in Redis: {e}")
        
        # Capture stdout for logging
        stdout_capture = io.StringIO()
        stderr_capture = io.StringIO()
        
        # Create test run record and get test_run_id
        test_run_id = None
        step_execution_results = []
        
        with self._test_case_lock(test_case_id):
            try:
                # Clean up any orphaned running steps before starting
                self._cleanup_orphaned_running_steps()
                
                # Initialize browser using our ensure method instead of direct initialization
                self.logger.info(f"[PID:{pid}] Ensuring browser is initialized for test case {test_case_id}")
                self._ensure_browser_initialized()
                self.logger.info(f"[PID:{self.pid}] Browser ready for test execution")

                # Get and execute test steps
                self.logger.info(f"[PID:{pid}] Retrieving test steps")
                steps = self._get_test_steps(test_case_id)
                
                # Create initial test run record
                test_run_id = self._create_test_run(test_case_id, "running")
                self.logger.info(f"[PID:{pid}] Created test run record with ID: {test_run_id}")
                
                self.logger.info(f"[PID:{pid}] Navigating to base URL: {env.base_url}")
                self.browser.navigate(url=env.base_url)
                
                self.logger.info(f"[PID:{pid}] Starting test step execution")
                step_order = 1
                
                for step in steps:
                    # Check if we should stop execution
                    if self._redis and self._redis.exists(f"test_case_stop_execution:{test_case_id}"):
                        self.logger.info(f"[PID:{pid}] Stopping test case execution as requested for test case {test_case_id}")
                        
                        # Mark remaining steps as skipped
                        for remaining_step in steps[step_order-1:]:
                            remaining_step_id, remaining_action, remaining_element_path, remaining_description, remaining_expected_result, remaining_value, remaining_path_type = remaining_step
                            self._log_step_execution_result(
                                test_run_id, remaining_step_id, step_order, "skipped",
                                error_message="Test execution stopped by user",
                                step_description=remaining_description, step_action=remaining_action,
                                step_element_path=remaining_element_path, step_value=remaining_value
                            )
                            step_order += 1
                        
                        duration = (datetime.now() - start_time).total_seconds()
                        self._update_test_run(test_run_id, "stopped", duration=duration)
                        return {
                            "status": "stopped", 
                            "message": "Test execution stopped by user", 
                            "duration": duration,
                            "test_run_id": test_run_id,
                            "step_results": self._get_step_execution_results(test_run_id)
                        }
                    
                    step_id, action, element_path, description, expected_result, value, path_type = step
                    self.logger.info(f"[PID:{pid}] Executing step {step_order}: {action} (step_id: {step_id})")
                    
                    # Record step start
                    step_start_time = datetime.now()
                    step_result_id = self._log_step_execution_result(
                        test_run_id, step_id, step_order, "running",
                        step_description=description, step_action=action,
                        step_element_path=element_path, step_value=value
                    )
                    
                    try:
                        self.execute_step(action, element_path, value, path_type, env)
                        
                        # Take screenshot after successful step execution
                        screenshot_path = None
                        screenshot_base64 = None
                        try:
                            screenshot_path = self.browser.take_screenshot(f"step_{step_order}_success")
                            # Convert screenshot to base64 for database storage
                            if screenshot_path and os.path.exists(screenshot_path):
                                with open(screenshot_path, "rb") as img_file:
                                    screenshot_base64 = base64.b64encode(img_file.read()).decode('utf-8')
                        except Exception as screenshot_error:
                            self.logger.warning(f"[PID:{pid}] Failed to capture screenshot for step {step_id}: {screenshot_error}")
                        
                        # Calculate execution time
                        execution_time_ms = int((datetime.now() - step_start_time).total_seconds() * 1000)
                        
                        # Update step result as passed
                        self._update_step_execution_result(
                            step_result_id, "passed", 
                            screenshot_path=screenshot_path,
                            screenshot_base64=screenshot_base64,
                            execution_time_ms=execution_time_ms
                        )
                        
                        self.logger.info(f"[PID:{pid}] Step {step_order} completed successfully")
                        
                    except AssertionError as assertion_error:
                        # Capture assertion failures specifically
                        error_message = str(assertion_error)
                        self.logger.error(f"[PID:{pid}] Assertion failed in step {step_id}: {error_message}")
                        
                        # Take screenshot on failure
                        screenshot_path = None
                        screenshot_base64 = None
                        try:
                            screenshot_path = self.browser.take_screenshot(f"step_{step_order}_assertion_failed")
                            if screenshot_path and os.path.exists(screenshot_path):
                                with open(screenshot_path, "rb") as img_file:
                                    screenshot_base64 = base64.b64encode(img_file.read()).decode('utf-8')
                        except Exception as screenshot_error:
                            self.logger.warning(f"[PID:{pid}] Failed to capture error screenshot: {screenshot_error}")
                        
                        # Calculate execution time
                        execution_time_ms = int((datetime.now() - step_start_time).total_seconds() * 1000)
                        
                        # Update step result as failed
                        self._update_step_execution_result(
                            step_result_id, "failed",
                            error_message=error_message,
                            screenshot_path=screenshot_path,
                            screenshot_base64=screenshot_base64,
                            execution_time_ms=execution_time_ms
                        )
                        
                        # Mark remaining steps as skipped
                        remaining_step_order = step_order + 1
                        for remaining_step in steps[step_order:]:
                            remaining_step_id, remaining_action, remaining_element_path, remaining_description, remaining_expected_result, remaining_value, remaining_path_type = remaining_step
                            self._log_step_execution_result(
                                test_run_id, remaining_step_id, remaining_step_order, "skipped",
                                error_message="Skipped due to previous step failure",
                                step_description=remaining_description, step_action=remaining_action,
                                step_element_path=remaining_element_path, step_value=remaining_value
                            )
                            remaining_step_order += 1
                        
                        # Get stack trace for detailed error info
                        import traceback
                        stack_trace = traceback.format_exc()
                        
                        # Log the test run as a failure
                        duration = (datetime.now() - start_time).total_seconds()
                        stdout_content = stdout_capture.getvalue()
                        stderr_content = stderr_capture.getvalue() + f"\nAssertion Error in step {step_id}: {error_message}\n{stack_trace}"
                        
                        self._update_test_run(
                            test_run_id, "failure", 
                            exception=error_message,
                            duration=duration,
                            stdout=stdout_content,
                            stderr=stderr_content
                        )
                        
                        # Clean up Redis flags
                        try:
                            if self._redis:
                                self._redis.delete(f"test_case_running:{test_case_id}")
                                self._redis.delete(f"test_case_stop_execution:{test_case_id}")
                        except Exception as redis_error:
                            self.logger.error(f"[PID:{pid}] Failed to clean up Redis flags: {redis_error}")
                        
                        return {
                            "status": "failure", 
                            "error": error_message, 
                            "step_id": step_id,
                            "duration": duration,
                            "test_run_id": test_run_id,
                            "step_results": self._get_step_execution_results(test_run_id)
                        }
                        
                    except Exception as step_error:
                        # Handle other exceptions during step execution
                        error_message = str(step_error)
                        self.logger.error(f"[PID:{pid}] Error in step {step_id}: {error_message}")
                        
                        # Take screenshot on error
                        screenshot_path = None
                        screenshot_base64 = None
                        try:
                            screenshot_path = self.browser.take_screenshot(f"step_{step_order}_error")
                            if screenshot_path and os.path.exists(screenshot_path):
                                with open(screenshot_path, "rb") as img_file:
                                    screenshot_base64 = base64.b64encode(img_file.read()).decode('utf-8')
                        except Exception as screenshot_error:
                            self.logger.warning(f"[PID:{pid}] Failed to capture error screenshot: {screenshot_error}")
                        
                        # Calculate execution time
                        execution_time_ms = int((datetime.now() - step_start_time).total_seconds() * 1000)
                        
                        # Update step result as failed
                        self._update_step_execution_result(
                            step_result_id, "failed",
                            error_message=error_message,
                            screenshot_path=screenshot_path,
                            screenshot_base64=screenshot_base64,
                            execution_time_ms=execution_time_ms
                        )
                        
                        # Mark remaining steps as skipped
                        remaining_step_order = step_order + 1
                        for remaining_step in steps[step_order:]:
                            remaining_step_id, remaining_action, remaining_element_path, remaining_description, remaining_expected_result, remaining_value, remaining_path_type = remaining_step
                            self._log_step_execution_result(
                                test_run_id, remaining_step_id, remaining_step_order, "skipped",
                                error_message="Skipped due to previous step failure",
                                step_description=remaining_description, step_action=remaining_action,
                                step_element_path=remaining_element_path, step_value=remaining_value
                            )
                            remaining_step_order += 1
                        
                        # Get stack trace for detailed error info
                        import traceback
                        stack_trace = traceback.format_exc()
                        
                        # Log the test run as a failure
                        duration = (datetime.now() - start_time).total_seconds()
                        stdout_content = stdout_capture.getvalue()
                        stderr_content = stderr_capture.getvalue() + f"\nError in step {step_id}: {error_message}\n{stack_trace}"
                        
                        self._update_test_run(
                            test_run_id, "failure", 
                            exception=error_message,
                            duration=duration,
                            stdout=stdout_content,
                            stderr=stderr_content
                        )
                        
                        # Clean up Redis flags
                        try:
                            if self._redis:
                                self._redis.delete(f"test_case_running:{test_case_id}")
                                self._redis.delete(f"test_case_stop_execution:{test_case_id}")
                        except Exception as redis_error:
                            self.logger.error(f"[PID:{pid}] Failed to clean up Redis flags: {redis_error}")
                        
                        return {
                            "status": "error", 
                            "error": error_message, 
                            "step_id": step_id,
                            "duration": duration,
                            "test_run_id": test_run_id,
                            "step_results": self._get_step_execution_results(test_run_id)
                        }
                    
                    step_order += 1

                # Calculate duration and log success
                duration = (datetime.now() - start_time).total_seconds()
                stdout_content = stdout_capture.getvalue()
                self._update_test_run(test_run_id, "success", duration=duration, stdout=stdout_content)
                self.logger.info(f"[PID:{pid}] Test case completed successfully in {duration} seconds")
                
                # Clean up Redis flags
                try:
                    if self._redis:
                        self._redis.delete(f"test_case_running:{test_case_id}")
                        self._redis.delete(f"test_case_stop_execution:{test_case_id}")
                except Exception as e:
                    self.logger.error(f"[PID:{pid}] Failed to clean up Redis flags: {e}")
                
                return {
                    "status": "success", 
                    "duration": duration,
                    "test_run_id": test_run_id,
                    "step_results": self._get_step_execution_results(test_run_id)
                }

            except Exception as e:
                duration = (datetime.now() - start_time).total_seconds()
                error_message = str(e)
                self.logger.error(f"[PID:{pid}] Test case failed: {error_message}")
                
                # Get stack trace for detailed error info
                import traceback
                stack_trace = traceback.format_exc()
                
                # CRITICAL FIX: Update any steps that are still in "running" status
                if test_run_id:
                    try:
                        self.logger.warning(f"[PID:{pid}] Updating any running steps to failed due to test case exception")
                        with self.get_db_connection() as connection:
                            with connection.cursor() as cursor:
                                # Find all running steps for this test run
                                cursor.execute(
                                    """
                                    SELECT id, test_step_id, step_order, started_at
                                    FROM test_step_execution_results 
                                    WHERE test_run_id = %s AND status = 'running'
                                    """,
                                    (test_run_id,)
                                )
                                running_steps = cursor.fetchall()
                                
                                # Update each running step to failed
                                for step_result_id, step_id, step_order, started_at in running_steps:
                                    execution_time_ms = int((datetime.now() - started_at).total_seconds() * 1000)
                                    cursor.execute(
                                        """
                                        UPDATE test_step_execution_results 
                                        SET status = %s, error_message = %s, execution_time_ms = %s, completed_at = %s
                                        WHERE id = %s
                                        """,
                                        ("failed", f"Test case failed with exception: {error_message}", 
                                         execution_time_ms, datetime.now(), step_result_id)
                                    )
                                    self.logger.info(f"[PID:{pid}] Updated step {step_id} (order {step_order}) from running to failed")
                                
                                connection.commit()
                                if running_steps:
                                    self.logger.info(f"[PID:{pid}] Updated {len(running_steps)} running steps to failed status")
                    except Exception as update_error:
                        self.logger.error(f"[PID:{pid}] Failed to update running steps: {update_error}")
                
                # Log the test run as a failure
                stdout_content = stdout_capture.getvalue()
                stderr_content = stderr_capture.getvalue() + f"\nTest case error: {error_message}\n{stack_trace}"
                
                if test_run_id:
                    self._update_test_run(
                        test_run_id, "failure", 
                        exception=error_message,
                        duration=duration,
                        stdout=stdout_content,
                        stderr=stderr_content
                    )
                else:
                    self._log_test_run(
                        test_case_id, 
                        "failure", 
                        exception=error_message,
                        duration=duration,
                        stdout=stdout_content,
                        stderr=stderr_content
                    )
                
                # Clean up Redis flags
                try:
                    if self._redis:
                        self._redis.delete(f"test_case_running:{test_case_id}")
                        self._redis.delete(f"test_case_stop_execution:{test_case_id}")
                except Exception as redis_error:
                    self.logger.error(f"[PID:{pid}] Failed to clean up Redis flags: {redis_error}")
                
                return {
                    "status": "error", 
                    "error": error_message, 
                    "duration": duration,
                    "test_run_id": test_run_id,
                    "step_results": self._get_step_execution_results(test_run_id) if test_run_id else []
                }

            finally:
                self.logger.info(f"[PID:{pid}] Cleaning up after test case execution")
                self._cleanup_browser()

    def generate_test_steps(self, test_case_id: int, environment_vars=None, ai_model_id=None):
        """
        Generate test steps using AI analysis of page HTML.
        
        Args:
            test_case_id: ID of the test case
            environment_vars: Optional dictionary with environment variables (base_url, login, password)
        """
        # Record start time
        start_time = datetime.now()
        
        # Update the test case with the start time and clear any stale end time
        try:
            with self.get_db_connection() as connection:
                with connection.cursor() as cursor:
                    cursor.execute(
                        """
                        UPDATE test_cases 
                        SET steps_generation_start_time = %s, steps_generation_end_time = NULL
                        WHERE id = %s
                        """,
                        (start_time, test_case_id)
                    )
                    connection.commit()
        except Exception as e:
            self.logger.error(f"Failed to update test case with start time: {e}")
        pid = os.getpid()
        self.logger.info(f"[PID:{pid}] Starting test step generation for test case {test_case_id}")
        
        # Get test case details from database
        test_name = ""
        test_description = ""
        try:
            with self.get_db_connection() as connection:
                with connection.cursor() as cursor:
                    cursor.execute(
                        """
                        SELECT name, description 
                        FROM test_cases 
                        WHERE id = %s
                        """,
                        (test_case_id,)
                    )
                    result = cursor.fetchone()
                    if result:
                        test_name = result[0] or ""
                        test_description = result[1] or ""
                        self.logger.info(f"[PID:{pid}] Retrieved test case: {test_name}")
                    else:
                        self.logger.warning(f"[PID:{pid}] Test case {test_case_id} not found in database")
        except Exception as e:
            self.logger.error(f"[PID:{pid}] Failed to retrieve test case details: {e}")
        
        # Set the generating status in Redis
        try:
            if self._redis:
                # Clear any existing stop flag
                self._redis.delete(f"test_case_stop_generating:{test_case_id}")
                # Set generating flag
                self._redis.set(f"test_case_generating:{test_case_id}", "1", ex=3600)  # Expire after 1 hour
                # Initialize current and next step information
                self._redis.set(f"test_case_current_step:{test_case_id}", "", ex=3600)
                self._redis.set(f"test_case_next_step:{test_case_id}", "Starting...", ex=3600)
                self.logger.info(f"[PID:{pid}] Set generation status in Redis for test case {test_case_id}")
        except Exception as e:
            self.logger.error(f"[PID:{pid}] Failed to set generation status in Redis: {e}")
        
        try:
            # Acquire test-case specific lock
            with self._test_case_lock(test_case_id):
                self.logger.info(f"[PID:{pid}] Acquired process lock for test case {test_case_id}")
                
                # Clean up any orphaned running steps before starting
                self._cleanup_orphaned_running_steps()
                
                # Initialize browser using our ensure method
                self._ensure_browser_initialized()
                self.logger.info(f"[PID:{pid}] Ensured browser is initialized for test case {test_case_id}")
                
                # Log the test run start
                test_run_id = self._log_test_run(test_case_id, "running")
                self.logger.info(f"[PID:{pid}] Logged test run {test_run_id} as running")
                
                # Create environment helper
                env = EnvHelper(environment_vars or {})
                
                # Set up HTML analyzer if not already initialized
                if not self.html_analyzer:
                    self.html_analyzer = HtmlAnalyzer()
                    self.logger.info(f"[PID:{pid}] Initialized HTML analyzer")
                
                html_analyzer = self.html_analyzer
                
                # If AI model ID is provided, get the model details and set the provider
                if ai_model_id:
                    try:
                        conn = get_db_connection()
                        with conn.cursor() as cursor:
                            cursor.execute(
                                """
                                SELECT model_id FROM ai_models 
                                WHERE id = %s AND is_active = TRUE
                                """, 
                                (ai_model_id,)
                            )
                            model = cursor.fetchone()
                            if model:
                                model_id = model[0]
                                # Extract provider from model_id (e.g., "gemini-2.5-pro" -> "gemini")
                                provider = model_id.split('-')[0] if '-' in model_id else model_id
                                self.logger.info(f"[PID:{pid}] Using AI model: {model_id} (provider: {provider})")
                                html_analyzer.switch_provider(provider)
                    except Exception as e:
                        self.logger.error(f"[PID:{pid}] Error setting AI model: {e}")
                    finally:
                        if 'conn' in locals() and conn:
                            return_db_connection(conn)
                
                # Navigate to the base URL
                base_url = env.get_base_url()
                if not base_url:
                    raise ValueError("Base URL is required for test step generation")
                
                self.logger.info(f"[PID:{pid}] Navigating to {base_url}")
                self.browser.navigate(base_url)
                
                # Wait for page to load
                self.browser.wait_for_page_load()
                
                # Take a screenshot for analysis
                screenshot_path = self.browser.take_screenshot(f"step_0_{test_case_id}")
                self.logger.info(f"[PID:{pid}] Screenshot saved to {screenshot_path}")
                
                # Get page source for analysis
                page_source = self.browser.get_page_source()
                
                # Initialize variables for the loop
                step_order = 1
                next_prompt = "Start"
                prev_step_description = ""
                max_retries = 3
                retry_delay = 5
                previous_steps = set()  # To avoid duplicate steps
                
                try:
                    while next_prompt != 'Stop':
                        # Check if we should stop generation
                        if self._redis and self._redis.exists(f"test_case_stop_generating:{test_case_id}"):
                            self.logger.info(f"[PID:{pid}] Stopping test step generation as requested for test case {test_case_id}")
                            break
                            
                        self.logger.info(f"[PID:{pid}] Processing step {step_order}, next_prompt: {next_prompt}")
                        
                        # Update current and next step information in Redis
                        if self._redis:
                            current_step = prev_step_description if prev_step_description else "Starting test generation"
                            next_step = next_prompt if next_prompt != "Stop" else "Finalizing test generation"
                            self._redis.set(f"test_case_current_step:{test_case_id}", current_step, ex=3600)
                            self._redis.set(f"test_case_next_step:{test_case_id}", next_step, ex=3600)
                        
                        retry_count = 0
                        while retry_count < max_retries:
                            try:
                                self.logger.info(f"[PID:{pid}] Processing step {screenshot_path}")
                                self.logger.info(f"[PID:{pid}] Calling html_analyzer with step_order={step_order}, next_prompt={next_prompt}")
                                analyzer_response = html_analyzer.html_analyzer(
                                    test_case_id=test_case_id,
                                    html_code=page_source,
                                    test_name=test_name,
                                    test_description=test_description,
                                    step_order=step_order,
                                    next_prompt=next_prompt,
                                    prev_step_description=prev_step_description,
                                    screenshot_path=screenshot_path
                                )
                                self.logger.info(f"[PID:{pid}] Analyzer response: {analyzer_response}")
                                
                                # Handle tuple unpacking with defaults
                                if isinstance(analyzer_response, tuple):
                                    self.logger.info(f"[PID:{pid}] Response length: {len(analyzer_response)}")
                                    if len(analyzer_response) == 5:
                                        # If we got a 5-tuple, add an empty value
                                        next_step, element_purpose, action, element_locator, by_strategy = analyzer_response
                                        value = ""  # Default empty value
                                    else:
                                        next_step, element_purpose, action, element_locator, by_strategy, value = analyzer_response
                                            
                                    self.logger.info(f"[PID:{pid}] Unpacked values: next_step={next_step}, purpose={element_purpose}, action={action}, locator={element_locator}, strategy={by_strategy}, value={value}")
                                    break
                            except Exception as e:
                                retry_count += 1
                                self.logger.error(f"[PID:{pid}] Error in attempt {retry_count}: {str(e)}")
                                if retry_count == max_retries:
                                    raise
                                if "429" in str(e):  # Rate limit error
                                    self.logger.warning(f"[PID:{pid}] Rate limit hit, waiting {retry_delay} seconds...")
                                    time.sleep(retry_delay)
                                    retry_delay *= 2  # Exponential backoff
                                else:
                                    raise
                        
                        next_prompt = next_step
                        prev_step_description = element_purpose
                        
                        # Store original values with variable placeholders
                        original_value = value
                        original_element_locator = element_locator
                        
                        # Process environment variables in values only for execution, not for storage
                        if value:
                            processed_value = env.process_variables(value)
                        else:
                            processed_value = value
                        
                        if element_locator:
                            processed_element_locator = env.process_variables(element_locator)
                        else:
                            processed_element_locator = element_locator
                        
                        # Create a unique key for this step
                        step_key = f"{action}:{element_locator}:{element_purpose}"
                        
                        # Skip if we've seen this exact step before
                        if step_key in previous_steps:
                            self.logger.info(f"[PID:{pid}] Skipping duplicate step: {element_purpose}")
                            continue
                        
                        previous_steps.add(step_key)
                        
                        # Special handling for navigate action which might have None as element_locator but has value
                        if action == "navigate" and value and not element_locator:
                            self.logger.info(f"[PID:{pid}] Executing navigate step to: {value}")
                            
                            # Save the step to the database first - use original values with placeholders
                            step_id = self._save_step(
                                test_case_id=test_case_id,
                                step_order=step_order,
                                element_purpose=element_purpose,
                                action=action,
                                element_locator=original_element_locator,
                                value=original_value,
                                by_strategy=by_strategy
                            )
                            
                            try:
                                self.execute_step(action, "N/A", processed_value, by_strategy, env)
                                

                            except Exception as e:

                                # Take a screenshot of the failure state
                                try:
                                    failure_screenshot = self.browser.take_screenshot(f"error_step_{step_order}")
                                    self.logger.error(f"[PID:{pid}] Error screenshot saved to: {failure_screenshot}")
                                    
                                    # Update the screenshot_path in the test_steps table
                                    with self.get_db_connection() as connection:
                                        with connection.cursor() as cursor:
                                            cursor.execute("""
                                                UPDATE test_steps 
                                                SET screenshot_path = %s
                                                WHERE id = %s
                                            """, (failure_screenshot, step_id))
                                            connection.commit()
                                    
                                    # Save the screenshot to the database
                                    with open(failure_screenshot, "rb") as image_file:
                                        encoded_string = base64.b64encode(image_file.read()).decode('utf-8')
                                    with self.get_db_connection() as connection:
                                        with connection.cursor() as cursor:
                                            cursor.execute("""
                                                INSERT INTO screenshots (test_step_id, screenshot, description)
                                                VALUES (%s, %s, %s)
                                            """, (step_id, encoded_string, f"Error screenshot for step {step_order}"))
                                            connection.commit()
                                except Exception as screenshot_error:
                                    self.logger.error(f"[PID:{pid}] Failed to capture error screenshot: {str(screenshot_error)}")
                                
                                # Update the step in the database to mark it as failed
                                try:
                                    with self.get_db_connection() as connection:
                                        with connection.cursor() as cursor:
                                            cursor.execute(
                                                """
                                                UPDATE test_steps 
                                                SET error_message = %s
                                                WHERE id = %s
                                                """,
                                                (str(e), step_id)
                                            )
                                            connection.commit()
                                except Exception as db_error:
                                    self.logger.error(f"[PID:{pid}] Failed to update step with error: {str(db_error)}")
                                
                                # Try to recover from the error using AI
                                max_recovery_attempts = 5
                                recovery_attempt = 0
                                
                                # Create a step history for error analysis
                                step_history = self._get_step_history(test_case_id)
                                
                                # Create a failed step dictionary
                                failed_step = {
                                    'element_purpose': element_purpose,
                                    'action': action,
                                    'element_locator': original_element_locator,
                                    'by_strategy': by_strategy,
                                    'value': original_value
                                }
                                
                                # Track previous recovery attempts
                                previous_attempts = []
                                
                                while recovery_attempt < max_recovery_attempts:
                                    recovery_attempt += 1
                                    self.logger.info(f"[PID:{pid}] Attempting error recovery (attempt {recovery_attempt}/{max_recovery_attempts})")
                                    
                                    try:
                                        # Get current page source for error analysis
                                        page_source = self.browser.get_page_source()
                                        
                                        # Debug the page structure if the error is related to element not found
                                        if "Element not found" in str(e) or "TimeoutException" in str(e):
                                            self.logger.info(f"[PID:{pid}] Element location issue detected, debugging page structure...")
                                            if "btn_recipientsGroup_newGroup" in str(failed_step['element_locator']):
                                                # Debug specific selectors for the New Group button
                                                self.browser.debug_page_structure("//a[contains(text(), 'New Group')]")
                                                self.browser.debug_page_structure("//button[contains(text(), 'New Group')]")
                                                self.browser.debug_page_structure("//a[contains(@class, 'new')]", "xpath")
                                            else:
                                                # Debug the specific failed selector
                                                self.browser.debug_page_structure(failed_step['element_locator'], failed_step['by_strategy'])
                                        
                                        # Use AI to analyze the error and suggest a fix
                                        analyzer_response = html_analyzer.analyze_error(
                                            test_case_id=test_case_id,
                                            html_code=page_source,
                                            test_name=test_name,
                                            test_description=test_description,
                                            step_history=step_history,
                                            failed_step=failed_step,
                                            error_message=str(e),
                                            previous_attempts=previous_attempts,
                                            screenshot_path=failure_screenshot
                                        )
                                        
                                        # Unpack the response
                                        if len(analyzer_response) == 5:
                                            next_step, element_purpose, action, element_locator, by_strategy = analyzer_response
                                            value = ""  # Default empty value
                                        else:
                                            next_step, element_purpose, action, element_locator, by_strategy, value = analyzer_response
                                            
                                        self.logger.info(f"[PID:{pid}] AI suggested fix: action={action}, locator={element_locator}, strategy={by_strategy}, value={value}")
                                        
                                        # Process environment variables for execution
                                        if value:
                                            processed_value = env.process_variables(value)
                                        else:
                                            processed_value = value
                                            
                                        if element_locator:
                                            processed_element_locator = env.process_variables(element_locator)
                                        else:
                                            processed_element_locator = element_locator
                                        
                                        # Save the corrected step to the database
                                        corrected_step_id = self._save_step(
                                            test_case_id=test_case_id,
                                            step_order=step_order,
                                            element_purpose=f"[CORRECTED] {element_purpose}",
                                            action=action,
                                            element_locator=element_locator,
                                            value=value,
                                            by_strategy=by_strategy
                                        )
                                        
                                        # Try to execute the corrected step
                                        self.logger.info(f"[PID:{pid}] Executing corrected step: {action} on {element_locator}")
                                        self.execute_step(action, processed_element_locator, processed_value, by_strategy, env)
                                        
                                        # If successful, update next_prompt and continue
                                        self.logger.info(f"[PID:{pid}] Error recovery successful on attempt {recovery_attempt}")
                                        next_prompt = next_step
                                        break
                                        
                                    except Exception as recovery_error:
                                        self.logger.error(f"[PID:{pid}] Error recovery attempt {recovery_attempt} failed: {str(recovery_error)}")
                                        
                                        # Add this failed attempt to the history
                                        previous_attempts.append({
                                            'action': action,
                                            'element_locator': element_locator,
                                            'by_strategy': by_strategy,
                                            'value': value,
                                            'error': str(recovery_error)
                                        })
                                        
                                        # If this was the last attempt, give up
                                        if recovery_attempt >= max_recovery_attempts:
                                            self.logger.warning(f"[PID:{pid}] Maximum recovery attempts reached, stopping test generation")
                                            return
                                    
                                    # If we've exhausted all recovery attempts, stop test generation
                                    if recovery_attempt >= max_recovery_attempts and next_prompt != next_step:
                                        self.logger.warning(f"[PID:{pid}] Stopping test generation due to step failure")
                                        return
                        elif action and element_locator:
                            self.logger.info(f"[PID:{pid}] Executing step: {action} on {element_locator}")

                            # Save the step to the database first - use original values with placeholders
                            step_id = self._save_step(
                                test_case_id=test_case_id,
                                step_order=step_order,
                                element_purpose=element_purpose,
                                action=action,
                                element_locator=original_element_locator,
                                value=original_value,
                                by_strategy=by_strategy
                            )
                            
                            try:
                                self.execute_step(action, processed_element_locator, processed_value, by_strategy, env)
                            except Exception as e:
                                # Take a screenshot of the failure state
                                try:
                                    failure_screenshot = self.browser.take_screenshot(f"error_step_{step_order}")
                                    self.logger.error(f"[PID:{pid}] Error screenshot saved to: {failure_screenshot}")
                                    
                                    # Update the screenshot_path in the test_steps table
                                    with self.get_db_connection() as connection:
                                        with connection.cursor() as cursor:
                                            cursor.execute("""
                                                UPDATE test_steps 
                                                SET screenshot_path = %s
                                                WHERE id = %s
                                            """, (failure_screenshot, step_id))
                                            connection.commit()
                                    
                                    # Save the screenshot to the database
                                    with open(failure_screenshot, "rb") as image_file:
                                        encoded_string = base64.b64encode(image_file.read()).decode('utf-8')
                                    with self.get_db_connection() as connection:
                                        with connection.cursor() as cursor:
                                            cursor.execute("""
                                                INSERT INTO screenshots (test_step_id, screenshot, description)
                                                VALUES (%s, %s, %s)
                                            """, (step_id, encoded_string, f"Error screenshot for step {step_order}"))
                                            connection.commit()
                                except Exception as screenshot_error:
                                    self.logger.error(f"[PID:{pid}] Failed to capture failure screenshot: {str(screenshot_error)}")
                                
                                # Log the current page URL and title
                                try:
                                    current_url = self.browser.driver.current_url
                                    current_title = self.browser.driver.title
                                    self.logger.error(f"[PID:{pid}] Page at failure: URL={current_url}, Title={current_title}")
                                except Exception as page_error:
                                    self.logger.error(f"[PID:{pid}] Failed to get page details: {str(page_error)}")
                                
                                # Update the step in the database to mark it as failed
                                try:
                                    with self.get_db_connection() as connection:
                                        with connection.cursor() as cursor:
                                            cursor.execute(
                                                """
                                                UPDATE test_steps 
                                                SET error_message = %s
                                                WHERE id = %s
                                                """,
                                                (str(e), step_id)
                                            )
                                            connection.commit()
                                except Exception as db_error:
                                    self.logger.error(f"[PID:{pid}] Failed to update step with error: {str(db_error)}")
                                
                                # Try to recover from the error using AI
                                max_recovery_attempts = 5
                                recovery_attempt = 0
                                
                                # Create a step history for error analysis
                                step_history = self._get_step_history(test_case_id)
                                
                                # Create a failed step dictionary
                                failed_step = {
                                    'element_purpose': element_purpose,
                                    'action': action,
                                    'element_locator': original_element_locator,
                                    'by_strategy': by_strategy,
                                    'value': original_value
                                }
                                
                                # Track previous recovery attempts
                                previous_attempts = []
                                
                                while recovery_attempt < max_recovery_attempts:
                                    recovery_attempt += 1
                                    self.logger.info(f"[PID:{pid}] Attempting error recovery (attempt {recovery_attempt}/{max_recovery_attempts})")
                                    
                                    try:
                                        # Get current page source for error analysis
                                        page_source = self.browser.get_page_source()
                                        
                                        # Debug the page structure if the error is related to element not found
                                        if "Element not found" in str(e) or "TimeoutException" in str(e):
                                            self.logger.info(f"[PID:{pid}] Element location issue detected, debugging page structure...")
                                            if "btn_recipientsGroup_newGroup" in str(failed_step['element_locator']):
                                                # Debug specific selectors for the New Group button
                                                self.browser.debug_page_structure("//a[contains(text(), 'New Group')]")
                                                self.browser.debug_page_structure("//button[contains(text(), 'New Group')]")
                                                self.browser.debug_page_structure("//a[contains(@class, 'new')]", "xpath")
                                            else:
                                                # Debug the specific failed selector
                                                self.browser.debug_page_structure(failed_step['element_locator'], failed_step['by_strategy'])
                                        
                                        # Use AI to analyze the error and suggest a fix
                                        analyzer_response = html_analyzer.analyze_error(
                                            test_case_id=test_case_id,
                                            html_code=page_source,
                                            test_name=test_name,
                                            test_description=test_description,
                                            step_history=step_history,
                                            failed_step=failed_step,
                                            error_message=str(e),
                                            previous_attempts=previous_attempts,
                                            screenshot_path=failure_screenshot
                                        )
                                        
                                        # Unpack the response
                                        if len(analyzer_response) == 5:
                                            next_step, element_purpose, action, element_locator, by_strategy = analyzer_response
                                            value = ""
                                        else:
                                            next_step, element_purpose, action, element_locator, by_strategy, value = analyzer_response
                                            
                                        self.logger.info(f"[PID:{pid}] AI suggested fix: action={action}, locator={element_locator}, strategy={by_strategy}, value={value}")
                                        
                                        # Process environment variables for execution
                                        if value:
                                            processed_value = env.process_variables(value)
                                        else:
                                            processed_value = value
                                            
                                        if element_locator:
                                            processed_element_locator = env.process_variables(element_locator)
                                        else:
                                            processed_element_locator = element_locator
                                        
                                        # Save the corrected step to the database
                                        corrected_step_id = self._save_step(
                                            test_case_id=test_case_id,
                                            step_order=step_order,
                                            element_purpose=f"[CORRECTED] {element_purpose}",
                                            action=action,
                                            element_locator=element_locator,
                                            value=value,
                                            by_strategy=by_strategy
                                        )
                                        
                                        # Try to execute the corrected step
                                        self.logger.info(f"[PID:{pid}] Executing corrected step: {action} on {element_locator}")
                                        self.execute_step(action, processed_element_locator, processed_value, by_strategy, env)
                                        
                                        # If successful, update next_prompt and continue
                                        self.logger.info(f"[PID:{pid}] Error recovery successful on attempt {recovery_attempt}")
                                        next_prompt = next_step
                                        break
                                        
                                    except Exception as recovery_error:
                                        self.logger.error(f"[PID:{pid}] Error recovery attempt {recovery_attempt} failed: {str(recovery_error)}")
                                        
                                        # Add this failed attempt to the history
                                        previous_attempts.append({
                                            'action': action,
                                            'element_locator': element_locator,
                                            'by_strategy': by_strategy,
                                            'value': value,
                                            'error': str(recovery_error)
                                        })
                                        
                                        # If this was the last attempt, give up
                                        if recovery_attempt >= max_recovery_attempts:
                                            self.logger.warning(f"[PID:{pid}] Maximum recovery attempts reached, stopping test generation")
                                            return
                                    
                                    # If we've exhausted all recovery attempts, stop test generation
                                    if recovery_attempt >= max_recovery_attempts and next_prompt != next_step:
                                        self.logger.warning(f"[PID:{pid}] Stopping test generation due to step failure")
                                        return

                        page_source = self.browser.get_page_source()
                        # Take a screenshot after getting page source
                        screenshot_path = self.browser.take_screenshot()
                        self.logger.info(f"[PID:{pid}] Screenshot taken: {screenshot_path}")
                        
                        # Update the screenshot_path in the test_steps table
                        with self.get_db_connection() as connection:
                            with connection.cursor() as cursor:
                                cursor.execute("""
                                    UPDATE test_steps 
                                    SET screenshot_path = %s
                                    WHERE id = %s
                                """, (screenshot_path, step_id))
                                connection.commit()
                        
                        # Save the screenshot to the database
                        with open(screenshot_path, "rb") as image_file:
                            encoded_string = base64.b64encode(image_file.read()).decode('utf-8')
                        with self.get_db_connection() as connection:
                            with connection.cursor() as cursor:
                                cursor.execute("""
                                    INSERT INTO screenshots (test_step_id, screenshot, description)
                                    VALUES (%s, %s, %s)
                                """, (step_id, encoded_string, f"Screenshot for step {step_order}"))
                                connection.commit()
                        step_order += 1
                except Exception as step_gen_error:
                    self.logger.error(f"[PID:{pid}] Error during step generation: {str(step_gen_error)}")
                    import traceback
                    self.logger.error(f"[PID:{pid}] Traceback: {traceback.format_exc()}")
                    # Update end time even on error
                    self._update_generation_end_time(test_case_id)
                    raise

            # Update end time on successful completion
            self._update_generation_end_time(test_case_id)
            self.logger.info(f"[PID:{pid}] Test step generation completed for test case {test_case_id}")

        except Exception as e:
            self.logger.error(f"[PID:{pid}] Error generating test steps: {str(e)}")
            # Update end time even on error
            self._update_generation_end_time(test_case_id)
            raise

    def _update_generation_end_time(self, test_case_id: int):
        """Update the steps_generation_end_time for the test case"""
        try:
            end_time = datetime.now()
            with self.get_db_connection() as connection:
                with connection.cursor() as cursor:
                    cursor.execute(
                        """
                        UPDATE test_cases 
                        SET steps_generation_end_time = %s
                        WHERE id = %s
                        """,
                        (end_time, test_case_id)
                    )
                    connection.commit()
        except Exception as e:
            self.logger.error(f"Failed to update test case with end time: {e}")

    def _create_test_run(self, test_case_id: int, status: str = "running"):
        """Create a new test run record and return the test_run_id"""
        try:
            connection = get_db_connection()
            try:
                with connection.cursor() as cursor:
                    cursor.execute(
                        """
                        INSERT INTO test_runs (test_case_id, result, run_date)
                        VALUES (%s, %s, %s)
                        RETURNING id
                        """,
                        (test_case_id, status, datetime.now())
                    )
                    test_run_id = cursor.fetchone()[0]
                    connection.commit()
                    return test_run_id
            finally:
                return_db_connection(connection)
        except Exception as e:
            self.logger.error(f"Failed to create test run: {e}")
            raise

    def _update_test_run(self, test_run_id: int, status: str, exception: str = None, 
                        duration: float = None, stdout: str = None, stderr: str = None):
        """Update an existing test run record"""
        try:
            connection = get_db_connection()
            try:
                with connection.cursor() as cursor:
                    cursor.execute(
                        """
                        UPDATE test_runs 
                        SET result = %s, exception = %s, duration = %s, stdout = %s, stderr = %s
                        WHERE id = %s
                        """,
                        (status, exception, duration, stdout, stderr, test_run_id)
                    )
                    connection.commit()
            finally:
                return_db_connection(connection)
        except Exception as e:
            self.logger.error(f"Failed to update test run {test_run_id}: {e}")

    def _log_step_execution_result(self, test_run_id: int, test_step_id: int, step_order: int, 
                                  status: str, error_message: str = None, screenshot_path: str = None,
                                  screenshot_base64: str = None, execution_time_ms: int = None,
                                  step_description: str = None, step_action: str = None,
                                  step_element_path: str = None, step_value: str = None):
        """Log a step execution result and return the result ID"""
        try:
            connection = get_db_connection()
            try:
                with connection.cursor() as cursor:
                    cursor.execute(
                        """
                        INSERT INTO test_step_execution_results 
                        (test_run_id, test_step_id, step_order, status, error_message, 
                         screenshot_path, screenshot_base64, execution_time_ms, started_at,
                         step_description, step_action, step_element_path, step_value)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        RETURNING id
                        """,
                        (test_run_id, test_step_id, step_order, status, error_message,
                         screenshot_path, screenshot_base64, execution_time_ms, datetime.now(),
                         step_description, step_action, step_element_path, step_value)
                    )
                    result_id = cursor.fetchone()[0]
                    connection.commit()
                    return result_id
            finally:
                return_db_connection(connection)
        except Exception as e:
            self.logger.error(f"Failed to log step execution result: {e}")
            return None

    def _update_step_execution_result(self, result_id: int, status: str, error_message: str = None,
                                     screenshot_path: str = None, screenshot_base64: str = None,
                                     execution_time_ms: int = None):
        """Update an existing step execution result"""
        try:
            connection = get_db_connection()
            try:
                with connection.cursor() as cursor:
                    cursor.execute(
                        """
                        UPDATE test_step_execution_results 
                        SET status = %s, error_message = %s, screenshot_path = %s, 
                            screenshot_base64 = %s, execution_time_ms = %s, completed_at = %s
                        WHERE id = %s
                        """,
                        (status, error_message, screenshot_path, screenshot_base64, 
                         execution_time_ms, datetime.now(), result_id)
                    )
                    connection.commit()
            finally:
                return_db_connection(connection)
        except Exception as e:
            self.logger.error(f"Failed to update step execution result {result_id}: {e}")

    def _cleanup_orphaned_running_steps(self, test_run_id: int = None):
        """
        Clean up any steps that have been stuck in 'running' status for more than 5 minutes.
        This handles cases where the process was killed or crashed unexpectedly.
        
        Args:
            test_run_id: Optional specific test run ID to clean up. If None, cleans all orphaned steps.
        """
        try:
            with self.get_db_connection() as connection:
                with connection.cursor() as cursor:
                    if test_run_id:
                        # Clean up specific test run
                        cursor.execute(
                            """
                            SELECT id, test_step_id, step_order, started_at
                            FROM test_step_execution_results 
                            WHERE test_run_id = %s AND status = 'running' 
                            AND started_at < NOW() - INTERVAL '5 minutes'
                            """,
                            (test_run_id,)
                        )
                    else:
                        # Clean up all orphaned steps
                        cursor.execute(
                            """
                            SELECT id, test_step_id, step_order, started_at, test_run_id
                            FROM test_step_execution_results 
                            WHERE status = 'running' 
                            AND started_at < NOW() - INTERVAL '5 minutes'
                            """
                        )
                    
                    orphaned_steps = cursor.fetchall()
                    
                    if orphaned_steps:
                        self.logger.warning(f"Found {len(orphaned_steps)} orphaned running steps, cleaning up...")
                        
                        for row in orphaned_steps:
                            step_result_id = row[0]
                            step_id = row[1]
                            step_order = row[2]
                            started_at = row[3]
                            run_id = row[4] if not test_run_id else test_run_id
                            
                            execution_time_ms = int((datetime.now() - started_at).total_seconds() * 1000)
                            cursor.execute(
                                """
                                UPDATE test_step_execution_results 
                                SET status = %s, error_message = %s, execution_time_ms = %s, completed_at = %s
                                WHERE id = %s
                                """,
                                ("failed", "Step was orphaned - process may have crashed or been killed", 
                                 execution_time_ms, datetime.now(), step_result_id)
                            )
                            self.logger.info(f"Cleaned up orphaned step {step_id} (order {step_order}) in test run {run_id}")
                        
                        connection.commit()
                        self.logger.info(f"Successfully cleaned up {len(orphaned_steps)} orphaned running steps")
                    
        except Exception as e:
            self.logger.error(f"Failed to clean up orphaned running steps: {e}")

    def _get_step_execution_results(self, test_run_id: int):
        """
        Get all step execution results for a test run.
        
        Args:
            test_run_id: ID of the test run
            
        Returns:
            List of step execution results with step details
        """
        try:
            # First clean up any orphaned steps for this test run
            self._cleanup_orphaned_running_steps(test_run_id)
            
            with self.get_db_connection() as connection:
                with connection.cursor() as cursor:
                    cursor.execute(
                        """
                        SELECT tser.id, tser.test_step_id, tser.step_order, tser.status,
                               tser.error_message, tser.screenshot_path, tser.screenshot_base64,
                               tser.execution_time_ms, tser.started_at, tser.completed_at,
                               ts.description, ts.action, ts.element_path, ts.value
                        FROM test_step_execution_results tser
                        JOIN test_steps ts ON tser.test_step_id = ts.id
                        WHERE tser.test_run_id = %s
                        ORDER BY tser.step_order
                        """,
                        (test_run_id,)
                    )
                    
                    results = []
                    for row in cursor.fetchall():
                        result = {
                            'id': row[0],
                            'test_step_id': row[1],
                            'step_order': row[2],
                            'status': row[3],
                            'error_message': row[4],
                            'screenshot_path': row[5],
                            'screenshot_base64': row[6],
                            'execution_time_ms': row[7],
                            'started_at': row[8].isoformat() if row[8] else None,
                            'completed_at': row[9].isoformat() if row[9] else None,
                            'description': row[10],
                            'action': row[11],
                            'element_path': row[12],
                            'value': row[13]
                        }
                        results.append(result)
                    
                    return results
                    
        except Exception as e:
            self.logger.error(f"Failed to get step execution results: {e}")
            return []

    def _get_step_history(self, test_case_id: int) -> list:
        """
        Get the history of executed steps for a test case.
        
        Args:
            test_case_id: ID of the test case
            
        Returns:
            List of dictionaries containing step information
        """
        try:
            with self.get_db_connection() as connection:
                with connection.cursor() as cursor:
                    cursor.execute("""
                        SELECT id, step_order, description, action, element_path, value, path_type
                        FROM test_steps
                        WHERE test_case_id = %s
                        ORDER BY step_order
                    """, (test_case_id,))
                    
                    steps = cursor.fetchall()
                    
                    # Convert to list of dictionaries
                    step_history = []
                    for step in steps:
                        step_id, step_order, description, action, element_path, value, path_type = step
                        step_history.append({
                            'element_purpose': description,
                            'action': action,
                            'element_locator': element_path,
                            'by_strategy': path_type,
                            'value': value if value else ''
                        })
                    
                    return step_history
                    
        except Exception as e:
            self.logger.error(f"Error getting step history: {str(e)}")
            return []

    def is_generating_steps(self, test_case_id: int) -> bool:
        """
        Check if a test case is currently generating steps.
        
        Args:
            test_case_id: ID of the test case
            
        Returns:
            bool: True if the test case is generating steps, False otherwise
        """
        try:
            if self._redis:
                result = self._redis.exists(f"test_case_generating:{test_case_id}")
                return bool(result)
        except Exception as e:
            self.logger.error(f"Error checking generation status in Redis: {e}")
        
        return False

    def stop_generating_steps(self, test_case_id: int) -> bool:
        """
        Stop the generation of test steps for a test case.
        
        Args:
            test_case_id: ID of the test case
            
        Returns:
            bool: True if the generation was stopped, False otherwise
        """
        pid = os.getpid()
        self.logger.info(f"[PID:{pid}] Stopping test step generation for test case {test_case_id}")
        
        try:
            # Set a stop flag in Redis
            if self._redis:
                self._redis.set(f"test_case_stop_generating:{test_case_id}", "1", ex=3600)  # Expire after 1 hour
                
                # Also clear the generating status
                self._redis.delete(f"test_case_generating:{test_case_id}")
                
                # Update the generation end time when manually stopped
                self._update_generation_end_time(test_case_id)
                
                self.logger.info(f"[PID:{pid}] Set stop flag in Redis for test case {test_case_id}")
                return True
        except Exception as e:
            self.logger.error(f"[PID:{pid}] Failed to set stop flag in Redis: {e}")
        
        return False

    def stop_test_case_execution(self, test_case_id: int) -> bool:
        """
        Stop the execution of a test case.
        
        Args:
            test_case_id: ID of the test case
            
        Returns:
            bool: True if the execution was stopped, False otherwise
        """
        pid = os.getpid()
        self.logger.info(f"[PID:{pid}] Stopping test case execution for test case {test_case_id}")
        
        try:
            # Set a stop flag in Redis
            if self._redis:
                self._redis.set(f"test_case_stop_execution:{test_case_id}", "1", ex=3600)  # Expire after 1 hour
                
                # Also clear the running status
                self._redis.delete(f"test_case_running:{test_case_id}")
                
                self.logger.info(f"[PID:{pid}] Set stop execution flag in Redis for test case {test_case_id}")
                return True
        except Exception as e:
            self.logger.error(f"[PID:{pid}] Failed to set stop execution flag in Redis: {e}")
        
        return False
