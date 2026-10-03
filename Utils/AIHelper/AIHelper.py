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
import re

from auroqa.Utils.System import System
from auroqa.Services.AIRequestLogger import AIRequestLogger


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
        self.request_logger = AIRequestLogger()
        self.logger.info(f"Initialized AIHelper with provider: {self.provider}")
        # Don't store DB connection - get it when needed to avoid pool exhaustion

    def _setup_logger(self):
        logger = logging.getLogger('AIHelper')
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
           """
        text_prompt = (
            f"Act as QA engineer. Analyze attached schema export file and generate as much as possible test cases for this API.\n"
            f"The response must be a valid JSON array following this exact structure, with NO additional text or explanation:\n"
            f"{json_structure}\n\n"
            f"Here is the schema file to analyze: {text_content}"
        )
        return text_prompt

    @staticmethod
    def clean_html_for_prompt(html_code: str) -> str:
        """
        Strip markup that carries no information for locator generation, to cut prompt tokens.
        Removes scripts, style blocks, comments, <link>/<meta>, SVG internals and data: URIs.
        Inline style attributes are dropped, except that hidden elements stay marked as hidden.
        Tags, ids, classes, names and text are left intact.
        """
        if not html_code:
            return html_code

        def _reduce_style(match):
            value = match.group(2).lower().replace(' ', '')
            hidden = [rule for rule in ('display:none', 'visibility:hidden') if rule in value]
            return f' style="{";".join(hidden)}"' if hidden else ''

        cleaned = re.sub(r'<script\b.*?</script>', '', html_code, flags=re.S | re.I)
        cleaned = re.sub(r'<style\b.*?</style>', '', cleaned, flags=re.S | re.I)
        cleaned = re.sub(r'<!--.*?-->', '', cleaned, flags=re.S)
        cleaned = re.sub(r'<(?:link|meta)\b[^>]*>', '', cleaned, flags=re.I)
        cleaned = re.sub(r'(<svg\b[^>]*>).*?(</svg>)', r'\1\2', cleaned, flags=re.S | re.I)
        cleaned = re.sub(r'\sstyle\s*=\s*(["\'])(.*?)\1', _reduce_style, cleaned, flags=re.S | re.I)
        cleaned = re.sub(r'data:[\w/+.-]+;base64,[A-Za-z0-9+/=]+', 'data:...', cleaned)
        cleaned = re.sub(r'[ \t]+', ' ', cleaned)
        cleaned = re.sub(r'\n\s*\n+', '\n', cleaned)
        return cleaned

    def get_analyze_html_prompt(self, html_code: str, test_name: str, test_description: str, step_order: int, next_prompt: str, prev_step_description: str, attached_screenshot: str = None, variable_registry: dict = None) -> str:
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
        
        # Build variable registry section
        variable_context = ""
        if variable_registry and len(variable_registry) > 0:
            variable_context = "\n\n🔵 VARIABLES CREATED IN PREVIOUS STEPS - REUSE THESE WHEN NEEDED:\n"
            variable_context += "=" * 80 + "\n"
            
            for var_name, var_info in variable_registry.items():
                step_num = var_info['first_use_step']
                placeholder = var_info['placeholder']
                purpose = var_info['purpose']
                usage_count = var_info['usage_count']
                
                variable_context += f"\n📌 Variable: {placeholder}\n"
                variable_context += f"   - First created in: Step {step_num}\n"
                variable_context += f"   - Created for: {purpose}\n"
                variable_context += f"   - Used {usage_count} time(s) so far\n"
                
                # Detect variable type and provide usage hints
                var_lower = var_name.lower()
                if 'email' in var_lower:
                    variable_context += f"   ⚠️ TYPE: Email - If this step needs an email (login, verify, etc.), use {placeholder}\n"
                elif 'password' in var_lower:
                    variable_context += f"   ⚠️ TYPE: Password - If this step needs password (login, confirm, etc.), use {placeholder}\n"
                elif 'var:' in var_name:
                    # Named variable - extract the meaningful part
                    clean_name = var_name.replace('var:', '')
                    variable_context += f"   ⚠️ NAMED VARIABLE: {clean_name} - Reuse this for related actions\n"
                elif 'unique_name:' in var_name:
                    variable_context += f"   ⚠️ TYPE: Unique identifier - Use for finding/selecting the created item\n"
                
            variable_context += "\n" + "=" * 80 + "\n"
            variable_context += "⚠️ CRITICAL RULES FOR VARIABLE REUSE:\n"
            variable_context += "1. If this step uses data CREATED in a previous step, use the EXACT SAME variable\n"
            variable_context += "2. Example: Step 8 created user with %var:admin_email%, Step 16 logs in → MUST use %var:admin_email%\n"
            variable_context += "3. DO NOT create new variables (like %random_email%) if one already exists above\n"
            variable_context += "4. Using a different variable will cause TEST FAILURE - values won't match!\n"
            variable_context += "=" * 80 + "\n"
        
        # Detect authentication state from step history
        auth_state_context = ""
        if test_case_id is not None:
            history = self.get_step_history(test_case_id)
            if history:
                # Track login/logout actions
                last_login_step = -1
                last_logout_step = -1
                login_user = None
                
                for idx, step in enumerate(history):
                    purpose = step.get('element_purpose', '').lower()
                    action = step.get('action', '').lower()
                    value = step.get('value', '')
                    
                    # Detect login actions
                    if 'login' in purpose or 'submit' in purpose:
                        # Check if this is part of login flow (password or login button)
                        if action == 'click' or (action == 'type' and 'password' in purpose):
                            last_login_step = idx
                            # Detect which user is logging in
                            if '%login%' in value or 'admin' in purpose.lower():
                                login_user = "admin"
                            elif 'var:' in value or 'new' in purpose.lower():
                                login_user = "newly created user"
                    
                    # Detect logout actions
                    if 'logout' in purpose or 'sign out' in purpose:
                        last_logout_step = idx
                        login_user = None
                
                # Determine current authentication state
                if last_login_step > last_logout_step:
                    auth_state_context = f"\n\n🟢 AUTHENTICATION STATE:\n"
                    auth_state_context += "=" * 80 + "\n"
                    auth_state_context += f"✅ USER IS CURRENTLY LOGGED IN (step {last_login_step})\n"
                    if login_user:
                        auth_state_context += f"   Logged in as: {login_user}\n"
                    auth_state_context += "\n⚠️ CRITICAL: DO NOT LOGIN AGAIN unless you see a login page or authentication error!\n"
                    auth_state_context += "   - If you're already logged in, continue with the next action in the test flow\n"
                    auth_state_context += "   - Only suggest login actions if you see login form fields in the HTML\n"
                    auth_state_context += "   - Check the HTML for indicators like account menu, user name, or authenticated content\n"
                    auth_state_context += "=" * 80 + "\n"
                elif last_logout_step > last_login_step and last_logout_step >= 0:
                    auth_state_context = f"\n\n🔴 AUTHENTICATION STATE:\n"
                    auth_state_context += "=" * 80 + "\n"
                    auth_state_context += f"❌ USER IS LOGGED OUT (step {last_logout_step})\n"
                    auth_state_context += "   - If test requires authentication, you may need to login\n"
                    auth_state_context += "   - Check if the HTML shows a login form\n"
                    auth_state_context += "=" * 80 + "\n"

        prev_step_prompt = ''
        if prev_step_description != '':
            prev_step_prompt = f'. Take in account that previous step was {prev_step_description}'

        skip_start_navigate = ''
        if step_order == 0:
            skip_start_navigate = ". Skip the step with navigating to the first page.\n"

        # Calculate screenshot text
        screenshot_text = 'Also, consider the attached screenshot if available' if attached_screenshot is not None else ''

        # Enhanced prompt with stronger focus on test description and login handling
        prompt = f"""Act as an experienced QA engineer, you are creating a test case: "{test_name}".

