import base64
import requests
import json
from pathlib import Path
import os
from PIL import Image
from io import BytesIO

from Utils.DbConnector import DbConnector


JSON_STRUCTURE = """
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

# Database functions
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

def get_max_test_case_id():
    db = DbConnector()
    conn = db.get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT MAX(test_case_id) FROM test_cases
    ''')
    result = cursor.fetchone()[0]
    conn.close()
    return result if result else 1

def insert_test_case(name, description, parent_id, type_, order_, test_case_id=None, python_script=None):
    db = DbConnector()
    conn = db.get_connection()
    cursor = conn.cursor()
    
    if test_case_id is None:
        test_case_id = get_max_test_case_id() + 1
        
    cursor.execute('''
        INSERT INTO test_cases (name, description, parent_id, type, "order", test_case_id, python_script)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        RETURNING id
    ''', (name, description, parent_id, type_, order_, test_case_id, python_script))
    
    new_id = cursor.fetchone()[0]
    conn.commit()
    conn.close()
    return new_id

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
    for idx, test_case in enumerate(test_cases, 1):
        name = test_case.get('name', '')
        description = test_case.get('description', '')
        test_type = test_case.get('type', type_)
        python_script = test_case.get('python_script')
        
        # Skip if test case already exists
        if check_test_case_exists(name, description):
            continue
            
        # Insert the test case
        new_id = insert_test_case(
            name=name,
            description=description,
            parent_id=parent_id,
            type_=test_type,
            order_=idx,
            python_script=python_script
        )
        
        # If it's a test case with steps, insert the steps
        if test_type == 'test' and 'steps' in test_case:
            for step_idx, step in enumerate(test_case['steps'], 1):
                insert_test_step(
                    test_case_id=new_id,
                    step_order=step_idx,
                    description=step.get('description', ''),
                    expected_result=step.get('expected_result', '')
                )
        
        # Recursively handle children
        if 'children' in test_case:
            save_test_cases(test_case['children'], new_id, test_type)

# Claude API functions
def send_message_with_image_claude(api_key, image_content, prompt):
    """Send a message with an image to Claude API."""
    if not api_key:
        raise ValueError("API key is required")

    if not api_key.startswith('sk-'):
        raise ValueError("Invalid API key format. Key should start with 'sk-'")

    headers = {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }

    try:
        # Convert bytes to Image object
        image = Image.open(BytesIO(image_content))
        
        # Check image size and compress if necessary
        max_size = (1600, 1600)  # Maximum dimensions
        if image.size[0] > max_size[0] or image.size[1] > max_size[1]:
            image.thumbnail(max_size, Image.Resampling.LANCZOS)
        
        # Convert to RGB if necessary (removing alpha channel)
        if image.mode in ('RGBA', 'LA'):
            background = Image.new('RGB', image.size, (255, 255, 255))
            background.paste(image, mask=image.split()[-1])
            image = background
        
        # Convert Image to base64 with compression
        buffered = BytesIO()
        image.save(buffered, format='JPEG', quality=85, optimize=True)
        base64_image = base64.b64encode(buffered.getvalue()).decode('utf-8')
        
        media_type = "image/jpeg"  # We're always converting to JPEG

        payload = {
            "model": "claude-3-opus-20240229",
            "max_tokens": 4096,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": prompt
                        },
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": media_type,
                                "data": base64_image
                            }
                        }
                    ]
                }
            ]
        }

        response = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers=headers,
            json=payload,
            timeout=180  # Increased timeout to 60 seconds
        )

        if response.status_code != 200:
            error_msg = f"API Error (Status {response.status_code}): {response.text}"
            print(error_msg)
            return {"error": error_msg}

        return response.json()

    except requests.Timeout:
        error_msg = "Request timed out. The image might be too large or the network connection is slow."
        print(error_msg)
        return {"error": error_msg}
    except Exception as e:
        error_msg = f"Error processing image or making request: {str(e)}"
        print(error_msg)
        if hasattr(e, 'response') and hasattr(e.response, 'text'):
            print(f"Error details: {e.response.text}")
        return {"error": error_msg}

def get_test_cases_from_image(file_content, file):
    """Generate test cases from an image using Claude API."""
    # Get API key from environment variable
    # api_key = os.getenv('ANTHROPIC_API_KEY')
    api_key = "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"
    if not api_key:
        print({"error": "ANTHROPIC_API_KEY environment variable not set"})
        return False

    try:
        # Process the image
        image = Image.open(BytesIO(file_content))
        print({"message": f"Processing image: {file.filename}"})
    except Exception as e:
        print({"error": f"Failed to process image: {str(e)}"})
        return False

    # Construct the prompt
    prompt = (
        "Act as a QA engineer. Analyze the attached screenshot of a web page and generate comprehensive test cases. "
        "Focus on UI elements, functionality, and user interactions visible in the screenshot. "
        "Include specific test steps that verify each UI element's functionality, appearance, and behavior. "
        "Consider edge cases and validation scenarios. Return ONLY the JSON without any additional text or explanation."
        "Generate the test cases in the following JSON format, ensuring detailed test steps for each action. "
        f"{JSON_STRUCTURE}"
    )

    try:
        response = send_message_with_image_claude(api_key, file_content, prompt)
        
        if response and 'content' in response and response['content']:
            # Extract the JSON part from Claude's response
            response_text = response['content'][0]['text']
            
            # Find the JSON part in the response
            json_start = response_text.find('[')
            json_end = response_text.rfind(']') + 1
            
            if json_start >= 0 and json_end > json_start:
                json_str = response_text[json_start:json_end]
                test_cases = json.loads(json_str)
                
                # Save the test cases to the database
                save_test_cases(test_cases)
                return True
            else:
                print({"error": "Could not extract valid JSON from Claude's response"})
                return False
        else:
            print({"error": "Invalid response from Claude API"})
            return False

    except Exception as e:
        print({"error": f"Error processing test cases: {str(e)}"})
        return False
