import base64
import requests
import json
from pathlib import Path
import os


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


def encode_image(image_path):
    """
    Encode an image file to base64 string with error handling.
    """
    try:
        with open(image_path, "rb") as image_file:
            return base64.b64encode(image_file.read()).decode('utf-8')
    except FileNotFoundError:
        raise Exception(f"Image file not found: {image_path}")
    except Exception as e:
        raise Exception(f"Error encoding image: {str(e)}")


def send_message_with_image_claude(api_key, image_path, prompt, model="claude-3-opus-20240229"):
    """
    Send a message with an image to Claude API with improved error handling.
    """
    if not api_key.startswith('sk-'):
        raise ValueError("Invalid API key format. Key should start with 'sk-'")

    headers = {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }

    # Verify image exists and encode it
    if not os.path.exists(image_path):
        raise FileNotFoundError(f"Image file not found: {image_path}")

    base64_image = encode_image(image_path)

    # Get file extension to determine media type
    file_extension = Path(image_path).suffix.lower()
    media_type = {
        '.jpg': 'image/jpeg',
        '.jpeg': 'image/jpeg',
        '.png': 'image/png',
    }.get(file_extension, 'image/jpeg')

    payload = {
        "model": model,
        "max_tokens": 4096,  # Increased token limit for detailed response
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

    try:
        response = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers=headers,
            json=payload
        )

        # Print detailed error information
        if response.status_code != 200:
            print(f"Error Status Code: {response.status_code}")
            print(f"Error Response: {response.text}")
            response.raise_for_status()

        return response.json()

    except requests.exceptions.RequestException as e:
        print(f"Error making request: {str(e)}")
        if hasattr(e.response, 'text'):
            print(f"Error details: {e.response.text}")
        return None


def main():
    # Use environment variable for API key
    # api_key = os.getenv('ANTHROPIC_API_KEY')
    api_key = "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"
    if not api_key:
        print("Error: ANTHROPIC_API_KEY environment variable not set")
        return

    image_path = "../model/data/dashboard_page.png"

    # Simplified prompt structure
    prompt = (
            "Act as QA engineer. Analyze attached screenshot of a web page and generate test cases "
            "in the following JSON format. Include detailed test steps for each action:\n" +
            JSON_STRUCTURE
    )

    try:
        response = send_message_with_image_claude(api_key, image_path, prompt)

        if response:
            try:
                print("Claude's response:")
                print(response['content'][0]['text'])
            except (KeyError, IndexError) as e:
                print(f"Error parsing response: {e}")
                print("Full response:", response)

    except Exception as e:
        print(f"Error: {str(e)}")


if __name__ == "__main__":
    main()