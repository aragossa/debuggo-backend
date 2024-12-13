import sys
from transformers import AutoTokenizer, AutoModelForCausalLM
from extract_text import extract_text_from_image

def generate_test_case_from_screenshot(image_path):
    """
    Uses the fine-tuned LLM to generate a test case from the given screenshot image.
    Args:
        image_path (str): Path to the screenshot image.

    Returns:
        str: Generated test case.
    """
    # Load the fine-tuned model and tokenizer
    tokenizer = AutoTokenizer.from_pretrained('./models/fine_tuned_model')
    model = AutoModelForCausalLM.from_pretrained('./models/fine_tuned_model')

    # Set pad token if not set (for GPT-2 like models)
    if tokenizer.pad_token_id is None:
        tokenizer.pad_token = tokenizer.eos_token
        model.config.pad_token_id = tokenizer.eos_token_id

    # Extract text from the screenshot
    input_text = extract_text_from_image(image_path)

    # Encode the input text
    input_ids = tokenizer.encode(
        input_text,
        return_tensors='pt',
        truncation=True,
        max_length=512
    )

    # Generate test case text
    output = model.generate(
        input_ids,
        max_length=512,
        num_beams=5,
        no_repeat_ngram_size=2,
        early_stopping=True
    )

    test_case = tokenizer.decode(output[0], skip_special_tokens=True)
    return test_case

if __name__ == "__main__":
    # If an image path is provided as a command-line argument, use it; otherwise use a default
    image_path = sys.argv[1] if len(sys.argv) > 1 else 'data/dashboard_page.png'

    # Generate the test case
    generated_test_case = generate_test_case_from_screenshot(image_path)

    # Print the generated test case
    print("Generated Test Case:")
    print(generated_test_case)
