import google.generativeai as genai
import google
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

def get_test_cases_from_json(text_content):
    GOOGLE_API_KEY = 'AIzaSyDnnYkKQyBGVM1kE2FitVNGav7aZVeMRDU'

    genai.configure(api_key=GOOGLE_API_KEY)
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
        f"Act as QA engineer. Analyze attached swagger export file and generate as much as possible test cases for this API:\n"
        f"{text_content}\n"
        "I need response only in json format don't give me any other info:\n"
        f"{json_structure}"
    )

    model = genai.GenerativeModel("gemini-1.5-flash-001")
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
        # Save the test cases
        print('saving data')
        save_test_cases(response_json)
    except ValueError as e:
        print(response.text)
        print(e)
        return False

def insert_test_case(name, description, parent_id, type_, order_, curl=None, test_case_id=None):
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
    ''', (name, description, parent_id, type_, order_, curl, test_case_id))

    conn.commit()
    last_row_id = cursor.lastrowid  # Get the ID of the inserted test case
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
    for case in test_cases:
        # Extract fields from the case
        name = case.get('name', '')
        description = case.get('description', '')
        elem_type = case.get('type', '')
        curl = case.get('curl', None)
        expected_result = case.get('expected_result', None)

        # For 'test' type, assign test_case_id
        if elem_type == 'test':
            # Increment the test_case_id
            max_test_case_id = get_max_test_case_id()
            test_case_id = max_test_case_id + 1
        else:
            test_case_id = None

        print('saving test case')
        current_id = insert_test_case(
            name=name,
            description=description,
            parent_id=parent_id,
            type_=elem_type,
            order_=order_,
            curl=curl,
            test_case_id=test_case_id
        )

        # If the type is 'test', save the test step
        if elem_type == 'test':
            step_order = 1
            insert_test_step(
                test_case_id=current_id,
                step_order=step_order,
                description=curl or description,
                expected_result=expected_result
            )

        order_ += 1

        # If there are children, recursively insert them
        if 'children' in case:
            next_type = 'child' if type_ == 'root' else ('grandchild' if type_ == 'child' else 'step')
            save_test_cases(case['children'], current_id, next_type)
