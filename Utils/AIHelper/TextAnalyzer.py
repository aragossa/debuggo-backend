from contextlib import contextmanager
import uuid

from fastapi import UploadFile

from auroqa.Utils.AIHelper.AIHelper import AIHelper
from auroqa.Utils.System import System


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

    def insert_test_case(self, name, description, parent_id, type_, order_, test_case_id=None, client_id=None, project_id=None, test_type='ui'):
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
                    INSERT INTO test_cases (name, description, parent_id, type, "order", test_case_id, client_id, project_id, test_type)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id
                ''', (name, description, parent_id, type_, order_, test_case_id, client_id, project_id, test_type))

                connection.commit()  # Explicitly commit the transaction
                return cursor.fetchone()[0]

    def save_test_cases(self, test_cases, parent_id=None, type_='root', client_id=None, project_id=None):
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
                    client_id=client_id,
                    project_id=project_id,
                    test_type='ui'  # Screenshot-based test cases are always UI tests
                )

                if new_id is None:
                    self.logger.error(f"Failed to insert test case: {name}")
                    continue

                # Recursively handle children only if new_id is valid
                if new_id and 'children' in test_case and test_case['children']:
                    self.save_test_cases(test_case['children'], new_id, test_type, client_id, project_id)

            except Exception as e:
                self.logger.error(f"Error processing test case: {str(e)}")
                continue

    def analyze_txt(self, file_content: bytes, client_id: int = None, project_id: str = None):
        # Generate unique job ID for tracking all AI requests in this analysis
        generation_job_id = str(uuid.uuid4())
        self.logger.info(f"Analyzing text with Job ID: {generation_job_id}")
        
        text = file_content.decode('utf-8')
        genai_response = self.send_request_to_gemini(
            prompt=self.get_analyze_txt_promt(text), 
            text_content=text,
            request_type='text_analysis',
            request_context=f'project_{project_id}',
            client_id=client_id,
            generation_job_id=generation_job_id
        )
        self.save_test_cases(genai_response, client_id=client_id, project_id=project_id)
        return True

    def analyze_api_schema(self, file_content: bytes, client_id: int = None, project_id: str = None, file_name: str = None):
        """Analyze API schema files (OpenAPI, Swagger, etc.) and generate API test cases."""
        try:
            schema_text = file_content.decode('utf-8')
            
            # First, save the schema to api_schemas table for future use
            self._save_api_schema(schema_text, client_id, project_id, file_name)
            
            # Create API-specific prompt for Gemini
            api_prompt = self.get_analyze_api_schema_prompt(schema_text, file_name)
            
            # Generate unique job ID for tracking all AI requests in this analysis
            generation_job_id = str(uuid.uuid4())
            self.logger.info(f"Analyzing API schema with Job ID: {generation_job_id}")
            
            # Send request to Gemini for API test case generation
            genai_response = self.send_request_to_gemini(
                prompt=api_prompt, 
                text_content=schema_text,
                request_type='api_schema',
                request_context=f'project_{project_id}_schema_{file_name}',
                client_id=client_id,
                generation_job_id=generation_job_id
            )
            
            # Save test cases with API type
            self.save_api_test_cases(genai_response, client_id=client_id, project_id=project_id)
            
            return True
        except Exception as e:
            self.logger.error(f"Error analyzing API schema: {str(e)}")
            return False
    
    def _save_api_schema(self, schema_content: str, client_id: str, project_id: str, file_name: str):
        """Save API schema to database for future test step generation."""
        try:
            from auroqa.Utils.Connectors.db_utils import get_db_connection_context
            
            # Determine schema type from file extension or content
            schema_type = 'openapi'
            if file_name:
                if 'swagger' in file_name.lower():
                    schema_type = 'swagger'
                elif 'postman' in file_name.lower():
                    schema_type = 'postman'
            
            # Extract schema name from filename
            schema_name = file_name.replace('.json', '').replace('.yaml', '').replace('.yml', '').replace('-', ' ').title() if file_name else 'API Schema'
            
            with get_db_connection_context() as conn:
                with conn.cursor() as cursor:
                    # Check if schema already exists for this project
                    cursor.execute("""
                        SELECT id FROM api_schemas 
                        WHERE project_id = %s AND client_id = %s AND name = %s
                    """, (project_id, client_id, schema_name))
                    
                    existing = cursor.fetchone()
                    
                    if existing:
                        # Update existing schema
                        schema_id = existing[0]
                        cursor.execute("""
                            UPDATE api_schemas 
                            SET content = %s, schema_type = %s, updated_at = CURRENT_TIMESTAMP
                            WHERE id = %s
                        """, (schema_content, schema_type, existing[0]))
                        self.logger.info(f"Updated existing API schema: {schema_name}")
                    else:
                        # Insert new schema
                        cursor.execute("""
                            INSERT INTO api_schemas (
                                project_id, client_id, name, description, 
                                schema_type, content
                            ) VALUES (%s, %s, %s, %s, %s, %s)
                            RETURNING id
                        """, (
                            project_id,
                            client_id,
                            schema_name,
                            f"Auto-uploaded from {file_name}",
                            schema_type,
                            schema_content
                        ))
                        schema_id = cursor.fetchone()[0]
                        self.logger.info(f"Saved API schema to database with ID: {schema_id}")
                    
                    conn.commit()
            
            # Keep the library of API calls in step with the stored schema
            from auroqa.Services.ApiOperationLibrary import sync_operations
            sync_operations(schema_id)
                    
        except Exception as e:
            self.logger.error(f"Error saving API schema: {str(e)}")
            # Don't fail the whole process if schema save fails
            pass

    def get_analyze_api_schema_prompt(self, schema_text: str, file_name: str = None):
        """Generate a prompt for analyzing API schemas."""
        return f"""
        You are an expert API test automation engineer. Analyze the following API schema and generate comprehensive test case flows.

        File: {file_name or 'API Schema'}
        
        Schema Content:
        {schema_text}

        Instructions:
        1. Analyze the API schema to identify endpoints, operations, and data models
        2. Generate test case flows that cover related operations (not individual endpoints)
        3. Create authentication flows if authentication is required
        4. Generate test cases for CRUD operations, error scenarios, and edge cases
        5. Each test case should have a clear name and description
        6. Organize test cases in logical groups/folders

        Return the response as a JSON array with this structure:
        [
            {{
                "name": "Test Case or Group Name",
                "description": "Description of what this tests",
                "type": "test",  // or "group" for folders
                "test_type": "api",  // Always set to "api" for API tests
                "children": []  // For groups, can contain nested test cases
            }}
        ]

        Generate COMPREHENSIVE test coverage with MULTIPLE test cases per endpoint:

        **Authentication & Authorization (generate 5-7 test cases):**
        - Valid login, invalid credentials, missing fields, expired tokens, unauthorized access, token refresh
        
        **CRUD Operations (generate 4-6 test cases PER endpoint):**
        - CREATE: valid data, missing required fields, invalid types, duplicates
        - READ: single item, list with pagination, filtering, non-existent ID
        - UPDATE: full update, partial update, invalid ID, concurrent updates
        - DELETE: valid deletion, non-existent ID, cascading deletes
        
        **Data Validation (generate 6-8 test cases per endpoint with input):**
        - Required fields missing, invalid data types, length limits (min/max)
        - Format validation (email, phone, URL, date), special characters, unicode
        - SQL injection attempts, XSS attempts
        
        **Pagination & Filtering (generate 5-7 test cases for list endpoints):**
        - First/last/middle page, page size limits (1, 10, 100, 1000)
        - Invalid page numbers, sorting (asc/desc), filtering, search
        
        **Error Scenarios (generate 8-10 test cases):**
        - 400 Bad Request, 401 Unauthorized, 403 Forbidden, 404 Not Found
        - 409 Conflict, 422 Unprocessable Entity, 500 Server Error
        - Network timeouts, malformed JSON
        
        **Edge Cases (generate 6-8 test cases):**
        - Empty body, null values, very large payloads, very long strings
        - Boundary values (0, -1, MAX_INT), special dates, concurrent requests
        - Rate limiting, duplicate submissions
        
        **Business Workflows (generate 4-6 test case sequences):**
        - Complete workflows (create → read → update → delete)
        - State transitions, dependent resources, cascading operations
        - Transaction rollbacks, partial failures
        
        IMPORTANT: Generate AT LEAST 10-15 test cases per major endpoint.
        For a schema with 20 endpoints, aim for 200-300 total test cases.
        Prioritize practical, real-world scenarios that catch actual bugs.
        """

    def save_api_test_cases(self, test_cases, parent_id=None, type_='root', client_id=None, project_id=None):
        """Save API test cases with proper API test type."""
        if not isinstance(test_cases, list):
            self.logger.error(f"Expected list of test cases, got {type(test_cases)}")
            return

        for idx, test_case in enumerate(test_cases, 1):
            try:
                name = test_case.get('name', '')
                description = test_case.get('description', '')
                test_type = test_case.get('type', type_)

                # Insert the test case and get its ID - IMPORTANT: Set test_type='api'
                new_id = self.insert_test_case(
                    name=name,
                    description=description,
                    parent_id=parent_id,
                    type_=test_type,
                    order_=idx,
                    client_id=client_id,
                    project_id=project_id,
                    test_type='api'  # API schema-based test cases are always API tests
                )

                if new_id is None:
                    self.logger.error(f"Failed to insert API test case: {name}")
                    continue

                # Recursively handle children only if new_id is valid
                if new_id and 'children' in test_case and test_case['children']:
                    self.save_api_test_cases(test_case['children'], new_id, test_type, client_id, project_id)

            except Exception as e:
                self.logger.error(f"Error processing API test case: {str(e)}")
                continue