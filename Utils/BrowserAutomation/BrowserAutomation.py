from selenium import webdriver
from selenium.webdriver import Keys
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, WebDriverException
from selenium.webdriver.common.desired_capabilities import DesiredCapabilities
import logging
import sys
import os
import tempfile
import datetime
import time
import re

from Utils.BrowserAutomation.EnvHelper import EnvHelper
from Utils.System import System


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
            chrome_options.add_argument('--enable-logging')  # Enable Chrome logging
            chrome_options.add_argument('--v=1')  # Verbose logging

            # Get system configuration for Selenium Grid URL
            system = System()
            # Default to localhost:4444 if not specified in System
            grid_url = getattr(system, 'selenium_grid_url', 'http://localhost:4444/wd/hub')
            
            # Log the Selenium Grid connection attempt
            self.logger.info(f"[PID:{self.pid}] Connecting to Selenium Grid at {grid_url}")
            
            # Create a remote WebDriver connection to Selenium Grid
            # In Selenium 4+, capabilities are specified through options object
            self.driver = webdriver.Remote(
                command_executor=grid_url,
                options=chrome_options
            )
            
            self.driver.implicitly_wait(5)
            self.logger.info(f"[PID:{self.pid}] Successfully connected to Selenium Grid")

        except Exception as e:
            self.logger.error(f"[PID:{self.pid}] Failed to connect to Selenium Grid: {str(e)}")
            if hasattr(e, 'msg'):
                self.logger.error(f"[PID:{self.pid}] Error message: {e.msg}")
            raise

    def navigate(self, url):
        try:
            self.driver.get(url)
            self.logger.info(f"[PID:{self.pid}] Navigated to {url}")
        except WebDriverException as e:
            # Check if this is a session timeout/invalid session error
            if "Unable to find session" in str(e) or "InvalidSessionIdException" in str(e) or "NoSuchSessionException" in str(e):
                self.logger.warning(f"[PID:{self.pid}] Session expired/invalid. Creating new session...")
                try:
                    # Close the old driver if it exists
                    if self.driver:
                        try:
                            self.driver.quit()
                        except:
                            pass
                    
                    # Recreate the driver connection
                    self.setup_driver(headless=False)
                    # Retry the navigation with new session
                    self.driver.get(url)
                    self.logger.info(f"[PID:{self.pid}] Successfully navigated to {url} with new session")
                    return
                except Exception as retry_e:
                    self.logger.error(f"[PID:{self.pid}] Failed to recover session and navigate: {str(retry_e)}")
                    raise retry_e
            
            self.logger.error(f"[PID:{self.pid}] Failed to navigate to {url}: {str(e)}")
            raise

    def wait_for_page_load(self, timeout=None):
        """
        Wait for the page to fully load by checking document.readyState.
        
        Args:
            timeout (int, optional): Timeout in seconds. If None, uses the default timeout.
        """
        if timeout is None:
            timeout = self.timeout
            
        try:
            WebDriverWait(self.driver, timeout).until(
                lambda d: d.execute_script('return document.readyState') == 'complete'
            )
            self.logger.info(f"[PID:{self.pid}] Page loaded successfully")
        except TimeoutException:
            self.logger.warning(f"[PID:{self.pid}] Timed out waiting for page to load completely")
        except Exception as e:
            self.logger.error(f"[PID:{self.pid}] Error waiting for page load: {str(e)}")

    def find_element(self, selector, by='xpath', action=None):
        """
        Find element using either CSS selector or XPath with fallback strategies.
        Action-aware strategy for better performance.
        """
        try:
            # Handle None or empty by parameter
            if not by:
                by = 'xpath'  # Default to xpath if by is None or empty
            
            # Set the appropriate By strategy based by parameter
            by_strategy = By.XPATH if by.lower() == 'xpath' else By.CSS_SELECTOR

            # First try to find the element with presence_of_element_located
            try:
                element = WebDriverWait(self.driver, self.timeout).until(
                    EC.presence_of_element_located((by_strategy, selector))
                )
                return element
            except TimeoutException:
                # If element not found, try to check if we need to switch to an iframe
                iframes = self.driver.find_elements(By.TAG_NAME, "iframe")
                if iframes:
                    self.logger.info(f"[PID:{self.pid}] Element not found in main frame. Checking {len(iframes)} iframes...")
                    
                    # Store the current context to switch back later
                    current_context = self.driver
                    
                    # Try each iframe
                    for i, iframe in enumerate(iframes):
                        try:
                            self.driver.switch_to.frame(iframe)
                            self.logger.info(f"[PID:{self.pid}] Switched to iframe {i+1}")
                            
                            # Try to find the element in this iframe
                            element = WebDriverWait(self.driver, 2).until(
                                EC.presence_of_element_located((by_strategy, selector))
                            )
                            self.logger.info(f"[PID:{self.pid}] Found element in iframe {i+1}")
                            return element
                        except:
                            # Element not in this iframe, switch back to main content and try next
                            self.driver.switch_to.default_content()
                    
                    # If we've checked all iframes and still haven't found it, switch back to original context
                    self.driver.switch_to.default_content()
                    
                    # Try one more time with a different wait condition
                    try:
                        self.logger.info(f"[PID:{self.pid}] Trying with element_to_be_clickable...")
                        element = WebDriverWait(self.driver, self.timeout).until(
                            EC.element_to_be_clickable((by_strategy, selector))
                        )
                        return element
                    except:
                        # Last resort: try with JavaScript
                        self.logger.info(f"[PID:{self.pid}] Trying with JavaScript...")
                        if by.lower() == 'xpath':
                            # For XPath, we need to use document.evaluate
                            js_script = """
                            var result = document.evaluate(arguments[0], document, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null);
                            return result.singleNodeValue;
                            """
                        else:
                            # For CSS, we can use querySelector
                            js_script = "return document.querySelector(arguments[0]);"
                        
                        element = self.driver.execute_script(js_script, selector)
                        if element:
                            self.logger.info(f"[PID:{self.pid}] Found element using JavaScript")
                            return element
                        else:
                            self.logger.error(f"[PID:{self.pid}] Element not found: {selector}")
                            raise TimeoutException(f"Element not found: {selector}")
                else:
                    # Choose appropriate wait condition based on action
                    if action == 'click':
                        try:
                            self.logger.info(f"[PID:{self.pid}] Trying with element_to_be_clickable for click action...")
                            element = WebDriverWait(self.driver, self.timeout).until(
                                EC.element_to_be_clickable((by_strategy, selector))
                            )
                            return element
                        except TimeoutException:
                            self.logger.warning(f"[PID:{self.pid}] Element not clickable, trying JavaScript fallback...")
                    else:
                        # For type, wait, etc. - just need element to be present and visible
                        try:
                            self.logger.info(f"[PID:{self.pid}] Trying with visibility_of_element_located for {action or 'unknown'} action...")
                            element = WebDriverWait(self.driver, self.timeout).until(
                                EC.visibility_of_element_located((by_strategy, selector))
                            )
                            return element
                        except TimeoutException:
                            self.logger.warning(f"[PID:{self.pid}] Element not visible, trying JavaScript fallback...")
                    
                    # Last resort: try with JavaScript
                    self.logger.info(f"[PID:{self.pid}] Trying with JavaScript...")
                    if by.lower() == 'xpath':
                        # For XPath, we need to use document.evaluate
                        js_script = """
                        var result = document.evaluate(arguments[0], document, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null);
                        return result.singleNodeValue;
                        """
                    else:
                        # For CSS, we can use querySelector
                        js_script = "return document.querySelector(arguments[0]);"
                    
                    element = self.driver.execute_script(js_script, selector)
                    if element:
                        self.logger.info(f"[PID:{self.pid}] Found element using JavaScript")
                        return element
                    else:
                        # Take a screenshot for debugging
                        try:
                            screenshot_path = f"/tmp/element_not_found_{self.pid}_{int(time.time())}.png"
                            self.driver.save_screenshot(screenshot_path)
                            self.logger.error(f"[PID:{self.pid}] Element not found: {selector}. Screenshot saved: {screenshot_path}")
                        except:
                            self.logger.error(f"[PID:{self.pid}] Element not found: {selector}")
                        raise TimeoutException(f"Element not found: {selector}")

        except TimeoutException:
            self.logger.error(f"[PID:{self.pid}] Element not found: {selector}")
            raise
        except Exception as e:
            self.logger.error(f"[PID:{self.pid}] Error finding element {selector}: {str(e)}")
            raise

    def click(self, selector, by='xpath'):
        """
        Click an element using either CSS selector or XPath.
        Automatically waits for the element to be clickable before attempting to click.
        Includes retry logic for stale elements.

        Args:
            selector (str): The CSS selector or XPath to find the element.
            by (str): Either 'css' or 'xpath' to specify the selector type.
        """
        from selenium.common.exceptions import StaleElementReferenceException
        
        max_retries = 3
        for attempt in range(max_retries):
            try:
                # First, try to wait for the element to be clickable (especially important for modals)
                by_strategy = By.XPATH if by.lower() == 'xpath' else By.CSS_SELECTOR
                try:
                    self.logger.info(f"[PID:{self.pid}] Waiting for element to be clickable before clicking: {selector}")
                    element = WebDriverWait(self.driver, self.timeout).until(
                        EC.element_to_be_clickable((by_strategy, selector))
                    )
                    self.logger.info(f"[PID:{self.pid}] Element is clickable, proceeding with click")
                except TimeoutException:
                    self.logger.warning(f"[PID:{self.pid}] Element not clickable within timeout, falling back to find_element")
                    element = self.find_element(selector, by, action='click')
                
                # Validate element was found
                if element is None:
                    raise TimeoutException(f"Element not found: {selector}")
                
                # Try standard click first
                try:
                    element.click()
                    self.logger.info(f"[PID:{self.pid}] Clicked element: {selector}")
                    return
                except StaleElementReferenceException:
                    raise  # Re-raise to trigger retry
                except Exception as e:
                    self.logger.warning(f"[PID:{self.pid}] Standard click failed, trying alternative methods: {str(e)}")
                
                # If standard click fails, try JavaScript click with null check
                try:
                    self.logger.info(f"[PID:{self.pid}] Trying JavaScript click with null check...")
                    # Re-find element to avoid stale reference
                    element = self.driver.find_element(by_strategy, selector)
                    # Use safer JavaScript that checks for null
                    self.driver.execute_script("""
                        var element = arguments[0];
                        if (element !== null && element !== undefined) {
                            element.click();
                        } else {
                            throw new Error('Element is null or undefined');
                        }
                    """, element)
                    self.logger.info(f"[PID:{self.pid}] Clicked element with JavaScript: {selector}")
                    return
                except StaleElementReferenceException:
                    raise  # Re-raise to trigger retry
                except Exception as js_error:
                    self.logger.warning(f"[PID:{self.pid}] JavaScript click failed: {str(js_error)}")
                
                # If JavaScript click fails, try Actions
                try:
                    self.logger.info(f"[PID:{self.pid}] Trying Actions click...")
                    from selenium.webdriver.common.action_chains import ActionChains
                    # Re-find element to avoid stale reference
                    element = self.driver.find_element(by_strategy, selector)
                    actions = ActionChains(self.driver)
                    actions.move_to_element(element).click().perform()
                    self.logger.info(f"[PID:{self.pid}] Clicked element with Actions: {selector}")
                    return
                except StaleElementReferenceException:
                    raise  # Re-raise to trigger retry
                except Exception as actions_error:
                    self.logger.warning(f"[PID:{self.pid}] Actions click failed: {str(actions_error)}")
                
                # If all methods fail, try to scroll to the element and then click with null check
                try:
                    self.logger.info(f"[PID:{self.pid}] Trying scroll and click with null check...")
                    # Re-find element to avoid stale reference
                    element = self.driver.find_element(by_strategy, selector)
                    # Use safer JavaScript that checks for null before scrollIntoView
                    self.driver.execute_script("""
                        var element = arguments[0];
                        if (element !== null && element !== undefined) {
                            element.scrollIntoView({behavior: 'smooth', block: 'center'});
                        } else {
                            throw new Error('Element is null or undefined');
                        }
                    """, element)
                    time.sleep(0.5)  # Give time for the page to settle after scrolling
                    element.click()
                    self.logger.info(f"[PID:{self.pid}] Clicked element after scrolling: {selector}")
                    return
                except StaleElementReferenceException:
                    raise  # Re-raise to trigger retry
                except Exception as scroll_error:
                    self.logger.error(f"[PID:{self.pid}] All click methods failed: {str(scroll_error)}")
                    raise
                    
            except StaleElementReferenceException:
                if attempt < max_retries - 1:
                    self.logger.warning(f"[PID:{self.pid}] Element became stale, retrying... (attempt {attempt + 1}/{max_retries})")
                    time.sleep(0.5)  # Brief pause before retry
                    continue
                else:
                    self.logger.error(f"[PID:{self.pid}] Element remained stale after {max_retries} attempts")
                    raise
                
    def type_text(self, selector, text, by='xpath'):
        try:
            element = self.find_element(selector, by, action='type')
            element.clear()
            element.send_keys(text)
            self.logger.info(f"[PID:{self.pid}] Typed text: {text} into element: {selector}")
        except Exception as e:
            self.logger.error(f"[PID:{self.pid}] Failed to type text into element {selector}: {str(e)}")
            raise

    def press_key(self, selector, value, by='xpath'):
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
            'arrow_up': Keys.UP,
            'arrow_down': Keys.DOWN,
            'arrow_left': Keys.LEFT,
            'arrow_right': Keys.RIGHT,
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
            element = self.find_element(selector, by)
            element.send_keys(selenium_key)
            self.logger.info(f"[PID:{self.pid}] Pressed {key.upper()} key on element: {selector}")

        except Exception as e:
            self.logger.error(f"[PID:{self.pid}] Failed to press {key.upper()} key on element {selector}: {str(e)}")
            raise

    def get_text(self, selector, by='xpath'):
        try:
            element = self.find_element(selector, by)
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

    def wait_for_clickable(self, selector, by='xpath', timeout=None):
        """
        Wait for an element to be clickable (visible and enabled).
        This is especially useful for modal dialogs and dynamic elements.
        
        Args:
            selector (str): The CSS selector or XPath to find the element.
            by (str): Either 'css' or 'xpath' to specify the selector type.
            timeout (int): Maximum time to wait in seconds (uses default if not specified).
            
        Returns:
            WebElement: The clickable element
        """
        timeout = timeout or self.timeout
        try:
            by_strategy = By.XPATH if by.lower() == 'xpath' else By.CSS_SELECTOR
            
            self.logger.info(f"[PID:{self.pid}] Waiting for element to be clickable: '{selector}' using strategy: {by_strategy}")
            
            # Wait for element to be clickable (visible and enabled)
            element = WebDriverWait(self.driver, timeout).until(
                EC.element_to_be_clickable((by_strategy, selector))
            )
            
            self.logger.info(f"[PID:{self.pid}] Element is now clickable: '{selector}'")
            return element
            
        except TimeoutException:
            # Take a screenshot to debug the current page state
            screenshot_path = self.take_screenshot()
            self.logger.error(f"[PID:{self.pid}] Timeout waiting for element to be clickable: '{selector}'. Screenshot: {screenshot_path}")
            
            # Gather debug information
            try:
                page_url = self.driver.current_url
                page_title = self.driver.title
                self.logger.error(f"[PID:{self.pid}] Current page: {page_url} (Title: {page_title})")
                
                # Check if element exists but is not clickable
                try:
                    element = self.driver.find_element(by_strategy, selector)
                    self.logger.error(f"[PID:{self.pid}] Element exists but is not clickable. Displayed: {element.is_displayed()}, Enabled: {element.is_enabled()}")
                except:
                    self.logger.error(f"[PID:{self.pid}] Element does not exist in DOM")
                
            except Exception as debug_ex:
                self.logger.error(f"[PID:{self.pid}] Failed to gather debug info: {str(debug_ex)}")
                
            raise
        except Exception as e:
            self.logger.error(f"[PID:{self.pid}] Error waiting for clickable element {selector}: {str(e)}")
            raise

    def wait_for_modal(self, modal_selector='//div[contains(@class, "modal")]', timeout=None):
        """
        Wait for a modal dialog to appear and become visible.
        
        Args:
            modal_selector (str): XPath or CSS selector for the modal container
            timeout (int): Maximum time to wait in seconds (uses default if not specified)
            
        Returns:
            WebElement: The modal element
        """
        timeout = timeout or self.timeout
        try:
            self.logger.info(f"[PID:{self.pid}] Waiting for modal to appear: {modal_selector}")
            
            # Wait for modal to be present in DOM
            by_strategy = By.XPATH if '//' in modal_selector else By.CSS_SELECTOR
            modal = WebDriverWait(self.driver, timeout).until(
                EC.presence_of_element_located((by_strategy, modal_selector))
            )
            
            # Wait for modal to be visible
            WebDriverWait(self.driver, timeout).until(
                EC.visibility_of(modal)
            )
            
            # Give modal animation time to complete
            time.sleep(0.3)
            
            self.logger.info(f"[PID:{self.pid}] Modal is visible and ready")
            return modal
            
        except TimeoutException:
            self.logger.error(f"[PID:{self.pid}] Modal did not appear within {timeout} seconds: {modal_selector}")
            
            # Take screenshot for debugging
            try:
                screenshot_path = f"/tmp/modal_not_found_{self.pid}_{int(time.time())}.png"
                self.driver.save_screenshot(screenshot_path)
                self.logger.error(f"[PID:{self.pid}] Screenshot saved: {screenshot_path}")
            except:
                pass
                
            raise
        except Exception as e:
            self.logger.error(f"[PID:{self.pid}] Error waiting for modal: {str(e)}")
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

            elif assertion_type == "current_url_contains":
                current_url = self.driver.current_url
                if value not in current_url:
                    raise AssertionError(f"[PID:{self.pid}] Expected URL to contain '{value}' but got '{current_url}'")
                self.logger.info(f"[PID:{self.pid}] URL contains '{value}' as expected: '{current_url}'")

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

    def debug_page_structure(self, selector=None, by='xpath'):
        """
        Logs detailed information about the page structure to help debug element locator issues.
        
        Args:
            selector (str, optional): Specific element selector to debug
            by (str): Selector type - 'xpath' or 'css' (default: 'xpath')
        """
        self.logger.info(f"[PID:{self.pid}] === DEBUG PAGE STRUCTURE ===")
        self.logger.info(f"[PID:{self.pid}] Current URL: {self.driver.current_url}")
        self.logger.info(f"[PID:{self.pid}] Page Title: {self.driver.title}")
        
        # Log all buttons and links on the page
        self.logger.info(f"[PID:{self.pid}] === BUTTONS AND LINKS ===")
        buttons = self.driver.find_elements(By.TAG_NAME, "button")
        links = self.driver.find_elements(By.TAG_NAME, "a")
        
        for i, button in enumerate(buttons):
            try:
                text = button.text.strip() if button.text else "[No text]"
                id_attr = button.get_attribute("id") or "[No ID]"
                class_attr = button.get_attribute("class") or "[No class]"
                data_test = button.get_attribute("data-test-id") or button.get_attribute("lucy-test-id") or "[No test ID]"
                is_visible = button.is_displayed()
                is_enabled = button.is_enabled()
                
                self.logger.info(f"[PID:{self.pid}] Button {i+1}: Text='{text}', ID='{id_attr}', Class='{class_attr}', TestID='{data_test}', Visible={is_visible}, Enabled={is_enabled}")
            except:
                self.logger.info(f"[PID:{self.pid}] Button {i+1}: [Error getting attributes]")
        
        for i, link in enumerate(links):
            try:
                text = link.text.strip() if link.text else "[No text]"
                href = link.get_attribute("href") or "[No href]"
                id_attr = link.get_attribute("id") or "[No ID]"
                class_attr = link.get_attribute("class") or "[No class]"
                data_test = link.get_attribute("data-test-id") or link.get_attribute("lucy-test-id") or "[No test ID]"
                is_visible = link.is_displayed()
                
                self.logger.info(f"[PID:{self.pid}] Link {i+1}: Text='{text}', Href='{href}', ID='{id_attr}', Class='{class_attr}', TestID='{data_test}', Visible={is_visible}")
            except:
                self.logger.info(f"[PID:{self.pid}] Link {i+1}: [Error getting attributes]")
        
        # If a specific selector was provided, try to find it and log details
        if selector:
            self.logger.info(f"[PID:{self.pid}] === DEBUGGING SPECIFIC SELECTOR: {selector} ===")
            by_strategy = By.XPATH if by.lower() == 'xpath' else By.CSS_SELECTOR
            
            # Try to find all matching elements
            try:
                elements = self.driver.find_elements(by_strategy, selector)
                self.logger.info(f"[PID:{self.pid}] Found {len(elements)} matching elements")
                
                for i, element in enumerate(elements):
                    try:
                        tag_name = element.tag_name
                        text = element.text.strip() if element.text else "[No text]"
                        is_visible = element.is_displayed()
                        is_enabled = element.is_enabled()
                        
                        self.logger.info(f"[PID:{self.pid}] Match {i+1}: Tag='{tag_name}', Text='{text}', Visible={is_visible}, Enabled={is_enabled}")
                        
                        # Log all attributes
                        attributes = self.driver.execute_script(
                            'var items = {}; for (index = 0; index < arguments[0].attributes.length; ++index) { items[arguments[0].attributes[index].name] = arguments[0].attributes[index].value }; return items;',
                            element
                        )
                        self.logger.info(f"[PID:{self.pid}] Attributes: {attributes}")
                        
                        # Check if element is covered by another element
                        is_covered = self.driver.execute_script("""
                            var elem = arguments[0];
                            var rect = elem.getBoundingClientRect();
                            var cx = rect.left + rect.width / 2;
                            var cy = rect.top + rect.height / 2;
                            var el = document.elementFromPoint(cx, cy);
                            return el !== elem && !elem.contains(el);
                        """, element)
                        
                        if is_covered:
                            self.logger.info(f"[PID:{self.pid}] Element is covered by another element")
                            
                            # Try to identify the covering element
                            covering_element = self.driver.execute_script("""
                                var elem = arguments[0];
                                var rect = elem.getBoundingClientRect();
                                var cx = rect.left + rect.width / 2;
                                var cy = rect.top + rect.height / 2;
                                return document.elementFromPoint(cx, cy);
                            """, element)
                            
                            if covering_element:
                                covering_tag = covering_element.tag_name
                                covering_text = covering_element.text.strip() if covering_element.text else "[No text]"
                                self.logger.info(f"[PID:{self.pid}] Covered by: Tag='{covering_tag}', Text='{covering_text}'")
                        
                    except Exception as e:
                        self.logger.info(f"[PID:{self.pid}] Error getting element details: {str(e)}")
            except Exception as e:
                self.logger.info(f"[PID:{self.pid}] Error finding elements with selector {selector}: {str(e)}")
        
        # Check for iframes
        iframes = self.driver.find_elements(By.TAG_NAME, "iframe")
        if iframes:
            self.logger.info(f"[PID:{self.pid}] === IFRAMES ({len(iframes)}) ===")
            
            for i, iframe in enumerate(iframes):
                try:
                    iframe_id = iframe.get_attribute("id") or "[No ID]"
                    iframe_name = iframe.get_attribute("name") or "[No name]"
                    iframe_src = iframe.get_attribute("src") or "[No src]"
                    
                    self.logger.info(f"[PID:{self.pid}] Iframe {i+1}: ID='{iframe_id}', Name='{iframe_name}', Src='{iframe_src}'")
                    
                    # Try to switch to this iframe and look for the element
                    if selector:
                        try:
                            self.driver.switch_to.frame(iframe)
                            iframe_elements = self.driver.find_elements(by_strategy, selector)
                            self.logger.info(f"[PID:{self.pid}] Found {len(iframe_elements)} matching elements in iframe {i+1}")
                            self.driver.switch_to.default_content()
                        except:
                            self.logger.info(f"[PID:{self.pid}] Error searching in iframe {i+1}")
                            self.driver.switch_to.default_content()
                except:
                    self.logger.info(f"[PID:{self.pid}] Iframe {i+1}: [Error getting attributes]")
        
        self.logger.info(f"[PID:{self.pid}] === END DEBUG PAGE STRUCTURE ===")

    def clear(self, selector, by='xpath'):
        """
        Clear the content of an input field.
        
        Args:
            selector (str): The selector to find the element
            by (str): The selector strategy ('xpath' or 'css')
        """
        try:
            by_strategy = By.XPATH if by.lower() == 'xpath' else By.CSS_SELECTOR
            element = self.find_element(selector, by_strategy)
            element.clear()
            self.logger.info(f"[PID:{self.pid}] Cleared content from element: {selector}")
        except Exception as e:
            self.logger.error(f"[PID:{self.pid}] Failed to clear element {selector}: {str(e)}")
            raise

    def assert_text_contains(self, element_path: str, expected_text: str, by_strategy: str = None):
        """
        Assert that an element's text contains the expected text.
        
        Args:
            element_path (str): The locator path to find the element
            expected_text (str): The text that should be contained within the element's text
            by_strategy (str, optional): The strategy to locate the element (e.g., 'xpath', 'css')
            
        Raises:
            AssertionError: If the element's text does not contain the expected text
            ValueError: If expected_text is not provided
        """
        # Handle None or empty by_strategy
        if not by_strategy:
            by_strategy = 'xpath'  # Default to xpath if by_strategy is None or empty
        
        if not expected_text:
            raise ValueError(f"[PID:{self.pid}] Expected text cannot be empty for text contains assertion")
        
        self.logger.info(f"[PID:{self.pid}] Asserting that element '{element_path}' contains text: '{expected_text}' using {by_strategy}")
        
        try:
            element = self.find_element(element_path, by_strategy)
            
            if not element:
                raise AssertionError(f"[PID:{self.pid}] Element not found: {element_path}")
            
            # Get the actual text from the element
            actual_text = element.text.strip()
            expected_text = expected_text.strip()
            
            self.logger.info(f"[PID:{self.pid}] Element actual text: '{actual_text}'")
            
            # Check if the expected text is contained in the actual text (case-sensitive)
            if expected_text not in actual_text:
                raise AssertionError(
                    f"[PID:{self.pid}] Text '{expected_text}' not found in element text. "
                    f"Element text: '{actual_text}'"
                )
            
            self.logger.info(f"[PID:{self.pid}] Text contains assertion passed: '{expected_text}' found in '{actual_text}'")
            return True
            
        except TimeoutException:
            # Take a screenshot for debugging
            screenshot_path = self.take_screenshot()
            
            # Log additional debugging information
            try:
                page_url = self.driver.current_url
                page_title = self.driver.title
                
                error_msg = f"[PID:{self.pid}] Element not found for text contains assertion: {element_path}\n"
                error_msg += f"Current URL: {page_url}\n"
                error_msg += f"Page title: {page_title}\n"
                error_msg += f"Screenshot saved at: {screenshot_path}"
                
                self.logger.error(error_msg)
            except Exception as debug_ex:
                self.logger.error(f"[PID:{self.pid}] Error gathering debug info: {str(debug_ex)}")
            
            raise AssertionError(f"[PID:{self.pid}] Element not found for text contains assertion: {element_path}")
        
        except Exception as e:
            self.logger.error(f"[PID:{self.pid}] Error in text contains assertion for element {element_path}: {str(e)}")
            raise

    def close(self):
        """Close the browser and cleanup with better error handling"""
        if self.driver:
            try:
                # Check if session is still valid before trying to quit
                try:
                    self.driver.current_url  # Test if session is alive
                    self.driver.quit()
                    self.logger.info(f"[PID:{self.pid}] Browser closed successfully")
                except Exception as session_error:
                    # Session already dead, just clean up
                    self.logger.warning(f"[PID:{self.pid}] Session already closed or invalid: {str(session_error)}")
            except Exception as e:
                # Catch any other errors during cleanup
                error_msg = str(e)
                # Don't log "session not found" as error - it's expected when browser crashes
                if "Unable to find session" in error_msg or "NoSuchSessionException" in error_msg:
                    self.logger.warning(f"[PID:{self.pid}] Browser session already terminated")
                else:
                    self.logger.error(f"[PID:{self.pid}] Error closing browser: {error_msg}")
            finally:
                self.driver = None
