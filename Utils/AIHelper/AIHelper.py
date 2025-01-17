import google.generativeai as genai
import google
import json
import logging
from typing import Literal, Dict, Any

import requests

from Utils.System import System


class AIHelper:
    def __init__(self, provider: Literal["chatgpt", "gemini", "claude"] = "gemini"):
        """
        Initialize the AIHelper with a specified AI provider and optional Gemini API key.

        Args:
            provider (str): The AI provider to use ("ChatGPT", "Gemini", "Claude").
            gemini_api_key (str): The API key for Gemini (if applicable).
        """
        system = System()
        self.provider = provider.lower()
        self.gemini_api_key = system.gemini_api_key
        self.claude_api_key = system.claude_api_key
        self.logger = self._setup_logger()
        self.logger.info(f"Initialized AIHelper with provider: {self.provider}")


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
                break
            except google.api_core.exceptions.InternalServerError:
                continue
            except google.api_core.exceptions.DeadlineExceeded:
                continue

            finally:
                raise UserWarning("Unable to connect to Gemini right now")
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
