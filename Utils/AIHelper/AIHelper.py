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
                                   "type": "test",
                                   "steps": [
                                       {
                                           "description": "Navigate to the page ...",
                                           "expected_result": "The page ... is opened"
                                       },
                                       {
                                           "description": "Click on the button ...",
                                           "expected_result": "User navigated to the page"
                                       },
                                       {
                                           "description": "Put text to the field",
                                           "expected_result": "Text is in the field"
                                       },
                                       {
                                           "description": "Press ENTER",
                                           "expected_result": "Filed saved"
                                       }
                                   ]
                               },
                               {
                                   "id": 4,
                                   "name": "Test case name",
                                   "description": "Test description",
                                   "expected_result": "Test expected result",
                                   "type": "test",
                                   "steps": [
                                       {
                                           "description": "Navigate to the page ...",
                                           "expected_result": "The page ... is opened"
                                       },
                                       {
                                           "description": "Click on the button ...",
                                           "expected_result": "User navigated to the page"
                                       },
                                       {
                                           "description": "Put text to the field",
                                           "expected_result": "Text is in the field"
                                       },
                                       {
                                           "description": "Press ENTER",
                                           "expected_result": "Filed saved"
                                       }
                                   ]
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
                                   "steps": [
                                       {
                                           "description": "Navigate to the page ...",
                                           "expected_result": "The page ... is opened"
                                       },
                                       {
                                           "description": "Click on the button ...",
                                           "expected_result": "User navigated to the page"
                                       },
                                       {
                                           "description": "Put text to the field",
                                           "expected_result": "Text is in the field"
                                       },
                                       {
                                           "description": "Press ENTER",
                                           "expected_result": "Filed saved"
                                       }
                                   ]
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
            "Give me detailed test steps, each action should be as a separated step (like put value in a field, click button etc.) each step should be an action for selenium tests\n"
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
                                   "type": "test",
                                   "steps": [
                                       {
                                           "description": "Navigate to the page ...",
                                           "expected_result": "The page ... is opened"
                                       },
                                       {
                                           "description": "Click on the button ...",
                                           "expected_result": "User navigated to the page"
                                       },
                                       {
                                           "description": "Put text to the field",
                                           "expected_result": "Text is in the field"
                                       },
                                       {
                                           "description": "Press ENTER",
                                           "expected_result": "Filed saved"
                                       }
                                   ]
                               },
                               {
                                   "id": 4,
                                   "name": "Test case name",
                                   "description": "Test description",
                                   "expected_result": "Test expected result",
                                   "type": "test",
                                   "steps": [
                                       {
                                           "description": "Navigate to the page ...",
                                           "expected_result": "The page ... is opened"
                                       },
                                       {
                                           "description": "Click on the button ...",
                                           "expected_result": "User navigated to the page"
                                       },
                                       {
                                           "description": "Put text to the field",
                                           "expected_result": "Text is in the field"
                                       },
                                       {
                                           "description": "Press ENTER",
                                           "expected_result": "Filed saved"
                                       }
                                   ]
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
                                   "steps": [
                                       {
                                           "description": "Navigate to the page ...",
                                           "expected_result": "The page ... is opened"
                                       },
                                       {
                                           "description": "Click on the button ...",
                                           "expected_result": "User navigated to the page"
                                       },
                                       {
                                           "description": "Put text to the field",
                                           "expected_result": "Text is in the field"
                                       },
                                       {
                                           "description": "Press ENTER",
                                           "expected_result": "Filed saved"
                                       }
                                   ]
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

    def get_analyze_html_promt(self, html_code: str, element_purpose: str):
        response_format = """
        {
          "element_locator": "xpath or css locator",
          "by_strategy": "css or xpath",
          "action": "click, type, select, hover, wait, assert, scroll, clear, navigate, press_key"
        }
        """

        text_prompt = (
            f"Act as an experienced QA engineer. Analyze the provided HTML code of a web page to identify an element responsible for: {element_purpose}.\n\n"
            f"HTML Code:\n{html_code}\n\n"
            "Provide your response **only** in JSON format without any additional explanation. Follow this format strictly:\n"
            f"{response_format}"
        )
        return text_prompt

    def switch_provider(self, provider: Literal["chatgpt", "gemini", "claude"]):
        """
        Switch the AI provider.

        Args:
            provider (str): The new AI provider to use ("ChatGPT", "Gemini", "Claude").
        """
        self.provider = provider.lower()
        self.logger.info(f"Switched AI provider to: {self.provider}")

    def send_request_to_gemini(self, prompt: str, image: Optional[Image.Image] = None, text_content: str = None) -> Union[bool, Any]:
        if not self.gemini_api_key:
            raise ValueError("Gemini API key is required to send requests to Gemini.")
        model = genai.GenerativeModel("gemini-2.0-flash-exp")
        genai.configure(api_key=self.gemini_api_key)
        response = None
        for i in range(5):
            try:
                if image:
                    # model = genai.GenerativeModel('gemini-pro-vision')
                    response = model.generate_content([prompt, image])
                else:
                    # model = genai.GenerativeModel('gemini-pro')
                    response = model.generate_content(prompt)

                self.logger.info(response)
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
            valid_json = response.text.replace("`", "").replace("json", "")
            response_json = json.loads(valid_json)
            return response_json

        except ValueError:
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
