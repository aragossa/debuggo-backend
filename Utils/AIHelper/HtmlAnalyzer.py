import psycopg2

from datetime import datetime
from typing import Dict, Any

from Utils.AIHelper.AIHelper import AIHelper
from Utils.System import System

from contextlib import contextmanager

class HtmlAlanyzer(AIHelper):
    def __init__(self):
        super().__init__()
        self.system = System()

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


    def save_step(self, test_case_id: int, step_order: int, element_purpose: str, ai_response: Dict[str, Any]) -> int:
        try:
            with self.get_db_connection() as connection:
                with connection.cursor() as cursor:
                    insert_query = """
                        INSERT INTO public.test_steps (
                            test_case_id,
                            step_order,
                            description,
                            action,
                            element_path,
                            path_type,
                            created_at,
                            updated_at
                        ) VALUES (
                            %s, %s, %s, %s, %s, %s, %s, %s
                        ) RETURNING id;
                    """

                    current_timestamp = datetime.now()

                    cursor.execute(
                        insert_query,
                        (
                            test_case_id,
                            step_order,
                            element_purpose,
                            ai_response['action'],
                            ai_response['element_locator'],
                            ai_response['by_strategy'],
                            current_timestamp,
                            current_timestamp
                        )
                    )

                    new_step_id = cursor.fetchone()[0]
                    connection.commit()

                    self.logger.info(f"Successfully saved test step with ID: {new_step_id}")
                    return new_step_id

        except psycopg2.Error as e:
            self.logger.error(f"Database error while saving test step: {str(e)}")
            raise
        except Exception as e:
            self.logger.error(f"Unexpected error while saving test step: {str(e)}")
            raise


    def html_analyzer(self, html_code: str, element_purpose: str, test_case_id: int, step_order: int) -> Dict[str, Any]:

        self.logger.info("Sending request to AI provider for HTML analysis.")
        prompt = self.get_analyze_html_promt(html_code=html_code, element_purpose=element_purpose)

        if self.provider == "gemini":
            ai_response = self.send_request_to_gemini(prompt)
        # todo: implement sending request to chatgpt, claude
        # elif self.provider == "chatgpt":
        #     response = self._mock_response("ChatGPT", html_code, element_purpose)
        # elif self.provider == "claude":
        #     response = self._mock_response("Claude", html_code, element_purpose)
        else:
            raise ValueError(f"Unsupported AI provider: {self.provider}")

        self.logger.info(f"Received response from {self.provider}: {ai_response}")

        # Save the step to database
        step_id = self.save_step(
            test_case_id=test_case_id,
            step_order=step_order,
            element_purpose=element_purpose,
            ai_response=ai_response
        )

        # Return both the AI response and the new step ID
        return {
            "step_id": step_id
        }

if __name__ == "__main__":
    system = System()

    # Initialize AIHelper with the default provider
    ai_helper = HtmlAlanyzer()

    # Analyze HTML
    html_code = "<button data-purpose='submit_button'>Submit</button>"
    element_purpose = "Submit button"
    response = ai_helper.html_analyzer(html_code, element_purpose, 385, 1)

    # Output the result
    print("AI Analysis Result:", response)