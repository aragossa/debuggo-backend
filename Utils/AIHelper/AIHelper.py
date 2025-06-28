import base64
import sys
from io import BytesIO
import time
import google.generativeai as genai
import google
import json
import logging
import os
from typing import Literal, Dict, Any, Union, Optional
from PIL import Image
import threading
import requests
import glob

from Utils.System import System


class AIHelper:
    _request_times = []  # Class variable to track request timestamps
    _request_lock = threading.Lock()  # Lock for thread-safe access
    _MAX_REQUESTS_PER_MINUTE = 10  # Gemini API limit
    _step_history = {}  # Dictionary to store step history for each test case

    def __init__(self):
        system = System()
        self.provider = system.ai_model.lower()
        self.gemini_api_key = system.gemini_api_key
        self.claude_api_key = system.claude_api_key
        self.deepseek_api_key = system.deepseek_api_key
        self.logger = self._setup_logger()
        self.logger.info(f"Initialized AIHelper with provider: {self.provider}")
        self.db_connection = System.get_db_connection()

    def _setup_logger(self):
        logger = logging.getLogger('AIHelper')
        logger.setLevel(logging.INFO)

        # Remove existing handlers to prevent duplicate logging
        logger.handlers = []

        handler = logging.StreamHandler(sys.stdout)
        handler.setLevel(logging.INFO)
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(filename)s:%(lineno)d  - %(message)s')
        handler.setFormatter(formatter)
        logger.addHandler(handler)

        return logger

    def read_img(self, file_path: str) -> Union[Image.Image, bool]:
        try:
            self.logger.debug({"message": f"Processed image: {file_path}"})
            return Image.open(file_path)
        except (IOError, OSError) as e:
            self.logger.error({"error": f"Failed to process image: {str(e)}"})
            return False
        except Exception as e:
            self.logger.error({"error": f"Unexpected error while processing image: {str(e)}"})
            return False

    def get_analyze_img_promt(self):
        json_structure = """
           [
               {
                   "name": "UI TESTS",
                   "type": "root",
                   "children": [
                       {
                           "name": "Test Group 1",
                           "type": "group",
                           "children": [
                               {
                                   "name": "Test case name",
                                   "description": "Test description",
                                   "expected_result": "Test expected result",
                                   "type": "test"
                                   ]
                               },
                               {
                                   "id": 4,
                                   "name": "Test case name",
                                   "description": "Test description",
                                   "expected_result": "Test expected result",
                                   "type": "test"
                               }
                           ]
                       },
                       {
                           "id": 5,
                           "name": "Test Group 2",
                           "type": "group",
                           "children": [
                               {
                                   "id": 6,
                                   "name": "Test case name",
                                   "description": "Test description",
                                   "expected_result": "Test expected result",
                                   "type": "test",
                               }
                           ]
                       }
                   ]
               }
           ]
           """
        text_prompt = (
            f"Act as QA engineer. Analyze attached screenshot of a web page and generate as much as possible test cases for this Web page\n"
            "I need response only in json format don't give me any other info:\n"
            f"{json_structure}"
        )
        return text_prompt

    def get_analyze_txt_promt(self, text_content):
        json_structure = """
           [
               {
                   "name": "UI TESTS or API TESTS",
                   "type": "root",
                   "children": [
                       {
                           "name": "Test Group 1",
                           "type": "group",
                           "children": [
                               {
                                   "name": "Test case name",
                                   "description": "Test description",
                                   "expected_result": "Test expected result",
                                   "type": "test"
                               },
                               {
                                   "id": 4,
                                   "name": "Test case name",
                                   "description": "Test description",
                                   "expected_result": "Test expected result",
                                   "type": "test"
                               }
                           ]
                       },
                       {
                           "id": 5,
                           "name": "Test Group 2",
                           "type": "group",
                           "children": [
                               {
                                   "id": 6,
                                   "name": "Test case name",
                                   "description": "Test description",
                                   "expected_result": "Test expected result",
                                   "type": "test"
                               }
                           ]
                       }
                   ]
               }
           ]
           """
        text_prompt = (
            f"Act as QA engineer. Analyze attached schema export file and generate as much as possible test cases for this API.\n"
            f"For API tests try to find requests that can be used together and build a test case with chain of requests\n"
            f"If you see here UI TESTS either API TESTS create 2 root UI TESTS and API TESTS\n"
            f"The response must be a valid JSON array following this exact structure, with NO additional text or explanation:\n"
            f"{json_structure}\n\n"
            f"Here is the schema file to analyze: {text_content}"
        )
        return text_prompt

    def get_analyze_html_prompt(self, html_code: str, test_name: str, test_description: str, step_order: int, next_prompt: str, prev_step_description: str, attached_screenshot: str = None) -> str:
        # Get test case ID from test name (assuming it's stored in the format "Test Case #123")
        try:
            test_case_id = int(''.join(filter(str.isdigit, test_name)))
        except (ValueError, TypeError):
            test_case_id = None
            
        # Build step history string
        step_history = ""
        if test_case_id is not None:
            history = self.get_step_history(test_case_id)
            if history:
                step_history = "Previous steps executed:\n"
                for idx, step in enumerate(history):
                    step_history += (
                        f"Step {idx}: {step['element_purpose']}\n"
                        f"- Action: {step['action']}\n"
                        f"- Element: {step['element_locator']} (using {step['by_strategy']})\n"
                        f"- Value: {step['value']}\n"
                    )
                step_history += "\nAvoid repeating the same steps. Each new step should progress the test forward.\n"

        prev_step_prompt = ''
        if prev_step_description != '':
            prev_step_prompt = f'. Take in account that previous step was {prev_step_description}'

        skip_start_navigate = ''
        if step_order == 0:
            skip_start_navigate = ". Skip the step with navigating to the first page.\n"

        # Enhanced prompt with stronger focus on test description and login handling
        return f"""Act as an experienced QA engineer, you are creating a test case: "{test_name}".

This is the suggested test description, some steps might be missing, if you see that executing this step will not help you to complete the test, suggest next step:
{test_description}

You should recursively go through all test steps and on each step you should assume next step until the test will be finished.
If current step will be final step, put to the next_step attribute the word 'Stop'.
You are on the test step # {step_order}{prev_step_prompt}{skip_start_navigate}
{step_history}

IMPORTANT GUIDELINES:
1. BEFORE SUGGESTING ELEMENT TO LOCATE, ANALYZE THE HTML CODE AND THE SCREENSHOT TO UNDERSTAND THE CONTEXT AND MAKE SURE THAT ELEMENT IS VISIBLE AND CLICKABLE
2. ELEMENT EXISTENCE VERIFICATION IS MANDATORY:
   - You MUST confirm that each element you suggest actually exists in the current HTML code
   - Do NOT suggest any element without verifying its existence in the provided HTML
   - Before suggesting a locator, search the HTML code for text fragments, IDs, or other attributes
   - Include a comment in the element_purpose field like: "Element verified in HTML: <attribute/value found>"
3. STRICT SEQUENTIAL NAVIGATION - NO SKIPPING STEPS:
   - You must STRICTLY follow one action at a time in a logical sequence
   - NEVER skip to form fields or other interactions before completing the navigation steps
   - NEVER assume the user has already performed actions not mentioned in step_history

4. MENU NAVIGATION - For dropdown or expandable menus:
   - If a menu item appears to be hidden or requires expanding a parent menu first:
     a. FIRST step: Locate and click/hover on the parent menu item to expand it
     b. SECOND step: Only after the submenu is visible, interact with the submenu item
   - NEVER try to directly click on hidden submenu items
   - Check for CSS classes like 'hidden', 'collapsed', or attributes like 'aria-expanded="false"' to identify hidden elements
   - Look for elements with 'dropdown', 'submenu', or similar classes to identify dropdown menus
   - For multi-level menus, handle ONE LEVEL AT A TIME (hover/click parent → click child)
5. LOGIN HANDLING - If login is required, use environment variables:
   - Use {{base_url}} for the base URL
   - First locate and interact with the username/email field, using {{login}} as the value
   - Then locate and interact with the password field, using {{password}} as the value
   - Only after both fields are filled, locate and click the login/submit button
   - ENSURE login is successful before proceeding with any subsequent steps
   - NEVER skip the password field even if it appears to be optional
6. SEQUENTIAL EXECUTION - All steps after login must only be executed after successful login verification

FORM COMPLETION REQUIREMENTS:
1. When filling out forms, ALWAYS complete ALL available fields before submission
2. For login forms specifically:
   - FIRST step: Locate and fill the username/email field with {{login}}
   - SECOND step: Locate and fill the password field with {{password}}
   - THIRD step: Click the login/submit button
   - These steps MUST be performed as separate actions in this exact sequence
3. NEVER combine multiple form field actions into a single step
4. NEVER skip form fields, especially password fields

ELEMENT VISIBILITY REQUIREMENTS:
1. ALWAYS check if an element is visible and interactable before suggesting it
2. For navigation menus:
   - Check if the menu item requires a parent menu to be expanded first
   - If a menu is collapsed/hidden, first expand it before trying to click items within it
   - Look for parent elements with classes like 'dropdown', 'menu', 'nav', etc.
   - Check for elements with 'display: none', visibility: hidden', or opacity: 0' styles
   - For flyout/hover menus, use 'hover' action on parent before clicking child items
3. For dynamic elements:
   - Ensure the element is in the viewport and not obscured by other elements
   - Consider using 'scroll' action to bring elements into view if needed
   - Use 'hover' action for elements that require mouse hover to be accessible

STEP SEQUENCING REQUIREMENTS:
1. FOLLOW THE LOGICAL FLOW of the application - don't skip steps or jump ahead
2. If the next_prompt suggests clicking on a menu item, FIRST check if that menu item is visible
3. If a menu item is hidden inside a dropdown/expandable menu:
   - FIRST step must be to expand/hover the parent menu
   - NEXT step must be to click the specific menu item
4. For any action that leads to a new page or significant UI change:
   - Wait for the page to load completely before proceeding to the next step
   - Verify the new page/state is loaded correctly before interacting with elements

NAVIGATION FLOW ENFORCEMENT:
1. If the next_prompt is to click a specific button or link (e.g., "Click the 'Recipients' link"), you MUST:
   - First verify the button/link exists in the current page
   - If it exists, create a step to click it
   - If it doesn't exist, check if navigation to another page is required first
2. For form interactions:
   - First click the form element
   - Then type or select the appropriate value
   - Never skip directly to form submission without completing all fields
3. For multi-page workflows:
   - Complete all actions on the current page before proceeding to the next page
   - Verify page transitions before interacting with elements on the new page
4. If a url is provided, navigate to instead of trying to click on a link

When performing assertions, consider the following validation patterns:
- Verify presence and text content of error messages, success messages, or labels
- Check if buttons or forms are enabled/disabled after certain actions
- Validate if elements are visible/hidden based on user interactions
- Confirm correct values in input fields, dropdowns, or other form elements
- Verify selected state of checkboxes and radio buttons

Analyze the provided HTML code of a web page to identify an element that possible to be used on this step.
{'Also, consider the attached screenshot if available' if attached_screenshot is not None else ''}
HTML Code:
{html_code}

Your response MUST be a valid JSON object with ALL of the following required fields:
{{
    "element_locator": "XPath selector to locate the element",
    "by_strategy": "xpath",
    "action": "click, type, select, hover, wait, assert, scroll, clear, navigate, press_key",
    "element_purpose": "Brief description of what this step does (e.g., 'verify error message is displayed')",
    "value": "For type actions: MUST provide actual test data (e.g., '{{{{login}}}}' for login field)",
    "next_step": "Description of what to verify next, or 'Stop' if test is complete"
}}

IMPORTANT REQUIREMENTS:
1. JSON Format: The response must strictly follow the valid JSON structure, including all specified fields.
2. Action Types: For any type of actions, ensure that the value field is non-empty and includes appropriate test data.
3. Environment Variables: Use {{{{base_url}}}}, {{{{login}}}}, and {{{{password}}}} for environment-specific values.
4. by_strategy: The value of by_strategy must be either 'css' or 'xpath'—no other values are allowed.
5. Field Validation: If typing an invalid email or another value does not trigger validation, ensure the form is submitted to force validation.
6. Test Progression: Ensure that each test step advances forward. Avoid repeating any steps. Each step must represent a unique action.
7. No Explanations: Do not include any explanation text. Only the required JSON object should be output.
8. Assertion: If applicable, specify an assertion to validate expected behavior.
9. Login Verification: After login steps, include a verification step to confirm successful login before proceeding.
10. Password Field Handling: When dealing with login forms, ALWAYS include a separate step for entering the password in the password field before clicking the login button. This is mandatory even if the form appears to function without it.
11. Hidden Menus: NEVER try to click on hidden submenu items directly. Always expand parent menus first before interacting with their child elements.
12. FOLLOW THE EXACT NEXT STEP: If the next_prompt specifies an action like "Click the 'Recipients' link", make sure to perform exactly that action, not skip ahead to subsequent steps.
13. STRICT SEQUENCE ADHERENCE: You MUST follow the exact sequence of steps. If the next_prompt is "Click the 'New group' button", you MUST create a step that clicks that button, even if you can see form fields that will need to be filled afterward.
14. NEVER ASSUME COMPLETION: Never assume a step has already been completed. If the next_prompt indicates an action, that action must be performed as the current step.
15. ONE ACTION PER STEP: Each step should perform exactly one action (click, type, etc.). Do not combine multiple actions into a single step.
16. ELEMENT EXISTENCE VERIFICATION: Your element_locator MUST be for an element that actually exists in the provided HTML.
   - Before providing a locator, verify that it exists in the HTML code by searching for unique text or attributes
   - Document your verification in the element_purpose with "Element verified in HTML: <text/attribute found>"
   - If you cannot verify the element exists, do not proceed - suggest a "wait" action instead
17. FOCUS ON THE MAIN FLOW: Only include steps that are specifically described in the test description.
   - Do NOT add unnecessary steps like field validation that aren't part of the test description
   - Stay focused on completing the core workflow as described in the test case
   - Avoid adding "nice to have" assertions or verifications that aren't explicitly required
   - Follow the minimal path to complete the described test scenario
"""

    def get_error_analysis_prompt(self, html_code: str, error_message: str, test_name: str, test_description: str, 
                                 step_history: list, failed_step: dict, previous_attempts: list = None, 
                                 screenshot_path: str = None) -> str:
        """
        Generate a prompt for Gemini to analyze a test step failure and suggest a fix.
        
        Args:
            html_code: The HTML of the page when the error occurred
            error_message: The error message from the failed step
            test_name: The name of the test case
            test_description: The description of the test case
            step_history: List of previously executed steps
            failed_step: The step that failed
            previous_attempts: List of previous recovery attempts and their errors
            screenshot_path: Path to the screenshot of the failure state
            
        Returns:
            A prompt for Gemini to analyze the error and suggest a fix
        """
        # Format step history for readability
        formatted_history = ""
        for idx, step in enumerate(step_history):
            formatted_history += (
                f"Step {idx}: {step['element_purpose']}\n"
                f"- Action: {step['action']}\n"
                f"- Element: {step['element_locator']} (using {step['by_strategy']})\n"
                f"- Value: {step['value']}\n"
            )
        
        # Format failed step
        failed_step_info = (
            f"Failed Step: {failed_step['element_purpose']}\n"
            f"- Action: {failed_step['action']}\n"
            f"- Element: {failed_step['element_locator']} (using {failed_step['by_strategy']})\n"
            f"- Value: {failed_step['value']}\n"
            f"- Error: {error_message}\n"
        )
        
        # Format previous attempts if available
        previous_attempts_info = ""
        if previous_attempts and len(previous_attempts) > 0:
            previous_attempts_info = "PREVIOUS RECOVERY ATTEMPTS (THESE DID NOT WORK):\n"
            for idx, attempt in enumerate(previous_attempts):
                previous_attempts_info += (
                    f"Attempt {idx+1}:\n"
                    f"- Action: {attempt['action']}\n"
                    f"- Element: {attempt['element_locator']} (using {attempt['by_strategy']})\n"
                    f"- Value: {attempt['value']}\n"
                    f"- Error: {attempt['error']}\n\n"
                )
        
        return f"""Act as an experienced QA automation expert. You are debugging a failed test step in test case: "{test_name}".

TEST DESCRIPTION: {test_description}

EXECUTED STEPS:
{formatted_history}

FAILED STEP:
{failed_step_info}

{previous_attempts_info}

ERROR ANALYSIS TASK:
Analyze the error and the current page state to determine why the step failed and how to fix it.
The most common issues are:
1. Element not found - The locator might be incorrect or the element might not be visible/present
2. Element not interactable - The element might be hidden, disabled, or covered by another element
3. Navigation issues - The test might be on the wrong page or a previous step might have failed
4. Timing issues - The page might not have loaded completely

CURRENT PAGE HTML:
{html_code}

{'SCREENSHOT OF FAILURE STATE: A screenshot of the page at the time of failure is attached.' if screenshot_path else ''}

Your response MUST be a valid JSON object with ALL of the following required fields:
{{
    "analysis": "Brief analysis of why the step failed",
    "element_locator": "Corrected XPath or CSS selector that should work",
    "by_strategy": "xpath or css",
    "action": "Same or corrected action (click, type, etc.)",
    "element_purpose": "Description of what this step does",
    "value": "Same or corrected value if applicable",
    "next_step": "Description of what to do next"
}}

IMPORTANT:
1. Focus on fixing the CURRENT step, not skipping ahead
2. If the element truly doesn't exist, suggest an alternative approach
3. Consider if a parent menu needs to be expanded first
4. For hidden elements, consider using hover actions or JavaScript execution
5. If timing is the issue, suggest adding a wait step
6. Ensure your solution follows the logical flow of the application
7. DO NOT suggest solutions that have already been tried in the previous attempts
"""

    def switch_provider(self, provider: Literal["chatgpt", "gemini", "claude", "deepseek"]):
        """
        Switch the AI provider.

        Args:
            provider (str): The new AI provider to use ("ChatGPT", "Gemini", "Claude", "Deepseek").
        """
        self.provider = provider.lower()
        self.logger.info(f"Switched to provider: {self.provider}")

    def _wait_for_rate_limit(self):
        """Wait if necessary to comply with rate limits."""
        with self._request_lock:
            now = time.time()
            # Remove timestamps older than 1 minute
            self._request_times = [t for t in self._request_times if now - t < 60]
            
            if len(self._request_times) >= self._MAX_REQUESTS_PER_MINUTE:
                # Calculate how long to wait
                oldest_request = self._request_times[0]
                wait_time = 60 - (now - oldest_request)
                if wait_time > 0:
                    self.logger.warning(f"Rate limit approaching. Waiting {wait_time:.2f} seconds...")
                    time.sleep(wait_time)
                
                # Clean up old timestamps again after waiting
                now = time.time()
                self._request_times = [t for t in self._request_times if now - t < 60]
            
            # Add current request timestamp
            self._request_times.append(now)

    def _get_next_file_number(self, prefix):
        """Get the next available file number for saving screenshots and prompts."""
        # Create page_sources directory if it doesn't exist
        page_sources_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), 'page_sources')
        if not os.path.exists(page_sources_dir):
            os.makedirs(page_sources_dir)
            self.logger.info(f"Created directory: {page_sources_dir}")
        
        # Find the highest existing file number
        pattern = os.path.join(page_sources_dir, f"{prefix}_*.png")
        existing_files = glob.glob(pattern)
        
        max_number = 0
        for file in existing_files:
            try:
                # Extract the number from the filename
                filename = os.path.basename(file)
                number_part = filename.replace(f"{prefix}_", "").replace(".png", "")
                if number_part.isdigit():
                    number = int(number_part)
                    max_number = max(max_number, number)
            except (ValueError, IndexError):
                continue
        
        return max_number + 1

    def _save_to_page_sources(self, image=None, prompt=None, response=None):
        """Save screenshot, prompt, and response to page_sources folder."""
        # Create page_sources directory if it doesn't exist
        page_sources_dir = os.path.join(os.getcwd(), 'page_sources')
        os.makedirs(page_sources_dir, exist_ok=True)
        
        # Get the next available file number
        file_number = self._get_next_file_number(page_sources_dir)
        
        if image:
            # Save screenshot
            screenshot_path = os.path.join(page_sources_dir, f"screenshot_{file_number}.png")
            image.save(screenshot_path)
            self.logger.info(f"Saved screenshot to {screenshot_path}")
        
        if prompt is not None:
            prompt_path = os.path.join(page_sources_dir, f"text_input_{file_number}.txt")
            with open(prompt_path, 'w', encoding='utf-8') as f:
                f.write(prompt)
            self.logger.info(f"Saved prompt to {prompt_path}")
        
        if response is not None:
            response_path = os.path.join(page_sources_dir, f"text_output_{file_number}.txt")
            with open(response_path, 'w', encoding='utf-8') as f:
                f.write(response)
            self.logger.info(f"Saved response to {response_path}")

    def _get_model_id(self) -> str:
        """Get the model ID from the database based on the provider."""
        try:
            # Default model ID in case database query fails
            default_model_id = "gemini-2.5-pro-preview-06-05"
            
            # If provider is not gemini, return the default model ID
            if self.provider != 'gemini':
                self.logger.info(f"Provider is not Gemini, using default model ID: {default_model_id}")
                return default_model_id
            
            # Get a connection from the pool
            conn = self.db_connection
            if not conn:
                self.logger.warning("No database connection available, using default model ID")
                return default_model_id
                
            with conn.cursor() as cur:
                # Query the database for the active default model
                cur.execute("""
                    SELECT model_id FROM ai_models 
                    WHERE is_active = TRUE AND is_default = TRUE
                    LIMIT 1
                """)
                
                result = cur.fetchone()
                
                if result and result[0]:
                    model_id = result[0]
                    self.logger.info(f"Using model ID from database: {model_id}")
                    return model_id
                else:
                    self.logger.warning(f"No default active model found in database, using default model ID: {default_model_id}")
                    return default_model_id
                    
        except Exception as e:
            self.logger.error(f"Error retrieving model ID from database: {str(e)}")
            self.logger.warning(f"Using default model ID: gemini-2.5-pro-preview-06-05")
            return "gemini-2.5-pro-preview-06-05"

    def send_request_to_gemini(self, prompt: str, image: Optional[Image.Image] = None, text_content: str = None) -> Union[bool, Any]:
        if not self.gemini_api_key:
            raise ValueError("Gemini API key is required to send requests to Gemini.")
        
        self._wait_for_rate_limit()
        
        # Log detailed information about the request
        prompt_length = len(prompt)
        truncated_prompt = prompt[:6000] + "..." if prompt_length > 6000 else prompt
        
        self.logger.info(f"====== GEMINI REQUEST START ======")
        self.logger.info(f"Prompt length: {prompt_length} characters")
        self.logger.info(f"Image included: {'Yes' if image else 'No'}")
        self.logger.info(f"Text content included: {'Yes' if text_content else 'No'}")
        self.logger.info(f"Prompt preview: {truncated_prompt}")
        self.logger.info(f"====== GEMINI REQUEST END ======")
        
        # Get the model ID from the database
        model_id = self._get_model_id()
        genai.configure(api_key=self.gemini_api_key)
        model = genai.GenerativeModel(model_id)
        response = None
        max_retries = 5
        base_delay = 2  # Start with 2 seconds delay
        request_start_time = time.time()
        
        for attempt in range(max_retries):
            try:
                # Wait for rate limit before each attempt
                if attempt > 0:
                    self._wait_for_rate_limit()
                    self.logger.info(f"Retry attempt {attempt+1}/{max_retries} for Gemini request")
                
                if image:
                    self.logger.info(f"Sending prompt to Gemini with image - attempt {attempt+1}")
                    response = model.generate_content([prompt, image])
                else:
                    self.logger.info(f"Sending prompt to Gemini - attempt {attempt+1}")
                    response = model.generate_content(prompt)
                # Get the response text and calculate response time
                request_end_time = time.time()
                response_time = request_end_time - request_start_time
                response_text = response.text.strip()
                response_length = len(response_text)
                
                self.logger.info(f"====== GEMINI RESPONSE START ======")
                self.logger.info(f"Response time: {response_time:.2f} seconds")
                self.logger.info(f"Response length: {response_length} characters")
                self.logger.info(f"Raw response text (first 1000 chars):\n{response_text[:1000]}")
                if len(response_text) > 1000:
                    self.logger.info(f"... and {len(response_text) - 1000} more characters")
                self.logger.info(f"====== GEMINI RESPONSE END ======")
                
                # Save screenshot, prompt, and response to page_sources folder
                self._save_to_page_sources(image=image, prompt=prompt, response=response_text)

                # Try to parse as JSON
                self.logger.info("====== JSON PARSING START ======")
                try:
                    self.logger.info("Attempt 1: Direct JSON parsing of full response")
                    parsed_response = json.loads(response_text)
                    self.logger.info("✓ Successfully parsed full response as JSON")
                    self.logger.info(f"Parsed structure: {json.dumps(parsed_response, indent=2)[:500]}..." if len(json.dumps(parsed_response)) > 500 else json.dumps(parsed_response, indent=2))
                    self.logger.info("====== JSON PARSING END ======")
                    return parsed_response
                except json.JSONDecodeError as e:
                    self.logger.info(f"✗ Direct JSON parsing failed: {str(e)}")
                    
                    # If JSON parsing fails, check if it's in a code block with json tag
                    if "```json" in response_text:
                        self.logger.info("Attempt 2: Parsing JSON from ```json code block")
                        try:
                            json_content = response_text.split("```json")[1].split("```")[0].strip()
                            self.logger.info(f"Extracted JSON code block length: {len(json_content)} characters")
                            parsed_response = json.loads(json_content)
                            self.logger.info("✓ Successfully parsed JSON from code block")
                            self.logger.info(f"Parsed structure: {json.dumps(parsed_response, indent=2)[:500]}..." if len(json.dumps(parsed_response)) > 500 else json.dumps(parsed_response, indent=2))
                            self.logger.info("====== JSON PARSING END ======")
                            return parsed_response
                        except json.JSONDecodeError as e:
                            self.logger.error(f"✗ Failed to parse JSON from ```json code block: {str(e)}")
                            self.logger.info(f"Problem content: {json_content[:200]}..." if len(json_content) > 200 else json_content)
                    
                    # Try extracting from any code block
                    elif "```" in response_text:
                        self.logger.info("Attempt 3: Parsing JSON from generic ``` code block")
                        try:
                            json_content = response_text.split("```")[1].strip()
                            self.logger.info(f"Extracted generic code block length: {len(json_content)} characters")
                            parsed_response = json.loads(json_content)
                            self.logger.info("✓ Successfully parsed JSON from generic code block")
                            self.logger.info(f"Parsed structure: {json.dumps(parsed_response, indent=2)[:500]}..." if len(json.dumps(parsed_response)) > 500 else json.dumps(parsed_response, indent=2))
                            self.logger.info("====== JSON PARSING END ======")
                            return parsed_response
                        except json.JSONDecodeError as e:
                            self.logger.error(f"✗ Failed to parse JSON from generic code block: {str(e)}")
                            self.logger.info(f"Problem content: {json_content[:200]}..." if len(json_content) > 200 else json_content)
                    
                    # Try to find JSON object within text using regex as a last resort
                    self.logger.info("Attempt 4: Searching for JSON-like patterns in response")
                    import re
                    json_pattern = r'\{[^\{\}]*\{[^\{\}]*\}[^\{\}]*\}'
                    potential_jsons = re.findall(json_pattern, response_text)
                    
                    if potential_jsons:
                        self.logger.info(f"Found {len(potential_jsons)} potential JSON objects")
                        for i, potential_json in enumerate(potential_jsons):
                            try:
                                parsed_response = json.loads(potential_json)
                                self.logger.info(f"✓ Successfully parsed JSON from pattern match #{i+1}")
                                self.logger.info(f"Parsed structure: {json.dumps(parsed_response, indent=2)[:500]}..." if len(json.dumps(parsed_response)) > 500 else json.dumps(parsed_response, indent=2))
                                self.logger.info("====== JSON PARSING END ======")
                                return parsed_response
                            except json.JSONDecodeError:
                                self.logger.info(f"✗ Failed to parse potential JSON #{i+1}")
                                continue
                    
                    self.logger.error("✗ All JSON parsing attempts failed")
                    self.logger.error(f"Raw response that failed parsing (first 300 chars): {response_text[:300]}")
                    self.logger.info("====== JSON PARSING END ======")
                    raise ValueError('Cannot parse the response - all parsing attempts failed')
                break
            except google.api_core.exceptions.InternalServerError as e:
                self.logger.warning(f"Internal server error (attempt {attempt + 1}/{max_retries}): {e}")
                if attempt < max_retries - 1:
                    time.sleep(base_delay)
            except google.api_core.exceptions.DeadlineExceeded as e:
                self.logger.warning(f"Deadline exceeded (attempt {attempt + 1}/{max_retries}): {e}")
                if attempt < max_retries - 1:
                    time.sleep(base_delay)
            except google.api_core.exceptions.ResourceExhausted as e:
                # For rate limit errors, always wait for the rate limiter
                self.logger.warning(f"Rate limit hit (attempt {attempt + 1}/{max_retries})")
                if attempt < max_retries - 1:
                    # Use exponential backoff in addition to rate limiting
                    delay = base_delay * (10 ** attempt)  # Exponential backoff
                    self.logger.warning(f"Additional backoff: {delay} seconds")
                    self.logger.error(e)
                    time.sleep(delay)
            except Exception as e:
                self.logger.error(f"Unexpected error: {str(e)}")
                raise
        
        if not response:
            raise ValueError("No response received from Gemini API after retries")
        
        return response.text.strip()  # Return raw text if we couldn't parse JSON

    def send_message_to_claude(self, prompt: str, image: Union[Image.Image, None] = None):
        """Send a message to Claude API."""
        if not self.claude_api_key:
            raise ValueError("API key is required")

        if not self.claude_api_key.startswith('sk-'):
            raise ValueError(f"Invalid API key format. Key should start with 'sk-'")

        headers = {
            "x-api-key": self.claude_api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }

        # Check image size and compress if necessary
        max_size = (1600, 1600)  # Maximum dimensions
        if image and (image.size[0] > max_size[0] or image.size[1] > max_size[1]):
            image.thumbnail(max_size, Image.Resampling.LANCZOS)

        # Convert to RGB if necessary (removing alpha channel)
        if image and image.mode in ('RGBA', 'LA'):
            background = Image.new('RGB', image.size, (255, 255, 255))
            background.paste(image, mask=image.split()[-1])
            image = background

        # Convert Image to base64 with compression
        if image:
            buffered = BytesIO()
            image.save(buffered, format='JPEG', quality=85, optimize=True)
            base64_image = base64.b64encode(buffered.getvalue()).decode('utf-8')

        media_type = "image/jpeg"
        content = [
            {
                "type": "text",
                "text": prompt
            },
        ]
        if base64_image:
            content.append({
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": media_type,
                    "data": base64_image
                }
            })

        payload = {
            "model": "claude-3-opus-20240229",
            "max_tokens": 4096,
            "messages": [
                {
                    "role": "user",
                    "content": content
                }
            ]
        }

        try:
            response = requests.post(
                "https://api.anthropic.com/v1/messages",
                headers=headers,
                json=payload,
                timeout=180
            )

            if response.status_code != 200:
                error_msg = f"API Error (Status {response.status_code}): {response.text}"
                self.logger.error(error_msg)
                return {"error": error_msg}

            response_data = response.json()
            if "content" in response_data:
                return response_data
            else:
                return {"error": "Unexpected response format from Claude API"}

        except requests.Timeout:
            error_msg = "Request timed out. Please try again."
            self.logger.error(error_msg)
            return {"error": error_msg}
        except Exception as e:
            error_msg = f"Error making request: {str(e)}"
            self.logger.error(error_msg)
            if hasattr(e, 'response') and hasattr(e.response, 'text'):
                print(f"Error details: {e.response.text}")
            return {"error": error_msg}

    def send_request_to_deepseek(self, prompt: str, image: Union[Image.Image, None] = None, text_content: str = None) -> Union[bool, Any]:
        """
        Send a request to Deepseek R1 API.
        
        Args:
            prompt (str): The prompt to send to Deepseek
            image (Image.Image, optional): PIL Image to analyze
            text_content (str, optional): Additional text content
        
        Returns:
            Union[bool, Any]: Response from the API
        """
        if not self.deepseek_api_key:
            raise ValueError("Deepseek API key is required")

        headers = {
            "Authorization": f"Bearer {self.deepseek_api_key}",
            "Content-Type": "application/json"
        }

        messages = [{"role": "user", "content": prompt}]

        # Handle image if provided
        if image:
            # Convert image to base64
            buffered = BytesIO()
            image.save(buffered, format="PNG")
            img_str = base64.b64encode(buffered.getvalue()).decode()
            
            # Add image content to messages
            messages[0]["content"] = [
                {
                    "type": "text",
                    "text": prompt
                },
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/png;base64,{img_str}"
                    }
                }
            ]

        payload = {
            "model": "deepseek-coder-33b-instruct",
            "messages": messages,
            "temperature": 0.7,
            "max_tokens": 2048
        }

        try:
            response = requests.post(
                "https://api.deepseek.com/v1/chat/completions",
                headers=headers,
                json=payload
            )
            response.raise_for_status()
            response_data = response.json()
            
            try:
                valid_json = response_data['choices'][0]['message']['content'].replace("`", "").replace("json", "").strip()
                response_json = json.loads(valid_json)
                # Ensure we return a list of test cases
                if isinstance(response_json, dict) and 'children' in response_json:
                    return response_json['children']
                elif isinstance(response_json, list):
                    return response_json
                else:
                    raise ValueError('Response does not contain a valid test case structure')
            except ValueError as e:
                self.logger.error(f"JSON parsing error: {str(e)}")
                self.logger.error(f"Raw response: {response_data}")
                raise ValueError('Cannot parse the response')
        except requests.RequestException as e:
            error_msg = f"Error sending request to Deepseek: {str(e)}"
            self.logger.error(error_msg)
            if hasattr(e, 'response') and hasattr(e.response, 'text'):
                self.logger.error(f"Error details: {e.response.text}")
            raise RuntimeError(error_msg)
