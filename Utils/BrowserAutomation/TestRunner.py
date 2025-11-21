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
from auroqa.Utils.AIHelper.HtmlAnalyzer import HtmlAnalyzer
from auroqa.Utils.BrowserAutomation.BrowserAutomation import BrowserAutomation
from auroqa.Utils.BrowserAutomation.EnvHelper import EnvHelper
from auroqa.Utils.System import System
import io
from auroqa.Utils.Connectors.db_utils import get_db_connection, return_db_connection
from auroqa.Services.ExecutionFeedbackCollector import ExecutionFeedbackCollector
from auroqa.Services.ValidationAgent import ValidationAgent
from auroqa.Services.ConfidenceScorer import ConfidenceScorer


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
            
            # Phase 1: Initialize feedback collector
            self.feedback_collector = ExecutionFeedbackCollector()
            self.logger.info(f"[PID:{self.pid}] Execution Feedback Collector initialized")
            
            # Phase 1: Initialize validation agent
            self.validator = ValidationAgent()
            self.logger.info(f"[PID:{self.pid}] Validation Agent initialized")
            
            # Phase 1: Initialize confidence scorer
            self.scorer = ConfidenceScorer()
            self.logger.info(f"[PID:{self.pid}] Confidence Scorer initialized")
            
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
                # Get session ID before closing for logging
                session_id = None
                if hasattr(self.browser, 'driver') and self.browser.driver:
                    try:
                        session_id = self.browser.driver.session_id
                        self.logger.info(f"[PID:{pid}] Closing Selenium session: {session_id}")
                    except:
                        pass
                
                # Force close the driver directly
                if hasattr(self.browser, 'driver') and self.browser.driver:
                    self.browser.driver.quit()
                    self.logger.info(f"[PID:{pid}] Called driver.quit() directly for session: {session_id}")
                
                # Also call the browser's close method
                self.browser.close()
                self.browser = None
                self.logger.info(f"[PID:{pid}] Browser closed successfully, session {session_id} should be terminated")
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

    def _save_step(self, test_case_id: int, step_order: int, element_purpose: str, action: str, element_locator: str, value: str, by_strategy: str, css_selector: str = "") -> int:
        try:
            with self.get_db_connection() as connection:
                with connection.cursor() as cursor:
                    # Map AI-generated specific actions to supported actions
                    action_mapping = {
                        # Assertion actions -> wait_for_element_to_be_visible (more reliable)
                        'assert_element_is_visible': 'wait_for_element_to_be_visible',
                        'assert_element_visible': 'wait_for_element_to_be_visible',
                        'assert_element_present': 'wait_for_element_to_be_visible',
                        'assert_element_not_present': 'assert',
                        'assert_text_equals': 'assert_text_contains',
                        'assert_url_contains': 'assert',
                        'assert_title_contains': 'assert',
                        'verify_text': 'assert_text_contains',
                        'verify_element': 'wait_for_element_to_be_visible',
                        'check_text': 'assert_text_contains',
                        'check_element': 'wait_for_element_to_be_visible'
                    }
                    
                    # Convert action if it's a specific assertion type
                    mapped_action = action_mapping.get(action, action)
                    
                    self.logger.info(f"Saving step with action: {action} -> {mapped_action}")
                    
                    # Check for duplicate steps (deduplication)
                    # Get the last 3 steps to check for duplicates
                    cursor.execute("""
                        SELECT action, element_path, description FROM test_steps 
                        WHERE test_case_id = %s 
                        ORDER BY step_order DESC 
                        LIMIT 3
                    """, (test_case_id,))
                    recent_steps = cursor.fetchall()
                    
                    if recent_steps:
                        # Helper function to extract key identifiers from locator
                        def extract_locator_keys(locator):
                            """Extract key identifiers from XPath/CSS locator"""
                            if not locator:
                                return set()
                            # Extract IDs, classes, and text patterns
                            import re
                            keys = set()
                            # Extract @id values
                            id_matches = re.findall(r"@id='([^']+)'", locator)
                            keys.update(id_matches)
                            # Extract text patterns
                            text_matches = re.findall(r"\[contains\(.*?'([^']+)'\)", locator)
                            keys.update(text_matches)
                            # Extract element tags
                            tag_matches = re.findall(r"//(\w+)\[", locator)
                            keys.update(tag_matches)
                            return keys
                        
                        current_keys = extract_locator_keys(element_locator)
                        
                        # Check against recent steps
                        for recent_action, recent_locator, recent_desc in recent_steps:
                            recent_keys = extract_locator_keys(recent_locator)
                            
                            # Consider it a duplicate if:
                            # 1. Targeting the same element (same keys)
                            # 2. Same or similar action type (wait, assert, verify)
                            if (current_keys and recent_keys and current_keys == recent_keys):
                                # Check if actions are similar (both verification-type actions)
                                verification_actions = {'wait', 'assert', 'wait_for_element_to_be_visible', 
                                                       'assert_element_is_visible', 'assert_text_contains'}
                                if (mapped_action in verification_actions and 
                                    recent_action in verification_actions):
                                    self.logger.warning(
                                        f"Skipping duplicate verification step: {mapped_action} on {element_locator} "
                                        f"(previous: {recent_action})"
                                    )
                                    return -1  # Return -1 to indicate skipped duplicate
                    
                    insert_query = """
                        INSERT INTO public.test_steps (
                            test_case_id,
                            step_order,
                            description,
                            action,
                            element_path,
                            css_selector,
                            value,
                            path_type,
                            created_at,
                            updated_at,
                            screenshot_path
                        ) VALUES (
                            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                        ) RETURNING id;
                    """

                    current_timestamp = datetime.now()
                    
                    # Convert value to string if it's a dict or other non-string type
                    # This handles cases where Gemini returns complex objects like {"condition": "element_is_visible", "timeout": 10}
                    if isinstance(value, dict):
                        import json
                        value_str = json.dumps(value)
                    elif value is None:
                        value_str = None
                    else:
                        value_str = str(value)

                    cursor.execute(
                        insert_query,
                        (
                            test_case_id,
                            step_order,
                            element_purpose,
                            mapped_action,
                            element_locator,
                            css_selector,
                            value_str,
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

    def _execute_click_with_fallback(self, xpath_selector: str, css_selector: str, by_strategy: str):
        """
        Execute click with dual locator fallback strategy:
        1. Try XPath selector first
        2. If XPath fails, try CSS selector
        3. If CSS fails, try JavaScript click on either locator
        
        Args:
            xpath_selector (str): Primary XPath locator
            css_selector (str): Fallback CSS locator
            by_strategy (str): Initial strategy hint
        """
        from selenium.common.exceptions import TimeoutException, NoSuchElementException
        
        # Strategy 1: Try XPath first
        if xpath_selector:
            try:
                self.logger.info(f"[PID:{self.pid}] Strategy 1: Trying XPath locator: {xpath_selector}")
                self.browser.click(xpath_selector, 'xpath')
                self.logger.info(f"[PID:{self.pid}] ✅ Click succeeded with XPath")
                return
            except Exception as e:
                self.logger.warning(f"[PID:{self.pid}] ❌ XPath click failed: {str(e)}")
        
        # Strategy 2: Try CSS selector fallback
        if css_selector:
            try:
                self.logger.info(f"[PID:{self.pid}] Strategy 2: Trying CSS selector fallback: {css_selector}")
                self.browser.click(css_selector, 'css')
                self.logger.info(f"[PID:{self.pid}] ✅ Click succeeded with CSS selector")
                return
            except Exception as e:
                self.logger.warning(f"[PID:{self.pid}] ❌ CSS selector click failed: {str(e)}")
        
        # Strategy 3: Try JavaScript click as last resort
        self.logger.info(f"[PID:{self.pid}] Strategy 3: Trying JavaScript click as last resort")
        try:
            # Try to find element with either locator
            element = None
            if xpath_selector:
                try:
                    from selenium.webdriver.common.by import By
                    element = self.browser.driver.find_element(By.XPATH, xpath_selector)
                    self.logger.info(f"[PID:{self.pid}] Found element with XPath for JS click")
                except:
                    pass
            
            if not element and css_selector:
                try:
                    from selenium.webdriver.common.by import By
                    element = self.browser.driver.find_element(By.CSS_SELECTOR, css_selector)
                    self.logger.info(f"[PID:{self.pid}] Found element with CSS for JS click")
                except:
                    pass
            
            if element:
                self.browser.driver.execute_script("arguments[0].click();", element)
                self.logger.info(f"[PID:{self.pid}] ✅ Click succeeded with JavaScript")
                return
            else:
                raise Exception(f"Element not found with XPath '{xpath_selector}' or CSS '{css_selector}'")
                
        except Exception as e:
            self.logger.error(f"[PID:{self.pid}] ❌ All click strategies failed")
            raise Exception(f"Failed to click element. XPath: {xpath_selector}, CSS: {css_selector}. Error: {str(e)}")

    def execute_step(self, action: str, element_path: str = None, value: str = None, by_strategy: str = None, env_helper=None, css_selector: str = None):
        """
        Execute a test step with the given action.
        Implements dual locator strategy: tries XPath first, then CSS fallback, then JavaScript click.
        
        Args:
            action (str): The action to perform (click, type, etc.)
            element_path (str): The XPath selector for the element (PRIMARY)
            value (str): The value to use for the action (e.g., text to type)
            by_strategy (str): The locator strategy ('xpath' or 'css')
            env_helper: Environment helper for variable substitution
            css_selector (str): The CSS selector for the element (FALLBACK)
        """
        try:
            # Process environment variables if env_helper is provided
            if env_helper:
                if element_path:
                    element_path = env_helper.process_variables(element_path)
                if css_selector:
                    css_selector = env_helper.process_variables(css_selector)
                if value:
                    value = env_helper.process_variables(value)
            
            # Handle None or empty by_strategy
            if not by_strategy:
                # Try to auto-detect the strategy
                if element_path and (element_path.startswith('//') or element_path.startswith('(')):
                    by_strategy = 'xpath'
                else:
                    by_strategy = 'css'
            
            self.logger.info(f"[PID:{self.pid}] Executing {action} with xpath='{element_path}' css='{css_selector}' using {by_strategy}")

            if action == "click":
                # Implement dual locator strategy with JavaScript fallback
                self._execute_click_with_fallback(element_path, css_selector, by_strategy)
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
            elif action == "wait_for_clickable":
                self.browser.wait_for_clickable(element_path, by_strategy)
            elif action == "wait_for_element_to_be_visible":
                self.browser.wait_for_element_to_be_visible(element_path, by_strategy)
            elif action == "wait_for_element_visible":
                self.browser.wait_for_element_visible(element_path, by_strategy)
            elif action == "wait_for_modal":
                # Wait for modal to appear, optionally with custom selector
                modal_selector = element_path if element_path else '//div[contains(@class, "modal")]'
                self.browser.wait_for_modal(modal_selector)
            elif action == "press_key":
                self.browser.press_key(element_path, value, by_strategy)
            elif action == "assert":
                self.browser.assert_element(element_path, value, by_strategy)
            elif action == "assert_text":
                # Exact text match assertion
                self.browser.assert_text(element_path, value, by_strategy)
            elif action == "assert_text_contains":
                self.browser.assert_text_contains(element_path, value, by_strategy)
            elif action == "hover":
                self.browser.hover(element_path, by_strategy)
            elif action == "select":
                self.browser.select(element_path, value, by_strategy)
            elif action == "clear":
                self.browser.clear(element_path, by_strategy)
            elif action == "stop_test":
                # Gracefully stop the test
                self.logger.info(f"[PID:{self.pid}] ✅ Test completed successfully - stopping test execution")
                return "test_completed"
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
                    
                    # Process environment variables to get resolved values for logging
                    resolved_value = value
                    resolved_element_path = element_path
                    if env and value:
                        resolved_value = env.process_variables(value)
                    if env and element_path:
                        resolved_element_path = env.process_variables(element_path)
                    
                    # Record step start with RESOLVED values
                    step_start_time = datetime.now()
                    step_result_id = self._log_step_execution_result(
                        test_run_id, step_id, step_order, "running",
                        step_description=description, step_action=action,
                        step_element_path=resolved_element_path, step_value=resolved_value
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
                        
                        # Phase 1: Collect validation result for successful step
                        try:
                            step_data = {
                                'action': action,
                                'element_locator': resolved_element_path,
                                'value': resolved_value,
                                'by_strategy': path_type
                            }
                            validation_result = self.validator.validate_step(step_data)
                            self.validator.save_validation_result(test_case_id, step_id, validation_result)
                            self.logger.info(f"✓ Step {step_order} validation: {validation_result.confidence:.1f}% confidence")
                        except Exception as validation_error:
                            self.logger.warning(f"⚠️ Failed to validate step {step_order}: {validation_error}")
                        
                        # Phase 1: Collect confidence score for successful step
                        try:
                            confidence_score = self.scorer.score_step(step_data)
                            self.scorer.save_confidence_score(test_case_id, confidence_score)
                            self.logger.info(f"📊 Step {step_order} confidence: {confidence_score.overall_confidence:.1f}% ({confidence_score.risk_level} risk)")
                        except Exception as scoring_error:
                            self.logger.warning(f"⚠️ Failed to score step {step_order}: {scoring_error}")
                        
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
                        
                        # Phase 1: Collect failure feedback
                        failure_record = self.feedback_collector.collect_failure(
                            test_case_id=test_case_id,
                            step_id=step_id,
                            step_order=step_order,
                            action=action,
                            element_locator=resolved_element_path,
                            error=step_error
                        )
                        
                        # Save failure record to database
                        self.feedback_collector.save_failure_record(failure_record)
                        self.logger.info(f"📝 Saved failure record for step {step_id}")
                        
                        # Generate AI feedback for potential retry
                        ai_feedback = self.feedback_collector.generate_ai_feedback(failure_record)
                        self.logger.info(f"🤖 AI Feedback:\n{ai_feedback}")
                        
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
                self._update_test_run(test_run_id, "completed", duration=duration, stdout=stdout_content)
                self.logger.info(f"[PID:{pid}] Test case completed successfully in {duration} seconds")
                
                # Clean up Redis flags
                try:
                    if self._redis:
                        self._redis.delete(f"test_case_running:{test_case_id}")
                        self._redis.delete(f"test_case_stop_execution:{test_case_id}")
                except Exception as e:
                    self.logger.error(f"[PID:{pid}] Failed to clean up Redis flags: {e}")
                
                return {
                    "status": "completed", 
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
        Uses single connection per session to optimize database usage.
        
        Args:
            test_case_id: ID of the test case
            environment_vars: Optional dictionary with environment variables (base_url, login, password)
        """
        pid = os.getpid()
        self.logger.info(f"[PID:{pid}] Starting optimized test step generation for test case {test_case_id}")
        
        # Use single database connection for entire session
        try:
            with self.get_db_connection() as session_conn:
                session_cursor = session_conn.cursor()
                
                # Record start time and get test case details in single transaction
                start_time = datetime.now()
                test_name = ""
                test_description = ""
                model_id = None
                
                try:
                    # Batch initial database operations
                    session_cursor.execute(
                        """
                        UPDATE test_cases 
                        SET steps_generation_start_time = %s, steps_generation_end_time = NULL
                        WHERE id = %s
                        """,
                        (start_time, test_case_id)
                    )
                    
                    # Get test case details in same transaction
                    session_cursor.execute(
                        """
                        SELECT name, description 
                        FROM test_cases 
                        WHERE id = %s
                        """,
                        (test_case_id,)
                    )
                    result = session_cursor.fetchone()
                    if result:
                        test_name = result[0] or ""
                        test_description = result[1] or ""
                        self.logger.info(f"[PID:{pid}] Retrieved test case: {test_name}")
                    else:
                        self.logger.warning(f"[PID:{pid}] Test case {test_case_id} not found in database")
                        return
                    
                    # Get AI model details if provided (batch with other operations)
                    if ai_model_id:
                        session_cursor.execute(
                            """
                            SELECT model_id FROM ai_models 
                            WHERE id = %s AND is_active = TRUE
                            """, 
                            (ai_model_id,)
                        )
                        model = session_cursor.fetchone()
                        if model:
                            model_id = model[0]
                            provider = model_id.split('-')[0] if '-' in model_id else model_id
                            self.logger.info(f"[PID:{pid}] Using AI model: {model_id} (provider: {provider})")
                            if self.html_analyzer:
                                self.html_analyzer.switch_provider(provider)
                    
                    # Commit initial setup
                    session_conn.commit()
                    
                except Exception as e:
                    session_conn.rollback()
                    self.logger.error(f"[PID:{pid}] Failed to initialize test generation: {e}")
                    return
                
                # Continue with test generation using the same connection
                return self._generate_test_steps_with_session_connection(
                    test_case_id, session_conn, session_cursor, test_name, test_description, 
                    environment_vars, model_id
                )
                
        except Exception as e:
            self.logger.error(f"[PID:{pid}] Database connection error during test generation: {e}")
            
    def _generate_test_steps_with_session_connection(self, test_case_id, session_conn, session_cursor, 
                                                   test_name, test_description, environment_vars, model_id):
        """
        Generate test steps using a single database connection session.
        """
        pid = os.getpid()
        
        # Initialize ReasoningCollector
        try:
            from Services.ReasoningCollector import ReasoningCollector
            from Utils.System import System
            
            system = System()
            reasoning_collector = ReasoningCollector(
                redis_host=system.redis_host,
                redis_port=system.redis_port
            )
            reasoning_collector.start_generation(test_case_id, test_name, test_description)
            reasoning_collector.set_test_split_strategy(
                test_case_id,
                total_steps=8,  # Will be updated as we generate
                phases=["Analysis", "Interaction", "Validation", "Cleanup"],
                strategy="Automated UI test generation with AI analysis"
            )
            self.logger.info(f"[PID:{pid}] Initialized ReasoningCollector for test case {test_case_id}")
        except Exception as e:
            self.logger.error(f"[PID:{pid}] Failed to initialize ReasoningCollector: {e}")
            reasoning_collector = None
        
        # Set the generating status in Redis with shorter TTL to prevent stale flags
        try:
            if self._redis:
                # Clear any existing stop flag
                self._redis.delete(f"test_case_stop_generating:{test_case_id}")
                # Set generating flag with 5-minute TTL to prevent stale generation flags
                self._redis.set(f"test_case_generating:{test_case_id}", "1", ex=300)  # Expire after 5 minutes
                # Initialize current and next step information
                self._redis.set(f"test_case_current_step:{test_case_id}", "", ex=300)
                self._redis.set(f"test_case_next_step:{test_case_id}", "Starting...", ex=300)
                self.logger.info(f"[PID:{pid}] Set generation status in Redis for test case {test_case_id} (TTL: 5 min)")
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
                        
                        # Update ReasoningCollector with current step
                        if reasoning_collector:
                            try:
                                reasoning_collector.set_current_step(
                                    test_case_id,
                                    step_number=step_order,
                                    action="analyzing",
                                    description=f"Analyzing page for step {step_order}",
                                    reasoning="Waiting for AI analysis of current page state"
                                )
                            except Exception as e:
                                self.logger.error(f"[PID:{pid}] Failed to update reasoning collector: {e}")
                        
                        retry_count = 0
                        while retry_count < max_retries:
                            # Check for stop flag before attempting AI analysis
                            if self._redis and self._redis.exists(f"test_case_stop_generating:{test_case_id}"):
                                self.logger.info(f"[PID:{pid}] Stop flag detected during retry loop, aborting generation")
                                break
                            
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
                                
                                # Check for stop flag after AI response
                                if self._redis and self._redis.exists(f"test_case_stop_generating:{test_case_id}"):
                                    self.logger.info(f"[PID:{pid}] Stop flag detected after AI response, aborting generation")
                                    break
                                
                                self.logger.info(f"[PID:{pid}] Analyzer response: {analyzer_response}")
                                
                                # Handle tuple unpacking with defaults
                                if isinstance(analyzer_response, tuple):
                                    self.logger.info(f"[PID:{pid}] Response length: {len(analyzer_response)}")
                                    if len(analyzer_response) == 5:
                                        # Old format (5-tuple) - backward compatibility
                                        next_step, element_purpose, action, element_locator, by_strategy = analyzer_response
                                        css_selector = ""  # No CSS fallback
                                        value = ""  # Default empty value
                                    elif len(analyzer_response) == 6:
                                        # Old format (6-tuple) - backward compatibility
                                        next_step, element_purpose, action, element_locator, by_strategy, value = analyzer_response
                                        css_selector = ""  # No CSS fallback
                                    else:
                                        # New format (7-tuple) with CSS fallback
                                        next_step, element_purpose, action, element_locator, css_selector, by_strategy, value = analyzer_response
                                            
                                    self.logger.info(f"[PID:{pid}] Unpacked values: next_step={next_step}, purpose={element_purpose}, action={action}, xpath={element_locator}, css={css_selector}, strategy={by_strategy}, value={value}")
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
                        
                        # Check if stop was requested during retry loop
                        if self._redis and self._redis.exists(f"test_case_stop_generating:{test_case_id}"):
                            self.logger.info(f"[PID:{pid}] Stop flag detected after retry loop, breaking main generation loop")
                            break
                        
                        # Normalize next_step to handle cases where Gemini returns "Test complete..." instead of "Stop"
                        if next_step and isinstance(next_step, str):
                            next_step_lower = next_step.strip().lower()
                            # Check if Gemini returned a completion message instead of "Stop"
                            # Only catch CLEAR completion/optional indicators, not descriptive steps
                            completion_phrases = [
                                'test complete', 'test finished', 'test done', 'no more steps', 'test is complete',
                                'test has successfully', 'test is now complete', 'test is finished'
                            ]
                            if any(phrase in next_step_lower for phrase in completion_phrases):
                                self.logger.info(f"[PID:{pid}] Detected test completion message: '{next_step}' - normalizing to 'Stop'")
                                next_step = "Stop"
                        
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
                            
                            # Save the step to the database first using session connection
                            step_id = self._save_step_with_session(
                                session_cursor, session_conn,
                                test_case_id=test_case_id,
                                step_order=step_order,
                                element_purpose=element_purpose,
                                action=action,
                                element_locator=original_element_locator,
                                value=original_value,
                                by_strategy=by_strategy,
                                css_selector=css_selector
                            )
                            
                            try:
                                self.execute_step(action, "N/A", processed_value, by_strategy, env)
                                

                            except Exception as e:

                                # Take a screenshot of the failure state
                                try:
                                    failure_screenshot = self.browser.take_screenshot(f"error_step_{step_order}")
                                    self.logger.error(f"[PID:{pid}] Error screenshot saved to: {failure_screenshot}")
                                    
                                    # Save screenshot using session connection
                                    with open(failure_screenshot, "rb") as image_file:
                                        encoded_string = base64.b64encode(image_file.read()).decode('utf-8')
                                    self._update_step_with_screenshot_session(
                                        session_cursor, session_conn, step_id, 
                                        failure_screenshot, encoded_string, 
                                        f"Error screenshot for step {step_order}"
                                    )
                                except Exception as screenshot_error:
                                    self.logger.error(f"[PID:{pid}] Failed to capture error screenshot: {str(screenshot_error)}")
                                
                                # Update the step in the database to mark it as failed using session connection
                                try:
                                    self._update_step_error_session(session_cursor, session_conn, step_id, str(e))
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
                                        # CRITICAL: Check if browser session is still alive
                                        if not self.browser:
                                            self.logger.error(f"[PID:{pid}] Browser session lost during error recovery, re-initializing...")
                                            self._ensure_browser_initialized()
                                            if not self.browser:
                                                raise Exception("Failed to re-initialize browser session")
                                        
                                        # Verify browser session is actually functional
                                        try:
                                            _ = self.browser.driver.current_url
                                        except Exception as session_error:
                                            self.logger.error(f"[PID:{pid}] Browser session dead (error: {session_error}), re-initializing...")
                                            self.browser = None
                                            self._ensure_browser_initialized()
                                        
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
                                            # Old format (5-tuple)
                                            next_step, element_purpose, action, element_locator, by_strategy = analyzer_response
                                            css_selector = ""
                                            value = ""
                                        elif len(analyzer_response) == 6:
                                            # Old format (6-tuple)
                                            next_step, element_purpose, action, element_locator, by_strategy, value = analyzer_response
                                            css_selector = ""
                                        else:
                                            # New format (7-tuple) with CSS fallback
                                            next_step, element_purpose, action, element_locator, css_selector, by_strategy, value = analyzer_response
                                            
                                        self.logger.info(f"[PID:{pid}] AI suggested fix: action={action}, xpath={element_locator}, css={css_selector}, strategy={by_strategy}, value={value}")
                                        
                                        # Process environment variables for execution
                                        if value:
                                            processed_value = env.process_variables(value)
                                        else:
                                            processed_value = value
                                            
                                        if element_locator:
                                            processed_element_locator = env.process_variables(element_locator)
                                        else:
                                            processed_element_locator = element_locator
                                        
                                        # TRY TO EXECUTE THE CORRECTED STEP FIRST
                                        self.logger.info(f"[PID:{pid}] Executing corrected step: {action} on {element_locator}")
                                        self.execute_step(action, processed_element_locator, processed_value, by_strategy, env)
                                        
                                        # EXECUTION SUCCEEDED - Now save the corrected step to the database
                                        self.logger.info(f"[PID:{pid}] Corrected step execution succeeded, saving to database")
                                        corrected_step_id = self._save_step(
                                            test_case_id=test_case_id,
                                            step_order=step_order,
                                            element_purpose=f"[CORRECTED] {element_purpose}",
                                            action=action,
                                            element_locator=element_locator,
                                            value=value,
                                            by_strategy=by_strategy,
                                            css_selector=css_selector
                                        )
                                        
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
                                        
                                        # If this was the last attempt, save as risky step instead of stopping
                                        if recovery_attempt >= max_recovery_attempts:
                                            self.logger.warning(f"[PID:{pid}] Maximum recovery attempts reached, saving step as risky with very low confidence")
                                            
                                            # Save the failed step with very low confidence
                                            try:
                                                step_id = self._save_step(
                                                    test_case_id=test_case_id,
                                                    step_order=step_order,
                                                    element_purpose=f"[RISKY] {element_purpose}",
                                                    action=action,
                                                    element_locator=original_element_locator,
                                                    value=original_value,
                                                    by_strategy=by_strategy,
                                                    css_selector=css_selector
                                                )
                                                
                                                # Save very low confidence score for this step
                                                if step_id and step_id != -1:
                                                    with self.get_db_connection() as conn:
                                                        with conn.cursor() as cursor:
                                                            cursor.execute("""
                                                                INSERT INTO confidence_scores 
                                                                (test_case_id, step_id, overall_confidence, selector_confidence, 
                                                                 action_confidence, data_confidence, pattern_confidence, risk_level)
                                                                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                                                                ON CONFLICT (test_case_id, step_id) 
                                                                DO UPDATE SET 
                                                                    overall_confidence = %s,
                                                                    risk_level = %s
                                                            """, (
                                                                test_case_id, step_id, 0.15, 0.2, 0.1, 0.1, 0.1, 'very_low',
                                                                0.15, 'very_low'
                                                            ))
                                                            conn.commit()
                                                    
                                                    self.logger.info(f"[PID:{pid}] Saved risky step {step_id} with very low confidence (15%)")
                                                    
                                                    # Move to next step instead of stopping
                                                    next_prompt = next_step
                                                    step_order += 1
                                                    break
                                            except Exception as risky_save_error:
                                                self.logger.error(f"[PID:{pid}] Failed to save risky step: {str(risky_save_error)}")
                                                return
                        elif action and element_locator:
                            # Check for stop flag before executing step
                            if self._redis and self._redis.exists(f"test_case_stop_generating:{test_case_id}"):
                                self.logger.info(f"[PID:{pid}] Stop flag detected before step execution, aborting generation")
                                break
                            
                            self.logger.info(f"[PID:{pid}] Executing step: {action} on {element_locator}")

                            # TRY TO EXECUTE FIRST (don't save yet)
                            step_id = None
                            try:
                                result = self.execute_step(action, processed_element_locator, processed_value, by_strategy, env)
                                
                                # Check if test was completed via stop_test action
                                if result == "test_completed":
                                    self.logger.info(f"[PID:{pid}] ✅ Test completed successfully via stop_test action")
                                    break
                                
                                # EXECUTION SUCCEEDED - Now save the step to database
                                self.logger.info(f"[PID:{pid}] Step execution succeeded, saving to database")
                                step_id = self._save_step(
                                    test_case_id=test_case_id,
                                    step_order=step_order,
                                    element_purpose=element_purpose,
                                    action=action,
                                    element_locator=original_element_locator,
                                    value=original_value,
                                    by_strategy=by_strategy,
                                    css_selector=css_selector
                                )
                                
                                # Update ReasoningCollector with successful step
                                if reasoning_collector:
                                    try:
                                        reasoning_collector.set_current_step(
                                            test_case_id,
                                            step_number=step_order,
                                            action=action,
                                            description=element_purpose,
                                            reasoning=f"Successfully executed: {action} on target element",
                                            element_info=original_element_locator
                                        )
                                    except Exception as e:
                                        self.logger.error(f"[PID:{pid}] Failed to update reasoning with successful step: {e}")
                                
                                # Skip if this was a duplicate step
                                if step_id == -1:
                                    self.logger.info(f"[PID:{pid}] Duplicate step detected, skipping database save")
                                    next_prompt = next_step
                                    continue
                                
                                # Take screenshot after successful step
                                try:
                                    page_source = self.browser.get_page_source()
                                    screenshot_path = self.browser.take_screenshot()
                                    self.logger.info(f"[PID:{pid}] Screenshot taken: {screenshot_path}")
                                    
                                    # Save screenshot using session connection
                                    with open(screenshot_path, "rb") as image_file:
                                        encoded_string = base64.b64encode(image_file.read()).decode('utf-8')
                                    self._update_step_with_screenshot_session(
                                        session_cursor, session_conn, step_id, 
                                        screenshot_path, encoded_string, 
                                        f"Screenshot for step {step_order}"
                                    )
                                except Exception as screenshot_error:
                                    self.logger.error(f"[PID:{pid}] Failed to save screenshot: {str(screenshot_error)}")
                                
                                # Move to next step
                                next_prompt = next_step
                                step_order += 1
                                continue
                            except Exception as e:
                                # EXECUTION FAILED - Don't save the step yet, try to fix it with AI
                                self.logger.error(f"[PID:{pid}] Step execution failed: {str(e)}")
                                
                                # Take a screenshot of the failure state
                                failure_screenshot = None
                                try:
                                    failure_screenshot = self.browser.take_screenshot(f"error_step_{step_order}")
                                    self.logger.error(f"[PID:{pid}] Error screenshot saved to: {failure_screenshot}")
                                except Exception as screenshot_error:
                                    self.logger.error(f"[PID:{pid}] Failed to capture failure screenshot: {str(screenshot_error)}")
                                
                                # Log the current page URL and title
                                try:
                                    current_url = self.browser.driver.current_url
                                    current_title = self.browser.driver.title
                                    self.logger.error(f"[PID:{pid}] Page at failure: URL={current_url}, Title={current_title}")
                                except Exception as page_error:
                                    self.logger.error(f"[PID:{pid}] Failed to get page details: {str(page_error)}")
                                
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
                                        # CRITICAL: Check if browser session is still alive
                                        if not self.browser:
                                            self.logger.error(f"[PID:{pid}] Browser session lost during error recovery, re-initializing...")
                                            self._ensure_browser_initialized()
                                            if not self.browser:
                                                raise Exception("Failed to re-initialize browser session")
                                        
                                        # Verify browser session is actually functional
                                        try:
                                            _ = self.browser.driver.current_url
                                        except Exception as session_error:
                                            self.logger.error(f"[PID:{pid}] Browser session dead (error: {session_error}), re-initializing...")
                                            self.browser = None
                                            self._ensure_browser_initialized()
                                        
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
                                            # Old format (5-tuple)
                                            next_step, element_purpose, action, element_locator, by_strategy = analyzer_response
                                            css_selector = ""
                                            value = ""
                                        elif len(analyzer_response) == 6:
                                            # Old format (6-tuple)
                                            next_step, element_purpose, action, element_locator, by_strategy, value = analyzer_response
                                            css_selector = ""
                                        else:
                                            # New format (7-tuple) with CSS fallback
                                            next_step, element_purpose, action, element_locator, css_selector, by_strategy, value = analyzer_response
                                            
                                        self.logger.info(f"[PID:{pid}] AI suggested fix: action={action}, xpath={element_locator}, css={css_selector}, strategy={by_strategy}, value={value}")
                                        
                                        # Process environment variables for execution
                                        if value:
                                            processed_value = env.process_variables(value)
                                        else:
                                            processed_value = value
                                            
                                        if element_locator:
                                            processed_element_locator = env.process_variables(element_locator)
                                        else:
                                            processed_element_locator = element_locator
                                        
                                        # TRY TO EXECUTE THE CORRECTED STEP FIRST
                                        self.logger.info(f"[PID:{pid}] Executing corrected step: {action} on {element_locator}")
                                        self.execute_step(action, processed_element_locator, processed_value, by_strategy, env)
                                        
                                        # EXECUTION SUCCEEDED - Now save the corrected step to the database
                                        self.logger.info(f"[PID:{pid}] Corrected step execution succeeded, saving to database")
                                        corrected_step_id = self._save_step(
                                            test_case_id=test_case_id,
                                            step_order=step_order,
                                            element_purpose=f"[CORRECTED] {element_purpose}",
                                            action=action,
                                            element_locator=element_locator,
                                            value=value,
                                            by_strategy=by_strategy,
                                            css_selector=css_selector
                                        )
                                        
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
                                        
                                        # If this was the last attempt, save as risky step instead of stopping
                                        if recovery_attempt >= max_recovery_attempts:
                                            self.logger.warning(f"[PID:{pid}] Maximum recovery attempts reached, saving step as risky with very low confidence")
                                            
                                            # Save the failed step with very low confidence
                                            try:
                                                step_id = self._save_step(
                                                    test_case_id=test_case_id,
                                                    step_order=step_order,
                                                    element_purpose=f"[RISKY] {element_purpose}",
                                                    action=action,
                                                    element_locator=original_element_locator,
                                                    value=original_value,
                                                    by_strategy=by_strategy,
                                                    css_selector=css_selector
                                                )
                                                
                                                # Save very low confidence score for this step
                                                if step_id and step_id != -1:
                                                    with self.get_db_connection() as conn:
                                                        with conn.cursor() as cursor:
                                                            cursor.execute("""
                                                                INSERT INTO confidence_scores 
                                                                (test_case_id, step_id, overall_confidence, selector_confidence, 
                                                                 action_confidence, data_confidence, pattern_confidence, risk_level)
                                                                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                                                                ON CONFLICT (test_case_id, step_id) 
                                                                DO UPDATE SET 
                                                                    overall_confidence = %s,
                                                                    risk_level = %s
                                                            """, (
                                                                test_case_id, step_id, 0.15, 0.2, 0.1, 0.1, 0.1, 'very_low',
                                                                0.15, 'very_low'
                                                            ))
                                                            conn.commit()
                                                    
                                                    self.logger.info(f"[PID:{pid}] Saved risky step {step_id} with very low confidence (15%)")
                                                    
                                                    # Move to next step instead of stopping
                                                    next_prompt = next_step
                                                    step_order += 1
                                                    break
                                            except Exception as risky_save_error:
                                                self.logger.error(f"[PID:{pid}] Failed to save risky step: {str(risky_save_error)}")
                                                return
                except Exception as step_gen_error:
                    self.logger.error(f"[PID:{pid}] Error during step generation: {str(step_gen_error)}")
                    import traceback
                    self.logger.error(f"[PID:{pid}] Traceback: {traceback.format_exc()}")
                    # Update end time even on error
                    self._update_generation_end_time(test_case_id)
                    raise

                # Update end time on successful completion using session connection
                self._update_generation_end_time_with_session(session_cursor, session_conn, test_case_id)
                self.logger.info(f"[PID:{pid}] Test step generation completed for test case {test_case_id}")
                
                # Complete reasoning collection
                if reasoning_collector:
                    try:
                        reasoning_collector.complete_generation(test_case_id, step_order - 1)
                    except Exception as e:
                        self.logger.error(f"[PID:{pid}] Failed to complete reasoning collection: {e}")
                
                # Mark test_run as completed after successful generation
                try:
                    with self.get_db_connection() as connection:
                        with connection.cursor() as cursor:
                            cursor.execute("""
                                UPDATE test_runs 
                                SET result = 'completed'
                                WHERE test_case_id = %s AND result = 'running'
                            """, (test_case_id,))
                            connection.commit()
                            if cursor.rowcount > 0:
                                self.logger.info(f"[PID:{pid}] Marked test_run as completed after successful generation for test case {test_case_id}")
                except Exception as db_error:
                    self.logger.error(f"[PID:{pid}] Failed to mark test_run as completed: {db_error}")
                
                # Clear the generation flag from Redis
                try:
                    if self._redis:
                        self._redis.delete(f"test_case_generating:{test_case_id}")
                        self._redis.delete(f"test_case_current_step:{test_case_id}")
                        self._redis.delete(f"test_case_next_step:{test_case_id}")
                        self.logger.info(f"[PID:{pid}] Cleared generation flags from Redis for test case {test_case_id}")
                except Exception as redis_error:
                    self.logger.error(f"[PID:{pid}] Failed to clear Redis flags: {redis_error}")

        except Exception as e:
            self.logger.error(f"[PID:{pid}] Error generating test steps: {str(e)}")
            # Update end time even on error using fallback method
            self._update_generation_end_time(test_case_id)
            
            # Mark any running test_run as stopped when generation fails
            try:
                with self.get_db_connection() as connection:
                    with connection.cursor() as cursor:
                        cursor.execute("""
                            UPDATE test_runs 
                            SET result = 'stopped'
                            WHERE test_case_id = %s AND result = 'running'
                        """, (test_case_id,))
                        connection.commit()
                        if cursor.rowcount > 0:
                            self.logger.info(f"[PID:{pid}] Marked test_run as stopped due to generation error for test case {test_case_id}")
            except Exception as db_error:
                self.logger.error(f"[PID:{pid}] Failed to mark test_run as stopped: {db_error}")
            
            # Clear the generation flag from Redis on error too
            try:
                if self._redis:
                    self._redis.delete(f"test_case_generating:{test_case_id}")
                    self._redis.delete(f"test_case_current_step:{test_case_id}")
                    self._redis.delete(f"test_case_next_step:{test_case_id}")
                    self.logger.info(f"[PID:{pid}] Cleared generation flags from Redis after error for test case {test_case_id}")
            except Exception as redis_error:
                self.logger.error(f"[PID:{pid}] Failed to clear Redis flags on error: {redis_error}")
            
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

    def _create_test_run(self, test_case_id: int, status: str = "running", execution_id=None):
        """Create a new test run record and return the test_run_id"""
        try:
            connection = get_db_connection()
            try:
                with connection.cursor() as cursor:
                    cursor.execute(
                        """
                        INSERT INTO test_runs (test_case_id, result, run_date, execution_id)
                        VALUES (%s, %s, %s, %s)
                        RETURNING id
                        """,
                        (test_case_id, status, datetime.now(), execution_id)
                    )
                    test_run_id = cursor.fetchone()[0]
                    connection.commit()
                    self.logger.info(f"Created test run {test_run_id} for test case {test_case_id}, execution: {execution_id}")
                    return test_run_id
            finally:
                return_db_connection(connection)
        except Exception as e:
            self.logger.error(f"Failed to create test run: {e}")
            raise

    def start_test_case_async(self, test_case_id: int, environment_vars=None, execution_id=None):
        """
        Start test case execution asynchronously and return test_run_id immediately.
        
        Args:
            test_case_id: ID of the test case to run
            environment_vars: Optional dictionary with environment variables
            execution_id: Optional ID of the execution to link this test run to
            
        Returns:
            dict: Contains test_run_id and status
        """
        pid = os.getpid()
        self.logger.info(f"[PID:{pid}] Starting async test case execution for ID: {test_case_id}, execution_id: {execution_id}")
        
        try:
            # Create test run record immediately with execution_id
            test_run_id = self._create_test_run(test_case_id, status="running", execution_id=execution_id)
            self.logger.info(f"[PID:{pid}] Created test run with ID: {test_run_id}, linked to execution: {execution_id}")
            
            # Start background execution
            import threading
            thread = threading.Thread(
                target=self._execute_test_case_background,
                args=(test_run_id, test_case_id, environment_vars)
            )
            thread.daemon = True
            thread.start()
            
            return {
                "test_run_id": test_run_id,
                "status": "started",
                "message": "Test execution started in background"
            }
            
        except Exception as e:
            self.logger.error(f"[PID:{pid}] Failed to start async test execution: {e}")
            raise

    def _execute_test_case_background(self, test_run_id: int, test_case_id: int, environment_vars=None):
        """
        Execute test case in background and update test run record with results.
        
        Args:
            test_run_id: ID of the test run
            test_case_id: ID of the test case to run
            environment_vars: Optional dictionary with environment variables
        """
        pid = os.getpid()
        self.logger.info(f"[PID:{pid}] Background execution started for test run {test_run_id}")
        start_time = datetime.now()
        
        try:
            # Execute the original test case logic
            result = self._run_test_case_internal(test_run_id, test_case_id, environment_vars)
            
            # Update test run with success result
            duration = (datetime.now() - start_time).total_seconds()
            self._update_test_run(
                test_run_id, 
                result.get("status", "completed"), 
                result.get("exception"), 
                duration,
                result.get("stdout"),
                result.get("stderr")
            )
            
            self.logger.info(f"[PID:{pid}] Background execution completed for test run {test_run_id}")
            
        except Exception as e:
            # Update test run with failure result
            duration = (datetime.now() - start_time).total_seconds()
            self._update_test_run(
                test_run_id, 
                "failed", 
                str(e), 
                duration,
                None,
                str(e)
            )
            self.logger.error(f"[PID:{pid}] Background execution failed for test run {test_run_id}: {e}")

    def _run_test_case_internal(self, test_run_id: int, test_case_id: int, environment_vars=None):
        """
        Internal method that contains the original test case execution logic.
        This is extracted from the original run_test_case method.
        """
        pid = os.getpid()
        self.logger.info(f"[PID:{pid}] Internal execution started for test run {test_run_id}, test case {test_case_id}")
        
        # Initialize environment helper with provided variables
        env = EnvHelper(environment_vars)
        
        # Log environment variables for debugging
        if environment_vars:
            self.logger.info(f"[PID:{pid}] Environment variables provided: {list(environment_vars.keys())}")
        else:
            self.logger.info(f"[PID:{pid}] No environment variables provided")
        
        try:
            # Get test case info
            test_case_name, test_case_description = self._get_test_case(test_case_id)
            
            # Get test steps
            steps = self._get_test_steps(test_case_id)
            if not steps:
                self.logger.warning(f"[PID:{pid}] No test steps found for test case {test_case_id}")
                return {
                    "test_run_id": test_run_id,
                    "status": "completed",
                    "exception": "No test steps found",
                    "stdout": None,
                    "stderr": "No test steps found for this test case"
                }
            
            # Ensure browser is initialized
            self._ensure_browser_initialized()
            
            # Clear browser cookies and cache before starting test execution to prevent session carryover
            try:
                self.logger.info(f"[PID:{pid}] Clearing browser cookies and cache before test execution")
                self.browser.driver.delete_all_cookies()
                # Clear local storage and session storage via JavaScript
                self.browser.driver.execute_script("window.localStorage.clear();")
                self.browser.driver.execute_script("window.sessionStorage.clear();")
                self.logger.info(f"[PID:{pid}] Browser cache cleared successfully")
            except Exception as cleanup_error:
                self.logger.warning(f"[PID:{pid}] Failed to clear browser cache: {cleanup_error}")
            
            # Navigate to base_url from environment variables before executing steps
            base_url = env.base_url
            if base_url:
                self.logger.info(f"[PID:{pid}] Navigating to base_url from environment: {base_url}")
                try:
                    self.browser.navigate(base_url)
                    self.logger.info(f"[PID:{pid}] Successfully navigated to base_url: {base_url}")
                except Exception as e:
                    self.logger.error(f"[PID:{pid}] Failed to navigate to base_url {base_url}: {str(e)}")
                    return {
                        "test_run_id": test_run_id,
                        "status": "failed",
                        "exception": f"Failed to navigate to base_url: {str(e)}",
                        "stdout": None,
                        "stderr": f"Failed to navigate to base_url {base_url}: {str(e)}"
                    }
            else:
                self.logger.warning(f"[PID:{pid}] No base_url found in environment variables")
            
            self.logger.info(f"[PID:{pid}] Executing {len(steps)} test steps for test case: {test_case_name}")
            
            # Execute each step and track results
            step_order = 0
            failed_steps = 0
            total_steps = len(steps)
            for step in steps:
                # Check for stop execution flag
                if self._redis and self._redis.exists(f"test_case_stop_execution:{test_case_id}"):
                    self.logger.info(f"[PID:{pid}] Stop execution flag found, stopping test case {test_case_id}")
                    self._redis.delete(f"test_case_stop_execution:{test_case_id}")
                    return {
                        "test_run_id": test_run_id,
                        "status": "stopped",
                        "exception": "Test execution stopped by user",
                        "stdout": None,
                        "stderr": "Test execution was stopped by user request"
                    }
                
                step_order += 1
                
                step_id, action, element_path, description, expected_result, value, path_type = step
                self.logger.info(f"[PID:{pid}] Executing step {step_order}: {action} (step_id: {step_id})")
                
                # Process environment variables to get resolved values for logging
                resolved_value = value
                resolved_element_path = element_path
                if env and value:
                    resolved_value = env.process_variables(value)
                if env and element_path:
                    resolved_element_path = env.process_variables(element_path)
                
                # Prepare step data for Phase 1 collection (used for both success and failure)
                step_data = {
                    'id': step_id,  # CRITICAL: Include step_id so confidence scorer doesn't default to 0
                    'action': action,
                    'element_locator': resolved_element_path,
                    'value': resolved_value,
                    'by_strategy': path_type
                }
                
                # Record step start with RESOLVED values
                step_start_time = datetime.now()
                step_result_id = self._log_step_execution_result(
                    test_run_id, step_id, step_order, "running",
                    step_description=description, step_action=action,
                    step_element_path=resolved_element_path, step_value=resolved_value
                )
                
                try:
                    # Execute the step
                    self.execute_step(action, element_path, value, path_type, env)
                    
                    # Calculate execution time
                    execution_time_ms = int((datetime.now() - step_start_time).total_seconds() * 1000)
                    
                    # Capture screenshot after successful step execution
                    screenshot_path = None
                    screenshot_base64 = None
                    try:
                        screenshot_path = self.browser.take_screenshot(f"step_{step_order}_{action}")
                        self.logger.info(f"[PID:{pid}] Screenshot captured: {screenshot_path}")
                        
                        # Convert screenshot to base64 for database storage
                        if screenshot_path and os.path.exists(screenshot_path):
                            with open(screenshot_path, "rb") as image_file:
                                screenshot_base64 = base64.b64encode(image_file.read()).decode('utf-8')
                                
                    except Exception as screenshot_error:
                        self.logger.warning(f"[PID:{pid}] Failed to capture screenshot for step {step_order}: {screenshot_error}")
                    
                    # Update step result to passed with screenshot data
                    self._update_step_execution_result(
                        step_result_id, "passed", None, screenshot_path, screenshot_base64, execution_time_ms
                    )
                    self.logger.info(f"[PID:{pid}] Step {step_order} result updated with screenshot (base64: {len(screenshot_base64) if screenshot_base64 else 0} bytes)")
                    
                    # Phase 1: Collect validation result for successful step
                    try:
                        validation_result = self.validator.validate_step(step_data)
                        self.validator.save_validation_result(test_case_id, step_id, validation_result)
                        self.logger.info(f"✓ Step {step_order} validation: {validation_result.confidence:.1f}% confidence")
                    except Exception as validation_error:
                        self.logger.error(f"❌ Failed to validate step {step_order}: {validation_error}", exc_info=True)
                    
                    # Phase 1: Collect confidence score for successful step
                    try:
                        confidence_score = self.scorer.score_step(step_data)
                        if confidence_score:
                            self.scorer.save_confidence_score(test_case_id, confidence_score)
                            self.logger.info(f"📊 Step {step_order} confidence: {confidence_score.overall_confidence:.1f}% ({confidence_score.risk_level} risk)")
                        else:
                            self.logger.warning(f"⚠️ Confidence scorer returned None for step {step_order}")
                    except Exception as scoring_error:
                        self.logger.error(f"❌ Failed to score step {step_order}: {scoring_error}", exc_info=True)
                    
                    self.logger.info(f"[PID:{pid}] Step {step_order} completed successfully")
                    
                except Exception as step_error:
                    # Calculate execution time
                    execution_time_ms = int((datetime.now() - step_start_time).total_seconds() * 1000)
                    
                    # Capture screenshot for failed step as well
                    screenshot_path = None
                    screenshot_base64 = None
                    try:
                        screenshot_path = self.browser.take_screenshot(f"step_{step_order}_{action}_error")
                        self.logger.info(f"[PID:{pid}] Error screenshot captured: {screenshot_path}")
                        
                        # Convert screenshot to base64 for database storage
                        if screenshot_path and os.path.exists(screenshot_path):
                            with open(screenshot_path, "rb") as image_file:
                                screenshot_base64 = base64.b64encode(image_file.read()).decode('utf-8')
                                
                    except Exception as screenshot_error:
                        self.logger.warning(f"[PID:{pid}] Failed to capture error screenshot for step {step_order}: {screenshot_error}")
                    
                    # Update step result to failed with screenshot data
                    self._update_step_execution_result(
                        step_result_id, "failed", str(step_error), screenshot_path, screenshot_base64, execution_time_ms
                    )
                    
                    # Phase 1: Collect execution feedback for failed step
                    try:
                        failure_record = self.feedback_collector.collect_failure(
                            test_case_id=test_case_id,
                            step_id=step_id,
                            step_order=step_order,
                            action=action,
                            element_locator=resolved_element_path,
                            error=step_error
                        )
                        self.feedback_collector.save_failure_record(failure_record)
                        self.logger.info(f"📝 Saved failure record for step {step_order}")
                    except Exception as feedback_error:
                        self.logger.warning(f"⚠️ Failed to save feedback for step {step_order}: {feedback_error}")
                    
                    self.logger.error(f"[PID:{pid}] Step {step_order} failed: {step_error}")
                    failed_steps += 1
                    
                    # Continue to next step instead of stopping entire test
                    continue
            
            # Clean up any remaining steps in 'running' status
            self._cleanup_running_steps(test_run_id)
            
            # Determine final test run status based on step results
            if failed_steps > 0:
                final_status = "failed" 
                final_stdout = f"Test case '{test_case_name}' completed with {failed_steps}/{total_steps} steps failed"
                final_stderr = f"{failed_steps} out of {total_steps} steps failed"
                self.logger.warning(f"[PID:{pid}] Test case {test_case_id} completed with {failed_steps} failed steps")
            else:
                final_status = "completed"
                final_stdout = f"Test case '{test_case_name}' executed successfully"
                final_stderr = None
                self.logger.info(f"[PID:{pid}] All steps completed successfully for test case {test_case_id}")
            
            # Cleanup browser session immediately after test execution completes
            self.logger.info(f"[PID:{pid}] Cleaning up Selenium session after test execution")
            self._cleanup_browser()
            
            # Clear browser cookies and cache to prevent session carryover
            try:
                self.logger.info(f"[PID:{pid}] Clearing browser cookies and cache")
                self.browser.driver.delete_all_cookies()
                self.logger.info(f"[PID:{pid}] Browser cookies cleared successfully")
            except Exception as cleanup_error:
                self.logger.warning(f"[PID:{pid}] Failed to clear browser cookies: {cleanup_error}")
            
            return {
                "test_run_id": test_run_id,
                "status": final_status,
                "exception": None,
                "stdout": final_stdout,
                "stderr": final_stderr
            }
            
        except Exception as e:
            # Clean up any remaining steps in 'running' status even on exception
            self._cleanup_running_steps(test_run_id)
            
            # Cleanup browser session immediately even on exception
            self.logger.info(f"[PID:{pid}] Cleaning up Selenium session after test execution failure")
            self._cleanup_browser()
            
            self.logger.error(f"[PID:{pid}] Test case execution failed: {e}")
            return {
                "test_run_id": test_run_id,
                "status": "failed",
                "exception": str(e),
                "stdout": None,
                "stderr": str(e)
            }

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
                            
                            # Use timezone-aware datetime to avoid "can't subtract offset-naive and offset-aware datetimes" error
                            from datetime import datetime as dt, timezone
                            now_utc = dt.now(timezone.utc)
                            
                            # Make started_at timezone-aware if it's naive
                            if started_at.tzinfo is None:
                                started_at = started_at.replace(tzinfo=timezone.utc)
                            
                            execution_time_ms = int((now_utc - started_at).total_seconds() * 1000)
                            cursor.execute(
                                """
                                UPDATE test_step_execution_results 
                                SET status = %s, error_message = %s, execution_time_ms = %s, completed_at = %s
                                WHERE id = %s
                                """,
                                ("failed", "Step was orphaned - process may have crashed or been killed", 
                                 execution_time_ms, now_utc, step_result_id)
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
            
            # Mark any running test_run as stopped in database
            try:
                with self.get_db_connection() as connection:
                    with connection.cursor() as cursor:
                        cursor.execute("""
                            UPDATE test_runs 
                            SET result = 'stopped'
                            WHERE test_case_id = %s AND result = 'running'
                        """, (test_case_id,))
                        connection.commit()
                        if cursor.rowcount > 0:
                            self.logger.info(f"[PID:{pid}] Marked test_run as stopped for test case {test_case_id}")
            except Exception as db_error:
                self.logger.error(f"[PID:{pid}] Failed to mark test_run as stopped: {db_error}")
            
            # Cleanup browser session immediately when generation is stopped
            self.logger.info(f"[PID:{pid}] Cleaning up Selenium session after stopping generation")
            self._cleanup_browser()
            
            return True
        except Exception as e:
            self.logger.error(f"[PID:{pid}] Failed to set stop flag in Redis: {e}")
        
        return False

    def _cleanup_running_steps(self, test_run_id: int):
        """
        Clean up any steps that are still in 'running' status for a completed test run.
        Sets them to 'skipped' status to indicate they weren't executed.
        
        Args:
            test_run_id: ID of the test run
        """
        try:
            connection = get_db_connection()
            try:
                with connection.cursor() as cursor:
                    cursor.execute(
                        """
                        UPDATE test_step_execution_results 
                        SET status = 'skipped', 
                            error_message = 'Step not executed - test run completed',
                            execution_time_ms = 0
                        WHERE test_run_id = %s AND status = 'running'
                        """,
                        (test_run_id,)
                    )
                    
                    rows_updated = cursor.rowcount
                    if rows_updated > 0:
                        self.logger.info(f"Cleaned up {rows_updated} running steps for test run {test_run_id}")
                    
                    connection.commit()
            finally:
                connection.close()
        except Exception as e:
            self.logger.error(f"Error cleaning up running steps for test run {test_run_id}: {e}")

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

    def stop_all_test_executions(self, user_id: str = None, client_id: str = None) -> dict:
        """
        Stop all currently running test executions.
        
        Args:
            user_id: Optional user ID to filter executions
            client_id: Optional client ID to filter executions
            
        Returns:
            dict: Status information about stopped executions
        """
        pid = os.getpid()
        self.logger.info(f"[PID:{pid}] Stopping all test executions for user {user_id}, client {client_id}")
        
        stopped_count = 0
        error_count = 0
        
        try:
            if not self._redis:
                return {"status": "error", "message": "Redis not available", "stopped_count": 0}
            
            # Get all running test case keys from Redis
            running_pattern = "test_case_running:*"
            running_keys = self._redis.keys(running_pattern)
            
            self.logger.info(f"[PID:{pid}] Found {len(running_keys)} running test cases in Redis")
            
            # Process Redis keys first
            for key in running_keys:
                try:
                    # Extract test case ID from key
                    test_case_id = key.decode('utf-8').replace('test_case_running:', '')
                    
                    # Optionally filter by user/client if provided
                    if user_id or client_id:
                        # Query database to check ownership
                        conn = get_db_connection()
                        cursor = conn.cursor()
                        
                        query = """
                            SELECT tc.id FROM test_cases tc 
                            JOIN users u ON tc.created_by = u.id 
                            WHERE tc.id = %s
                        """
                        params = [test_case_id]
                        
                        if user_id:
                            query += " AND u.id = %s"
                            params.append(user_id)
                        if client_id:
                            query += " AND u.client_id = %s"
                            params.append(client_id)
                        
                        cursor.execute(query, params)
                        result = cursor.fetchone()
                        
                        return_db_connection(conn)
                        
                        if not result:
                            continue  # Skip this test case - doesn't belong to user/client
                    
                    # Set stop flag for this test case
                    self._redis.set(f"test_case_stop_execution:{test_case_id}", "1", ex=3600)
                    
                    # Clear running status
                    self._redis.delete(f"test_case_running:{test_case_id}")
                    
                    # Also update database records to mark running tests as stopped
                    try:
                        conn = get_db_connection()
                        cursor = conn.cursor()
                        
                        # Update any running test_runs for this test case to stopped
                        cursor.execute("""
                            UPDATE test_runs 
                            SET result = 'stopped', duration = EXTRACT(EPOCH FROM (NOW() - run_date))::real
                            WHERE test_case_id = %s AND result = 'running'
                        """, (test_case_id,))
                        
                        updated_rows = cursor.rowcount
                        conn.commit()
                        return_db_connection(conn)
                        
                        if updated_rows > 0:
                            self.logger.info(f"[PID:{pid}] Updated {updated_rows} database records for test case {test_case_id}")
                        
                    except Exception as db_error:
                        self.logger.error(f"[PID:{pid}] Failed to update database for test case {test_case_id}: {db_error}")
                        if conn:
                            return_db_connection(conn)
                    
                    stopped_count += 1
                    self.logger.info(f"[PID:{pid}] Set stop flag for test case {test_case_id}")
                    
                except Exception as e:
                    error_count += 1
                    self.logger.error(f"[PID:{pid}] Failed to stop test case from key {key}: {e}")
            
            # Also check for stale database records without Redis keys
            self.logger.info(f"[PID:{pid}] Checking for stale database records without Redis keys...")
            
            try:
                conn = get_db_connection()
                cursor = conn.cursor()
                
                # Find test runs with 'running' status
                query = """
                    SELECT DISTINCT tr.test_case_id, tc.name
                    FROM test_runs tr
                    JOIN test_cases tc ON tr.test_case_id = tc.id
                    WHERE tr.result = 'running'
                """
                params = []
                
                # Apply client filter if provided
                if client_id:
                    query += " AND tc.client_id = %s"
                    params.append(client_id)
                
                cursor.execute(query, params)
                stale_records = cursor.fetchall()
                
                self.logger.info(f"[PID:{pid}] Found {len(stale_records)} database records with 'running' status")
                
                for test_case_id, test_name in stale_records:
                    # Check if Redis key exists
                    redis_key = f"test_case_running:{test_case_id}"
                    if not self._redis.exists(redis_key):
                        # This is a stale record - no Redis key but database shows 'running'
                        self.logger.info(f"[PID:{pid}] Found stale record for test case {test_case_id} ({test_name})")
                        
                        # Update database to mark as stopped
                        try:
                            cursor.execute("""
                                UPDATE test_runs 
                                SET result = 'stopped', duration = EXTRACT(EPOCH FROM (NOW() - run_date))::real
                                WHERE test_case_id = %s AND result = 'running'
                            """, (test_case_id,))
                            
                            updated_rows = cursor.rowcount
                            if updated_rows > 0:
                                stopped_count += updated_rows
                                self.logger.info(f"[PID:{pid}] Cleaned up {updated_rows} stale database records for test case {test_case_id}")
                        
                        except Exception as cleanup_error:
                            error_count += 1
                            self.logger.error(f"[PID:{pid}] Failed to cleanup stale record for test case {test_case_id}: {cleanup_error}")
                
                conn.commit()
                return_db_connection(conn)
                
            except Exception as db_error:
                error_count += 1
                self.logger.error(f"[PID:{pid}] Failed to check for stale database records: {db_error}")
                if 'conn' in locals():
                    return_db_connection(conn)
            
            return {
                "status": "success",
                "message": f"Stopped {stopped_count} test executions",
                "stopped_count": stopped_count,
                "error_count": error_count
            }
            
        except Exception as e:
            self.logger.error(f"[PID:{pid}] Failed to stop all test executions: {e}")
            return {
                "status": "error", 
                "message": f"Failed to stop all test executions: {str(e)}",
                "stopped_count": stopped_count,
                "error_count": error_count
            }

    def _save_step_with_session(self, cursor, conn, test_case_id, step_order, element_purpose, action, element_locator, value, by_strategy, css_selector=""):
        """
        Save a test step using an existing database session connection.
        Returns the step_id of the saved step.
        """
        try:
            cursor.execute(
                """
                INSERT INTO test_steps (test_case_id, step_number, description, action, target, element_path, css_selector, value, "order") 
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) 
                RETURNING id
                """,
                (test_case_id, step_order, element_purpose, action, element_locator, element_locator, css_selector, value, step_order)
            )
            step_id = cursor.fetchone()[0]
            conn.commit()
            return step_id
        except Exception as e:
            conn.rollback()
            self.logger.error(f"Failed to save step with session: {e}")
            raise

    def _update_step_with_screenshot_session(self, cursor, conn, step_id, screenshot_path, encoded_screenshot, description=""):
        """
        Update a test step with screenshot information using existing session connection.
        """
        try:
            # Update step with screenshot path
            cursor.execute("""
                UPDATE test_steps 
                SET screenshot_path = %s
                WHERE id = %s
            """, (screenshot_path, step_id))
            
            # Insert screenshot data
            cursor.execute("""
                INSERT INTO screenshots (test_step_id, screenshot, description)
                VALUES (%s, %s, %s)
            """, (step_id, encoded_screenshot, description))
            
            conn.commit()
        except Exception as e:
            conn.rollback()
            self.logger.error(f"Failed to update step with screenshot using session: {e}")
            raise

    def _update_step_error_session(self, cursor, conn, step_id, error_message):
        """
        Update a test step with error message using existing session connection.
        """
        try:
            cursor.execute("""
                UPDATE test_steps 
                SET error_message = %s
                WHERE id = %s
            """, (error_message, step_id))
            conn.commit()
        except Exception as e:
            conn.rollback()
            self.logger.error(f"Failed to update step error using session: {e}")
            raise

    def _update_generation_end_time_with_session(self, cursor, conn, test_case_id):
        """
        Update the steps_generation_end_time for the test case using existing session connection.
        """
        try:
            end_time = datetime.now()
            cursor.execute("""
                UPDATE test_cases 
                SET steps_generation_end_time = %s
                WHERE id = %s
            """, (end_time, test_case_id))
            conn.commit()
        except Exception as e:
            conn.rollback()
            self.logger.error(f"Failed to update generation end time using session: {e}")
            raise
