import requests
import json
from Utils.DbConnector import DbConnector
from Utils.System import System
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Function to check if a test case already exists
def check_test_case_exists(name, description):
    db = DbConnector()
    conn = db.get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT id FROM test_cases
        WHERE name = %s AND description = %s
    ''', (name, description))
    result = cursor.fetchone()
    conn.close()
    return result

# Function to get the maximum test_case_id from the database
def get_max_test_case_id():
    db = DbConnector()
    conn = db.get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT MAX(test_case_id) FROM test_cases
    ''')
    result = cursor.fetchone()[0]
    conn.close()
    return result if result else 0  # Return 0 if no test_case_id exists

def send_message_to_claude(prompt):
    """Send a message to Claude API."""
    system = System()
    if not system.claude_api_key:
        raise ValueError("Claude API key not found in environment configuration")

    if not system.claude_api_key.startswith('sk-'):
        raise ValueError("Invalid API key format. Key should start with 'sk-'")

    headers = {
        "x-api-key": system.claude_api_key,
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

    logger.info("Sending request to Claude API...")
    logger.info(f"Headers: {json.dumps(headers, indent=2)}")
    logger.info(f"Payload: {json.dumps(payload, indent=2)}")

    response = requests.post(
        "https://api.anthropic.com/v1/messages",
        headers=headers,
        json=payload
    )

    logger.info(f"Response status code: {response.status_code}")
    logger.info(f"Response headers: {json.dumps(dict(response.headers), indent=2)}")
    
    if response.status_code != 200:
        logger.error(f"Error response: {response.text}")
        raise Exception(f"Error from Claude API: {response.text}")

    response_json = response.json()
    logger.info(f"Response JSON: {json.dumps(response_json, indent=2)}")

    if "content" not in response_json or not response_json["content"]:
        raise Exception("No content in Claude API response")

    content = response_json["content"][0]["text"]
    logger.info(f"Extracted content: {content}")
    
    return content

def get_test_cases_from_json_claude(text_content):
    # Create a properly escaped example for the model
    example_python_script = '''import requests\\nimport json\\n\\ntry:\\n    url = \\'https://petstore.swagger.io/v2/pet\\'\\n    headers = {\\n        \\'Content-Type\\': \\'application/json\\',\\n        \\'accept\\': \\'application/json\\'\\n    }\\n    data = {\\n        "id": 0,\\n        "category": {"id": 0, "name": "string"},\\n        "name": "doggie",\\n        "photoUrls": ["string"],\\n        "tags": [{"id": 0, "name": "string"}],\\n        "status": "available"\\n    }\\n    \\n    print(f"Making POST request to {url}")\\n    print(f"Headers: {json.dumps(headers, indent=2)}")\\n    print(f"Data: {json.dumps(data, indent=2)}")\\n    \\n    response = requests.post(url, headers=headers, json=data)\\n    \\n    print(f"Response status code: {response.status_code}")\\n    print(f"Response headers: {json.dumps(dict(response.headers), indent=2)}")\\n    print(f"Response body: {json.dumps(response.json(), indent=2) if response.text else \\'\\')\\n    \\n    if response.status_code == 200:\\n        print("Test passed!")\\n    else:\\n        raise Exception(f"Expected status code 200, got {response.status_code}")\\nexcept Exception as e:\\n    print(f"Error: {str(e)}")\\n    raise'''
    
    json_structure = f"""{{
        "name": "API TESTS",
        "type": "root",
        "children": [
            {{
                "name": "Test Group 1",
                "type": "group",
                "children": [
                    {{
                        "name": "Test POST /pet",
                        "description": "Add a new pet to the store",
                        "type": "test",
                        "python_script": "{example_python_script}",
                        "expected_result": "200 OK - Pet created successfully"
                    }}
                ]
            }}
        ]
    }}"""

    text_prompt = f"Act as QA engineer. Analyze attached swagger export file and generate as much as possible test cases for this API.\n" \
                 f"The response must be a valid JSON object following this exact structure, with NO additional text or explanation:\n" \
                 f"{json_structure}\n\n" \
                 f"Important guidelines for generating test cases:\n" \
                 f"1. All Python scripts must be properly escaped in the JSON response\n" \
                 f"2. Use double backslashes for newlines (\\\\n) in Python scripts\n" \
                 f"3. Use single quotes with backslash escaping (\\')\n" \
                 f"4. The response must be valid JSON that can be parsed by json.loads()\n" \
                 f"5. Follow the exact structure of the example\n\n" \
                 f"Here is the schema file to analyze:\n{text_content}"

    try:
        logger.info("\nSending request to Claude...")
        response_text = send_message_to_claude(text_prompt)
        logger.info(f"Characters of response: {response_text}...")
        
        # Clean and parse the JSON response
        test_cases = clean_json_response(response_text)
        logger.info("Successfully parsed JSON response")
        logger.info(f"Test cases structure: {json.dumps(test_cases, indent=2)}")
        
        logger.info("\nSaving test cases to database...")
        save_test_cases(test_cases)
        logger.info("Successfully saved test cases")
        return True
        
    except json.JSONDecodeError as e:
        logger.error(f"\nJSON decode error at position {e.pos}: {e.msg}")
        logger.error(f"Error line: {e.doc[max(0, e.pos-50):min(len(e.doc), e.pos+50)]}")
        return False
    except Exception as e:
        logger.error(f"\nError in get_test_cases_from_json_claude: {str(e)}")
        logger.error(f"Type of error: {type(e)}")
        return False

def clean_json_response(response_text):
    """Clean and format JSON response text."""
    logger.info("Cleaning JSON response...")
    
    # Remove any markdown formatting
    if "```json" in response_text:
        logger.info("Found markdown code block, extracting JSON...")
        parts = response_text.split("```json")
        if len(parts) > 1:
            response_text = parts[1].split("```")[0]
    
    # Remove any leading/trailing whitespace
    response_text = response_text.strip()
    
    try:
        # First try to parse as is
        return json.loads(response_text)
    except json.JSONDecodeError as e:
        logger.info(f"Initial JSON parsing failed: {str(e)}")
        
        try:
            # Try with minimal cleanup
            cleaned_text = response_text.strip()
            if cleaned_text.endswith('...'):
                cleaned_text = cleaned_text[:-3]  # Remove trailing ellipsis
            if cleaned_text.endswith('"'):
                cleaned_text = cleaned_text[:-1]  # Remove trailing quote if not properly terminated
            return json.loads(cleaned_text)
        except json.JSONDecodeError as e:
            logger.info(f"Minimal cleanup failed: {str(e)}")
            
            try:
                # Try with advanced string normalization
                import re
                
                def normalize_escapes(text):
                    """Normalize escape sequences in the text."""
                    # First unescape any double-escaped characters
                    text = text.replace('\\\\', '\u0000')  # Temporarily replace \\ with null char
                    text = text.replace('\\"', '\u0001')   # Temporarily replace \" with start of heading
                    text = text.replace('\\n', '\u0002')   # Temporarily replace \n with start of text
                    
                    # Replace any remaining single backslashes with double backslashes
                    text = text.replace('\\', '\\\\')
                    
                    # Restore the properly escaped sequences
                    text = text.replace('\u0000', '\\\\')  # Restore \\
                    text = text.replace('\u0001', '\\"')   # Restore \"
                    text = text.replace('\u0002', '\\n')   # Restore \n
                    return text
                
                # Handle line continuation characters
                def fix_line_continuation(text):
                    # Replace \\\n with just \n
                    text = re.sub(r'\\\s*\n', '\n', text)
                    # Handle remaining backslashes
                    text = normalize_escapes(text)
                    return text
                
                # First fix line continuations and normalize escapes
                cleaned_text = fix_line_continuation(response_text)
                
                # Normalize newlines and remove carriage returns
                cleaned_text = cleaned_text.replace('\r\n', '\n').replace('\r', '\n')
                
                # Fix any unterminated strings by adding missing quotes
                def fix_unterminated_strings(text):
                    fixed_text = ""
                    in_string = False
                    escape_next = False
                    
                    for i, char in enumerate(text):
                        if char == '\\' and not escape_next:
                            escape_next = True
                        elif char == '"' and not escape_next:
                            in_string = not in_string
                        else:
                            escape_next = False
                            
                        fixed_text += char
                        
                        # If we hit a newline while in a string, terminate the string
                        if char in '\n' and in_string:
                            fixed_text += '"'
                            in_string = False
                    
                    # If we're still in a string at the end, terminate it
                    if in_string:
                        fixed_text += '"'
                    
                    return fixed_text
                
                cleaned_text = fix_unterminated_strings(cleaned_text)
                
                # Remove any trailing commas in arrays and objects
                cleaned_text = re.sub(r',(\s*[}\]])', r'\1', cleaned_text)
                
                # Try to parse with fixed strings
                try:
                    return json.loads(cleaned_text)
                except json.JSONDecodeError:
                    # If that fails, try to truncate at the last complete object/array
                    last_brace = cleaned_text.rfind('}')
                    last_bracket = cleaned_text.rfind(']')
                    truncate_pos = max(last_brace, last_bracket)
                    if truncate_pos > 0:
                        cleaned_text = cleaned_text[:truncate_pos + 1]
                        return json.loads(cleaned_text)
                    raise
                    
            except json.JSONDecodeError as e:
                logger.error(f"All cleanup attempts failed: {str(e)}")
                logger.error(f"Final cleaned text: {cleaned_text[:200]}...")
                raise json.JSONDecodeError(
                    f"Failed to parse JSON after all cleanup attempts: {str(e)}", 
                    response_text, 0
                )

def insert_test_case(name, description, parent_id, type_, order_, python_script=None, test_case_id=None):
    # Skip inserting a case with parent_id of 0
    if parent_id == 0:
        parent_id = None

    db = DbConnector()
    conn = db.get_connection()
    cursor = conn.cursor()

    # Insert the test case
    cursor.execute('''
        INSERT INTO test_cases (name, description, parent_id, type, "order", python_script, test_case_id)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        RETURNING id
    ''', (name, description, parent_id, type_, order_, python_script, test_case_id))

    last_row_id = cursor.fetchone()[0]
    conn.commit()
    conn.close()
    return last_row_id

def insert_test_step(test_case_id, step_order, description, expected_result):
    db = DbConnector()
    conn = db.get_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        INSERT INTO test_steps (test_case_id, step_order, description, expected_result)
        VALUES (%s, %s, %s, %s)
    ''', (test_case_id, step_order, description, expected_result))
    
    conn.commit()
    conn.close()

def save_test_cases(test_cases, parent_id=None, type_='root'):
    if not isinstance(test_cases, dict):
        return False

    name = test_cases.get('name', '')
    description = test_cases.get('description', '')
    elem_type = test_cases.get('type', '')
    python_script = test_cases.get('python_script', None)
    expected_result = test_cases.get('expected_result', None)

    # For 'test' type, assign test_case_id
    test_case_id = None
    if elem_type == 'test':
        test_case_id = get_max_test_case_id() + 1

    # Get the next order number
    order_ = len(test_cases.get('children', []))

    current_id = insert_test_case(
        name=name,
        description=description,
        parent_id=parent_id,
        type_=elem_type,
        order_=order_,
        python_script=python_script,
        test_case_id=test_case_id
    )

    if current_id and elem_type == 'test':
        step_order = 1
        insert_test_step(
            test_case_id=current_id,
            step_order=step_order,
            description=python_script or description,
            expected_result=expected_result
        )

    # Process children
    children = test_cases.get('children', [])
    for child in children:
        save_test_cases(child, current_id, child.get('type', ''))
