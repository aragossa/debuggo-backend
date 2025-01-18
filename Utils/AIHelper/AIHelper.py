import google.generativeai as genai
import google
import json
import logging
from typing import Literal, Dict, Any

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


    def send_request_to_gemini(self, promt: str) -> Dict[str, Any]:
        if not self.gemini_api_key:
            raise ValueError("Gemini API key is required to send requests to Gemini.")


        model = genai.GenerativeModel("gemini-2.0-flash-exp")
        genai.configure(api_key=self.gemini_api_key)
        for i in range(5):
            try:
                response = model.generate_content([promt])
                self.logger.info(response)
                break
            except google.api_core.exceptions.InternalServerError as e:
                self.logger.info(e)
                continue
            except google.api_core.exceptions.DeadlineExceeded as e:
                self.logger.info(e)
                continue


        try:
            valid_json = response.text.replace("`", "").replace("json", "")
            response_json = json.loads(valid_json)
            return response_json

        except ValueError as e:
            return False

    def send_message_to_claude(self, prompt):
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

        payload = {
            "model": "claude-3-opus-20240229",
            "max_tokens": 4096,
            "messages": [
                {
                    "role": "user",
                    "content": prompt
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
