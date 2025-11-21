# Fine-Tuning Service

## Overview
The Fine-Tuning Service collects successful test cases, extracts training data, and fine-tunes specialized models for improved domain-specific performance.

## Key Components

### 1. Data Collection
```python
collector = FineTuningDataCollector()

# Collect successful tests
successful_tests = collector.collect_successful_tests(
    min_success_rate=0.95,
    limit=1000
)

# Extract training examples
examples = collector.extract_training_examples(successful_tests)

# Format for fine-tuning
training_data = collector.format_for_finetuning(examples)
```

**Collection Criteria**:
- Success rate ≥ 95%
- Confidence score ≥ 0.8
- Diverse test types
- Recent data (last 30 days)

### 2. Training Data Preparation
```python
# Format examples for model training
formatted_data = collector.format_for_finetuning(examples)

# Output format:
# {
#   "prompt": "Generate login test steps for React app",
#   "completion": "Step 1: Click email field..."
# }
```

### 3. Model Fine-tuning
```python
finetuner = FineTuningService()

# Submit fine-tuning job
job = finetuner.submit_finetuning_job(
    model='gemini',
    training_data=training_data,
    job_name='gemini_finetuned_v1',
    hyperparameters={
        'epochs': 3,
        'learning_rate': 0.0001,
        'batch_size': 32
    }
)

# Monitor job
status = finetuner.get_job_status(job.job_id)
# Returns: 'pending', 'running', 'completed', 'failed'
```

### 4. Model Deployment
```python
# Deploy fine-tuned model
finetuner.deploy_model(
    job_id=job.job_id,
    model_id=job.result_model_id,
    environment='staging'
)

# Promote to production
finetuner.promote_to_production(model_id)
```

## Database Schema

### finetuning_data
```sql
CREATE TABLE finetuning_data (
    id SERIAL PRIMARY KEY,
    test_case_id INTEGER REFERENCES test_cases(id),
    step_number INTEGER,
    prompt TEXT,
    response JSONB,
    success BOOLEAN,
    confidence FLOAT,
    collected_at TIMESTAMP,
    status VARCHAR(20) -- 'pending', 'approved', 'rejected', 'used'
);
```

### finetuning_jobs
```sql
CREATE TABLE finetuning_jobs (
    id SERIAL PRIMARY KEY,
    job_name VARCHAR(100),
    model_name VARCHAR(50),
    training_data_count INTEGER,
    status VARCHAR(20),
    job_id VARCHAR(255),
    result_model_id VARCHAR(255),
    accuracy FLOAT,
    created_at TIMESTAMP,
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    error_message TEXT
);
```

## Usage Examples

### Example 1: Collect and Fine-tune
```python
# Step 1: Collect successful tests
collector = FineTuningDataCollector()
successful_tests = collector.collect_successful_tests(
    min_success_rate=0.95,
    limit=500
)
print(f"Collected {len(successful_tests)} successful tests")

# Step 2: Extract training examples
examples = collector.extract_training_examples(successful_tests)
print(f"Extracted {len(examples)} training examples")

# Step 3: Format for fine-tuning
training_data = collector.format_for_finetuning(examples)

# Step 4: Submit fine-tuning job
finetuner = FineTuningService()
job = finetuner.submit_finetuning_job(
    model='gemini',
    training_data=training_data,
    job_name='gemini_finetuned_login_tests'
)
print(f"Submitted job: {job.job_id}")

# Step 5: Monitor job
while True:
    status = finetuner.get_job_status(job.job_id)
    if status in ['completed', 'failed']:
        break
    time.sleep(60)

# Step 6: Deploy if successful
if status == 'completed':
    finetuner.deploy_model(job.job_id, job.result_model_id)
```

### Example 2: Multi-Model Fine-tuning
```python
# Fine-tune multiple models
models_to_finetune = ['gemini', 'claude', 'deepseek']

for model in models_to_finetune:
    job = finetuner.submit_finetuning_job(
        model=model,
        training_data=training_data,
        job_name=f'{model}_finetuned_v1'
    )
    print(f"Submitted {model} job: {job.job_id}")

# Monitor all jobs
jobs = finetuner.get_active_jobs()
for job in jobs:
    print(f"{job.model_name}: {job.status}")
```

### Example 3: Evaluate Fine-tuned Model
```python
# Evaluate fine-tuned model
evaluation = finetuner.evaluate_model(
    model_id=job.result_model_id,
    test_cases=test_cases
)

print(f"Accuracy: {evaluation['accuracy']:.2%}")
print(f"Precision: {evaluation['precision']:.2%}")
print(f"Recall: {evaluation['recall']:.2%}")
print(f"F1 Score: {evaluation['f1_score']:.2%}")

# Compare with baseline
baseline = finetuner.evaluate_model(
    model_id='gemini',
    test_cases=test_cases
)

improvement = (evaluation['accuracy'] - baseline['accuracy']) / baseline['accuracy']
print(f"Improvement: {improvement:.2%}")
```

## Training Data Quality

### Criteria for Inclusion
- ✅ Success rate ≥ 95%
- ✅ Confidence score ≥ 0.8
- ✅ Valid test case
- ✅ Clear prompt/response pair
- ✅ No sensitive data