This is the suggested test description, some steps might be missing, if you see that executing this step will not help you to complete the test, suggest next step:
{test_description}; end of the test.

You should recursively go through all test steps and on each step you should assume next step until the test will be finished.
If current step will be final step, put to the next_step attribute the word 'Stop'.
You are on the test step # {step_order}{prev_step_prompt}{skip_start_navigate}
{step_history}{variable_context}{auth_state_context}"""
        
        # Add the rest of the prompt as a regular string (no format substitution)
        prompt += """

CRITICAL - TEST COMPLETION RULE:
When the test is complete and no more steps are needed:
- Set "next_step": "Stop" (EXACTLY this word, nothing else)
- Do NOT add any explanation or description after "Stop"
- ONLY use "Stop" as the value
- The system uses this exact value to determine when to stop generating steps

IMPORTANT - When to use "Stop":
- Use "Stop" ONLY when the main test objective has been achieved and verified
- Do NOT use "Stop" for verification steps that are part of the test flow (e.g., "Wait for the dashboard page to load and verify a key element is visible" is a REQUIRED step, not a completion indicator)
- Do NOT use "Stop" just because you could describe optional future actions
- Use "Stop" only when there are genuinely no more steps needed to complete the test objective

Examples:
- ✅ CORRECT: "Stop" (when login is verified and dashboard is confirmed)
- ❌ WRONG: "Wait for dashboard to load and verify navigation menu is visible" (this is a required verification step, not completion)

🔴 CRITICAL - PLACEHOLDER SYNTAX RULE:
ALL placeholders MUST be wrapped with % on BOTH sides: %placeholder_name%
✅ CORRECT: %unique_name:P@ssword1!% | %random_email% | %timestamp_name:Client%
❌ WRONG: %unique_name:P@ssword1! | random_email% | %timestamp_name:Client
If you forget the closing %, the placeholder will NOT work and will be typed literally!

IMPORTANT GUIDELINES:
1. BEFORE SUGGESTING ELEMENT TO LOCATE, ANALYZE THE HTML CODE AND THE SCREENSHOT TO UNDERSTAND THE CONTEXT AND MAKE SURE THAT ELEMENT IS VISIBLE AND CLICKABLE AND NOT DISABLED
2. ELEMENT EXISTENCE VERIFICATION IS MANDATORY:
   - You MUST confirm that each element you suggest actually exists in the current HTML code
   - Do NOT suggest any element without verifying its existence in the provided HTML
   - Before suggesting a locator, search the HTML code for text fragments, IDs, or other attributes
   - Verify the element exists but DO NOT include verification details in element_purpose
   - Keep element_purpose clean and user-friendly (e.g., "Click the Login button to submit credentials")
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
   - Use %base_url% for the base URL
   - First locate and interact with the username/email field, using %login% as the value
   - Then locate and interact with the password field, using %password% as the value
   - Only after both fields are filled, locate and click the login/submit button
   - Don't use variables %login% and %password% in any other place except login page
   - ENSURE login is successful before proceeding with any subsequent steps
   - NEVER skip the password field even if it appears to be optional
6. SEQUENTIAL EXECUTION - All steps after login must only be executed after successful login verification

FORM COMPLETION REQUIREMENTS:
1. When filling out forms, ALWAYS complete ALL available fields before submission
2. For login forms specifically:
   - FIRST step: Locate and fill the username/email field with %login%
   - SECOND step: Locate and fill the password field with %password%
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

🔴 CRITICAL - ACTION VALIDATION:
You MUST ONLY use these valid actions. NO OTHER ACTIONS ARE ALLOWED:
- UI Actions: click, type, select, hover, wait, scroll, clear, navigate, press_key, use_component
- Assertion Actions: assert, assert_text_contains, assert_attribute
  (assert_attribute: put "attribute=expected" into "value", e.g. "aria-valuenow=0", "value=John", "checked=true", "disabled=false";
   use it when the state is not visible text: input values, checked/disabled state, progress values, href)
- Wait Actions: wait_for_element_to_be_visible, wait_for_element_visible, wait_for_modal, wait_for_clickable
- Browser Actions (no element: element_locator is "N/A"):
  switch_tab ("value": "new" for the tab that just opened, "main" for the first tab, a tab number, or a part of the title/URL),
  accept_alert (OK in a native alert/confirm/prompt; for a prompt put the text to type into "value"),
  dismiss_alert (Cancel in a native confirm/prompt),
  assert_alert_text (exact text of the native alert in "value"; the alert stays open)
  Native alerts are NOT in the HTML and block the page: handle one before any other action. These actions wait up to 10 seconds for it.
