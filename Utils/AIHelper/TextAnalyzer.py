from contextlib import contextmanager

from fastapi import UploadFile

from Utils.AIHelper.AIHelper import AIHelper
from Utils.System import System


class TextAnalyzer(AIHelper):
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

    def check_test_case_exists(self, name, description):
        with self.get_db_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute('''
                    SELECT id FROM test_cases
                    WHERE name = %s AND description = %s
                ''', (name, description))
                result = cursor.fetchone()

        return result

    def get_max_test_case_id(self):
        with self.get_db_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute('''
                    SELECT MAX(test_case_id) FROM test_cases
                ''')
                result = cursor.fetchone()[0]
                return result if result else 1  # Return 0 if no test_case_id exists

    def insert_test_case(self, name, description, parent_id, type_, order_, test_case_id=None, client_id=None):
        """Insert a test case and return its ID."""
        # Set parent_id to None if it is 0 (indicating no parent)
        if parent_id == 0:
            parent_id = None

        # Check if the test case already exists
        existing_id = self.check_test_case_exists(name, description)
        if existing_id:
            self.logger.info(f"Test case '{name}' already exists. Returning existing ID.")
            return existing_id[0]  # Return the existing ID

        with self.get_db_connection() as connection:
            with connection.cursor() as cursor:
                # Verify parent_id exists if it's not None
                if parent_id is not None:
                    cursor.execute('SELECT id FROM test_cases WHERE id = %s', (parent_id,))
                    if not cursor.fetchone():
                        self.logger.error(f"Parent ID {parent_id} does not exist")
                        return None

                self.logger.info('Inserting test case')
                cursor.execute('''
                    INSERT INTO test_cases (name, description, parent_id, type, "order", test_case_id, client_id)
                    VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id
                ''', (name, description, parent_id, type_, order_, test_case_id, client_id))

                connection.commit()  # Explicitly commit the transaction
                return cursor.fetchone()[0]

    def save_test_cases(self, test_cases, parent_id=None, type_='root', client_id=None):
        """Recursively save test cases and their children."""
        if not isinstance(test_cases, list):
            self.logger.error(f"Expected list of test cases, got {type(test_cases)}")
            return

        for idx, test_case in enumerate(test_cases, 1):
            try:
                name = test_case.get('name', '')
                description = test_case.get('description', '')
                test_type = test_case.get('type', type_)

                # Insert the test case and get its ID
                new_id = self.insert_test_case(
                    name=name,
                    description=description,
                    parent_id=parent_id,
                    type_=test_type,
                    order_=idx,
                    client_id=client_id
                )

                if new_id is None:
                    self.logger.error(f"Failed to insert test case: {name}")
                    continue

                # Recursively handle children only if new_id is valid
                if new_id and 'children' in test_case and test_case['children']:
                    self.save_test_cases(test_case['children'], new_id, test_type, client_id)

            except Exception as e:
                self.logger.error(f"Error processing test case: {str(e)}")
                continue

    def analyze_txt(self, file_content: bytes, client_id: int = None) -> bool:
        text_content = file_content.decode('utf-8')
        genai_response = self.send_request_to_gemini(prompt=self.get_analyze_txt_promt(text_content=text_content))
        self.save_test_cases(genai_response, client_id=client_id)
        return True