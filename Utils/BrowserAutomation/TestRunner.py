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
                cls._instance.html_analyzer = None  # Initialize HTML analyzer as None
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
        self.logger = self._setup_logger()
        self.pid = os.getpid()
        if not hasattr(self, '_initialized'):
            self.logger.info(f"[PID:{self.pid}] Initializing TestRunner")
            self._initialized = True
            # Initialize HTML analyzer only once
            self.html_analyzer = HtmlAnalyzer()
            self.logger.info(f"[PID:{self.pid}] HTML Analyzer initialized")
            # Initialize browser
            try:
                self.browser = BrowserAutomation(headless=True)
                self.logger.info(f"[PID:{self.pid}] Browser initialized")
            except Exception as e:
                self.logger.error(f"[PID:{self.pid}] Failed to initialize browser: {str(e)}")
                raise
        else:
            self.logger.info(f"[PID:{self.pid}] TestRunner already initialized")

    def __del__(self):
        """Cleanup method to ensure browser is closed when TestRunner is destroyed"""
        pid = os.getpid()
        self.logger.info(f"[PID:{pid}] TestRunner instance being destroyed")
        self._cleanup_browser()

    @contextmanager
    def _process_lock(self):
        """Process-safe lock using Redis or threading lock as fallback"""
        pid = os.getpid()
        acquired = False
        redis_error = None
        
        try:
            self.logger.info(f"[PID:{pid}] Attempting to acquire lock")
            
            # First try Redis lock if available
            if hasattr(self, '_redis_lock') and self._redis_lock:
                try:
                    self.logger.info(f"[PID:{pid}] Trying Redis lock")
                    acquired = self._redis_lock.acquire(blocking=True, blocking_timeout=5)
                    if acquired:
                        self.logger.info(f"[PID:{pid}] Successfully acquired Redis lock")
                        redis_error = None
                    else:
                        self.logger.warning(f"[PID:{pid}] Failed to acquire Redis lock, falling back to threading lock")
                        redis_error = "Failed to acquire Redis lock after timeout"
                except Exception as e:
                    self.logger.warning(f"[PID:{pid}] Redis error: {str(e)}, falling back to threading lock")
                    redis_error = str(e)
            else:
                self.logger.info(f"[PID:{pid}] Redis lock not available")
                redis_error = "Redis lock not initialized"
            
            # If Redis failed, use threading lock
            if redis_error:
                try:
                    self._lock.acquire()
                    acquired = True
                    self.logger.info(f"[PID:{pid}] Successfully acquired threading lock")
                except Exception as e:
                    self.logger.error(f"[PID:{pid}] Failed to acquire threading lock: {str(e)}")
                    raise TimeoutError(f"Could not acquire any lock for test execution: {str(e)}")
            
            yield
        finally:
            if acquired:
                try:
                    # Release the appropriate lock
                    if redis_error is None and hasattr(self, '_redis_lock') and self._redis_lock:
                        self._redis_lock.release()
                        self.logger.info(f"[PID:{pid}] Released Redis lock")
                    else:
                        self._lock.release()
                        self.logger.info(f"[PID:{pid}] Released threading lock")
                except Exception as e:
                    self.logger.error(f"[PID:{pid}] Error releasing lock: {str(e)}")
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
            # We're no longer processing variables here since they should already be processed
            # when passed to this method from generate_test_steps
            
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
            elif action == "hover":
                self.browser.hover(element_path, by_strategy)
            elif action == "select":
                self.browser.select(element_path, value, by_strategy)
            else:
                raise ValueError(f"Unsupported action: {action}")
                
            # Only add a 5-second wait if the page has been reloaded
            if action in ['click', 'navigate', 'submit']:
                # Check if the page has been reloaded
                self.logger.info(f"[PID:{self.pid}] Checking if page has been reloaded after {action}")
                if self.browser.wait_for_page_changes():
                    self.logger.info(f"[PID:{self.pid}] Page was reloaded, waiting 5 seconds for it to stabilize")
                    time.sleep(5)
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
            connection = System.get_db_connection()
            yield connection
        finally:
            if connection:
                System._pool.putconn(connection)

    def run_test_case(self, test_case_id: int, environment_vars=None):
        """
        Run a complete test case

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
        
        with self._process_lock():
            try:
                # Initialize browser
                self.logger.info(f"[PID:{pid}] Cleaning up any existing browser instance")
                self._cleanup_browser()
                
                self.logger.info(f"[PID:{pid}] Creating new browser instance")
                self.browser = BrowserAutomation(headless=True)
                self.logger.info(f"[PID:{self.pid}] Browser started successfully")

                # Get and execute test steps
                self.logger.info(f"[PID:{pid}] Retrieving test steps")
                steps = self._get_test_steps(test_case_id)
                
                self.logger.info(f"[PID:{pid}] Navigating to base URL: {env.base_url}")
                self.browser.navigate(url=env.base_url)
                
                self.logger.info(f"[PID:{pid}] Starting test step execution")
                for step in steps:
                    step_id, action, element_path, description, expected_result, value, path_type = step
                    self.logger.info(f"[PID:{pid}] Executing step {step_id}: {action}")
                    self.execute_step(action, element_path, value, path_type, env)

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

    def generate_test_steps(self, test_case_id: int, environment_vars=None):
        """
        Generate test steps using AI analysis of page HTML.
        
        Args:
            test_case_id: ID of the test case
            environment_vars: Optional dictionary with environment variables (base_url, login, password)
        """
        pid = os.getpid()
        try:
            # Acquire process lock
            with self._process_lock():
                self.logger.info(f"[PID:{pid}] Starting test step generation for ID: {test_case_id}")
                
                # Initialize components
                system = System()
                # Initialize environment helper with provided variables
                env = EnvHelper(environment_vars)
                
                # Log environment variables for debugging
                if environment_vars:
                    self.logger.info(f"[PID:{pid}] Using environment variables: {environment_vars}")
                else:
                    self.logger.warning(f"[PID:{pid}] No environment variables provided")
                    
                html_analyzer = self.html_analyzer  # Use the singleton HTML analyzer
                
                # Clean up any existing browser instance
                self._cleanup_browser()
                
                # Create new browser instance
                self.browser = BrowserAutomation(headless=True)
                
                # Get test case details - name and description
                test_case_data = self._get_test_case(test_case_id=test_case_id)
                test_name = test_case_data[0]
                test_description = test_case_data[1] or ""  # Use empty string if description is None
                
                self.logger.info(f"[PID:{pid}] Test case: {test_name}")
                self.logger.info(f"[PID:{pid}] Description: {test_description}")

                # Ensure we have a base URL to navigate to
                if not env.base_url:
                    self.logger.warning(f"[PID:{pid}] No base_url provided in environment variables")
                    # Use a default or fallback URL if needed
                    if 'http' not in test_description.lower():
                        self.logger.warning(f"[PID:{pid}] Using a default URL since none was provided")
                        env.base_url = "http://localhost"  # Default fallback
                
                self.logger.info(f"[PID:{pid}] Navigating to base URL: {env.base_url}")
                self.browser.navigate(url=env.base_url)
                
                step_order = 0
                page_source = self.browser.get_page_source()
                screenshot_path = self.browser.take_screenshot()
                prev_step_description = ''
                next_prompt = ''
                
                # Track previous steps to avoid duplicates
                previous_steps = set()
                max_retries = 3
                retry_delay = 2  # seconds
                
                try:
                    while next_prompt != 'Stop':
                        self.logger.info(f"[PID:{pid}] Processing step {step_order}, next_prompt: {next_prompt}")
                        
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
                                    self.logger.error(f"[PID:{pid}] Failed to capture failure screenshot: {str(screenshot_error)}")
                                
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
                    raise

        except Exception as e:
            self.logger.error(f"[PID:{pid}] Error generating test steps: {str(e)}")
            raise
        
        finally:
            # Always clean up resources
            self._cleanup_browser()
            self.logger.info(f"[PID:{pid}] Test step generation completed")

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