- Drag and drop: drag_and_drop (element_locator is the element to drag, "value" is the XPath of the drop target,
  e.g. "//div[@id='droppable']"; works for sortable lists and native HTML5 draggables; fails if nothing moved)
- File upload: upload_file (element_locator is the <input type="file"> itself, "value" is a sample file name:
  "sample.txt", "sample.png", "sample.pdf" or "sample.csv"; NEVER click a file input)
- API Actions: api_request, api_auth, api_get, api_post, api_put, api_delete, api_patch, response_validation, validation

❌ DO NOT use these invalid actions:
- assert_element_is_visible (WRONG - use wait_for_element_to_be_visible instead)
- assert_element_visible (WRONG - use wait_for_element_visible instead)
- verify_element (WRONG - use assert or assert_text_contains)
- check_element (WRONG - use assert or assert_text_contains)
- Any other action not in the valid list above

Your response MUST be a valid JSON object with ALL of the following required fields:
{{
    "element_locator": "XPath selector to locate the element (PRIMARY locator)",
    "css_selector": "CSS selector to locate the same element (FALLBACK locator)",
    "by_strategy": "xpath",
    "action": "click, type, select, hover, wait, assert, assert_text_contains, assert_attribute, switch_tab, accept_alert, dismiss_alert, assert_alert_text, drag_and_drop, upload_file, scroll, clear, navigate, press_key, use_component, wait_for_element_to_be_visible, wait_for_element_visible, wait_for_modal, wait_for_clickable",
    "element_purpose": "Brief description of what this step does (e.g., 'verify error message is displayed')",
    "value": "For type actions: MUST use placeholders like %login%, %random_email%, %unique_name:Prefix% (ALWAYS with % on BOTH sides)",
    "next_step": "Description of what to verify next, or 'Stop' if test is complete"
}}

⚠️ VALUE FIELD REMINDER: Always wrap placeholders with % on both sides!
Examples: %login%, %password%, %unique_name:Client%, %random_email%
NEVER: %login, password%, unique_name:Client%, %random_email

CRITICAL - DUAL LOCATOR REQUIREMENT:
- You MUST provide BOTH element_locator (XPath) AND css_selector (CSS) for the SAME element
- Both locators must target the exact same element on the page
- XPath will be tried first, CSS selector will be used as fallback if XPath fails
- Example:
  * element_locator: "//button[@id='submit-btn']"
  * css_selector: "button#submit-btn"
- Both should be equally reliable and specific

