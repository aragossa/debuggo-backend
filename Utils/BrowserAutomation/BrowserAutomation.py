from selenium import webdriver
from selenium.webdriver import Keys
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, WebDriverException, NoAlertPresentException, UnexpectedAlertPresentException
from selenium.webdriver.common.desired_capabilities import DesiredCapabilities
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.remote.file_detector import LocalFileDetector
import json
import logging
import sys
import os
import tempfile
import datetime
import time
import re

from auroqa.Utils.BrowserAutomation.EnvHelper import EnvHelper
from auroqa.Utils.System import System


class BrowserAutomation:
    def __init__(self, headless=False, timeout=10):
        self.timeout = timeout
        self.driver = None
        self._seen_handles = set()  # tabs the test has already been in, see switch_tab
        self.logger = self._setup_logger()
        self.pid = os.getpid()  # Initialize pid before setup_driver
        self.setup_driver(headless)
        self.env = EnvHelper()

    def _setup_logger(self):
        logger = logging.getLogger('BrowserAutomation')
        logger.setLevel(logging.INFO)
        # The app configures root logging (main.py); an own handler here would print every line twice
        if logging.getLogger().handlers:
            return logger

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
            # Keep a native alert open until a step handles it. The default ("dismiss and notify")
            # closes it on the next command, so accept_alert/assert_alert_text would find nothing
            chrome_options.set_capability('unhandledPromptBehavior', 'ignore')
            # The requests of the page go to Chrome's performance log, read by drain_network_log()
            chrome_options.set_capability('goog:loggingPrefs', {'performance': 'ALL'})

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
            # The browser runs in another container: with this detector send_keys on a file input
            # uploads the local file to the Selenium node first (see upload_file)
            self.driver.file_detector = LocalFileDetector()
            self._seen_handles = set(self.driver.window_handles)
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

    def clear_http_cache(self):
        """
        Empty the browser's HTTP cache. Cookies and storage do not cover it: a response sent with
        Cache-Control: max-age is reused without a request, so a page opened again shows old data.
        """
        try:
            self.driver.execute("executeCdpCommand", {"cmd": "Network.clearBrowserCache", "params": {}})
            self.logger.info(f"[PID:{self.pid}] HTTP cache cleared")
            return True
        except Exception as e:
            self.logger.warning(f"[PID:{self.pid}] Could not clear the HTTP cache: {str(e)}")
            return False

    def drain_network_log(self):
        """
        The XHR/fetch requests the page has sent since the last call: [(method, url, status)].
        status is None for a request whose response has not arrived yet when the log is read
        and never arrives later. Reading the log empties it, so this is called after every step.
        """
        if not hasattr(self, '_net_pending'):
            self._net_pending = {}  # request id -> (method, url): sent, response not seen yet
        finished = []
        for entry in self.driver.get_log('performance'):
            try:
                message = json.loads(entry['message'])['message']
            except (KeyError, ValueError, TypeError):
                continue
            params = message.get('params') or {}
            if message.get('method') == 'Network.requestWillBeSent':
                request = params.get('request') or {}
                if params.get('type') in ('XHR', 'Fetch') and request.get('method') != 'OPTIONS':
                    self._net_pending[params.get('requestId')] = (request.get('method', 'GET'), request.get('url', ''))
            elif message.get('method') == 'Network.responseReceived':
                sent = self._net_pending.pop(params.get('requestId'), None)
                if sent:
                    finished.append((sent[0], sent[1], (params.get('response') or {}).get('status')))
            elif message.get('method') == 'Network.loadingFailed':
                sent = self._net_pending.pop(params.get('requestId'), None)
                if sent:
                    finished.append((sent[0], sent[1], None))
        return finished

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
                    # Other actions: the element is not in the DOM, so waiting for it to become
                    # visible would only repeat the wait that has just timed out
                    
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
            # What goes into a password field stays out of the log
            shown = '***' if (element.get_attribute('type') or '').lower() == 'password' else text
            self.logger.info(f"[PID:{self.pid}] Typed text: {shown} into element: {selector}")
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

    def wait_for_element_to_be_visible(self, selector, by='xpath', timeout=None):
        """
        Wait for an element to be visible on the page.
        This is an alias for wait_for_element but specifically checks for visibility.
        """
        timeout = timeout or self.timeout
        try:
            by_strategy = By.XPATH if by.lower() == 'xpath' else By.CSS_SELECTOR
            
            self.logger.info(f"[PID:{self.pid}] Waiting for element to be visible: '{selector}' using strategy: {by_strategy}")
            
            # Wait for the page to be loaded completely
            WebDriverWait(self.driver, timeout).until(
                lambda d: d.execute_script('return document.readyState') == 'complete'
            )
            
            # Wait for the element to be visible (not just present)
            element = WebDriverWait(self.driver, timeout).until(
                EC.visibility_of_element_located((by_strategy, selector))
            )
            
            self.logger.info(f"[PID:{self.pid}] Element is now visible: '{selector}'")
            return element
            
        except TimeoutException:
            screenshot_path = self.take_screenshot()
            self.logger.error(f"[PID:{self.pid}] Timeout waiting for element to be visible: '{selector}'. Screenshot: {screenshot_path}")
            raise
        except Exception as e:
            self.logger.error(f"[PID:{self.pid}] Error waiting for element to be visible {selector}: {str(e)}")
            raise

    def wait_for_element_visible(self, selector, by='xpath', timeout=None):
        """
        Alias for wait_for_element_to_be_visible.
        AI sometimes generates this variant without the 'to_be' part.
        """
        return self.wait_for_element_to_be_visible(selector, by, timeout)

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
            # The page cannot be read while a native alert is open
            if self.get_alert_text() is not None:
                self.logger.info(f"[PID:{self.pid}] Native alert is open, not waiting for page changes")
                return False

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
                lambda d: d.execute_script("return typeof jQuery === 'undefined' || jQuery.active == 0") or True
            )
            
            self.logger.info(f"[PID:{self.pid}] Page changes detected and page is stable")
            return True
            
        except TimeoutException:
            self.logger.warning(f"[PID:{self.pid}] No page changes detected within {timeout} seconds")
            return False
        except UnexpectedAlertPresentException:
            # An alert that opens with a delay interrupts the wait: that is the page's reaction, not an error
            self.logger.info(f"[PID:{self.pid}] Native alert opened while waiting for page changes")
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
            # Selenium cannot take a screenshot while a native alert is open
            if self.get_alert_text() is not None:
                self.logger.info(f"[PID:{self.pid}] Native alert is open, screenshot skipped")
                return None

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
        # Nothing here waits for an element: with the implicit wait every empty lookup costs 5 seconds
        self.driver.implicitly_wait(0)
        try:
            self._debug_page_structure(selector, by)
        finally:
            self.driver.implicitly_wait(5)

    def _debug_page_structure(self, selector=None, by='xpath'):
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

    def assert_text(self, element_path: str, expected_text: str, by_strategy: str = None):
        """
        Assert that an element's text exactly matches the expected text.
        
        Args:
            element_path (str): The locator path to find the element
            expected_text (str): The exact text that should match the element's text
            by_strategy (str, optional): The strategy to locate the element (e.g., 'xpath', 'css')
            
        Raises:
            AssertionError: If the element's text does not exactly match the expected text
            ValueError: If expected_text is not provided
        """
        # Handle None or empty by_strategy
        if not by_strategy:
            by_strategy = 'xpath'  # Default to xpath if by_strategy is None or empty
        
        if not expected_text:
            raise ValueError(f"[PID:{self.pid}] Expected text cannot be empty for text assertion")
        
        self.logger.info(f"[PID:{self.pid}] Asserting that element '{element_path}' has exact text: '{expected_text}' using {by_strategy}")
        
        try:
            element = self.find_element(element_path, by_strategy)
            
            if not element:
                raise AssertionError(f"[PID:{self.pid}] Element not found: {element_path}")
            
            # Get the actual text from the element
            actual_text = element.text.strip()
            expected_text = expected_text.strip()
            
            self.logger.info(f"[PID:{self.pid}] Element actual text: '{actual_text}'")
            
            # Check if the expected text exactly matches the actual text (case-sensitive)
            if expected_text != actual_text:
                raise AssertionError(
                    f"[PID:{self.pid}] Text does not match. "
                    f"Expected: '{expected_text}', "
                    f"Actual: '{actual_text}'"
                )
            
            self.logger.info(f"[PID:{self.pid}] Text assertion passed: '{expected_text}' matches element text")
            return True
            
        except TimeoutException:
            # Take a screenshot for debugging
            screenshot_path = self.take_screenshot()
            
            # Log additional debugging information
            self.logger.error(f"[PID:{self.pid}] Timeout waiting for element: {element_path}")
            self.logger.error(f"[PID:{self.pid}] Screenshot saved: {screenshot_path}")
            raise AssertionError(f"[PID:{self.pid}] Timeout waiting for element: {element_path}")
        except Exception as e:
            self.logger.error(f"[PID:{self.pid}] Error asserting text: {str(e)}")
            raise

    def assert_attribute(self, element_path: str, expected: str, by_strategy: str = None):
        """
        Assert that an element's attribute has the expected value.

        Args:
            element_path (str): The path to the element to check
            expected (str): "attribute=value", e.g. "aria-valuenow=0", "value=John", "href=/login".
                Boolean attributes (disabled, checked, selected, readonly) are "true" when set;
                use "disabled=false" to assert that one is not set.
            by_strategy (str): The strategy to locate elements (xpath or css)

        Raises:
            AssertionError: If the attribute value does not match
        """
        if not by_strategy:
            by_strategy = 'xpath'

        if not expected or '=' not in expected:
            raise ValueError(f"[PID:{self.pid}] assert_attribute expects value in the form 'attribute=value', got: '{expected}'")

        attribute_name, expected_value = expected.split('=', 1)
        attribute_name = attribute_name.strip()
        expected_value = expected_value.strip()
        if not attribute_name:
            raise ValueError(f"[PID:{self.pid}] assert_attribute needs an attribute name before '=', got: '{expected}'")

        self.logger.info(f"[PID:{self.pid}] Asserting that element '{element_path}' has attribute {attribute_name}='{expected_value}' using {by_strategy}")

        try:
            element = self.find_element(element_path, by_strategy)

            if not element:
                raise AssertionError(f"[PID:{self.pid}] Element not found: {element_path}")

            actual_value = element.get_attribute(attribute_name)
            self.logger.info(f"[PID:{self.pid}] Element actual {attribute_name}: {actual_value!r}")

            # A missing attribute comes back as None: that is "false" for boolean attributes
            if actual_value is None:
                matches = expected_value.lower() in ('', 'false')
            else:
                matches = expected_value == str(actual_value).strip()

            if not matches:
                raise AssertionError(
                    f"[PID:{self.pid}] Attribute '{attribute_name}' does not match. "
                    f"Expected: '{expected_value}', "
                    f"Actual: {actual_value!r}"
                )

            self.logger.info(f"[PID:{self.pid}] Attribute assertion passed: {attribute_name}='{expected_value}'")
            return True

        except TimeoutException:
            screenshot_path = self.take_screenshot()
            self.logger.error(f"[PID:{self.pid}] Timeout waiting for element: {element_path}")
            self.logger.error(f"[PID:{self.pid}] Screenshot saved: {screenshot_path}")
            raise AssertionError(f"[PID:{self.pid}] Timeout waiting for element: {element_path}")
        except Exception as e:
            self.logger.error(f"[PID:{self.pid}] Error asserting attribute: {str(e)}")
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

    # ------------------------------------------------------------------
    # Tabs and windows
    # ------------------------------------------------------------------

    def switch_tab(self, target: str = None):
        """
        Switch to another browser tab or window.

        Args:
            target (str): which tab to switch to:
                "new"  - the most recently opened tab other than the current one (default);
                         waits for it to open
                "main" - the first tab, the one the test started in
                "2"    - tab number, counted from 1 in opening order
                any other text - the tab whose title or URL contains it
        """
        target = (target or 'new').strip()
        key = target.lower()
        self.logger.info(f"[PID:{self.pid}] Switching tab: '{target}'")

        try:
            if key in ('new', 'last', 'latest'):
                handle = self._wait_for_new_tab()
            elif key in ('main', 'first', 'original'):
                handle = self.driver.window_handles[0]
            elif key.isdigit():
                number = int(key)
                try:
                    WebDriverWait(self.driver, self.timeout).until(lambda d: len(d.window_handles) >= number)
                except TimeoutException:
                    pass
                handles = self.driver.window_handles
                if number < 1 or number > len(handles):
                    raise AssertionError(f"[PID:{self.pid}] switch_tab: tab {number} does not exist, {len(handles)} tab(s) are open")
                handle = handles[number - 1]
            else:
                handle = self._find_tab_by_text(target)

            self.driver.switch_to.window(handle)
            self._seen_handles.update(self.driver.window_handles)
            self.wait_for_page_load()
            self.logger.info(f"[PID:{self.pid}] Switched to tab '{self.driver.title}' ({self.driver.current_url})")
        except Exception as e:
            self.logger.error(f"[PID:{self.pid}] Failed to switch tab '{target}': {str(e)}")
            raise

    def _wait_for_new_tab(self):
        """
        Handle of the tab that opened since the last switch; waits for it to open.
        If the browser is already on the newest tab, that tab is returned at once, so a
        repeated "new" is harmless.
        """
        current = self._current_handle()

        def pick(driver):
            handles = driver.window_handles
            unseen = [h for h in handles if h not in self._seen_handles and h != current]
            if unseen:
                return unseen[-1]
            if len(handles) > 1 and current == handles[-1]:
                return current
            return False

        try:
            return WebDriverWait(self.driver, self.timeout).until(pick)
        except TimeoutException:
            others = [h for h in self.driver.window_handles if h != current]
            if not others:
                raise AssertionError(f"[PID:{self.pid}] switch_tab 'new': no other tab opened within {self.timeout} seconds")
            return others[-1]

    def new_tab_opened(self):
        """True if a tab has opened that the test has not switched to yet. Does not wait."""
        try:
            current = self._current_handle()
            return any(h not in self._seen_handles and h != current for h in self.driver.window_handles)
        except WebDriverException:
            return False

    def _current_handle(self):
        """Handle of the current tab, or None if that tab was closed."""
        try:
            return self.driver.current_window_handle
        except WebDriverException:
            return None

    def _find_tab_by_text(self, text: str):
        """Find the tab whose title or URL contains the text; waits for it to open."""
        original = self._current_handle()
        wanted = text.lower()
        deadline = time.time() + self.timeout
        while True:
            for handle in self.driver.window_handles:
                self.driver.switch_to.window(handle)
                if wanted in (self.driver.title or '').lower() or wanted in (self.driver.current_url or '').lower():
                    return handle
            if time.time() > deadline:
                break
            time.sleep(0.5)
        if original in self.driver.window_handles:
            self.driver.switch_to.window(original)
        raise AssertionError(
            f"[PID:{self.pid}] switch_tab: no tab with '{text}' in title or URL. "
            f"Use 'new', 'main', a tab number, or a part of the title or URL"
        )

    # ------------------------------------------------------------------
    # Native alerts (alert, confirm, prompt)
    # ------------------------------------------------------------------

    def get_alert_text(self):
        """
        Text of the open native alert/confirm/prompt, or None if there is none.
        While an alert is open, Selenium can neither read the page nor take a screenshot.
        """
        try:
            return self.driver.switch_to.alert.text
        except NoAlertPresentException:
            return None
        except WebDriverException:
            return None

    def _wait_for_alert(self, action: str):
        try:
            return WebDriverWait(self.driver, self.timeout).until(EC.alert_is_present())
        except TimeoutException:
            raise AssertionError(f"[PID:{self.pid}] {action}: no native alert appeared within {self.timeout} seconds")

    def accept_alert(self, text: str = None):
        """
        Accept (OK) the native alert, confirm or prompt; waits for it to appear.

        Args:
            text (str): for a prompt, the text to type before pressing OK
        """
        try:
            alert = self._wait_for_alert('accept_alert')
            alert_text = alert.text
            if text:
                alert.send_keys(text)
            alert.accept()
            self.logger.info(f"[PID:{self.pid}] Accepted alert '{alert_text}'" + (f" with text '{text}'" if text else ""))
        except Exception as e:
            self.logger.error(f"[PID:{self.pid}] Failed to accept alert: {str(e)}")
            raise

    def dismiss_alert(self):
        """Dismiss (Cancel) the native alert, confirm or prompt; waits for it to appear."""
        try:
            alert = self._wait_for_alert('dismiss_alert')
            alert_text = alert.text
            alert.dismiss()
            self.logger.info(f"[PID:{self.pid}] Dismissed alert '{alert_text}'")
        except Exception as e:
            self.logger.error(f"[PID:{self.pid}] Failed to dismiss alert: {str(e)}")
            raise

    def assert_alert_text(self, expected_text: str):
        """
        Assert the text of the open native alert; waits for it to appear and leaves it open.

        Raises:
            AssertionError: If no alert appears or its text differs
        """
        if not expected_text:
            raise ValueError(f"[PID:{self.pid}] assert_alert_text expects the alert text in value")

        actual_text = (self._wait_for_alert('assert_alert_text').text or '').strip()
        if actual_text != expected_text.strip():
            raise AssertionError(
                f"[PID:{self.pid}] Alert text does not match. "
                f"Expected: '{expected_text.strip()}', Actual: '{actual_text}'"
            )
        self.logger.info(f"[PID:{self.pid}] Alert text assertion passed: '{actual_text}'")
        return True

    def describe_browser_state(self):
        """
        What the page HTML cannot show: an open native alert and the open tabs.

        Returns:
            dict: {'alert_text': str or None, 'tab_count': int, 'current_tab': int or None (from 1),
                   'title': str or None, 'url': str or None}
        """
        state = {'alert_text': self.get_alert_text(), 'tab_count': 1, 'current_tab': None, 'title': None, 'url': None}
        try:
            handles = self.driver.window_handles
            state['tab_count'] = len(handles)
            current = self._current_handle()
            if current in handles:
                state['current_tab'] = handles.index(current) + 1
            # Title and URL cannot be read while an alert is open
            if state['alert_text'] is None and state['current_tab']:
                state['title'] = self.driver.title
                state['url'] = self.driver.current_url
        except WebDriverException as e:
            self.logger.warning(f"[PID:{self.pid}] Could not read browser state: {str(e)}")
        return state

    # ------------------------------------------------------------------
    # Drag and drop
    # ------------------------------------------------------------------

    _DRAG_FINGERPRINT_JS = """
        function fp(el) {
            var r = el.getBoundingClientRect();
            var p = el.parentNode;
            var idx = p ? Array.prototype.indexOf.call(p.children, el) : -1;
            return [Math.round(r.left), Math.round(r.top), idx, el.className, el.innerHTML].join('|');
        }
        return fp(arguments[0]) + '||' + fp(arguments[1]);
    """

    # Events are spaced out like a real drag: libraries such as react-dnd react to dragover
    # on the next animation frame, so a burst of events in one tick moves nothing.
    # After dragstart the events go to whatever is under the drop point, as with a mouse:
    # in a sortable list the target moves away once the list re-orders.
    _HTML5_DRAG_JS = """
        var source = arguments[0], target = arguments[1], done = arguments[arguments.length - 1];
        var dataTransfer = new DataTransfer();
        var t = target.getBoundingClientRect();
        var x = t.left + t.width / 2, y = t.top + t.height / 2;
        function underPoint() {
            var el = document.elementFromPoint(x, y);
            return el && document.body.contains(el) ? el : target;
        }
        function fire(type, el, cx, cy) {
            el.dispatchEvent(new DragEvent(type, {
                bubbles: true, cancelable: true, composed: true, dataTransfer: dataTransfer,
                clientX: cx, clientY: cy
            }));
        }
        var s = source.getBoundingClientRect();
        var steps = [
            function () { fire('dragstart', source, s.left + s.width / 2, s.top + s.height / 2); },
            function () { fire('dragenter', underPoint(), x, y); },
            function () { fire('dragover', underPoint(), x, y); },
            function () { fire('dragover', underPoint(), x, y); },
            function () { fire('drop', underPoint(), x, y); },
            function () { fire('dragend', source, x, y); }
        ];
        (function next(i) {
            if (i >= steps.length) { done(true); return; }
            steps[i]();
            setTimeout(function () { next(i + 1); }, 100);
        })(0);
    """

    def drag_and_drop(self, source_path: str, target: str, by_strategy: str = None):
        """
        Drag one element onto another.

        Does a real mouse drag (ActionChains) first. If nothing changed on the page and the
        source is a native HTML5 draggable, emulates HTML5 drag-and-drop events with JavaScript.
        Fails if neither way changed the dragged element or the target.

        Args:
            source_path (str): locator of the element to drag
            target (str): XPath of the element to drop onto. Prefix "html5:" to try the HTML5
                emulation first and the mouse drag second, e.g. "html5://div[@id='column-b']"
            by_strategy (str): strategy for source_path (xpath or css)
        """
        if not by_strategy:
            by_strategy = 'xpath'
        if not target or not target.strip():
            raise ValueError(f"[PID:{self.pid}] drag_and_drop expects the XPath of the drop target in value")

        target = target.strip()
        html5_first = target.lower().startswith('html5:')
        if html5_first:
            target = target[len('html5:'):].strip()

        self.logger.info(f"[PID:{self.pid}] Dragging '{source_path}' onto '{target}'" + (" (HTML5 emulation first)" if html5_first else ""))

        try:
            source_el = self.find_element(source_path, by_strategy)
            target_el = self.find_element(target, 'xpath')
            self.driver.execute_script("arguments[0].scrollIntoView({block: 'center', inline: 'center'});", source_el)
            time.sleep(0.3)

            before = self._drag_fingerprint(source_el, target_el)
            is_html5 = self.driver.execute_script("return !!arguments[0].closest('[draggable=\"true\"]');", source_el)

            methods = [('mouse', self._drag_with_mouse)]
            if html5_first:
                methods.insert(0, ('HTML5 emulation', self._drag_with_html5_events))
            elif is_html5:
                methods.append(('HTML5 emulation', self._drag_with_html5_events))

            for name, drag in methods:
                drag(source_el, target_el)
                time.sleep(0.5)
                # None: the page re-rendered the elements, which is a change too
                after = self._drag_fingerprint(source_el, target_el)
                if before is None or after != before:
                    self.logger.info(f"[PID:{self.pid}] Dragged with {name}: {source_path} -> {target}")
                    return
                self.logger.info(f"[PID:{self.pid}] Drag with {name} changed nothing")

            raise AssertionError(
                f"[PID:{self.pid}] drag_and_drop had no effect: neither '{source_path}' nor '{target}' changed "
                f"(tried: {', '.join(name for name, _ in methods)}). Check that value is the XPath of the real drop target"
            )
        except Exception as e:
            self.logger.error(f"[PID:{self.pid}] Failed to drag {source_path} onto {target}: {str(e)}")
            raise

    def _drag_with_mouse(self, source_el, target_el):
        # Hold, nudge, move, wiggle over the target, release. A plain drag_and_drop() is too
        # fast: the target must see the pointer move over it (dragover) before the drop,
        # or sortable lists and native HTML5 drop zones ignore the release
        ActionChains(self.driver) \
            .move_to_element(source_el).click_and_hold().pause(0.3) \
            .move_by_offset(10, 10).pause(0.2) \
            .move_to_element(target_el).pause(0.3) \
            .move_by_offset(3, 3).pause(0.2) \
            .move_by_offset(-3, -3).pause(0.3) \
            .release().perform()

    def _drag_with_html5_events(self, source_el, target_el):
        self.driver.execute_async_script(self._HTML5_DRAG_JS, source_el, target_el)

    def _drag_fingerprint(self, source_el, target_el):
        """Position, order and content of both elements; None if the page re-rendered them."""
        try:
            return self.driver.execute_script(self._DRAG_FINGERPRINT_JS, source_el, target_el)
        except WebDriverException:
            return None

    # ------------------------------------------------------------------
    # File upload
    # ------------------------------------------------------------------

    SAMPLE_FILES_DIR = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), 'sample_files'
    )

    @classmethod
    def list_sample_files(cls):
        """Names of the sample files that upload_file can use."""
        try:
            return sorted(f for f in os.listdir(cls.SAMPLE_FILES_DIR) if not f.startswith('.') and f.lower() != 'readme.md')
        except OSError:
            return []

    def upload_file(self, selector: str, file_name: str, by: str = 'xpath'):
        """
        Put a sample file into an <input type="file">.

        Args:
            selector (str): locator of the file input
            file_name (str): name of a file in sample_files/, e.g. "sample.txt"
            by (str): selector type - 'xpath' or 'css'
        """
        available = self.list_sample_files()
        name = os.path.basename((file_name or '').strip())
        if not name or name not in available:
            raise ValueError(
                f"[PID:{self.pid}] upload_file expects a sample file name in value, got: '{file_name}'. "
                f"Available: {', '.join(available)}"
            )

        try:
            by_strategy = By.XPATH if (by or 'xpath').lower() == 'xpath' else By.CSS_SELECTOR
            # A file input is often hidden behind a styled button: presence is enough
            element = WebDriverWait(self.driver, self.timeout).until(
                EC.presence_of_element_located((by_strategy, selector))
            )
            if element.tag_name.lower() != 'input' or (element.get_attribute('type') or '').lower() != 'file':
                raise AssertionError(
                    f"[PID:{self.pid}] upload_file needs an <input type=\"file\"> element, "
                    f"got <{element.tag_name}> for {selector}"
                )
            element.send_keys(os.path.join(self.SAMPLE_FILES_DIR, name))
            self.logger.info(f"[PID:{self.pid}] Uploaded sample file '{name}' into element: {selector}")
        except Exception as e:
            self.logger.error(f"[PID:{self.pid}] Failed to upload file into element {selector}: {str(e)}")
            raise

    def capture_transient_notifications(self, timeout=5):
        """
        Capture transient notifications/toasts that appear and disappear quickly.
        Uses JavaScript to monitor DOM changes and capture notification text.
        
        Args:
            timeout: How long to monitor for notifications (seconds)
            
        Returns:
            List of captured notification texts
        """
        try:
            script = """
            return new Promise((resolve) => {
                const notifications = [];
                let captureTimeout;
                
                // Function to extract notification text
                function captureNotifications() {
                    // Common notification selectors
                    const selectors = [
                        '[data-notify="message"]',
                        '.notification',
                        '.toast',
                        '.alert',
                        '[role="alert"]',
                        '.message-box',
                        '.success-message',
                        '.error-message',
                        '.warning-message',
                        '.info-message'
                    ];
                    
                    selectors.forEach(selector => {
                        const elements = document.querySelectorAll(selector);
                        elements.forEach(el => {
                            const text = el.textContent.trim();
                            if (text && !notifications.includes(text)) {
                                notifications.push(text);
                            }
                        });
                    });
                }
                
                // Capture initial notifications
                captureNotifications();
                
                // Monitor for new notifications
                const observer = new MutationObserver(() => {
                    captureNotifications();
                });
                
                observer.observe(document.body, {
                    childList: true,
                    subtree: true,
                    characterData: true
                });
                
                // Stop monitoring after timeout and return captured notifications
                captureTimeout = setTimeout(() => {
                    observer.disconnect();
                    resolve(notifications);
                }, arguments[0] * 1000);
            });
            """
            
            notifications = self.driver.execute_async_script(script, timeout)
            if notifications:
                self.logger.info(f"[PID:{self.pid}] Captured notifications: {notifications}")
            return notifications
            
        except Exception as e:
            self.logger.warning(f"[PID:{self.pid}] Error capturing notifications: {str(e)}")
            return []

    def wait_for_page_state_change(self, initial_url=None, initial_title=None, timeout=10):
        """
        Wait for page state to change (URL or title change).
        Useful for verifying actions that trigger navigation.
        
        Args:
            initial_url: The URL before the action (if None, uses current URL)
            initial_title: The page title before the action (if None, uses current title)
            timeout: How long to wait for change (seconds)
            
        Returns:
            True if page state changed, False if timeout
        """
        try:
            if initial_url is None:
                initial_url = self.driver.current_url
            if initial_title is None:
                initial_title = self.driver.title
            
            start_time = time.time()
            while time.time() - start_time < timeout:
                current_url = self.driver.current_url
                current_title = self.driver.title
                
                if current_url != initial_url or current_title != initial_title:
                    self.logger.info(f"[PID:{self.pid}] Page state changed. URL: {initial_url} → {current_url}")
                    return True
                
                time.sleep(0.5)
            
            self.logger.warning(f"[PID:{self.pid}] Page state did not change within {timeout} seconds")
            return False
            
        except Exception as e:
            self.logger.error(f"[PID:{self.pid}] Error waiting for page state change: {str(e)}")
            return False

    def wait_for_element_count_change(self, selector, initial_count=None, timeout=10, by=By.XPATH):
        """
        Wait for the number of elements matching a selector to change.
        Useful for verifying new items were added to a list/table.
        
        Args:
            selector: XPath or CSS selector for elements
            initial_count: Initial count (if None, uses current count)
            timeout: How long to wait for change (seconds)
            by: Locator strategy (By.XPATH or By.CSS_SELECTOR)
            
        Returns:
            True if count changed, False if timeout
        """
        try:
            if initial_count is None:
                initial_count = len(self.driver.find_elements(by, selector))
            
            start_time = time.time()
            while time.time() - start_time < timeout:
                current_count = len(self.driver.find_elements(by, selector))
                
                if current_count != initial_count:
                    self.logger.info(f"[PID:{self.pid}] Element count changed: {initial_count} → {current_count}")
                    return True
                
                time.sleep(0.5)
            
            self.logger.warning(f"[PID:{self.pid}] Element count did not change within {timeout} seconds")
            return False
            
        except Exception as e:
            self.logger.error(f"[PID:{self.pid}] Error waiting for element count change: {str(e)}")
            return False

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