### Data Validation
```python
# Validate training data
validation_report = collector.validate_training_data(training_data)

print(f"Total examples: {validation_report['total']}")
print(f"Valid: {validation_report['valid']}")
print(f"Invalid: {validation_report['invalid']}")
print(f"Quality score: {validation_report['quality_score']:.2%}")
```

## Fine-tuning Strategies

### Strategy 1: Domain-Specific Model
- Fine-tune on specific domain (e.g., React apps)
- Improves accuracy for that domain
- Trade-off: Less general

### Strategy 2: Task-Specific Model
- Fine-tune on specific task (e.g., login flows)
- Improves accuracy for that task
- Trade-off: Less general

### Strategy 3: Ensemble Fine-tuning
- Fine-tune multiple models differently
- Each specializes in different area
- Combine for best results

### Strategy 4: Continuous Fine-tuning
- Regularly collect new successful tests
- Incrementally fine-tune
- Gradually improve over time

## Hyperparameter Tuning

### Key Hyperparameters
```python
hyperparameters = {
    'epochs': 3,           # Number of training passes
    'learning_rate': 0.0001,  # How fast to learn
    'batch_size': 32,      # Examples per batch
    'warmup_steps': 100,   # Initial training steps
    'weight_decay': 0.01   # Regularization
}
```

### Recommended Values
| Parameter | Recommended | Range |
|-----------|-------------|-------|
| Epochs | 3-5 | 1-10 |
| Learning Rate | 0.0001 | 0.00001-0.001 |
| Batch Size | 32 | 8-128 |
| Warmup Steps | 100 | 0-500 |

## Monitoring Fine-tuning

### Job Status
```python
job = finetuner.get_job(job_id)
print(f"Status: {job.status}")
print(f"Progress: {job.progress}%")
print(f"ETA: {job.eta_minutes} minutes")
```

### Training Metrics
- Loss (decreasing = good)
- Accuracy (increasing = good)
- Validation loss
- Learning rate schedule

### Post-Training Evaluation
```python
evaluation = finetuner.evaluate_model(model_id)
print(f"Accuracy: {evaluation['accuracy']:.2%}")
print(f"Latency: {evaluation['avg_latency_ms']}ms")
print(f"Cost per inference: ${evaluation['cost_per_inference']}")
```

## Deployment Strategy

### Staging Deployment
```python
# Deploy to staging first
finetuner.deploy_model(
    model_id=job.result_model_id,
    environment='staging'
)

# Run tests
results = run_tests_with_model(staging_model)
```

### Canary Deployment
```python
# Deploy to 10% of users
finetuner.deploy_model(
    model_id=job.result_model_id,
    environment='production',
    traffic_percentage=10
)

# Monitor metrics
metrics = finetuner.get_deployment_metrics()

# Gradually increase traffic
if metrics['success_rate'] > 0.95:
    finetuner.update_traffic(traffic_percentage=50)
```

### Full Rollout
```python
# Deploy to 100% of users
finetuner.update_traffic(traffic_percentage=100)

# Monitor for issues
finetuner.enable_monitoring(model_id)
```

## Cost Considerations

### Fine-tuning Costs
- API calls for training
- Storage for training data
- Compute for training
- Typically: $100-1000 per job

### Inference Costs
- Fine-tuned models may cost more
- Offset by fewer retries
- ROI positive if accuracy improves >5%

### Cost Optimization
- Batch multiple fine-tuning jobs
- Reuse training data
- Archive old models
- Monitor cost per inference

## Best Practices

1. **Start Small**: Fine-tune on subset first
2. **Validate Data**: Ensure quality training data
3. **Monitor Training**: Track metrics during training
4. **Test Thoroughly**: Evaluate before deployment
5. **Gradual Rollout**: Start with staging/canary
6. **Monitor Production**: Track metrics after deployment
7. **Document Changes**: Record what was fine-tuned
8. **Plan Rollback**: Have previous model ready

## Troubleshooting

### Training Fails
- Check training data format
- Verify data quality
- Check hyperparameters
- Review error logs

### Poor Accuracy
- Increase training data
- Adjust hyperparameters
- Try different strategy
- Review training data quality

### High Cost
- Reduce training data size
- Use cheaper base model
- Batch fine-tuning jobs
- Monitor inference costs

## Future Enhancements

1. **Automated Fine-tuning**: Trigger on schedule
2. **A/B Testing**: Compare fine-tuned vs baseline
3. **Multi-task Learning**: Fine-tune on multiple tasks
4. **Transfer Learning**: Start from specialized model
5. **Model Compression**: Reduce model size
6. **Federated Learning**: Train on distributed data

## API Endpoints (Future)

```
POST /api/finetuning/jobs
  Submit fine-tuning job

GET /api/finetuning/jobs/{job_id}
  Get job status

GET /api/finetuning/jobs
  List all jobs

POST /api/finetuning/models/{model_id}/deploy
  Deploy fine-tuned model

GET /api/finetuning/models/{model_id}/metrics
  Get model metrics

POST /api/finetuning/models/{model_id}/rollback
  Rollback to previous model
```