IMPORTANT REQUIREMENTS:
1. JSON Format: The response must strictly follow the valid JSON structure, including all specified fields.
2. Action Types: For any type of actions, ensure that the value field is non-empty and includes appropriate test data.
3. Environment Variables: Use %base_url%, %login%, and %password% for environment-specific values.
4. DYNAMIC DATA PLACEHOLDERS - CRITICAL FOR REALISTIC TEST DATA:
   - NEVER use hardcoded values like "Test Client", "test@test.com", "John Doe", "123-456-7890"
   - ALWAYS use dynamic placeholders that generate realistic data at runtime
   
   ⚠️ CRITICAL PLACEHOLDER SYNTAX - MUST HAVE BOTH % SIGNS:
   - ✅ CORRECT: %unique_name:P@ssword1!% (wrapped with % on BOTH sides)
   - ✅ CORRECT: %random_email% (wrapped with % on BOTH sides)
   - ✅ CORRECT: %timestamp_name:Client% (wrapped with % on BOTH sides)
   - ❌ WRONG: %unique_name:P@ssword1! (missing closing %)
   - ❌ WRONG: unique_name:Client% (missing opening %)
   - ❌ WRONG: unique_name (no % signs at all)
   
   ALL PLACEHOLDERS MUST BE WRAPPED WITH % SIGNS: %placeholder_name%
   
   A. NAMED VARIABLES (NEW - EXPLICITLY CACHED WITH CUSTOM NAMES):
     ⭐ USE THESE FOR VALUES THAT NEED TO BE REUSED LATER IN THE TEST ⭐
     * %var:user_email% - First use: generates email, subsequent uses: reuses same value
     * %var:user_password% - First use: generates password, subsequent uses: reuses same value
     * %var:admin_name% - First use: generates name, subsequent uses: reuses same value
     * %var:company_name% - First use: generates company, subsequent uses: reuses same value
     * %var:custom_value% - Generic cached variable
     
     ⚠️ WHEN TO USE %var:name%:
     - Step 8: Create user with email → value="%var:user_email%" (generates and caches)
     - Step 16: Login with that user → value="%var:user_email%" (reuses same email from step 8)
     - Step 11: Enter password → value="%var:user_password%" (generates and caches)
     - Step 12: Confirm password → value="%var:user_password%" (reuses same password)
     
     The variable name (after "var:") can be anything descriptive:
     - %var:new_user_email%, %var:admin_login%, %var:test_password%
     - System intelligently generates appropriate data based on the name
     
   B. UNIQUE IDENTIFIERS (cached per test run):
     * %unique_name% - Random unique ID (e.g., "a7b3c9d2")
     * %unique_name:Client% - With prefix (e.g., "Client_a7b3c9d2")
     * %unique_name:P@ssword1!% - With special char prefix (e.g., "P@ssword1!_a7b3c9d2")
     * %unique_name:User:Test% - With prefix and suffix (e.g., "User_a7b3c9d2_Test")
     * %timestamp_name% - Timestamp-based (e.g., "20250129_143052")
     * %timestamp_name:Group% - With prefix (e.g., "Group_20250129_143052")
   
   C. REALISTIC PERSONAL DATA (cached per test run):
     ⚠️ ALL THESE ARE NOW CACHED - First use generates, subsequent uses retrieve!
     * %random_name% - Full name (e.g., "John Smith") - CACHED
     * %random_first_name% - First name (e.g., "John") - CACHED
     * %random_last_name% - Last name (e.g., "Smith") - CACHED
     * %random_email% - Email (e.g., "john.smith@example.com") - CACHED
     * %random_username% - Username (e.g., "john_smith_123") - CACHED
     * %random_phone% - Phone number (e.g., "+1-555-234-5678") - CACHED
   
   D. REALISTIC LOCATION DATA (cached per test run):
     * %random_address% - Street address (e.g., "742 Evergreen Terrace") - CACHED
     * %random_city% - City name (e.g., "Springfield") - CACHED
     * %random_country% - Country name (e.g., "United States") - CACHED
   
   E. REALISTIC BUSINESS DATA (cached per test run):
     * %random_company% - Company name (e.g., "Acme Corporation") - CACHED
     * %random_job_title% - Job title (e.g., "Software Engineer") - CACHED
   
   F. TECHNICAL DATA (cached per test run):
     * %random_string% - Alphanumeric string (default 10 chars) - CACHED
     * %random_string:5% - Custom length string - CACHED
     * %random_number% - Number 1-10000 - CACHED
     * %random_number:1:100% - Custom range number - CACHED
     * %random_url% - URL (e.g., "https://www.example.com") - CACHED
     * %random_ip% - IP address (e.g., "192.168.1.42") - CACHED
     * %random_uuid% - Full UUID - CACHED
     * %random_color% - Color name (e.g., "blue") - CACHED
     * %random_date% - Date YYYY-MM-DD - CACHED
     * %random_boolean% - true/false - CACHED
     * %random_text% - Paragraph of text - CACHED
     * %random_text:5% - Custom sentences count - CACHED
   
   USAGE EXAMPLES:
     ❌ WRONG: {{"name": "Test Client", "email": "test@test.com", "phone": "123-456-7890"}}
     ✅ CORRECT: {{"name": "%random_company%", "email": "%random_email%", "phone": "%random_phone%"}}
     
     ❌ WRONG: value="John Doe" (for name field)
     ✅ CORRECT: value="%random_name%" (generates "Michael Johnson")
     
     ❌ WRONG: value="New York" (for city field)
     ✅ CORRECT: value="%random_city%" (generates "Los Angeles")
     
     ❌ WRONG: value="%unique_name:Password123" (missing closing %)
     ✅ CORRECT: value="%unique_name:Password123%" (generates "Password123_a7b3c9d2")
     
     ❌ WRONG: value="%random_email" (missing closing %)
     ✅ CORRECT: value="%random_email%" (generates "john.smith@example.com")
     
   ⚠️ REMEMBER: EVERY placeholder MUST start AND end with % sign!
     
   CRITICAL - VARIABLE REUSE SCENARIOS:
     
     Example 1: Creating and logging in as a user
     ❌ WRONG:
       Step 8:  Enter email → value="%random_email%" (generates "john@example.com")
       Step 16: Enter email → value="%random_email%" (generates NEW "mary@example.com" - DIFFERENT!)
     
     ✅ CORRECT Option A (using %var:name%):
       Step 8:  Enter email → value="%var:user_email%" (generates "john@example.com" and caches as "user_email")
       Step 16: Enter email → value="%var:user_email%" (retrieves "john@example.com" - SAME!)
     
     ✅ CORRECT Option B (using %random_email% with caching):
       Step 8:  Enter email → value="%random_email%" (generates "john@example.com" and caches)
       Step 16: Enter email → value="%random_email%" (retrieves "john@example.com" - SAME!)
     
     Example 2: Password confirmation fields
     ❌ WRONG:
       Step 11: Enter password → value="%unique_name:P@ssword1!%" (generates "P@ssword1!_abc123")
       Step 12: Confirm password → value="%unique_name:P@ssword1!%" (generates NEW "P@ssword1!_xyz789" - FAILS!)
     
     ✅ CORRECT:
       Step 11: Enter password → value="%unique_name:P@ssword1!%" (generates "P@ssword1!_abc123" and caches)
       Step 12: Confirm password → value="%unique_name:P@ssword1!%" (retrieves "P@ssword1!_abc123" - SAME!)
     
     Example 3: Using %var:name% for explicit control
     ✅ BEST PRACTICE:
       Step 5:  Enter new user email → value="%var:new_user_email%" (generates and caches)
       Step 10: Verify email in list → text contains "%var:new_user_email%" (reuses)
       Step 15: Login with new user → value="%var:new_user_email%" (reuses)
     
   WHEN TO USE EACH TYPE:
     - Use %var:custom_name% when you want EXPLICIT control and clear variable naming
     - Use %unique_name:Type% for entity names that need consistency (Client_xyz)
     - Use %random_*% for realistic data - NOW AUTOMATICALLY CACHED per test run!
     - Both %var:user_email% and %random_email% work, but %var:% is more explicit
     - Use %random_email% instead of "%unique_name%@test.com" for valid email format
     - Use %random_company% instead of "%unique_name:Company%" for realistic business names
   
   ⚠️ CRITICAL - NEVER HARDCODE DYNAMIC VALUES IN XPATH/CSS SELECTORS:
   - When creating an item with a dynamic name (e.g., %unique_name:Group%), DO NOT hardcode the generated value in subsequent selectors
   - ❌ WRONG: Step 1 uses "%unique_name:Group%", Step 2 uses "//tr[td/a[text()='Group_a7b3c9d2']]" (hardcoded!)
   - ✅ BEST: Reuse the SAME variable in the selector:
     * Step 1: value="%unique_name:Group%" creates the group
     * Step 2: element_locator="//tr[td/a[text()='%unique_name:Group%']]//a[@title='Delete']"
     * At runtime, both get replaced with the same value (e.g., "Group_a7b3c9d2")
     * This ensures you're always targeting the item you just created
   - ⚠️ AVOID position-based selectors if table can be sorted or filtered:
     * "//tr[1]" gets first row - but what if table is sorted by name desc?
     * "//tr[last()]" gets last row - but what if there's pagination?
   - Only use position-based when you're certain of the order:
     * Use contains() for partial match: "//tr[td/a[contains(text(), 'Group_')]]//a[@title='Delete']"
     * Use data attributes if available: "//tr[@data-id='...']/a[@title='Delete']"
   - Dynamic names change on every test run, so hardcoding them breaks test repeatability

