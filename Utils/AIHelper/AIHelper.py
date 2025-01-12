import google.generativeai as genai
import google
import json
import logging
from typing import Literal, Dict, Any

from Utils.System import System


class AIHelper:
    def __init__(self, provider: Literal["ChatGPT", "Gemini", "Claude"] = "ChatGPT", gemini_api_key: str = None):
        """
        Initialize the AIHelper with a specified AI provider and optional Gemini API key.

        Args:
            provider (str): The AI provider to use ("ChatGPT", "Gemini", "Claude").
            gemini_api_key (str): The API key for Gemini (if applicable).
        """
        system = System()
        self.provider = provider
        self.gemini_api_key = system.gemini_api_key
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

    def switch_provider(self, provider: Literal["ChatGPT", "Gemini", "Claude"]):
        """
        Switch the AI provider.

        Args:
            provider (str): The new AI provider to use ("ChatGPT", "Gemini", "Claude").
        """
        self.provider = provider
        self.logger.info(f"Switched AI provider to: {self.provider}")

    def html_analyzer(self, html_code: str, element_purpose: str) -> Dict[str, Any]:
        """
        Analyze HTML code and generate an element locator based on its purpose.

        Args:
            html_code (str): The HTML code to analyze.
            element_purpose (str): The purpose of the element to locate (e.g., "Submit button", "Search bar").

        Returns:
            Dict[str, Any]: A dictionary containing the element locator and any relevant metadata.
        """
        self.logger.info("Sending request to AI provider for HTML analysis.")

        # Placeholder logic to mimic AI provider interaction
        if self.provider == "ChatGPT":
            response = self._mock_response("ChatGPT", html_code, element_purpose)
        elif self.provider == "Gemini":
            response = self.send_request_to_gemini(html_code, element_purpose)
        elif self.provider == "Claude":
            response = self._mock_response("Claude", html_code, element_purpose)
        else:
            raise ValueError(f"Unsupported AI provider: {self.provider}")

        self.logger.info(f"Received response from {self.provider}: {response}")
        return response

    def send_request_to_gemini(self, html_code: str, element_purpose: str) -> Dict[str, Any]:
        """
        Send a request to Gemini API for analyzing HTML code.

        Args:
            html_code (str): The HTML code to analyze.
            element_purpose (str): The purpose of the element to locate (e.g., "Submit button").

        Returns:
            Dict[str, Any]: The response from Gemini API containing element locator details.
        """
        if not self.gemini_api_key:
            raise ValueError("Gemini API key is required to send requests to Gemini.")

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

        model = genai.GenerativeModel("gemini-2.0-flash-exp")
        for i in range(5):
            try:
                response = model.generate_content([text_prompt])
                break
            except google.api_core.exceptions.InternalServerError:
                continue
            except google.api_core.exceptions.DeadlineExceeded:
                continue
        try:
            valid_json = response.text.replace("`", "").replace("json", "")
            response_json = json.loads(valid_json)
            print(response_json)

        except ValueError as e:
            return False

if __name__ == "__main__":
    # Initialize AIHelper with the default provider
    ai_helper = AIHelper(provider="ChatGPT")

    # Switch provider if needed
    ai_helper.switch_provider("Claude")

    # Analyze HTML
    html_code = "<button data-purpose='submit_button'>Submit</button>"
    element_purpose = "Submit button"
    response = ai_helper.html_analyzer(html_code, element_purpose)

    # Output the result
    print("AI Analysis Result:", response)