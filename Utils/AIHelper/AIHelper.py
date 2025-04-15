import base64
import sys
from io import BytesIO
import time
import google.generativeai as genai
import google
import json
import logging
from typing import Literal, Dict, Any, Union, Optional
from PIL import Image
import threading
import requests

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

TEST DESCRIPTION: {test_description}

You should recursively go through all test steps and on each step you should assume next step until the test will be finished.
If current step will be final step, put to the next_step attribute the word 'Stop'.
You are on the test step # {step_order}{prev_step_prompt}{skip_start_navigate}
{step_history}

IMPORTANT GUIDELINES:
1. FOLLOW THE TEST DESCRIPTION PRECISELY - The test steps must implement exactly what is described in the test description.
2. LOGIN HANDLING - If login is required, use environment variables:
  - Use {{base_url}} for the base URL
   - First locate and interact with the username/email field, using {{login}} as the value
   - Then locate and interact with the password field, using {{password}} as the value
   - Only after both fields are filled, locate and click the login/submit button
   - ENSURE login is successful before proceeding with any subsequent steps
   - NEVER skip the password field even if it appears to be optional
3. SEQUENTIAL EXECUTION - All steps after login must only be executed after successful login verification

FORM COMPLETION REQUIREMENTS:
1. When filling out forms, ALWAYS complete ALL available fields before submission
2. For login forms specifically:
   - FIRST step: Locate and fill the username/email field with {{login}}
   - SECOND step: Locate and fill the password field with {{password}}
   - THIRD step: Click the login/submit button
   - These steps MUST be performed as separate actions in this exact sequence
3. NEVER combine multiple form field actions into a single step
4. NEVER skip form fields, especially password fields

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

    def send_request_to_gemini(self, prompt: str, image: Optional[Image.Image] = None, text_content: str = None) -> Union[bool, Any]:
        if not self.gemini_api_key:
            raise ValueError("Gemini API key is required to send requests to Gemini.")
        
        self._wait_for_rate_limit()
        
        model = genai.GenerativeModel("gemini-2.5-pro-exp-03-25")
        genai.configure(api_key=self.gemini_api_key)
        response = None
        max_retries = 5
        base_delay = 2  # Start with 2 seconds delay
        for attempt in range(max_retries):
            try:
                # Wait for rate limit before each attempt
                if attempt > 0:
                    self._wait_for_rate_limit()
                
                if image:
                    self.logger.info(f"Sending prompt to Gemini with image")
                    response = model.generate_content([prompt, image])
                else:
                    self.logger.info(f"Sending prompt to Gemini")
                    response = model.generate_content(prompt)
                # Get the response text
                response_text = response.text.strip()
                
                self.logger.info("=== RAW GEMINI RESPONSE START ===")
                self.logger.info(f"Raw response text (first 1000 chars):\n{response_text[:1000]}")
                if len(response_text) > 1000:
                    self.logger.info(f"... and {len(response_text) - 1000} more characters")
                self.logger.info("=== RAW GEMINI RESPONSE END ===")

                # Try to parse as JSON
                try:
                    self.logger.info("Attempting to parse response as JSON...")
                    parsed_response = json.loads(response_text)
                    self.logger.info("Successfully parsed JSON response")
                    self.logger.info(f"Parsed structure: {json.dumps(parsed_response, indent=2)}")
                    return parsed_response
                except json.JSONDecodeError as e:
                    self.logger.info(f"Direct JSON parsing failed: {str(e)}")
                    self.logger.info("Checking for JSON in code blocks...")

                    # If JSON parsing fails, check if it's in a code block
                    if "```json" in response_text:
                        json_content = response_text.split("```json")[1].split("```")[0].strip()
                        try:
                            parsed_response = json.loads(json_content)
                            self.logger.info(f"Parsed structure: {json.dumps(parsed_response, indent=2)}")
                            return parsed_response
                        except json.JSONDecodeError as e:
                            self.logger.error(f"Failed to parse JSON from code block: {str(e)}")
                            raise
                    elif "```" in response_text:
                        # Try extracting from any code block
                        json_content = response_text.split("```")[1].strip()
                        self.logger.info(f"Extracted content from code block:\n{json_content}")
                        try:
                            parsed_response = json.loads(json_content)
                            self.logger.info(f"Parsed structure: {json.dumps(parsed_response, indent=2)}")
                            return parsed_response
                        except json.JSONDecodeError as e:
                            self.logger.error(f"Failed to parse JSON from generic code block: {str(e)}")
                            raise

                    self.logger.error("No valid JSON found in code blocks")
                    self.logger.error(f"Raw response that failed parsing: {response_text}")
                    raise ValueError('Cannot parse the response')
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
                    delay = base_delay * (2 ** attempt)  # Exponential backoff
                    self.logger.warning(f"Additional backoff: {delay} seconds")
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