5. by_strategy: The value of by_strategy must be either 'css' or 'xpath'—no other values are allowed.
6. Field Validation: If typing an invalid email or another value does not trigger validation, ensure the form is submitted to force validation.
7. Test Progression: Ensure that each test step advances forward. Avoid repeating any steps. Each step must represent a unique action.
8. No Explanations: Do not include any explanation text. Only the required JSON object should be output.
9. Assertion: If applicable, specify an assertion to validate expected behavior.
10. Login Verification: After login steps, include a verification step to confirm successful login before proceeding.
11. Password Field Handling: When dealing with login forms, ALWAYS include a separate step for entering the password in the password field before clicking the login button. This is mandatory even if the form appears to function without it.
12. Hidden Menus: NEVER try to click on hidden submenu items directly. Always expand parent menus first before interacting with their child elements.
13. FOLLOW THE EXACT NEXT STEP: If the next_prompt specifies an action like "Click the 'Recipients' link", make sure to perform exactly that action, not skip ahead to subsequent steps.
14. STRICT SEQUENCE ADHERENCE: You MUST follow the exact sequence of steps. If the next_prompt is "Click the 'New group' button", you MUST create a step that clicks that button, even if you can see form fields that will need to be filled afterward.
15. NEVER ASSUME COMPLETION: Never assume a step has already been completed. If the next_prompt indicates an action, that action must be performed as the current step.
16. ONE ACTION PER STEP: Each step should perform exactly one action (click, type, etc.). Do not combine multiple actions into a single step.
17. ELEMENT EXISTENCE VERIFICATION: Your element_locator MUST be for an element that actually exists in the provided HTML.
   - Before providing a locator, verify that it exists in the HTML code by searching for unique text or attributes
   - Keep element_purpose clean and user-friendly - do NOT include HTML markup or verification details
   - If you cannot verify the element exists, do not proceed - suggest a "wait" action instead
18. FOCUS ON THE MAIN FLOW: Only include steps that are specifically described in the test description.
   - Do NOT add unnecessary steps like field validation that aren't part of the test description
   - Stay focused on completing the core workflow as described in the test case
   - Avoid adding "nice to have" assertions or verifications that aren't explicitly required
   - Follow the minimal path to complete the described test scenario
19. NOTIFICATION/TOAST MESSAGE ASSERTIONS - TIMING IS CRITICAL:
   - Notification messages (success, error, info) often appear briefly and then fade away
   - ❌ WRONG: Click delete → Immediately assert "Successfully deleted!" (notification already gone!)
   - ✅ CORRECT: Click delete → Wait 1 second → Assert "Successfully deleted!" (catch notification while visible)
   - Use time.sleep(1) or wait_for_clickable BEFORE assert_text_contains for notifications
   - If notification is already gone when assertion runs, you'll get empty text ('')
   - Common notification selectors: div[@id='notify'], div[contains(@class, 'alert')], div[contains(@class, 'toast')]
