from datasets import Dataset
from transformers import AutoTokenizer, AutoModelForCausalLM, TrainingArguments, Trainer
from prepare_dataset import prepare_dataset
from tokenize_dataset import tokenize_function

# Prepare the new dataset
new_input_texts, new_output_texts = prepare_dataset('data/new_test_cases.json', 'data')

new_raw_dataset = Dataset.from_dict({
    'input_texts': new_input_texts,
    'output_texts': new_output_texts
})

# Load the fine-tuned tokenizer and model
tokenizer = AutoTokenizer.from_pretrained('./models/fine_tuned_model')
model = AutoModelForCausalLM.from_pretrained('./models/fine_tuned_model')

# Tokenize the new dataset
new_tokenized_dataset = new_raw_dataset.map(
    lambda examples: tokenize_function(examples, tokenizer),
    batched=True
)

# Set up training arguments
training_args = TrainingArguments(
    output_dir='./models/results_retrain',
    num_train_epochs=3,
    per_device_train_batch_size=2,
    save_steps=500,
    save_total_limit=2,
    logging_steps=100,
    learning_rate=5e-5,
    weight_decay=0.01,
    evaluation_strategy="no",
)

# Initialize Trainer
trainer = Trainer(
    model=model,
    args=training_args,
    train_dataset=new_tokenized_dataset.remove_columns(['input_texts', 'output_texts']),
    tokenizer=tokenizer
)

# Retrain the model
trainer.train()

# Save the updated model and tokenizer
model.save_pretrained('./models/fine_tuned_model')
tokenizer.save_pretrained('./models/fine_tuned_model')
