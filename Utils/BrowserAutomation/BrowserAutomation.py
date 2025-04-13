from selenium import webdriver
from selenium.webdriver import Keys
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, WebDriverException
import logging
import sys
import os
import tempfile
import datetime

from Utils.BrowserAutomation.EnvHelper import EnvHelper


class BrowserAutomation:
    def __init__(self, headless=False, timeout=10):
        self.timeout = timeout
        self.driver = None
        self.logger = self._setup_logger()
        self.pid = os.getpid()  # Initialize pid before setup_driver
        self.setup_driver(headless)
        self.env = EnvHelper()

    def _setup_logger(self):
        logger = logging.getLogger('BrowserAutomation')
        logger.setLevel(logging.INFO)

        # Remove existing handlers to prevent duplicate logging
        logger.handlers = []

        handler = logging.StreamHandler(sys.stdout)
        handler.setLevel(logging.INFO)
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(filename)s:%(lineno)d  - %(message)s')
        handler.setFormatter(formatter)
        logger.addHandler(handler)

        return logger

    def setup_driver(self, headless=False):
        try:
            chrome_options = Options()
            if headless:
                chrome_options.add_argument('--headless=new')  # Using new headless mode

            # Add common Chrome options
            chrome_options.add_argument('--no-sandbox')
            chrome_options.add_argument('--disable-dev-shm-usage')
            chrome_options.add_argument('--disable-gpu')
            chrome_options.add_argument('--window-size=1920,1080')
            chrome_options.add_argument('--remote-debugging-port=9222')  # Enable debugging
            chrome_options.add_argument('--enable-logging')  # Enable Chrome logging
            chrome_options.add_argument('--v=1')  # Verbose logging

            self.driver = webdriver.Chrome(options=chrome_options)
            self.driver.implicitly_wait(5)
            # Don't log here as TestRunner will handle it

        except Exception as e:
            self.logger.error(f"[PID:{self.pid}] Failed to setup browser: {str(e)}")
            if hasattr(e, 'msg'):
                self.logger.error(f"[PID:{self.pid}] Error message: {e.msg}")
            raise

    def navigate(self, url):
        try:
            self.driver.get(url)
            self.logger.info(f"[PID:{self.pid}] Navigated to {url}")
        except WebDriverException as e:
            self.logger.error(f"[PID:{self.pid}] Failed to navigate to {url}: {str(e)}")
            raise

    def find_element(self, selector, by='xpath'):
        """
        Find an element using either CSS selector or XPath.

        Args:
            selector (str): Element selector
            by (str): Selector type - 'xpath' or 'css' (default: 'xpath')
        """
        try:
            # Handle None or empty by parameter
            if not by:
                by = 'xpath'  # Default to xpath if by is None or empty
            
            # Set the appropriate By strategy based on by parameter
            by_strategy = By.XPATH if by.lower() == 'xpath' else By.CSS_SELECTOR

            element = WebDriverWait(self.driver, self.timeout).until(
                EC.presence_of_element_located((by_strategy, selector))
            )
            return element

        except TimeoutException:
            self.logger.error(f"[PID:{self.pid}] Element not found: {selector}")
            raise
        except Exception as e:
            self.logger.error(f"[PID:{self.pid}] Error finding element {selector}: {str(e)}")
            raise

    def click(self, selector, by='xpath'):
        """
        Click an element using either CSS selector or XPath.

        Args:
            selector (str): Element selector
            by (str): Selector type - 'xpath' or 'css' (default: 'xpath')
        """
        try:
            by_strategy = By.XPATH if by.lower() == 'xpath' else By.CSS_SELECTOR
            element = self.find_element(selector, by_strategy)
            element.click()
            self.logger.info(f"[PID:{self.pid}] Clicked element: {selector}")
        except Exception as e:
            self.logger.error(f"[PID:{self.pid}] Failed to click element {selector}: {str(e)}")
            raise

    def type_text(self, selector, text, by='xpath'):
        try:
            by_strategy = By.XPATH if by.lower() == 'xpath' else By.CSS_SELECTOR
            element = self.find_element(selector, by_strategy)
            element.clear()
            element.send_keys(text)
            self.logger.info(f"[PID:{self.pid}] Typed text: {text} into element: {selector}")
        except Exception as e:
            self.logger.error(f"[PID:{self.pid}] Failed to type text into element {selector}: {str(e)}")
            raise

    def press_key(self, selector, value, by='xpath'):
        # Define mapping of keys to Selenium Keys constants
        KEY_MAPPING = {
            'enter': Keys.ENTER,
            'tab': Keys.TAB,
            'escape': Keys.ESCAPE,
            'backspace': Keys.BACKSPACE,
            'delete': Keys.DELETE,
            'space': Keys.SPACE,
            'page_up': Keys.PAGE_UP,
            'page_down': Keys.PAGE_DOWN,
            'up': Keys.UP,
            'down': Keys.DOWN,
            'left': Keys.LEFT,
            'right': Keys.RIGHT,
        }

        try:
            # Convert key to lowercase and get corresponding Selenium Key
            key = value.lower()
            if key not in KEY_MAPPING:
                raise ValueError(f"Invalid key: {key}. Supported keys: {', '.join(KEY_MAPPING.keys())}")

            selenium_key = KEY_MAPPING[key]

            # Set the appropriate By strategy based on by parameter
            by_strategy = By.XPATH if by.lower() == 'xpath' else By.CSS_SELECTOR

            # Find and interact with the element
            element = self.find_element(selector, by_strategy)
            element.send_keys(selenium_key)
            self.logger.info(f"[PID:{self.pid}] Pressed {key.upper()} key on element: {selector}")

        except Exception as e:
            self.logger.error(f"[PID:{self.pid}] Failed to press {key.upper()} key on element {selector}: {str(e)}")
            raise

    def get_text(self, selector, by='xpath'):
        try:
            by_strategy = By.XPATH if by.lower() == 'xpath' else By.CSS_SELECTOR
            element = self.find_element(selector, by_strategy)
            return element.text
        except Exception as e:
            self.logger.error(f"[PID:{self.pid}] Failed to get text from element {selector}: {str(e)}")
            raise

    def hover(self, selector, by='xpath'):
        """
        Hover over an element using either CSS selector or XPath.

        Args:
            selector (str): Element selector
            by (str): Selector type - 'xpath' or 'css' (default: 'xpath')
        """
        try:
            by_strategy = By.XPATH if by.lower() == 'xpath' else By.CSS_SELECTOR
            element = self.find_element(selector, by_strategy)
            
            # Import ActionChains for hover
            from selenium.webdriver.common.action_chains import ActionChains
            
            # Create ActionChains instance and perform hover
            actions = ActionChains(self.driver)
            actions.move_to_element(element).perform()
            
            self.logger.info(f"[PID:{self.pid}] Hovered over element: {selector}")
        except Exception as e:
            self.logger.error(f"[PID:{self.pid}] Failed to hover over element {selector}: {str(e)}")
            raise

    def wait_for_element(self, selector, by='xpath', timeout=None):
        timeout = timeout or self.timeout
        try:
            by_strategy = By.XPATH if by.lower() == 'xpath' else By.CSS_SELECTOR
            
            # Log the exact selector and strategy being used for debugging
            self.logger.info(f"[PID:{self.pid}] Waiting for element with selector: '{selector}' using strategy: {by_strategy}")
            
            # First, wait for the page to be loaded completely
            WebDriverWait(self.driver, timeout).until(
                lambda d: d.execute_script('return document.readyState') == 'complete'
            )
            
            # Then wait for the specific element
            element = WebDriverWait(self.driver, timeout).until(
                EC.presence_of_element_located((by_strategy, selector))
            )
            
            self.logger.info(f"[PID:{self.pid}] Element found: '{selector}'")
            return element
            
        except TimeoutException:
            # Take a screenshot to debug the current page state
            screenshot_path = self.take_screenshot()
            self.logger.error(f"[PID:{self.pid}] Timeout waiting for element: '{selector}'. Current page screenshot: {screenshot_path}")
            
            # Gather more information about the page for debugging
            try:
                page_url = self.driver.current_url
                page_title = self.driver.title
                self.logger.error(f"[PID:{self.pid}] Current page URL: {page_url}, Title: {page_title}")
                
                # Try to find all buttons on the page
                all_buttons = self.driver.find_elements(By.TAG_NAME, "button")
                button_texts = [btn.text for btn in all_buttons if btn.text.strip()]
                self.logger.error(f"[PID:{self.pid}] Available buttons on page: {button_texts}")
                
                # Extract and log a portion of the page source to help with debugging
                page_source = self.driver.page_source
                page_source_snippet = page_source[:1000] + "..." if len(page_source) > 1000 else page_source
                self.logger.error(f"[PID:{self.pid}] Page source snippet: {page_source_snippet}")
                
            except Exception as page_ex:
                self.logger.error(f"[PID:{self.pid}] Failed to gather debug info: {str(page_ex)}")
                
            raise
        except Exception as e:
            self.logger.error(f"[PID:{self.pid}] Error finding element {selector}: {str(e)}")
            raise

    def get_page_source(self):
        """
        Retrieve the HTML source code of the current page.

        Returns:
            str: The HTML source code of the page.
        """
        try:
            # Wait for the page to be in a stable state
            WebDriverWait(self.driver, self.timeout).until(
                lambda d: d.execute_script('return document.readyState') == 'complete'
            )
            
            # Get page source
            page_source = self.driver.page_source
            
            if not page_source:
                raise WebDriverException("Empty page source returned")
                
            self.logger.info(f"[PID:{self.pid}] Retrieved page source successfully")
            return page_source
            
        except TimeoutException:
            self.logger.error(f"[PID:{self.pid}] Timeout waiting for page to load")
            raise
        except WebDriverException as e:
            self.logger.error(f"[PID:{self.pid}] WebDriver error getting page source: {str(e)}")
            if hasattr(e, 'msg'):
                self.logger.error(f"[PID:{self.pid}] Error message: {e.msg}")
            raise
        except Exception as e:
            self.logger.error(f"[PID:{self.pid}] Failed to get page source: {str(e)}")
            raise

    def wait_for_page_changes(self, timeout=None):
        """
        Wait for any changes in the page DOM.
        
        Args:
            timeout (int, optional): Maximum time to wait in seconds. Defaults to self.timeout.
        """
        timeout = timeout or self.timeout
        try:
            # Get initial page source
            initial_source = self.driver.page_source
            
            # Wait for page source to change
            WebDriverWait(self.driver, timeout).until(
                lambda d: d.page_source != initial_source
            )
            
            # Wait for the page to be in a stable state
            WebDriverWait(self.driver, timeout).until(
                lambda d: d.execute_script('return document.readyState') == 'complete'
            )
            
            # Wait for any AJAX requests to complete
            WebDriverWait(self.driver, timeout).until(
                lambda d: d.execute_script('return jQuery.active == 0') or True
            )
            
            self.logger.info(f"[PID:{self.pid}] Page changes detected and page is stable")
            return True
            
        except TimeoutException:
            self.logger.warning(f"[PID:{self.pid}] No page changes detected within {timeout} seconds")
            return False
        except Exception as e:
            self.logger.error(f"[PID:{self.pid}] Error waiting for page changes: {str(e)}")
            return False

    def take_screenshot(self, name=None):
        """
        Takes a screenshot of the current browser window.
        
        Args:
            name (str, optional): A descriptive name for the screenshot. If not provided, a generic name will be used.
            
        Returns:
            str: The path to the saved screenshot file
        """
        try:
            # Create a unique filename using timestamp
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            screenshot_name = f"{name or 'screenshot'}_{timestamp}.png"
            
            # Use a dedicated screenshots directory instead of temp
            screenshots_dir = os.path.join(os.getcwd(), 'screenshots')
            
            # Create the directory if it doesn't exist
            if not os.path.exists(screenshots_dir):
                os.makedirs(screenshots_dir)
                
            screenshot_path = os.path.join(screenshots_dir, screenshot_name)
            
            # Take and save the screenshot
            self.driver.save_screenshot(screenshot_path)
            self.logger.info(f"[PID:{self.pid}] Screenshot saved: {screenshot_path}")
            
            return screenshot_path
            
        except WebDriverException as e:
            self.logger.error(f"[PID:{self.pid}] Failed to take screenshot: {str(e)}")
            return None

    def select(self, selector, option_value, by='xpath'):
        """
        Select an option from a dropdown/select element.

        Args:
            selector (str): Element selector for the select element
            option_value (str): Value of the option to select
            by (str): Selector type - 'xpath' or 'css' (default: 'xpath')
        """
        try:
            # Import Select for dropdown handling
            from selenium.webdriver.support.ui import Select as WebDriverSelect
            
            by_strategy = By.XPATH if by.lower() == 'xpath' else By.CSS_SELECTOR
            element = self.find_element(selector, by_strategy)
            
            # Create a Select object and select by value
            select = WebDriverSelect(element)
            select.select_by_value(option_value)
            
            self.logger.info(f"[PID:{self.pid}] Selected option with value '{option_value}' from select element: {selector}")
        except Exception as e:
            self.logger.error(f"[PID:{self.pid}] Failed to select option from element {selector}: {str(e)}")
            raise

    def assert_element(self, element_path: str, expected_value: str = None, by_strategy: str = None):
        """
        Assert various conditions about web elements.

        Args:
            element_path (str): The locator path to find the element
            expected_value (str, optional): The expected value or condition to assert
            by_strategy (str, optional): The strategy to locate the element (e.g., 'id', 'xpath', 'css')

        Raises:
            AssertionError: If the assertion fails
            ValueError: If the assertion type is invalid
        """
        # Handle None or empty by_strategy
        if not by_strategy:
            by_strategy = 'xpath'  # Default to xpath if by_strategy is None or empty
        
        self.logger.info(f"[PID:{self.pid}] Asserting on element with path: '{element_path}' using {by_strategy}")
        
        try:
            element = self.find_element(element_path, by_strategy)

            if not element:
                raise AssertionError(f"[PID:{self.pid}] Element not found: {element_path}")

            # If no expected value is provided, just assert element exists
            if not expected_value:
                self.logger.info(f"[PID:{self.pid}] Element exists assertion passed for: {element_path}")
                return True

            # Parse assertion type and expected value
            if "=" in expected_value:
                assertion_type, value = expected_value.split("=", 1)
            else:
                assertion_type = "text"
                value = expected_value

            assertion_type = assertion_type.strip().lower()
            self.logger.info(f"[PID:{self.pid}] Checking {assertion_type} assertion with expected value: '{value}'")

            # Handle different types of assertions
            if assertion_type == "text":
                # Special case for visibility-related assertions
                visibility_terms = ["is_displayed", "visible", "displayed", "visibility"]
                if value.strip().lower() in visibility_terms:
                    is_visible = element.is_displayed()
                    if not is_visible:
                        raise AssertionError(f"[PID:{self.pid}] Element is not visible")
                    self.logger.info(f"[PID:{self.pid}] Element is visible as expected")
                # Check for placeholder text in input elements
                elif element.tag_name.lower() in ["input", "textarea"] and value.strip():
                    # First check if this might be a placeholder assertion
                    placeholder = element.get_attribute("placeholder")
                    if placeholder and placeholder.strip() == value.strip():
                        self.logger.info(f"[PID:{self.pid}] Placeholder text '{value}' matches as expected")
                        return True
                    
                    # If not a placeholder or placeholder doesn't match, check text content
                    actual_text = element.text.strip()
                    if actual_text != value.strip():
                        # If text doesn't match and we have a placeholder, show that in the error
                        if placeholder:
                            raise AssertionError(f"[PID:{self.pid}] Expected text '{value}' but got '{actual_text}'. Element has placeholder='{placeholder}'")
                        else:
                            raise AssertionError(f"[PID:{self.pid}] Expected text '{value}' but got '{actual_text}'")
                else:
                    actual_text = element.text.strip()
                    if actual_text != value.strip():
                        raise AssertionError(f"[PID:{self.pid}] Expected text '{value}' but got '{actual_text}'")

            elif assertion_type == "value":
                actual_value = element.get_attribute("value")
                if actual_value != value:
                    raise AssertionError(f"[PID:{self.pid}] Expected value '{value}' but got '{actual_value}'")

            elif assertion_type == "visible":
                is_visible = element.is_displayed()
                expected_visible = value.lower() == "true"
                if is_visible != expected_visible:
                    raise AssertionError(f"[PID:{self.pid}] Expected visibility {expected_visible} but got {is_visible}")

            elif assertion_type == "enabled":
                is_enabled = element.is_enabled()
                expected_enabled = value.lower() == "true"
                if is_enabled != expected_enabled:
                    raise AssertionError(f"[PID:{self.pid}] Expected enabled {expected_enabled} but got {is_enabled}")

            elif assertion_type == "selected":
                is_selected = element.is_selected()
                expected_selected = value.lower() == "true"
                if is_selected != expected_selected:
                    raise AssertionError(f"[PID:{self.pid}] Expected selected {expected_selected} but got {is_selected}")

            elif assertion_type == "type":
                # Handle type attribute assertions specifically for input fields
                actual_type = element.get_attribute("type")
                expected_type = value.strip()
                self.logger.info(f"[PID:{self.pid}] Checking input type: expected '{expected_type}', actual '{actual_type}'")
                
                if actual_type != expected_type:
                    raise AssertionError(f"[PID:{self.pid}] Expected input type '{expected_type}' but got '{actual_type}'")
                self.logger.info(f"[PID:{self.pid}] Input type assertion passed: type='{actual_type}'")

            elif assertion_type == "attribute":
                # Handle attribute assertions
                if "," in value:
                    attr_name, expected_attr_value = value.split(",", 1)
                    attr_name = attr_name.strip()
                    expected_attr_value = expected_attr_value.strip()
                    if expected_attr_value.startswith("expected_value="):
                        expected_attr_value = expected_attr_value.replace("expected_value=", "").strip()
                else:
                    # If no expected value is provided, just check if attribute exists
                    attr_name = value.strip()
                    expected_attr_value = None
                
                self.logger.info(f"[PID:{self.pid}] Checking attribute '{attr_name}' with expected value: '{expected_attr_value}'")
                actual_attr_value = element.get_attribute(attr_name)
                
                if expected_attr_value is not None and actual_attr_value != expected_attr_value:
                    raise AssertionError(f"[PID:{self.pid}] Expected attribute '{attr_name}' to be '{expected_attr_value}' but got '{actual_attr_value}'")
                elif expected_attr_value is None and actual_attr_value is None:
                    raise AssertionError(f"[PID:{self.pid}] Attribute '{attr_name}' does not exist on element")

            else:
                raise ValueError(f"[PID:{self.pid}] Unsupported assertion type: {assertion_type}")

            self.logger.info(f"[PID:{self.pid}] Assertion passed for element: {element_path}")
            return True
        
        except TimeoutException as e:
            # Take a screenshot for debugging
            screenshot_path = self.take_screenshot()
            
            # Log additional debugging information
            try:
                page_url = self.driver.current_url
                page_title = self.driver.title
                
                # Try to find all buttons on the page to help with debugging
                all_buttons = self.driver.find_elements(By.TAG_NAME, "button")
                button_texts = [btn.text for btn in all_buttons if btn.text.strip()]
                
                error_msg = f"[PID:{self.pid}] Element not found: {element_path}\n"
                error_msg += f"Current URL: {page_url}\n"
                error_msg += f"Page title: {page_title}\n"
                error_msg += f"Available buttons: {button_texts}\n"
                error_msg += f"Screenshot saved at: {screenshot_path}"
                
                self.logger.error(error_msg)
            except Exception as debug_ex:
                self.logger.error(f"[PID:{self.pid}] Error gathering debug info: {str(debug_ex)}")
            
            raise

    def close(self):
        """Close the browser and cleanup"""
        if self.driver:
            try:
                self.driver.quit()
                # Don't log here as TestRunner will handle it
            except Exception as e:
                self.logger.error(f"[PID:{self.pid}] Error closing browser: {str(e)}")
            finally:
                self.driver = None
