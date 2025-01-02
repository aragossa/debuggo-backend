import requests
import json
from Utils.DbConnector import DbConnector

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

def send_message_to_claude(api_key, prompt):
    """Send a message to Claude API."""
    if not api_key:
        raise ValueError("API key is required")

    if not api_key.startswith('sk-'):
        raise ValueError(f"Invalid API key format. Key should start with 'sk-'")

    headers = {
        "x-api-key": api_key,
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
            print(error_msg)
            return {"error": error_msg}

        response_data = response.json()
        print(response.json)
        if "content" in response_data:
            return response_data
        else:
            return {"error": "Unexpected response format from Claude API"}

    except requests.Timeout:
        error_msg = "Request timed out. Please try again."
        print(error_msg)
        return {"error": error_msg}
    except Exception as e:
        error_msg = f"Error making request: {str(e)}"
        print(error_msg)
        if hasattr(e, 'response') and hasattr(e.response, 'text'):
            print(f"Error details: {e.response.text}")
        return {"error": error_msg}

def get_test_cases_from_json(text_content):
    json_structure = """
    [
        {
            "id": 1,
            "name": "API TESTS",
            "type": "root",
            "children": [
                {
                    "id": 2,
                    "name": "Test Group 1",
                    "type": "group",
                    "children": []
                },
                {
                    "id": 3,
                    "name": "Test Group 2",
                    "type": "group",
                    "children": [
                        {
                            "id": 4,
                            "name": "POST short test description",
                            "type": "test",
                            "curl": "curl -X POST http:/..../..../",
                            "expected_result": "Response code; Response body"
                        }
                    ]
                }
            ]
        }
    ]
    """

    text_prompt = (
        f"Act as QA engineer. Analyze attached swagger export file and generate as much as possible test cases for this API.\n"
        f"The response must be a valid JSON array following this exact structure, with NO additional text or explanation:\n"
        f"{json_structure}\n\n"
        f"Here is the schema file to analyze:\n{text_content}"
    )

    api_key = "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"
    
    for i in range(5):  # Retry up to 5 times
        try:
            response = send_message_to_claude(api_key, text_prompt)
            if "error" not in response:
                # Extract the content from Claude's response
                content = response["content"][0]["text"]
                
                # Try to find the JSON array by looking for the first '[' and last ']'
                try:
                    start_idx = content.find('[')
                    end_idx = content.rfind(']')
                    
                    if start_idx != -1 and end_idx != -1:
                        json_content = content[start_idx:end_idx + 1]
                        response_json = json.loads(json_content)
                        
                        if isinstance(response_json, list):
                            print('saving data')
                            save_test_cases(response_json)
                            return True
                        else:
                            print("Response is not a JSON array")
                            continue
                    else:
                        print("Could not find JSON array markers in response")
                        print(f"Content: {content}")
                        continue
                        
                except json.JSONDecodeError as je:
                    print(f"JSON parsing error: {je}")
                    print(f"Content: {content}")
                    continue
            else:
                print(f"API error: {response.get('error')}")
                if i == 4:  # Last attempt
                    return False
                continue
        except Exception as e:
            print(f"Unexpected error: {str(e)}")
            if i == 4:  # Last attempt
                return False
            continue
    return False

def insert_test_case(name, description, parent_id, type_, order_, curl=None, test_case_id=None):
    # Skip inserting a case with parent_id of 0
    if parent_id == 0:
        parent_id = None

    if check_test_case_exists(name, description):
        print(f"Test case '{name}' already exists. Skipping insertion.")
        return None

    db = DbConnector()
    conn = db.get_connection()
    cursor = conn.cursor()

    if test_case_id is None and type_ == 'test':
        # Increment the test_case_id
        max_test_case_id = get_max_test_case_id()
        test_case_id = max_test_case_id + 1

    print('inserting test case')
    cursor.execute('''
        INSERT INTO test_cases (name, description, parent_id, type, "order", curl, test_case_id)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        RETURNING id 
    ''', (name, description, parent_id, type_, order_, curl, test_case_id))

    last_row_id = cursor.fetchone()[0]
    print(last_row_id)
    conn.commit()
    conn.close()

    return last_row_id

def insert_test_step(test_case_id, step_order, description, expected_result):
    db = DbConnector()
    conn = db.get_connection()
    cursor = conn.cursor()

    # Insert the test step
    cursor.execute('''
        INSERT INTO test_steps (test_case_id, step_order, description, expected_result)
        VALUES (%s, %s, %s, %s)
    ''', (test_case_id, step_order, description, expected_result))

    conn.commit()
    conn.close()
    return cursor.lastrowid

def save_test_cases(test_cases, parent_id=None, type_='root'):
    order_ = 1
    print(test_cases)
    for case in test_cases:
        print(case)
        # Extract fields from the case
        name = case.get('name', '')
        description = case.get('description', '')
        elem_type = case.get('type', '')
        curl = case.get('curl', None)
        expected_result = case.get('expected_result', None)

        # For 'test' type, assign test_case_id
        if elem_type == 'test':
            max_test_case_id = get_max_test_case_id()
            test_case_id = max_test_case_id + 1
        else:
            test_case_id = None

        # Insert the test case and get the inserted ID
        current_id = insert_test_case(
            name=name,
            description=description,
            parent_id=None if type_ == 'root' else parent_id,
            type_=elem_type,
            order_=order_,
            curl=curl,
            test_case_id=test_case_id
        )

        # If the type is 'test', save the test step
        if elem_type == 'test' and current_id:
            step_order = 1
            insert_test_step(
                test_case_id=current_id,
                step_order=step_order,
                description=curl or description,
                expected_result=expected_result
            )

        order_ += 1

        # If there are children, recursively insert them
        if 'children' in case and current_id:
            next_type = 'child' if type_ == 'root' else ('grandchild' if type_ == 'child' else 'step')
            save_test_cases(case['children'], current_id, next_type)
