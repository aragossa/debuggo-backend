from transformers import AutoTokenizer, AutoModelForCausalLM
from extract_text import extract_text_from_image

def predict_test_case(image_path):
    """
    Generates a test case from a screenshot image.

    Args:
        image_path (str): Path to the screenshot image.

    Returns:
        str: Generated test case.
    """
    # Load the tokenizer and model
    tokenizer = AutoTokenizer.from_pretrained('./models/fine_tuned_model')
    model = AutoModelForCausalLM.from_pretrained('./models/fine_tuned_model')

    # Extract text from the image
    input_text = extract_text_from_image(image_path)

    # Encode the input text
    input_ids = tokenizer.encode(
        input_text,
        return_tensors='pt',
        truncation=True,
        max_length=512
    )

    # Generate the output
    output = model.generate(
        input_ids,
        max_length=512,
        num_beams=5,
        no_repeat_ngram_size=2,
        early_stopping=True
    )

    # Decode the output
    test_case = tokenizer.decode(output[0], skip_special_tokens=True)
    return test_case

if __name__ == "__main__":
    test_case = predict_test_case('data/new_screenshot.png')
    print("Generated Test Case:")
    print(test_case)
