import json
import os
from extract_text import extract_text_from_image

def prepare_dataset(json_file, images_folder):
    """
    Prepares the dataset by extracting text from images and pairing them with test cases.

    Args:
        json_file (str): Path to the JSON file containing test cases.
        images_folder (str): Path to the folder containing screenshots.

    Returns:
        list, list: Lists of input texts and output texts.
    """
    with open(json_file, 'r') as f:
        data = json.load(f)

    input_texts = []
    output_texts = []

    for item in data:
        image_path = os.path.join(images_folder, f"{item['screenshot_id']}.png")
        screenshot_text = extract_text_from_image(image_path)
        test_case = item['test_case']
        test_case_text = (
            f"Title: {test_case['title']}\n"
            f"Steps:\n" + "\n".join(test_case['steps']) + "\n"
            f"Expected Result: {test_case['expected_result']}"
        )
        input_texts.append(screenshot_text)
        output_texts.append(test_case_text)

    return input_texts, output_texts

if __name__ == "__main__":
    input_texts, output_texts = prepare_dataset('data/test_cases.json', 'data')
    # Save or process the input_texts and output_texts as needed
