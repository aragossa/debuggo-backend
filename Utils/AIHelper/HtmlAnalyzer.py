import google.generativeai as genai
import google
import json
import logging
from typing import Literal, Dict, Any

from Utils.AIHelper.AIHelper import AIHelper
from Utils.System import System


class HtmlAlanyzer(AIHelper):
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
        prompt = self.get_analyze_html_promt(html_code=html_code, element_purpose=element_purpose)

        if self.provider == "gemini":
            response = self.send_request_to_gemini(prompt)
        # elif self.provider == "chatgpt":
        #     response = self._mock_response("ChatGPT", html_code, element_purpose)
        # elif self.provider == "claude":
        #     response = self._mock_response("Claude", html_code, element_purpose)
        else:
            raise ValueError(f"Unsupported AI provider: {self.provider}")

        self.logger.info(f"Received response from {self.provider}: {response}")
        return response




if __name__ == "__main__":
    system = System()

    # Initialize AIHelper with the default provider
    ai_helper = HtmlAlanyzer(provider=system.ai_model)

    # Analyze HTML
    html_code = "<button data-purpose='submit_button'>Submit</button>"
    element_purpose = "Submit button"
    response = ai_helper.html_analyzer(html_code, element_purpose)

    # Output the result
    print("AI Analysis Result:", response)