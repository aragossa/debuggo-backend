from datasets import Dataset
from transformers import AutoTokenizer, AutoModelForCausalLM, TrainingArguments, Trainer
from prepare_dataset import prepare_dataset
from tokenize_dataset import tokenize_function

# Prepare the dataset
input_texts, output_texts = prepare_dataset('data/test_cases.json', 'data')

raw_dataset = Dataset.from_dict({
    'input_texts': input_texts,
    'output_texts': output_texts
})

# Load the tokenizer and model
tokenizer = AutoTokenizer.from_pretrained('gpt2')
model = AutoModelForCausalLM.from_pretrained('gpt2')

# Set the pad_token to eos_token
tokenizer.pad_token = tokenizer.eos_token
model.config.pad_token_id = tokenizer.eos_token_id

# Tokenize the dataset
tokenized_dataset = raw_dataset.map(
    lambda examples: tokenize_function(examples, tokenizer),
    batched=True
)

# Set up training arguments
training_args = TrainingArguments(
    output_dir='./models/results',
    num_train_epochs=3,
    per_device_train_batch_size=2,
    save_steps=500,
    save_total_limit=2,
    logging_steps=100,
    learning_rate=5e-5,
    weight_decay=0.01,
    eval_strategy="no",
)

# Initialize Trainer
trainer = Trainer(
    model=model,
    args=training_args,
    train_dataset=tokenized_dataset.remove_columns(['input_texts', 'output_texts']),
    tokenizer=tokenizer
)

# Train the model
trainer.train()

# Save the model and tokenizer
model.save_pretrained('./models/fine_tuned_model')
tokenizer.save_pretrained('./models/fine_tuned_model')
