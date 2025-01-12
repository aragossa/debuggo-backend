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


class BrowserAutomation:
    def __init__(self, headless=False, timeout=10):
        self.timeout = timeout
        self.driver = None
        self.logger = self._setup_logger()
        self.setup_driver(headless)

    def _setup_logger(self):
        logger = logging.getLogger('BrowserAutomation')
        logger.setLevel(logging.INFO)

        handler = logging.StreamHandler(sys.stdout)
        handler.setLevel(logging.INFO)
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        handler.setFormatter(formatter)
        logger.addHandler(handler)

        return logger

    def setup_driver(self, headless=False):
        try:
            chrome_options = Options()
            if headless:
                chrome_options.add_argument('--headless')

            # Add common Chrome options
            chrome_options.add_argument('--no-sandbox')
            chrome_options.add_argument('--disable-dev-shm-usage')
            chrome_options.add_argument('--disable-gpu')
            chrome_options.add_argument('--window-size=1920,1080')

            self.driver = webdriver.Chrome(options=chrome_options)
            self.driver.implicitly_wait(5)
            self.logger.info("Browser started successfully")

        except WebDriverException as e:
            self.logger.error(f"Failed to start browser: {str(e)}")
            raise

    def navigate(self, url):
        try:
            self.driver.get(url)
            self.logger.info(f"Navigated to {url}")
        except WebDriverException as e:
            self.logger.error(f"Failed to navigate to {url}: {str(e)}")
            raise

    def find_element(self, selector, by='css'):
        """
        Find an element using either CSS selector or XPath.

        Args:
            selector (str): Element selector
            by (str): Selector type - 'xpath' or 'css' (default: 'css')
        """
        try:
            # Set the appropriate By strategy based on by parameter
            by_strategy = By.XPATH if by.lower() == 'xpath' else By.CSS_SELECTOR

            element = WebDriverWait(self.driver, self.timeout).until(
                EC.presence_of_element_located((by_strategy, selector))
            )
            return element

        except TimeoutException:
            self.logger.error(f"Element not found: {selector}")
            raise
        except Exception as e:
            self.logger.error(f"Error finding element {selector}: {str(e)}")
            raise

    def click(self, selector, by='css'):
        """
        Click an element using either CSS selector or XPath.

        Args:
            selector (str): Element selector
            by (str): Selector type - 'xpath' or 'css' (default: 'css')
        """
        try:
            by_strategy = By.XPATH if by.lower() == 'xpath' else By.CSS_SELECTOR
            element = self.find_element(selector, by_strategy)
            element.click()
            self.logger.info(f"Clicked element: {selector}")
        except Exception as e:
            self.logger.error(f"Failed to click element {selector}: {str(e)}")
            raise

    def type_text(self, selector, text, by='css'):
        try:
            by_strategy = By.XPATH if by.lower() == 'xpath' else By.CSS_SELECTOR
            element = self.find_element(selector, by_strategy)
            element.clear()
            element.send_keys(text)
            self.logger.info(f"Typed text into element: {selector}")
        except Exception as e:
            self.logger.error(f"Failed to type text into element {selector}: {str(e)}")
            raise

    def press_key(self, selector, value, by='css'):
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
            self.logger.info(f"Pressed {key.upper()} key on element: {selector}")

        except Exception as e:
            self.logger.error(f"Failed to press {key.upper()} key on element {selector}: {str(e)}")
            raise

    def get_text(self, selector, by='css'):
        try:
            by_strategy = By.XPATH if by.lower() == 'xpath' else By.CSS_SELECTOR
            element = self.find_element(selector, by_strategy)
            return element.text
        except Exception as e:
            self.logger.error(f"Failed to get text from element {selector}: {str(e)}")
            raise

    def wait_for_element(self, selector, by='css', timeout=None):
        timeout = timeout or self.timeout
        try:
            by_strategy = By.XPATH if by.lower() == 'xpath' else By.CSS_SELECTOR
            element = WebDriverWait(self.driver, timeout).until(
                EC.presence_of_element_located((by_strategy, selector))
            )
            return element
        except TimeoutException:
            self.logger.error(f"Timeout waiting for element: {selector}")
            raise

    def get_page_source(self):
        """
        Retrieve the HTML source code of the current page.

        Returns:
            str: The HTML source code of the page.
        """
        try:
            page_source = self.driver.page_source
            self.logger.info("Retrieved page source successfully")
            return page_source
        except Exception as e:
            self.logger.error(f"Failed to get page source: {str(e)}")
            raise

    def close(self):
        if self.driver:
            self.driver.quit()
            self.logger.info("Browser closed")