"""
        
        # Add screenshot text and HTML code
        prompt += f"""
{screenshot_text}
HTML Code:
{self.clean_html_for_prompt(html_code)}
"""
        
        return prompt

    def get_error_analysis_prompt(self, html_code: str, error_message: str, test_name: str, test_description: str, 
                                 step_history: list, failed_step: dict, previous_attempts: list = None, 
                                 screenshot_path: str = None, browser_state: str = None) -> str:
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
{self.clean_html_for_prompt(html_code)}

{'SCREENSHOT OF FAILURE STATE: A screenshot of the page at the time of failure is attached.' if screenshot_path else ''}

{('BROWSER STATE (not visible in the HTML above):' + chr(10) + browser_state) if browser_state else ''}

Your response MUST be a valid JSON object with ALL of the following required fields:
{{
    "analysis": "Brief analysis of why the step failed",
    "element_locator": "Corrected XPath selector that should work (PRIMARY locator)",
    "css_selector": "Corrected CSS selector for the same element (FALLBACK locator)",
    "by_strategy": "xpath",
    "action": "Same or corrected action (click, type, etc.)",
    "element_purpose": "Description of what this step does",
    "value": "Same or corrected value if applicable",
    "next_step": "Description of what to do next"
}}

CRITICAL - DUAL LOCATOR REQUIREMENT:
- You MUST provide BOTH element_locator (XPath) AND css_selector (CSS) for the SAME element
- Both locators must target the exact same element on the page
- System will try XPath first, then CSS as fallback if XPath fails

IMPORTANT:
1. Focus on fixing the CURRENT step, not skipping ahead
2. If the element truly doesn't exist, suggest an alternative approach
3. Consider if a parent menu needs to be expanded first
4. For hidden elements, consider using hover actions or JavaScript execution
4a. If a text assertion fails because the element text is empty or not visible, but the state is present in an attribute (aria-valuenow, value, checked, disabled, href), use action "assert_attribute" with "value" set to "attribute=expected" (e.g. "aria-valuenow=0")
4b. If the error says "unexpected alert open" or BROWSER STATE reports an open native alert, the page is blocked: use "accept_alert", "dismiss_alert" or "assert_alert_text" (element_locator "N/A"), not a click
4c. If the element is not found because it is in another browser tab, use "switch_tab" (element_locator "N/A") with "value" "new", "main", a tab number or a part of the tab title/URL
4d. If "drag_and_drop" fails with "had no effect", the drop target is wrong: put the XPath of the real drop zone (or of the list item to drop onto) into "value". Mouse drag and HTML5 emulation are both tried automatically; the optional "html5:" value prefix only changes their order
4e. If a click on a file input or an "upload" button fails or does nothing, use "upload_file" on the <input type="file"> itself with "value" set to a sample file name ("sample.txt", "sample.png", "sample.pdf", "sample.csv")
5. If timing is the issue, suggest adding a wait step
6. ⚠️ FOR TRANSIENT NOTIFICATIONS/TOASTS (appear briefly then disappear):
   - AVOID waiting for notification elements as they disappear quickly
   - INSTEAD: Verify the ACTION RESULT by checking:
     * Page URL changed (e.g., redirect after save)
     * New item appears in list/table
     * Form was cleared/reset
     * Success indicator/badge changed state
     * Page title or heading changed
   - Example: Instead of "wait for 'Client saved' notification"
     → "Wait for URL to change to /admin/client/[id]" or
     → "Wait for new client to appear in clients list" or
     → "Wait for form to be cleared"
   - This approach is more reliable than waiting for transient UI elements
7. Ensure your solution follows the logical flow of the application
8. DO NOT suggest solutions that have already been tried in the previous attempts

⚠️ CRITICAL - NEVER HARDCODE DYNAMIC VALUES IN CORRECTED SELECTORS:
- If the failed step was trying to locate a dynamically created item (with %unique_name%, %timestamp_name%, etc.)
- DO NOT hardcode the generated value in the corrected XPath/CSS selector
- ❌ WRONG: "//tr[td/a[text()='Group_a7b3c9d2']]//a[@title='Delete']" (hardcoded!)
- ✅ BEST: Reuse the SAME variable in the corrected selector:
  * If creation step used "%unique_name:Group%"
  * Corrected selector: "//tr[td/a[text()='%unique_name:Group%']]//a[@title='Delete']"
  * At runtime, both get replaced with the same value
  * This ensures you're targeting the exact item that was created
- ⚠️ AVOID position-based selectors for sorted/paginated tables:
  * "//tr[1]" might not be the newly created item if table is sorted
  * "//tr[last()]" fails if there's pagination
- Only use position-based when order is guaranteed, otherwise use the variable reference
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
        
        # Find the highest existing file number, whatever the extension
        pattern = os.path.join(page_sources_dir, f"{prefix}_*.*")
        existing_files = glob.glob(pattern)
        
        max_number = 0
        for file in existing_files:
            try:
                # Extract the number from the filename
                filename = os.path.splitext(os.path.basename(file))[0]
                number_part = filename.replace(f"{prefix}_", "")
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
        
        # Get the next available file number: one number for the screenshot, prompt and response of a request
        file_number = max(self._get_next_file_number(prefix) for prefix in ('screenshot', 'text_input', 'text_output'))
        
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
            
            # Get a connection from the pool (and return it immediately after use)
            try:
                conn = System.get_db_connection()
            except Exception as e:
                self.logger.warning(f"Failed to get database connection: {e}, using default model ID")
                return default_model_id
            
            try:
                with conn.cursor() as cur:
                    # Query the database for the active default model (get the integer ID, not model_id)
                    cur.execute("""
                        SELECT id FROM ai_models 
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
            finally:
                # CRITICAL: Always return connection to pool
                System.return_connection(conn)
                    
        except Exception as e:
            self.logger.error(f"Error retrieving model ID from database: {str(e)}")
            self.logger.warning(f"Using default model ID: gemini-2.5-pro-preview-06-05")
            return "gemini-2.5-pro-preview-06-05"

    def _get_model_id_and_name(self, model_name: Optional[str] = None) -> tuple:
        """
        Get both the integer model ID and the model name from the database.

        Args:
            model_name: model chosen for this request (ai_models.model_id). When it is
                not given, or is not an active model, the default model is used.
        """
        try:
            # Default values in case database query fails
            default_model_id = 1
            default_model_name = "gemini-2.5-pro-preview-06-05"
            
            # If provider is not gemini, return the default values
            if self.provider != 'gemini':
                self.logger.info(f"Provider is not Gemini, using default model")
                return (default_model_id, default_model_name)
            
            # Get a connection from the pool (and return it immediately after use)
            try:
                conn = System.get_db_connection()
            except Exception as e:
                self.logger.warning(f"Failed to get database connection: {e}, using default model")
                return (default_model_id, default_model_name)
            
            try:
                with conn.cursor() as cur:
                    # Prefer the model chosen for this request
                    if model_name:
                        cur.execute("""
                            SELECT id, model_id FROM ai_models
                            WHERE is_active = TRUE AND model_id = %s
                            LIMIT 1
                        """, (model_name,))
                        result = cur.fetchone()
                        if result and result[0] and result[1]:
                            self.logger.info(f"Using selected model ID {result[0]} with name {result[1]}")
                            return (result[0], result[1])
                        self.logger.warning(f"Selected model '{model_name}' is not an active model, falling back to the default")

                    # Query the database for the active default model (get both id and model_id)
                    cur.execute("""
                        SELECT id, model_id FROM ai_models 
                        WHERE is_active = TRUE AND is_default = TRUE
                        LIMIT 1
                    """)
                    
                    result = cur.fetchone()
                    
                    if result and result[0] and result[1]:
                        model_id = result[0]
                        model_name = result[1]
                        self.logger.info(f"Using model ID {model_id} with name {model_name} from database")
                        return (model_id, model_name)
                    else:
                        self.logger.warning(f"No default active model found in database, using defaults")
                        return (default_model_id, default_model_name)
            finally:
                # CRITICAL: Always return connection to pool
                System.return_connection(conn)
                    
        except Exception as e:
            self.logger.error(f"Error retrieving model from database: {str(e)}")
            self.logger.warning(f"Using default model")
            return (default_model_id, default_model_name)

    def _process_image_for_gemini(self, image: Image.Image) -> Image.Image:
        """
        Process image for Gemini: resize if too large to prevent timeouts.
        """
        if not image:
            return None
            
        max_dimension = 1536  # Reasonable limit for VLM
        
        if image.width > max_dimension or image.height > max_dimension:
            ratio = min(max_dimension / image.width, max_dimension / image.height)
            new_size = (int(image.width * ratio), int(image.height * ratio))
            self.logger.info(f"Resizing image for Gemini from {image.size} to {new_size}")
            return image.resize(new_size, Image.Resampling.LANCZOS)
            
        return image

    def send_request_to_gemini(
        self, 
        prompt: str, 
        image: Optional[Image.Image] = None, 
        text_content: str = None,
        request_type: str = 'other',
        request_context: Optional[str] = None,
        client_id: Optional[int] = None,
        user_id: Optional[int] = None,
        generation_job_id: Optional[str] = None,
        model_name: Optional[str] = None
    ) -> Union[bool, Any]:
        if not self.gemini_api_key:
            raise ValueError("Gemini API key is required to send requests to Gemini.")
        
        self._wait_for_rate_limit()
        
        # Log detailed information about the request
        prompt_length = len(prompt)
        truncated_prompt = prompt[:6000] + "..." if prompt_length > 6000 else prompt
        
        # Get the model ID and name from the database
        # model_name is passed per request, not stored on the instance: the analyzer is a
        # singleton shared by concurrent generations
        model_id, model_name = self._get_model_id_and_name(model_name)
        genai.configure(api_key=self.gemini_api_key)
        model = genai.GenerativeModel(model_name)
        response = None
        max_retries = 3  # Reduced from 5 to fail faster
        base_delay = 2  # Start with 2 seconds delay
        request_start_time = time.time()
        
        # Process image if present
        processed_image = None
        if image:
            processed_image = self._process_image_for_gemini(image)
        
        for attempt in range(max_retries):
            try:
                # Wait for rate limit before each attempt
                if attempt > 0:
                    self._wait_for_rate_limit()
                    self.logger.info(f"Retry attempt {attempt+1}/{max_retries} for Gemini request")
                
                # Configure request options with timeout
                # 120s timeout for normal requests, 180s for image requests
                # This is much shorter than default 600s to fail fast and retry
                timeout = 180 if processed_image else 120
                
                if processed_image:
                    self.logger.info(f"Sending prompt to Gemini with image - attempt {attempt+1}")
                    response = model.generate_content([prompt, processed_image], request_options={'timeout': timeout})
                else:
                    self.logger.info(f"Sending prompt to Gemini without image - attempt {attempt+1}")
                    response = model.generate_content(prompt, request_options={'timeout': timeout})
                
                # Get the response text and calculate response time
                request_end_time = time.time()
                response_time = request_end_time - request_start_time
                
                # Check if response was blocked by safety filters
                if not response.candidates or not response.candidates[0].content.parts:
                    safety_ratings = response.candidates[0].safety_ratings if response.candidates else []
                    safety_info = []
                    for rating in safety_ratings:
                        if rating.probability.name != "NEGLIGIBLE":
                            safety_info.append(f"{rating.category.name}: {rating.probability.name}")
                    
                    error_msg = f"Response blocked by Gemini safety filters. Safety ratings: {', '.join(safety_info) if safety_info else 'Unknown safety issue'}"
                    self.logger.error(error_msg)
                    self.logger.error("Test generation stopped due to blocked AI response")
                    raise ValueError(error_msg)
                
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
                self._save_to_page_sources(image=processed_image, prompt=prompt, response=response_text)

                # Extract token counts for logging
                token_counts = self._extract_token_counts(response)
                
                # Try to parse as JSON
                self.logger.info("====== JSON PARSING START ======")
                try:
                    self.logger.info("Attempt 1: Direct JSON parsing of full response")
                    parsed_response = json.loads(response_text)
                    self.logger.info("✓ Successfully parsed full response as JSON")
                    self.logger.info(f"Parsed structure: {json.dumps(parsed_response, indent=2)[:500]}..." if len(json.dumps(parsed_response)) > 500 else json.dumps(parsed_response, indent=2))
                    self.logger.info("====== JSON PARSING END ======")
                    
                    # Log the request with token counts
                    self._log_ai_request(
                        prompt=prompt,
                        response_text=response_text,
                        token_counts=token_counts,
                        response_time=response_time,
                        status='success',
                        request_type=request_type,
                        request_context=request_context,
                        client_id=client_id,
                        user_id=user_id,
                        model_id=model_id,
                        generation_job_id=generation_job_id,
                        has_image=bool(processed_image)
                    )
                    
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
                            
                            # Log the successful request
                            self._log_ai_request(
                                prompt=prompt,
                                response_text=response_text,
                                token_counts=token_counts,
                                response_time=response_time,
                                status='success',
                                request_type=request_type,
                                request_context=request_context,
                                client_id=client_id,
                                user_id=user_id,
                                model_id=model_id,
                                generation_job_id=generation_job_id,
                                has_image=bool(processed_image)
                            )
                            
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
                            
                            # Log the successful request
                            self._log_ai_request(
                                prompt=prompt,
                                response_text=response_text,
                                token_counts=token_counts,
                                response_time=response_time,
                                status='success',
                                request_type=request_type,
                                request_context=request_context,
                                client_id=client_id,
                                user_id=user_id,
                                model_id=model_id,
                                generation_job_id=generation_job_id,
                                has_image=bool(processed_image)
                            )
                            
                            return parsed_response
                        except json.JSONDecodeError as e:
                            self.logger.error(f"✗ Failed to parse JSON from generic code block: {str(e)}")
                            self.logger.info(f"Problem content: {json_content[:200]}..." if len(json_content) > 200 else json_content)
                    
                    # Try to find JSON object within text using regex as a last resort
                    self.logger.info("Attempt 4: Searching for JSON-like patterns in response")
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
                                
                                # Log the successful request
                                self._log_ai_request(
                                    prompt=prompt,
                                    response_text=response_text,
                                    token_counts=token_counts,
                                    response_time=response_time,
                                    status='success',
                                    request_type=request_type,
                                    request_context=request_context,
                                    client_id=client_id,
                                    user_id=user_id,
                                    model_id=model_id,
                                    generation_job_id=generation_job_id,
                                    has_image=bool(processed_image)
                                )
                                
                                return parsed_response
                            except json.JSONDecodeError:
                                self.logger.info(f"✗ Failed to parse potential JSON #{i+1}")
                                continue
                    
                    self.logger.error("✗ All JSON parsing attempts failed")
                    self.logger.error(f"Raw response that failed parsing (first 300 chars): {response_text[:300]}")
                    self.logger.info("====== JSON PARSING END ======")
                    
                    # Log the failed request
                    self._log_ai_request(
                        prompt=prompt,
                        response_text=response_text,
                        token_counts=token_counts,
                        response_time=response_time,
                        status='error',
                        error_message='JSON parsing failed after all attempts',
                        request_type=request_type,
                        request_context=request_context,
                        client_id=client_id,
                        user_id=user_id,
                        model_id=model_id,
                        generation_job_id=generation_job_id,
                        has_image=bool(processed_image)
                    )
                    
                    raise ValueError('Cannot parse the response - all parsing attempts failed')
                break
            except google.api_core.exceptions.InternalServerError as e:
                self.logger.warning(f"Internal server error (attempt {attempt + 1}/{max_retries}): {e}")
                if attempt < max_retries - 1:
                    time.sleep(base_delay)
            except google.api_core.exceptions.DeadlineExceeded as e:
                self.logger.warning(f"Deadline exceeded (attempt {attempt + 1}/{max_retries}): {e}")
                
                # FALLBACK STRATEGY: If image request fails with deadline exceeded, try without image
                if processed_image and attempt == max_retries - 1:
                    self.logger.warning("Deadline exceeded with image. Falling back to text-only request.")
                    processed_image = None  # Disable image for next attempt (which is actually a fallback retry)
                    # We need to extend the loop or recursively call, but simpler to just try once here
                    try:
                        self.logger.info("Sending fallback text-only prompt to Gemini")
                        response = model.generate_content(prompt, request_options={'timeout': 120})
                        # If successful, the loop will continue to response processing
                        # But we need to make sure we don't hit the 'if attempt < max_retries - 1' block below
                        # So we handle success here or let it flow?
                        # Let's let it flow to the response processing block by not raising exception
                    except Exception as fallback_error:
                        self.logger.error(f"Fallback text-only request also failed: {fallback_error}")
                        raise e  # Raise the original error
                elif attempt < max_retries - 1:
                    time.sleep(base_delay)
                else:
                    raise
            except google.api_core.exceptions.ResourceExhausted as e:
                # For rate limit errors, always wait for the rate limiter
                self.logger.warning(f"Rate limit hit (attempt {attempt + 1}/{max_retries})")
                if attempt < max_retries - 1:
                    # Use exponential backoff in addition to rate limiting
                    delay = base_delay * (10 ** attempt)  # Exponential backoff
                    # The API reports when the quota window resets (retry_delay { seconds: N });
                    # retrying sooner than that is guaranteed to fail again
                    retry_match = re.search(r'retry_delay\s*\{\s*seconds:\s*(\d+)', str(e))
                    if retry_match:
                        retry_after = int(retry_match.group(1)) + 1
                        if retry_after > 90:
                            # A per-day quota: waiting inside the request is pointless
                            raise ValueError(
                                f"AI model quota exhausted, the provider allows a retry in about "
                                f"{retry_after // 60} min. Choose another model or try again later."
                            ) from e
                        delay = max(delay, retry_after)
                    self.logger.warning(f"Additional backoff: {delay} seconds")
                    self.logger.error(str(e).split('[links')[0].strip())
                    time.sleep(delay)
            except Exception as e:
                self.logger.error(f"Unexpected error: {str(e)}")
                raise
        
        if not response:
            raise ValueError("No response received from Gemini API after retries")
        
        return response.text.strip()  # Return raw text if we couldn't parse JSON

    def _log_ai_request(
        self,
        prompt: str,
        response_text: str,
        token_counts: Dict[str, int],
        response_time: float,
        status: str = 'success',
        error_message: Optional[str] = None,
        request_type: str = 'other',
        request_context: Optional[str] = None,
        client_id: Optional[int] = None,
        user_id: Optional[int] = None,
        model_id: Optional[int] = None,
        generation_job_id: Optional[str] = None,
        has_image: bool = False
    ):
        """
        Log an AI request with token counts and pricing.
        
        Args:
            prompt: The prompt sent to the AI
            response_text: The response from the AI
            token_counts: Dict with 'input_tokens' and 'output_tokens'
            response_time: Response time in seconds
            status: Request status ('success', 'error', etc.)
            error_message: Optional error message
            request_type: Type of request (ui_step, api_test, etc.)
            request_context: Optional context (test_case_id, etc.)
            client_id: Optional client ID
            user_id: Optional user ID
            model_id: Optional model ID (if not provided, will be retrieved from database)
            generation_job_id: Optional UUID to track all AI requests for a test generation job
            has_image: Whether the request included an image
        """
        try:
            # Get the default AI model ID if not provided
            if not model_id:
                model_id = self._get_model_id()
            if not model_id:
                self.logger.warning("Could not determine model ID for logging")
                return
            
            # Convert response time to milliseconds
            response_time_ms = int(response_time * 1000)
            
            # Log the request
            request_id = self.request_logger.log_request(
                ai_model_id=model_id,
                request_type=request_type,
                input_tokens=token_counts.get('input_tokens', 0),
                output_tokens=token_counts.get('output_tokens', 0),
                response_time_ms=response_time_ms,
                client_id=client_id,
                user_id=user_id,
                request_context=request_context,
                prompt_length=len(prompt),
                response_length=len(response_text),
                status=status,
                error_message=error_message,
                generation_job_id=generation_job_id
            )
            
            if request_id:
                image_status = "with image" if has_image else "without image"
                self.logger.info(f"✅ AI request logged with ID {request_id} ({image_status})")
            
        except Exception as e:
            self.logger.warning(f"Error logging AI request: {str(e)}")

    def _extract_token_counts(self, response) -> Dict[str, int]:
        """
        Extract token counts from Gemini API response.
        
        Args:
            response: The Gemini API response object
            
        Returns:
            Dict with 'input_tokens' and 'output_tokens' keys
        """
        try:
            tokens = {
                'input_tokens': 0,
                'output_tokens': 0
            }
            
            # Check if response has usage_metadata
            if hasattr(response, 'usage_metadata'):
                usage = response.usage_metadata
                
                # Extract prompt token count
                if hasattr(usage, 'prompt_token_count'):
                    tokens['input_tokens'] = usage.prompt_token_count
                
                # Extract candidates token count (output)
                if hasattr(usage, 'candidates_token_count'):
                    tokens['output_tokens'] = usage.candidates_token_count
                
                self.logger.info(
                    f"📊 Token counts extracted: "
                    f"input={tokens['input_tokens']}, "
                    f"output={tokens['output_tokens']}, "
                    f"total={tokens['input_tokens'] + tokens['output_tokens']}"
                )
            else:
                self.logger.warning("Response does not have usage_metadata attribute")
            
            return tokens
            
        except Exception as e:
            self.logger.warning(f"Error extracting token counts: {str(e)}")
            return {'input_tokens': 0, 'output_tokens': 0}

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
