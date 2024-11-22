import google.generativeai as genai
from PIL import Image
import google
import json
from io import BytesIO

from Utils.DbConnector import DbConnector


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
    return result if result else 1  # Return 0 if no test_case_id exists

def get_test_cases_from_image(file_content, file):
    GOOGLE_API_KEY = 'AIzaSyDnnYkKQyBGVM1kE2FitVNGav7aZVeMRDU'  # Replace with your actual API key
    try:
        image = Image.open(BytesIO(file_content))
        # Do something with the image, e.g., analyze or manipulate it
        print({"message": f"Processed image: {file.filename}"})
    except Exception as e:
        print({"error": f"Failed to process image: {str(e)}"})
        return False

    genai.configure(api_key=GOOGLE_API_KEY)
    json_structure = """
    [
        {
            "id": 1,
            "name": "UI TESTS",
            "type": "root",
            "children": [
                {
                    "id": 2,
                    "name": "Test Group 1",
                    "type": "group",
                    "children": [
                        {
                            "id": 3,
                            "name": "Test case name",
                            "description": "Test description",
                            "expected_result": "Test expected result",
                            "type": "test",
                            "python_script": "python script with assertions",
                            "steps": [
                                {
                                    "description": "Test step 1 description",
                                    "expected_result": "Test step expected result"
                                },
                                {
                                    "description": "Test step 2 description",
                                    "expected_result": "Test step expected result"
                                }
                            ]
                        },
                        {
                            "id": 4,
                            "name": "Test case name",
                            "description": "Test description",
                            "expected_result": "Test expected result",
                            "type": "test",
                            "python_script": "python script with assertions",
                            "steps": [
                                {
                                    "description": "Test step 1 description",
                                    "expected_result": "Test step expected result"
                                },
                                {
                                    "description": "Test step 2 description",
                                    "expected_result": "Test step expected result"
                                }
                            ]
                        }
                    ]
                },
                {
                    "id": 5,
                    "name": "Test Group 2",
                    "type": "group",
                    "children": [
                        {
                            "id": 6,
                            "name": "Test case name",
                            "description": "Test description",
                            "expected_result": "Test expected result",
                            "type": "test",
                            "python_script": "python script with assertions",
                            "steps": [
                                {
                                    "description": "Test step 1 description",
                                    "expected_result": "Test step expected result"
                                },
                                {
                                    "description": "Test step 2 description",
                                    "expected_result": "Test step expected result"
                                }
                            ]
                        }
                    ]
                }
            ]
        }
    ]
    """
    text_prompt = (
        f"Act as QA engineer. Analyze attached screenshot of a web page and generate as much as possible test cases for this Web page\n"
        "I need response only in json format don't give me any other info:\n"
        "Give me detailed test steps, each action should be as a separated step (like put value in a field, click button etc.)\n"
        f"{json_structure}"
    )

    model = genai.GenerativeModel("gemini-1.5-flash-001")
    for i in range(5):
        try:
            response = model.generate_content([text_prompt, image])
            break
        except google.api_core.exceptions.InternalServerError:
            continue
        except google.api_core.exceptions.DeadlineExceeded:
            continue
    try:
        valid_json = response.text.replace("`", "").replace("json", "")
        response_json = json.loads(valid_json)
        print(response_json)
        print('saving data')
        save_test_cases(response_json)
    except ValueError as e:
        print(response.text)
        print(e)
        return False

def insert_test_case(name, description, parent_id, type_, order_, test_case_id=None, python_script=None):
    # Set parent_id to None if it is 0 (indicating no parent)
    if parent_id == 0:
        parent_id = None

    # Check if the test case already exists
    if check_test_case_exists(name, description):
        print(f"Test case '{name}' already exists. Skipping insertion.")
        return None

    db = DbConnector()
    conn = db.get_connection()
    cursor = conn.cursor()

    print('inserting test case')
    # Insert the test case and return the ID of the inserted row
    cursor.execute('''
        INSERT INTO test_cases (name, description, parent_id, type, "order", test_case_id, python_script)
        VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id
    ''', (name, description, parent_id, type_, order_, test_case_id, python_script))

    # Fetch the ID of the inserted row
    last_row_id = cursor.fetchone()[0]

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
    for case in test_cases:
        # Extract necessary fields
        description = case.get('description', '')
        name = case.get('name', '')
        elem_type = case.get('type', '')
        expected_result = case.get('expected_result', '')
        python_script = case.get('python_script', None)

        # For 'test' type, get or increment test_case_id
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
            test_case_id=test_case_id,
            python_script=python_script  # Save python_script here
        )

        # If the type is 'test', save the steps
        if elem_type == 'test':
            steps = case.get('steps', [])
            step_order = 1
            for step in steps:
                step_description = step.get('description', '')
                step_expected_result = step.get('expected_result', '')
                insert_test_step(
                    test_case_id=current_id,
                    step_order=step_order,
                    description=step_description,
                    expected_result=step_expected_result
                )
                step_order += 1

        order_ += 1

        # If there are children, recursively insert them
        if 'children' in case:
            next_type = 'child' if type_ == 'root' else ('grandchild' if type_ == 'child' else 'step')
            save_test_cases(case['children'], current_id, next_type)
