# Prompt Optimizer Service

## Overview
The Prompt Optimizer implements an A/B testing framework for systematically improving AI prompts. It tests different prompt variants and automatically selects winners based on performance metrics.

## Key Features

### 1. Prompt Variant Creation
```python
variant = optimizer.create_prompt_variant(
    base_prompt="Generate test steps for login page",
    variant_name="detailed_instructions_v1",
    variant_type="instruction_clarity",
    variation_description="detailed",
    created_by=user_id
)
```

**Supported Variant Types**:
- `instruction_clarity`: Detailed vs concise instructions
- `example_format`: JSON vs natural language examples
- `constraint_emphasis`: Strict vs flexible constraints
- `error_handling`: Explicit vs implicit error handling
- `few_shot_examples`: 1 vs 3 vs 5 examples

### 2. A/B Testing Framework
```python
result = optimizer.run_ab_test(
    variant_a_id=1,
    variant_b_id=2,
    test_case_ids=[101, 102, 103, ...],
    test_runner_callback=run_test_with_prompt
)
```

**Test Metrics**:
- Success rate (% of tests that pass)
- Average confidence (AI confidence in generated steps)
- Statistical significance
- Winner determination

### 3. Result Analysis
```python
analysis = optimizer.analyze_results(ab_test_result)
# Returns: {
#   'winner': 'A',
#   'confidence_level': 0.85,
#   'success_rate_improvement': 0.12,
#   'recommendation': 'Deploy variant A'
# }
```

### 4. Automatic Deployment
```python
optimizer.update_prompt_template(
    winning_variant_id=1,
    prompt_name="test_step_generation"
)
```

## Database Schema

### prompt_variants
```sql
CREATE TABLE prompt_variants (
    id SERIAL PRIMARY KEY,
    variant_name VARCHAR(100) UNIQUE,
    variant_text TEXT,
    variant_type VARCHAR(50),
    description TEXT,
    created_by INTEGER REFERENCES users(id),
    created_at TIMESTAMP
);
```

### ab_test_results
```sql
CREATE TABLE ab_test_results (
    id SERIAL PRIMARY KEY,
    variant_a_id INTEGER REFERENCES prompt_variants(id),
    variant_b_id INTEGER REFERENCES prompt_variants(id),
    test_cases_count INTEGER,
    variant_a_success_rate FLOAT,
    variant_b_success_rate FLOAT,
    winner VARCHAR(10), -- 'A', 'B', 'TIE'
    confidence_level FLOAT,
    created_at TIMESTAMP,
    completed_at TIMESTAMP
);
```

## Usage Examples

### Example 1: Test Instruction Clarity
```python
# Create variants
detailed = optimizer.create_prompt_variant(
    base_prompt=base_prompt,
    variant_name="detailed_v1",
    variant_type="instruction_clarity",
    variation_description="detailed",
    created_by=1
)

concise = optimizer.create_prompt_variant(
    base_prompt=base_prompt,
    variant_name="concise_v1",
    variant_type="instruction_clarity",
    variation_description="concise",
    created_by=1
)

# Run A/B test
result = optimizer.run_ab_test(
    variant_a_id=detailed.id,
    variant_b_id=concise.id,
    test_case_ids=test_cases,
    test_runner_callback=test_runner.run
)

# Analyze and deploy
analysis = optimizer.analyze_results(result)
if analysis['recommendation'] == 'Deploy variant A':
    optimizer.update_prompt_template(detailed.id, "test_generation")
```

### Example 2: Test Few-Shot Examples
```python
# Create variants with different example counts
one_example = optimizer.create_prompt_variant(
    base_prompt=base_prompt,
    variant_name="one_example",
    variant_type="few_shot_examples",
    variation_description="1_example",
    created_by=1
)

five_examples = optimizer.create_prompt_variant(
    base_prompt=base_prompt,
    variant_name="five_examples",
    variant_type="few_shot_examples",
    variation_description="5_examples",
    created_by=1
)

# Test
result = optimizer.run_ab_test(
    variant_a_id=one_example.id,
    variant_b_id=five_examples.id,
    test_case_ids=test_cases,
    test_runner_callback=test_runner.run
)
```

## Metrics Tracked

### Success Rate
Percentage of test cases that generate valid, executable steps.

### Confidence Score
AI's confidence in the generated steps (0.0-1.0).

### Statistical Significance
Confidence level that the winner is truly better (not by chance).

## Winner Selection Logic

1. **Calculate scores** for both variants:
   - `score = (success_rate * 0.7) + (avg_confidence * 0.3)`

2. **Determine winner**:
   - If difference < 5%: TIE
   - Otherwise: Higher score wins

3. **Confidence level**:
   - Based on success rate difference
   - Minimum 0.1 for any winner

## Best Practices

### 1. Test Systematically
- Test one variable at a time
- Use sufficient test cases (50+)
- Run multiple rounds

### 2. Interpret Results
- Look for statistical significance
- Consider practical impact
- Don't over-optimize

### 3. Iterate
- Test winner vs new variant
- Gradually improve prompts
- Track improvements over time

### 4. Document Changes
- Record what was tested
- Document why changes were made
- Track impact on metrics

## API Endpoints (Future)

```
POST /api/prompt-variants
  Create new prompt variant

GET /api/prompt-variants?type=instruction_clarity
  List variants by type

POST /api/ab-tests
  Start A/B test

GET /api/ab-tests/{id}
  Get test results

POST /api/ab-tests/{id}/deploy
  Deploy winning variant

GET /api/ab-tests/history
  View test history
```

## Integration Points

### With AIHelper
- Prompts stored in prompt_variants table
- AIHelper loads active prompt at startup
- Updates trigger AIHelper reload

### With TestRunner
- Test runner uses current prompt variant
- Results feed into A/B test metrics
- Feedback loop for continuous improvement

### With Monitoring
- A/B test results tracked in agent_metrics
- Success rates monitored over time
- Alerts on performance degradation

## Performance Considerations

- A/B tests run asynchronously
- Results cached for quick access
- Variant selection optimized with indexes
- Historical data archived after 90 days

## Future Enhancements

1. **Multivariate Testing**: Test multiple variables simultaneously
2. **Bayesian Optimization**: Automatically suggest next variants
3. **Contextual Variants**: Different prompts for different test types
4. **Rollback Capability**: Quickly revert to previous prompt
5. **Gradual Rollout**: Deploy to percentage of users first
