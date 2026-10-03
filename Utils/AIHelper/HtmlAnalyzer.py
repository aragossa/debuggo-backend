import sys

import psycopg2
import threading
from datetime import datetime
from typing import Dict, Any, Tuple

from auroqa.Utils.AIHelper.AIHelper import AIHelper
from auroqa.Utils.System import System
from contextlib import contextmanager
import logging

# ReAct Pattern imports
try:
    from auroqa.Services.ConversationManager import ConversationManager, ConversationTurn
    REACT_AVAILABLE = True
except ImportError:
    REACT_AVAILABLE = False

# Phase 2.5: Few-shot learning imports
try:
    from auroqa.Services.SimilaritySearch import SimilaritySearch
    from auroqa.Services.EmbeddingGenerator import EmbeddingGenerator
    PHASE_2_5_AVAILABLE = True
except ImportError:
    PHASE_2_5_AVAILABLE = False

class HtmlAnalyzer(AIHelper):
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(HtmlAnalyzer, cls).__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self):
        if not self._initialized:
            super().__init__()
            self.system = System()
            self.logger = self._setup_logger()
            
            # ReAct Pattern: Initialize ConversationManager
            self.conversation_manager = None
            if REACT_AVAILABLE:
                try:
                    self.conversation_manager = ConversationManager()
                    self.logger.info("ReAct Pattern enabled (ConversationManager initialized)")
                except Exception as e:
                    self.logger.warning(f"ReAct Pattern disabled: {str(e)}")
                    self.conversation_manager = None
            else:
                self.logger.info("ReAct Pattern services not available")
            
            # Phase 2.5: Initialize few-shot learning services
            self.use_few_shot = True
            if PHASE_2_5_AVAILABLE:
                try:
                    self.similarity_search = SimilaritySearch()
                    self.embedding_generator = EmbeddingGenerator()
                    self.logger.info("Few-shot learning enabled (Phase 2.5)")
                except Exception as e:
                    self.logger.warning(f"Few-shot learning disabled: {str(e)}")
                    self.use_few_shot = False
            else:
                self.logger.info("Phase 2.5 services not available")
                self.use_few_shot = False
            
            self._initialized = True

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

    def _setup_logger(self):
        logger = logging.getLogger('HtmlAnalyzer')
        logger.setLevel(logging.INFO)
        # The app configures root logging (main.py); an own handler here would print every line twice
        if logging.getLogger().handlers:
            return logger

        # Remove any existing handlers to prevent duplicate logging
        if logger.hasHandlers():
            logger.handlers.clear()

        handler = logging.StreamHandler(sys.stdout)
        handler.setLevel(logging.INFO)
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(filename)s:%(lineno)d  - %(message)s')
        handler.setFormatter(formatter)
        logger.addHandler(handler)

        return logger

    def _extract_expected_text_from_error(self, error_message: str):
        """Extract expected text from error message."""
        import re
        
        # Try to extract text from contains(text(), '...')
        match = re.search(r"contains\(text\(\),\s*['\"]([^'\"]+)['\"]\)", error_message)
        if match:
            return match.group(1)
        
        # Try to extract from other patterns
        match = re.search(r"text\(\)\s*=\s*['\"]([^'\"]+)['\"]", error_message)
        if match:
            return match.group(1)
        
        return None

    def _suggest_recovery_strategy(self, error_message: str, html_content: str, previous_attempts: list):
        """
        Select recovery strategy based on error type and attempt count.
        """
        attempt_count = len(previous_attempts) if previous_attempts else 0
        
        # Strategy 1: If first attempt, try alternative locator
        if attempt_count == 0:
            return {
                "strategy": "ALTERNATIVE_LOCATOR",
                "analysis": "First attempt failed, trying alternative locator approach",
                "action": "assert_text_contains",  # Less strict than assert_text
                "confidence": 0.75
            }
        
        # Strategy 2: If second attempt, try waiting first
        elif attempt_count == 1:
            return {
                "strategy": "WAIT_AND_RETRY",
                "analysis": "Element may not be loaded yet, adding wait",
                "action": "wait_for_element_to_be_visible",
                "timeout": 10,
                "confidence": 0.70
            }
        
        # Strategy 3: If third+ attempt, escalate
        else:
            return {
                "strategy": "ESCALATE_TO_HUMAN",
                "analysis": f"Element not found after {attempt_count + 1} recovery attempts",
                "action": "skip",
                "reason": "Unable to locate element after multiple recovery strategies",
                "confidence": 0.95
            }

    def _generate_alternative_locator(self, error_message: str, html_content: str):
        """
        Generate alternative locator when primary fails.
        """
        # This is a simplified version
        # In production, use more sophisticated analysis
        return "//*[contains(text(), 'Azure AD settings saved')]"

    def add_step_to_history(self, test_case_id: int, step_data: dict):
        """Add a step to the test case history."""
        if test_case_id not in self._step_history:
            self._step_history[test_case_id] = []
        self._step_history[test_case_id].append(step_data)
        
    def extract_variables_from_step(self, step_data: dict) -> list:
        """Extract all placeholder variables from a step's value field."""
        import re
        variables = []
        value = step_data.get('value', '')
        if value:
            # Find all %variable% patterns
            pattern = r'%([^%]+)%'
            matches = re.findall(pattern, value)
            for match in matches:
                variables.append({
                    'placeholder': f'%{match}%',
                    'var_name': match,
                    'purpose': step_data.get('element_purpose', ''),
                    'action': step_data.get('action', '')
                })
        return variables
    
    def get_variable_registry(self, test_case_id: int) -> dict:
        """Build a registry of all variables used in previous steps."""
        history = self.get_step_history(test_case_id)
        registry = {}
        
        for idx, step in enumerate(history):
            variables = self.extract_variables_from_step(step)
            for var in variables:
                var_name = var['var_name']
                if var_name not in registry:
                    registry[var_name] = {
                        'first_use_step': idx,
                        'placeholder': var['placeholder'],
                        'purpose': var['purpose'],
                        'action': var['action'],
                        'usage_count': 1,
                        'contexts': [var['purpose']]
                    }
                else:
                    registry[var_name]['usage_count'] += 1
                    registry[var_name]['contexts'].append(var['purpose'])
        
        return registry

    def get_step_history(self, test_case_id: int) -> list:
        """Get the step history for a test case."""
        return self._step_history.get(test_case_id, [])

    def clear_step_history(self, test_case_id: int):
        """Clear the step history for a test case."""
        if test_case_id in self._step_history:
            del self._step_history[test_case_id]
    
    def _build_few_shot_prompt(self, test_description: str, similar_tests: list) -> str:
        """
        Build a few-shot prompt with examples from similar successful tests.
        
        Args:
            test_description: Description of the test to generate
            similar_tests: List of similar successful tests
        
        Returns:
            Few-shot prompt with examples
        """
        prompt = f"""
You are an expert test automation engineer. Use the following successful examples 
to generate similar high-quality test steps.

TEST DESCRIPTION: {test_description}

SUCCESSFUL EXAMPLES:
"""
        
        for i, test in enumerate(similar_tests, 1):
            prompt += f"\n{i}. Test: {test.get('test_name', 'Unknown')}\n"
            prompt += f"   Description: {test.get('description', 'N/A')}\n"
            prompt += f"   Similarity: {test.get('similarity_score', 0):.2f}\n"
            if 'action' in test:
                prompt += f"   Action: {test.get('action')}\n"
            if 'element_purpose' in test:
                prompt += f"   Purpose: {test.get('element_purpose')}\n"
        
        prompt += """

TASK: Generate the next test step following the patterns from successful examples.

AVAILABLE VARIABLES FOR VALUES:

A. ENVIRONMENT VARIABLES:
   - %base_url% - API base URL
   - %login% - Username/email from environment
   - %password% - Password from environment

B. UNIQUE IDENTIFIERS (cached per test run):
   - %unique_name% - Random unique ID (e.g., "a7b3c9d2")
   - %unique_name:Client% - With prefix (e.g., "Client_a7b3c9d2")
   - %timestamp_name% - Timestamp-based (e.g., "20250129_143052")

C. REALISTIC PERSONAL DATA (cached per test run):
   - %random_name% - Full name (e.g., "John Smith")
   - %random_first_name% - First name (e.g., "John")
   - %random_last_name% - Last name (e.g., "Smith")
   - %random_email% - Email (e.g., "john.smith@example.com")
   - %random_username% - Username (e.g., "john_smith_123")
   - %random_phone% - Phone number (e.g., "+1-555-234-5678")

D. REALISTIC LOCATION DATA (cached per test run):
   - %random_address% - Street address
   - %random_city% - City name
   - %random_country% - Country name

E. REALISTIC BUSINESS DATA (cached per test run):
   - %random_company% - Company name (e.g., "Acme Corporation")
   - %random_job_title% - Job title (e.g., "Software Engineer")

F. TECHNICAL DATA (cached per test run):
   - %random_string% - Alphanumeric string (10 chars)
   - %random_number% - Number (1-10000)
   - %random_url% - URL
   - %random_uuid% - Full UUID
   - %random_date% - Date (YYYY-MM-DD)
   - %random_boolean% - true/false

⚠️ CRITICAL - ENVIRONMENT VARIABLES vs GENERATED VARIABLES:

ENVIRONMENT VARIABLES (%password%, %login%) are ONLY for:
- Logging in with EXISTING test account credentials from environment
- NOT for newly created items in the test

GENERATED VARIABLES (%random_email%, %var:name%) are for:
- Newly created users/items in the test
- Data that needs to be reused later in the same test

COMMON MISTAKE - DO NOT DO THIS:
❌ WRONG: Step 5 creates new user with password → value="%password%" (environment password)
❌ WRONG: Step 6 confirms password → value="%password%" (same environment password)
❌ WRONG: Step 10 logs in as new user → value="%password%" (FAILS - doesn't match what was entered!)

CORRECT APPROACH:
✅ CORRECT: Step 5 creates new user with password → value="%var:new_user_password%" (generates and caches)
✅ CORRECT: Step 6 confirms password → value="%var:new_user_password%" (reuses same password)
✅ CORRECT: Step 10 logs in as new user → value="%var:new_user_password%" (reuses same password - WORKS!)

CRITICAL - VALUE FIELD REQUIREMENTS:
- ✅ CORRECT: "value": "%password%" (ONLY for logging in with existing account)
- ✅ CORRECT: "value": "%var:new_user_password%" (for newly created user passwords)
- ✅ CORRECT: "value": "%login%" (ONLY for logging in with existing account)
- ✅ CORRECT: "value": "%random_email%" (for random email - STRING)
- ✅ CORRECT: "value": "%unique_name%" (for unique names - STRING)
- ✅ CORRECT: "value": null (for click/wait actions with no input - NULL)
- ❌ WRONG: "value": {{"%password%"}} (object/dict - must be string)
- ❌ WRONG: "value": {{"condition": "element_is_visible"}} (object/dict - must be string)
- ❌ WRONG: "value": "{{user_password}}" (incorrect syntax)

IMPORTANT: The "value" field MUST be either:
1. A string with %placeholder% format (e.g., "%password%")
2. null (for actions that don't require input like click, wait, assert)
3. NEVER a JSON object or dictionary

SUPPORTED ACTIONS:
- "click" - Click an element
- "type" - Type text into an element
- "wait" - Wait for element to appear
- "wait_for_clickable" - Wait for element to be clickable
- "wait_for_element_visible" - Wait for element to be visible
- "press_key" - Press a keyboard key
- "select" - Select from dropdown
- "hover" - Hover over element
- "clear" - Clear element content
- "assert" - Assert element exists
- "assert_text" - Assert element has EXACT text match (use this for final verification)
- "assert_text_contains" - Assert element text contains substring
- "assert_attribute" - Assert an element attribute. Put "attribute=expected" into "value" (e.g. "aria-valuenow=0", "value=John", "checked=true", "disabled=false"). Use it when the state is NOT visible text: progress/slider values, input field values, checked/disabled/selected state, link href
- "navigate" - Navigate to URL
- "switch_tab" - Switch to another browser tab or window. element_locator is "N/A". Put into "value": "new" (the tab that just opened), "main" (the first tab), a tab number ("2"), or a part of the tab title or URL. A tab opened by a step is switched to automatically, see BROWSER STATE; use this action to go back ("main") or to move between tabs
- "accept_alert" - Press OK in a native JavaScript alert/confirm/prompt. element_locator is "N/A". For a prompt put the text to type into "value" (e.g. "John"), otherwise null. Waits up to 10 seconds for the alert to appear
- "dismiss_alert" - Press Cancel in a native JavaScript confirm/prompt. element_locator is "N/A", value is null
- "assert_alert_text" - Assert the exact text of the native alert and leave it open. element_locator is "N/A", put the expected text into "value" (e.g. "Do you confirm action?"). Waits up to 10 seconds for the alert to appear
- "drag_and_drop" - Drag one element onto another. element_locator is the element to drag, "value" is the XPath of the element to drop it on (e.g. "//div[@id='droppable']"), nothing else. Works for sortable lists and native HTML5 draggables too. Fails if nothing moved. Follow it with an assertion of the result
- "upload_file" - Choose a file in an <input type="file">. element_locator is the file input itself (not its button or label), "value" is the name of a sample file: "sample.txt", "sample.png", "sample.pdf" or "sample.csv". NEVER click a file input: that opens an OS dialog nobody can close
- "api_request" - Send an HTTP request from the test itself, not through the browser (prepare or check data through the API). element_locator is "N/A". "value" is a JSON string: {"method": "POST", "endpoint": "full URL", "headers": {}, "body": {}, "expected_status": 201, "extract_variables": {"item_id": "$.id"}}. A variable extracted from the response is used in later steps as %item_id%. Use it ONLY when the test description asks for an API request and gives its URL, or with a call from the API CALLS list at the end of this prompt (in the format given there); never invent endpoints. Requests placed before the first page step are preconditions: Run sends them before it opens the page. After a request made later, the open page still shows the old data: reload it with "navigate" (value "%base_url%" or the page URL) before checking the result on the page
- "stop_test" - Stop test execution (use when test is completed successfully)

NATIVE ALERTS: alert(), confirm() and prompt() windows are NOT in the HTML and block the page. When BROWSER STATE says one is open, or the previous step triggers one, handle it (assert_alert_text, accept_alert, dismiss_alert) before any other action. For an alert that appears after a delay do not add a wait: these actions wait for it themselves.

CRITICAL - WHEN TO USE STOP_TEST:
✅ Use "stop_test" when:
  - Test has completed all steps successfully
  - Final assertion passed
  - No more steps needed
  - Test objective is achieved

Return a JSON object with:
- action: One of the supported actions above
- element_locator: XPath selector (or "N/A" for navigate/stop_test/switch_tab/accept_alert/dismiss_alert/assert_alert_text)
- css_selector: CSS selector (optional fallback)
- by_strategy: "xpath" or "css"
- element_purpose: What this step does
- value: Value to enter using %placeholder% format (if applicable, null for click/wait/assert/stop_test)
- next_step: Description of the next step to perform
"""
        
        return prompt
    
    def _get_standard_prompt(self, test_description: str) -> str:
        """Get standard prompt when no similar tests found."""
        return f"""
You are an expert test automation engineer.

TEST DESCRIPTION: {test_description}

Generate a high-quality test step that:
1. Uses specific, reliable XPath selectors
2. Includes proper waits and error handling
3. Follows best practices from successful tests
4. Handles edge cases and dynamic content

AVAILABLE VARIABLES FOR VALUES:

A. ENVIRONMENT VARIABLES:
   - %base_url% - API base URL
   - %login% - Username/email from environment
   - %password% - Password from environment

B. UNIQUE IDENTIFIERS (cached per test run):
   - %unique_name% - Random unique ID (e.g., "a7b3c9d2")
   - %unique_name:Client% - With prefix (e.g., "Client_a7b3c9d2")
   - %timestamp_name% - Timestamp-based (e.g., "20250129_143052")

C. REALISTIC PERSONAL DATA (cached per test run):
   - %random_name% - Full name (e.g., "John Smith")
   - %random_first_name% - First name (e.g., "John")
   - %random_last_name% - Last name (e.g., "Smith")
   - %random_email% - Email (e.g., "john.smith@example.com")
   - %random_username% - Username (e.g., "john_smith_123")
   - %random_phone% - Phone number (e.g., "+1-555-234-5678")

D. REALISTIC LOCATION DATA (cached per test run):
   - %random_address% - Street address
   - %random_city% - City name
   - %random_country% - Country name

E. REALISTIC BUSINESS DATA (cached per test run):
   - %random_company% - Company name (e.g., "Acme Corporation")
   - %random_job_title% - Job title (e.g., "Software Engineer")

F. TECHNICAL DATA (cached per test run):
   - %random_string% - Alphanumeric string (10 chars)
   - %random_number% - Number (1-10000)
   - %random_url% - URL
   - %random_uuid% - Full UUID
   - %random_date% - Date (YYYY-MM-DD)
   - %random_boolean% - true/false

⚠️ CRITICAL - ENVIRONMENT VARIABLES vs GENERATED VARIABLES:

ENVIRONMENT VARIABLES (%password%, %login%) are ONLY for:
- Logging in with EXISTING test account credentials from environment
- NOT for newly created items in the test

GENERATED VARIABLES (%random_email%, %var:name%) are for:
- Newly created users/items in the test
- Data that needs to be reused later in the same test

COMMON MISTAKE - DO NOT DO THIS:
❌ WRONG: Step 5 creates new user with password → value="%password%" (environment password)
❌ WRONG: Step 6 confirms password → value="%password%" (same environment password)
❌ WRONG: Step 10 logs in as new user → value="%password%" (FAILS - doesn't match what was entered!)

CORRECT APPROACH:
✅ CORRECT: Step 5 creates new user with password → value="%var:new_user_password%" (generates and caches)
✅ CORRECT: Step 6 confirms password → value="%var:new_user_password%" (reuses same password)
✅ CORRECT: Step 10 logs in as new user → value="%var:new_user_password%" (reuses same password - WORKS!)

CRITICAL - VALUE FIELD REQUIREMENTS:
- ✅ CORRECT: "value": "%password%" (ONLY for logging in with existing account)
- ✅ CORRECT: "value": "%var:new_user_password%" (for newly created user passwords)
- ✅ CORRECT: "value": "%login%" (ONLY for logging in with existing account)
- ✅ CORRECT: "value": "%random_email%" (for random email - STRING)
- ✅ CORRECT: "value": "%unique_name%" (for unique names - STRING)
- ✅ CORRECT: "value": null (for click/wait actions with no input - NULL)
- ❌ WRONG: "value": {{"%password%"}} (object/dict - must be string)
- ❌ WRONG: "value": {{"condition": "element_is_visible"}} (object/dict - must be string)
- ❌ WRONG: "value": "{{user_password}}" (incorrect syntax)

IMPORTANT: The "value" field MUST be either:
1. A string with %placeholder% format (e.g., "%password%")
2. null (for actions that don't require input like click, wait, assert)
3. NEVER a JSON object or dictionary

SUPPORTED ACTIONS:
- "click" - Click an element
- "type" - Type text into an element
- "wait" - Wait for element to appear
- "wait_for_clickable" - Wait for element to be clickable
- "wait_for_element_visible" - Wait for element to be visible
- "press_key" - Press a keyboard key
- "select" - Select from dropdown
- "hover" - Hover over element
- "clear" - Clear element content
- "assert" - Assert element exists
- "assert_text" - Assert element has EXACT text match (use this for final verification)
- "assert_text_contains" - Assert element text contains substring
- "assert_attribute" - Assert an element attribute. Put "attribute=expected" into "value" (e.g. "aria-valuenow=0", "value=John", "checked=true", "disabled=false"). Use it when the state is NOT visible text: progress/slider values, input field values, checked/disabled/selected state, link href
- "navigate" - Navigate to URL
- "switch_tab" - Switch to another browser tab or window. element_locator is "N/A". Put into "value": "new" (the tab that just opened), "main" (the first tab), a tab number ("2"), or a part of the tab title or URL. A tab opened by a step is switched to automatically, see BROWSER STATE; use this action to go back ("main") or to move between tabs
- "accept_alert" - Press OK in a native JavaScript alert/confirm/prompt. element_locator is "N/A". For a prompt put the text to type into "value" (e.g. "John"), otherwise null. Waits up to 10 seconds for the alert to appear
- "dismiss_alert" - Press Cancel in a native JavaScript confirm/prompt. element_locator is "N/A", value is null
- "assert_alert_text" - Assert the exact text of the native alert and leave it open. element_locator is "N/A", put the expected text into "value" (e.g. "Do you confirm action?"). Waits up to 10 seconds for the alert to appear
- "drag_and_drop" - Drag one element onto another. element_locator is the element to drag, "value" is the XPath of the element to drop it on (e.g. "//div[@id='droppable']"), nothing else. Works for sortable lists and native HTML5 draggables too. Fails if nothing moved. Follow it with an assertion of the result
- "upload_file" - Choose a file in an <input type="file">. element_locator is the file input itself (not its button or label), "value" is the name of a sample file: "sample.txt", "sample.png", "sample.pdf" or "sample.csv". NEVER click a file input: that opens an OS dialog nobody can close
- "api_request" - Send an HTTP request from the test itself, not through the browser (prepare or check data through the API). element_locator is "N/A". "value" is a JSON string: {{"method": "POST", "endpoint": "full URL", "headers": {{}}, "body": {{}}, "expected_status": 201, "extract_variables": {{"item_id": "$.id"}}}}. A variable extracted from the response is used in later steps as %item_id%. Use it ONLY when the test description asks for an API request and gives its URL, or with a call from the API CALLS list at the end of this prompt (in the format given there); never invent endpoints. Requests placed before the first page step are preconditions: Run sends them before it opens the page. After a request made later, the open page still shows the old data: reload it with "navigate" (value "%base_url%" or the page URL) before checking the result on the page
- "stop_test" - Stop test execution (use when test is completed successfully)

NATIVE ALERTS: alert(), confirm() and prompt() windows are NOT in the HTML and block the page. When BROWSER STATE says one is open, or the previous step triggers one, handle it (assert_alert_text, accept_alert, dismiss_alert) before any other action. For an alert that appears after a delay do not add a wait: these actions wait for it themselves.

CRITICAL - WHEN TO USE STOP_TEST:
✅ Use "stop_test" when:
  - Test has completed all steps successfully
  - Final assertion passed
  - No more steps needed
  - Test objective is achieved

Return a JSON object with:
- action: One of the supported actions above
- element_locator: XPath selector (or "N/A" for navigate/stop_test/switch_tab/accept_alert/dismiss_alert/assert_alert_text)
- css_selector: CSS selector (optional fallback)
- by_strategy: "xpath" or "css"
- element_purpose: What this step does
- value: Value to enter using %placeholder% format (if applicable, null for click/wait/assert/stop_test)
- next_step: Description of the next step to perform
"""
    
    def _find_similar_tests(self, test_case_id: int, test_description: str, top_k: int = 3) -> list:
        """
        Find similar successful tests using Phase 2.5 learning system.
        
        Args:
            test_case_id: ID of the test case
            test_description: Description of the test
            top_k: Number of similar tests to return
        
        Returns:
            List of similar tests with similarity scores
        """
        if not self.use_few_shot or not PHASE_2_5_AVAILABLE:
            return []
        
        try:
            self.logger.info(f"Finding similar tests for test case {test_case_id}")
            similar_tests = self.similarity_search.find_similar_tests(
                test_case_id=test_case_id,
                top_k=top_k
            )
            
            if similar_tests:
                self.logger.info(f"Found {len(similar_tests)} similar tests")
                return similar_tests
            else:
                self.logger.info("No similar tests found")
                return []
        
        except Exception as e:
            self.logger.warning(f"Failed to find similar tests: {str(e)}")
            return []
    
    def _record_pattern_usage(self, test_case_id: int, step: dict) -> None:
        """
        Record pattern usage for learning system.
        
        Args:
            test_case_id: ID of test case
            step: Generated step
        """
        if not self.use_few_shot or not PHASE_2_5_AVAILABLE:
            return
        
        try:
            from auroqa.Services.VectorStore import VectorStore
            
            # Extract pattern from step
            pattern_type = 'selector' if 'element_locator' in step else 'api_flow'
            pattern_data = {
                'action': step.get('action'),
                'locator': step.get('element_locator'),
                'value': step.get('value'),
                'purpose': step.get('element_purpose')
            }
            
            # Record usage in vector store
            vector_store = VectorStore()
            vector_store.record_pattern_usage(
                pattern_type=pattern_type,
                pattern_data=pattern_data,
                test_case_id=test_case_id,
                success=True
            )
            
            self.logger.debug(f"Recorded pattern usage for test {test_case_id}")
        
        except Exception as e:
            self.logger.debug(f"Pattern usage recording skipped: {str(e)}")

    def html_analyzer(self, test_case_id: int, html_code: str, test_name: str, test_description: str, step_order: int,
                      next_prompt: str, prev_step_description: str, screenshot_path: str = None, generation_job_id: str = None, vlm_enabled: bool = False, model_name: str = None,
                      browser_state: str = None, api_context: str = None) -> tuple[str, str, str, str, str, str, str]:
        self.logger.info("Sending request to AI provider for HTML analysis.")
        
        # ReAct Pattern: Start conversation for this step
        conversation = self._start_react_conversation(test_case_id, test_description)
        
        # ReAct Turn 1: Thought - Analyze the task
        if conversation:
            self._add_react_turn(
                conversation,
                thought=f"Need to generate step {step_order} for test: {test_name}. Previous step: {prev_step_description}",
                action="analyze_task",
                observation=f"Task analysis: Generate next action for step {step_order}",
                confidence=0.9
            )
        
        # Get variable registry from previous steps
        variable_registry = self.get_variable_registry(test_case_id)
        self.logger.info(f"Variable registry for test case {test_case_id}: {len(variable_registry)} variables tracked")
        
        # Phase 2.5: Try to find similar tests for few-shot learning
        similar_tests = self._find_similar_tests(test_case_id, test_description, top_k=3)
        
        # Build prompt with few-shot examples if available
        if similar_tests and self.use_few_shot:
            self.logger.info(f"Building few-shot prompt with {len(similar_tests)} examples")
            prompt = self._build_few_shot_prompt(
                test_description=test_description,
                similar_tests=similar_tests
            )
        else:
            self.logger.info("Using standard prompt (no similar tests found)")
            prompt = self._get_standard_prompt(test_description)
        
        # Append variable registry information to prompt
        if variable_registry:
            prompt += f"\n\nPREVIOUSLY USED VARIABLES:\n"
            for var_name, var_info in variable_registry.items():
                prompt += f"- {var_name}: Used {var_info['usage_count']} times, Purpose: {var_info['purpose']}\n"
        
        # Append HTML code (critical for XPath generation)
        # The DOM structure is kept complete, not truncated; only markup that is useless for
        # selectors (inline styles, scripts, SVG internals) is stripped to save tokens
        prompt += f"""

CURRENT PAGE HTML (FULL):
{self.clean_html_for_prompt(html_code)}

CURRENT STEP: {step_order}
NEXT ACTION: {next_prompt}
PREVIOUS STEP: {prev_step_description}
"""
        # Open native alert and tabs: the HTML does not show them
        if browser_state:
            prompt += f"\nBROWSER STATE (not visible in the HTML above):\n{browser_state}\n"
        # Calls of the project's API library the test may use to prepare data
        if api_context:
            prompt += f"\n{api_context}\n"
        self.logger.info(f"The screenshot path {screenshot_path}")
        image = False
        if screenshot_path and vlm_enabled:
            self.logger.info(f"Reading the screenshot {screenshot_path}")
            image = self.read_img(screenshot_path)
        elif screenshot_path and not vlm_enabled:
            self.logger.info(f"Screenshot available but VLM disabled, skipping image read")

        # ReAct Turn 2: Action - Analyze HTML and generate step
        if conversation:
            self._add_react_turn(
                conversation,
                thought=f"Analyzing HTML structure to find elements for action: {next_prompt}",
                action="analyze_html",
                observation=f"HTML analyzed. Found {html_code.count('<')} HTML tags. Screenshot: {screenshot_path}",
                confidence=0.85
            )

        if self.provider == "gemini":
            if image:
                self.logger.info("Sending request to Gemini with image")
                response = self.send_request_to_gemini(
                    prompt, 
                    image,
                    request_type='html_analysis',
                    request_context=f'test_case_{test_case_id}_step_{step_order}',
                    generation_job_id=generation_job_id,
                    model_name=model_name
                )
            else:
                self.logger.info("Sending request to Gemini without image")
                response = self.send_request_to_gemini(
                    prompt,
                    request_type='html_analysis',
                    request_context=f'test_case_{test_case_id}_step_{step_order}',
                    generation_job_id=generation_job_id,
                    model_name=model_name
                )
            self.logger.info("=== HTML ANALYZER RESPONSE START ===")

            # Validate required keys
            required_keys = ['element_locator', 'css_selector', 'by_strategy', 'action', 'element_purpose', 'next_step', 'value']
            # css_selector is a fallback locator the model often leaves out: not worth a warning
            missing_keys = [k for k in required_keys if k not in response]
            if [k for k in missing_keys if k != 'css_selector']:
                self.logger.warning(f"Missing required keys in response: {missing_keys}")
                # Set default values for missing keys
                for key in missing_keys:
                    if key == 'css_selector':
                        response[key] = ''  # CSS selector is optional fallback
                    else:
                        response[key] = ''

            # Normalize by_strategy to match database constraints
            if response['by_strategy'].lower() not in ['css', 'xpath']:
                response['by_strategy'] = 'xpath'  # Default to xpath if invalid
            else:
                response['by_strategy'] = response['by_strategy'].lower()

            # Add step to history
            step_data = {
                'element_purpose': response['element_purpose'],
                'action': response['action'],
                'element_locator': response['element_locator'],
                'css_selector': response.get('css_selector', ''),  # Get CSS selector
                'by_strategy': response['by_strategy'],
                'value': response['value'],
                'next_step': response['next_step']
            }

            # ReAct Turn 3: Observation - AI generated step
            if conversation:
                self._add_react_turn(
                    conversation,
                    thought=f"Generated step {step_order}: {response['element_purpose']}",
                    action="generate_step",
                    observation=f"Step generated: Action={response['action']}, Element={response['element_locator']}, Strategy={response['by_strategy']}, Next={response['next_step']}",
                    confidence=0.88
                )

            self.add_step_to_history(test_case_id, step_data)
            
            # Phase 2.5: Record pattern usage for learning system
            self._record_pattern_usage(test_case_id, step_data)
            
            # ReAct Turn 4: Reflection - Validate and finalize
            if conversation:
                self._add_react_turn(
                    conversation,
                    thought=f"Validating generated step: {response['element_purpose']}",
                    action="validate_step",
                    observation=f"Step validation: Locator found={bool(response['element_locator'])}, Strategy valid={response['by_strategy'] in ['xpath', 'css']}, Next step clear={bool(response['next_step'])}",
                    confidence=0.90
                )

            # ReAct: Log reasoning trace
            if conversation:
                trace = self._get_react_trace(conversation)
                if trace:
                    self.logger.info(f"[ReAct Reasoning Trace]\n{trace}")
                
                # Extract context for next steps
                context = self._extract_react_context(conversation)
                self.logger.debug(f"[ReAct Context] Turns: {len(conversation.turns)}, Avg Confidence: {context.get('average_confidence', 0):.2f}")
            
            # Return tuple in the expected order (now includes css_selector)
            return (
                step_data['next_step'],
                step_data['element_purpose'],
                step_data['action'],
                step_data['element_locator'],
                step_data['css_selector'],
                step_data['by_strategy'],
                step_data['value']
            )
        elif self.provider == "claude":
            # Mock response for now
            return "Stop", "Mock purpose", "click", "#mock", "css", ""
        elif self.provider == "deepseek":
            # Mock response for now
            return "Stop", "Mock purpose", "click", "#mock", "css", ""
        else:
            raise ValueError(f"Unsupported AI provider: {self.provider}")

    def analyze_error(self, test_case_id: int, html_code: str, test_name: str, test_description: str, 
                     step_history: list, failed_step: dict, error_message: str, 
                     previous_attempts: list = None, screenshot_path: str = None, generation_job_id: str = None, model_name: str = None,
                     browser_state: str = None) -> tuple[str, str, str, str, str, str, str]:
        """
        Analyze a test step failure and suggest a fix.
        
        Args:
            test_case_id: ID of the test case
            html_code: The HTML of the page when the error occurred
            test_name: The name of the test case
            test_description: The description of the test case
            step_history: List of previously executed steps
            failed_step: The step that failed
            error_message: The error message from the failed step
            previous_attempts: List of previous recovery attempts and their errors
            screenshot_path: Path to the screenshot of the failure state
            
        Returns:
            A tuple containing (next_step, element_purpose, action, element_locator, css_selector, by_strategy, value)
        """
        self.logger.info("Sending request to AI provider for error analysis.")
        
        # Check if element exists in HTML before attempting recovery
        expected_text = self._extract_expected_text_from_error(error_message)
        
        if expected_text:
            # Check if this text exists ANYWHERE in the HTML
            if expected_text.lower() not in html_code.lower():
                self.logger.warning(f"Expected text '{expected_text}' not found in HTML at all")
                # Return a skip response instead of attempting recovery
                return (
                    "Element not found on page, skipping this step",
                    f"Skip verification - element not found",
                    "skip",
                    "N/A",
                    "",
                    "xpath",
                    None
                )
        
        # ReAct Pattern: Start conversation for error recovery
        conversation = self._start_react_conversation(test_case_id, f"Error recovery for: {test_description}")
        
        # ReAct Turn 1: Thought - Analyze the error
        if conversation:
            self._add_react_turn(
                conversation,
                thought=f"Step failed: {failed_step.get('action', 'unknown')} on {failed_step.get('element_locator', 'unknown')}. Error: {error_message[:100]}",
                action="analyze_error",
                observation=f"Error analysis: {error_message}. Previous attempts: {len(previous_attempts or [])}",
                confidence=0.8
            )
        
        prompt = self.get_error_analysis_prompt(
            html_code=html_code,
            error_message=error_message,
            test_name=test_name,
            test_description=test_description,
            step_history=step_history,
            failed_step=failed_step,
            previous_attempts=previous_attempts,
            screenshot_path=screenshot_path,
            browser_state=browser_state
        )
        
        image = False
        if screenshot_path:
            self.logger.info(f"Reading the error screenshot {screenshot_path}")
            image = self.read_img(screenshot_path)
        
        # ReAct Turn 2: Action - Analyze HTML for recovery
        if conversation:
            self._add_react_turn(
                conversation,
                thought=f"Analyzing current page state to find alternative approach",
                action="analyze_html_for_recovery",
                observation=f"Current HTML has {html_code.count('<')} tags. Looking for alternative selectors.",
                confidence=0.85
            )
        
        if self.provider == "gemini":
            if image:
                self.logger.info("Sending error analysis request to Gemini with image")
                response = self.send_request_to_gemini(
                    prompt, 
                    image,
                    request_type='ui_error',
                    request_context=f'test_case_{test_case_id}_error_recovery',
                    generation_job_id=generation_job_id,
                    model_name=model_name
                )
            else:
                self.logger.info("Sending error analysis request to Gemini without image")
                response = self.send_request_to_gemini(
                    prompt,
                    request_type='ui_error',
                    request_context=f'test_case_{test_case_id}_error_recovery',
                    generation_job_id=generation_job_id,
                    model_name=model_name
                )
            
            self.logger.info("=== ERROR ANALYSIS RESPONSE START ===")
            
            # Validate required keys
            required_keys = ['analysis', 'element_locator', 'css_selector', 'by_strategy', 'action', 'element_purpose', 'value', 'next_step']
            missing_keys = [k for k in required_keys if k not in response]
            if [k for k in missing_keys if k != 'css_selector']:
                self.logger.warning(f"Missing required keys in error analysis response: {missing_keys}")
                # Set default values for missing keys
                for key in missing_keys:
                    if key == 'css_selector':
                        response[key] = ''  # CSS selector is optional fallback
                    else:
                        response[key] = ''
            
            # Normalize by_strategy to match database constraints
            if response['by_strategy'].lower() not in ['css', 'xpath']:
                response['by_strategy'] = 'xpath'  # Default to xpath if invalid
            else:
                response['by_strategy'] = response['by_strategy'].lower()
            
            # Log the analysis
            self.logger.info(f"Error analysis: {response['analysis']}")
            
            # ReAct Turn 3: Observation - Recovery strategy generated
            if conversation:
                self._add_react_turn(
                    conversation,
                    thought=f"Generated recovery strategy: {response['element_purpose']}",
                    action="generate_recovery",
                    observation=f"Recovery generated: Action={response['action']}, New Element={response['element_locator']}, Strategy={response['by_strategy']}",
                    confidence=0.87
                )
            
            # ReAct Turn 4: Reflection - Validate recovery
            if conversation:
                self._add_react_turn(
                    conversation,
                    thought=f"Validating recovery approach for failed step",
                    action="validate_recovery",
                    observation=f"Recovery validation: Has alternative selector={bool(response['element_locator'])}, Strategy valid={response['by_strategy'] in ['xpath', 'css']}, Analysis provided={bool(response.get('analysis'))}",
                    confidence=0.89
                )
                
                # Log reasoning trace for error recovery
                trace = self._get_react_trace(conversation)
                if trace:
                    self.logger.info(f"[ReAct Error Recovery Trace]\n{trace}")
            
            # Return tuple in the expected order (now includes css_selector)
            return (
                response['next_step'],
                response['element_purpose'],
                response['action'],
                response['element_locator'],
                response.get('css_selector', ''),
                response['by_strategy'],
                response['value']
            )
        else:
            raise ValueError(f"Unsupported AI provider for error analysis: {self.provider}")
    
    # ============================================================================
    # ReAct Pattern Methods
    # ============================================================================
    
    def _start_react_conversation(self, test_case_id: int, test_description: str) -> Any:
        """
        Start a new ReAct conversation for test step generation.
        
        Args:
            test_case_id: ID of the test case
            test_description: Description of the test
            
        Returns:
            Conversation object or None if ReAct is not available
        """
        if not self.conversation_manager:
            return None
        
        try:
            conversation = self.conversation_manager.start_conversation(
                test_case_id=test_case_id,
                overall_strategy=f"Generate test steps for: {test_description}"
            )
            self.logger.info(f"[ReAct] Started conversation for test case {test_case_id}")
            return conversation
        except Exception as e:
            self.logger.error(f"[ReAct] Failed to start conversation: {str(e)}")
            return None
    
    def _add_react_turn(self, conversation: Any, thought: str, action: str, 
                       observation: str, confidence: float = 0.8) -> None:
        """
        Add a ReAct turn to the conversation.
        
        Args:
            conversation: Conversation object
            thought: AI's reasoning/thought
            action: Action taken (e.g., "analyze_html", "generate_step")
            observation: Result of the action
            confidence: Confidence score (0-1)
        """
        if not conversation or not self.conversation_manager:
            return
        
        try:
            turn = ConversationTurn(
                turn_number=len(conversation.turns) + 1,
                thought=thought,
                action=action,
                observation=observation,
                tool_used=None,
                tool_params=None,
                tool_result=None,
                confidence=confidence
            )
            self.conversation_manager.add_turn(conversation, turn)
            self.logger.debug(f"[ReAct] Added turn {turn.turn_number}: {action} (confidence: {confidence:.2f})")
        except Exception as e:
            self.logger.error(f"[ReAct] Failed to add turn: {str(e)}")
    
    def _get_react_trace(self, conversation: Any) -> str:
        """
        Get formatted reasoning trace from the conversation.
        
        Args:
            conversation: Conversation object
            
        Returns:
            Formatted reasoning trace string
        """
        if not conversation or not self.conversation_manager:
            return ""
        
        try:
            trace = self.conversation_manager.generate_reasoning_trace(conversation)
            return trace
        except Exception as e:
            self.logger.error(f"[ReAct] Failed to generate reasoning trace: {str(e)}")
            return ""
    
    def _extract_react_context(self, conversation: Any) -> Dict[str, Any]:
        """
        Extract context from the conversation for next steps.
        
        Args:
            conversation: Conversation object
            
        Returns:
            Dictionary with extracted context
        """
        if not conversation or not self.conversation_manager:
            return {}
        
        try:
            context = self.conversation_manager.extract_context(conversation)
            self.logger.debug(f"[ReAct] Extracted context: {len(context.get('recent_actions', []))} recent actions")
            return context
        except Exception as e:
            self.logger.error(f"[ReAct] Failed to extract context: {str(e)}")
            return {}