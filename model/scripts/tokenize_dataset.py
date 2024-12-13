def tokenize_function(examples, tokenizer):
    """
    Tokenizes the input and output texts.

    Args:
        examples (dict): Dictionary containing 'input_texts' and 'output_texts'.
        tokenizer: Tokenizer instance.

    Returns:
        dict: Tokenized inputs and labels.
    """
    model_inputs = tokenizer(
        examples['input_texts'],
        padding='max_length',
        truncation=True,
        max_length=512
    )
    labels = tokenizer(
        examples['output_texts'],
        padding='max_length',
        truncation=True,
        max_length=512
    )
    model_inputs["labels"] = labels["input_ids"]
    return model_inputs
