import base64
from io import BytesIO

import google.generativeai as genai
import google
import json
import logging
from typing import Literal, Dict, Any, Union, Optional
from PIL import Image

import requests

from Utils.System import System


class AIHelper:
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
        """
        Set up a logger for AIHelper.

        Returns:
            logging.Logger: Configured logger instance.
        """
        logger = logging.getLogger("AIHelper")
        logger.setLevel(logging.INFO)

        handler = logging.StreamHandler()
        handler.setLevel(logging.INFO)
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        handler.setFormatter(formatter)
        logger.addHandler(handler)

        return logger

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

    def get_analyze_html_promt(self, html_code: str, test_name: str, test_description: str, step_order: int, next_prompt: str, prev_step_description: str):
        response_format = """
        {
          "element_locator": "xpath or css locator",
          "by_strategy": "css or xpath",
          "action": "click, type, select, hover, wait, assert, scroll, clear, navigate, press_key",
          "element_purpose": "Describe the assertion purpose, e.g.: 'verify error message is displayed', 'check if button is enabled'",
          "value": "For assertions, use one of the following formats:
                   - Just text to verify element text content
                   - visible=true/false to check element visibility
                   - enabled=true/false to check if element is enabled
                   - selected=true/false to check checkbox/radio selection
                   - value=expected_value to check input/field value",
          "next_step": "Prompt for the next action or 'Stop' if test is complete"
        }
        """
        prev_step_prompt = ''
        if prev_step_description != '':
            prev_step_prompt = f'. Take in account that previous step was {prev_step_description}'

        skip_start_navigate = ''
        if step_order == 0:
            skip_start_navigate = ". Skip the step with navigating to the first page.\n"

        text_prompt = (
            f"Act as an experienced QA engineer, you are creating {test_name} {test_description} {next_prompt if next_prompt is not None else ''}."
            f"You should recursively go through all test steps and on each step you should assume next step until the test will be finished\n"
            "If current step will be final step, put to the next_step attribute the word 'Stop'\n"
            f"You are on the test step # {step_order}{prev_step_prompt}{skip_start_navigate}\n"
                "When performing assertions, consider the following validation patterns:\n"
                "- Verify presence and text content of error messages, success messages, or labels\n"
                "- Check if buttons or forms are enabled/disabled after certain actions\n"
                "- Validate if elements are visible/hidden based on user interactions\n"
                "- Confirm correct values in input fields, dropdowns, or other form elements\n"
                "- Verify selected state of checkboxes and radio buttons\n"
            f"Analyze the provided HTML code of a web page to identify an element that possible to be used on this step\n"
            f"HTML Code:\n{html_code}\n"
            "Provide your response **only** in JSON format without any additional explanation. Follow this format strictly:\n"
            f"{response_format}"
        )
        return text_prompt

    def switch_provider(self, provider: Literal["chatgpt", "gemini", "claude", "deepseek"]):
        """
        Switch the AI provider.

        Args:
            provider (str): The new AI provider to use ("ChatGPT", "Gemini", "Claude", "Deepseek").
        """
        self.provider = provider.lower()
        self.logger.info(f"Switched to provider: {self.provider}")

    def send_request_to_gemini(self, prompt: str, image: Optional[Image.Image] = None, text_content: str = None) -> Union[bool, Any]:
        if not self.gemini_api_key:
            raise ValueError("Gemini API key is required to send requests to Gemini.")
        model = genai.GenerativeModel("gemini-2.0-flash-exp")
        genai.configure(api_key=self.gemini_api_key)
        response = None
        for i in range(5):
            try:
                if image:
                    response = model.generate_content([prompt, image])
                else:
                    response = model.generate_content(prompt)
                break
            except google.api_core.exceptions.InternalServerError as e:
                self.logger.info(e)
                continue
            except google.api_core.exceptions.DeadlineExceeded as e:
                self.logger.info(e)
                continue
        if not response:
            raise RuntimeError('Unable to send request')
        try:
            valid_json = response.text.replace("`", "").replace("json", "").strip()
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
            self.logger.error(f"Raw response: {response.text}")
            raise ValueError('Cannot parse the response')

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
        if image.size[0] > max_size[0] or image.size[1] > max_size[1]:
            image.thumbnail(max_size, Image.Resampling.LANCZOS)

        # Convert to RGB if necessary (removing alpha channel)
        if image.mode in ('RGBA', 'LA'):
            background = Image.new('RGB', image.size, (255, 255, 255))
            background.paste(image, mask=image.split()[-1])
            image = background

        # Convert Image to base64 with compression
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
