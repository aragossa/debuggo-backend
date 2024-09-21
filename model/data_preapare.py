from transformers import T5ForConditionalGeneration, T5Tokenizer

model_name = "t5-base"  # or "facebook/bart-base"
tokenizer = T5Tokenizer.from_pretrained(model_name)
model = T5ForConditionalGeneration.from_pretrained(model_name)

from datasets import load_dataset

# Assuming your data is in a JSON file with 'input' and 'output' fields
dataset = load_dataset('json', data_files={'train': 'json/example3.json', 'validation': 'cases/result1.json'})

def preprocess_function(examples):
    inputs = [str(example['input']) for example in examples['input']]
    targets = [str(example['output']) for example in examples['output']]
    model_inputs = tokenizer(inputs, max_length=1024, truncation=True)

    # Setup the tokenizer for targets
    with tokenizer.as_target_tokenizer():
        labels = tokenizer(targets, max_length=512, truncation=True)

    model_inputs["labels"] = labels["input_ids"]
    return model_inputs

tokenized_datasets = dataset.map(preprocess_function, batched=True)

from transformers import Trainer, TrainingArguments

training_args = TrainingArguments(
    output_dir="./results",
    evaluation_strategy="epoch",
    learning_rate=2e-5,
    per_device_train_batch_size=2,
    per_device_eval_batch_size=2,
    num_train_epochs=10,
    weight_decay=0.01,
    save_total_limit=2,
    predict_with_generate=True,
)


trainer = Trainer(
    model=model,
    args=training_args,
    train_dataset=tokenized_datasets["train"],
    eval_dataset=tokenized_datasets["validation"],
)

trainer.train()

trainer.save_model("api-test-generator-model")
tokenizer.save_pretrained("api-test-generator-model")
