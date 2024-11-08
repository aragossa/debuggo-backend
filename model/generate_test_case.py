from transformers import T5ForConditionalGeneration, T5Tokenizer

model_name = "api-test-generator-model"
tokenizer = T5Tokenizer.from_pretrained(model_name)
model = T5ForConditionalGeneration.from_pretrained(model_name)

def generate_test_cases(openapi_schema, max_length=512):
    input_text = str(openapi_schema)
    input_ids = tokenizer.encode(input_text, return_tensors='pt', truncation=True, max_length=1024)
    output_ids = model.generate(input_ids, max_length=max_length, num_beams=4, early_stopping=True)
    output_text = tokenizer.decode(output_ids[0], skip_special_tokens=True)
    return output_text

import json

with open('json/example1.jsonjson') as f:
    new_schema = json.load(f)

test_cases_json = generate_test_cases(new_schema)
test_cases = json.loads(test_cases_json)
print(json.dumps(test_cases, indent=4))
