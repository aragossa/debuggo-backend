# Model Ensemble Service

## Overview
The Model Ensemble generates test steps using multiple AI models (Gemini, Claude, Deepseek) and intelligently selects the best result. This approach significantly improves reliability and reduces model-specific biases.

## Key Features

### 1. Multi-Model Generation
```python
ensemble = ModelEnsemble()
results = ensemble.generate_with_all_models(
    prompt="Generate login test steps",
    context={'page_type': 'login', 'framework': 'React'}
)
# Returns: [ModelResult(gemini), ModelResult(claude), ModelResult(deepseek)]
```

### 2. Result Comparison
```python
comparison = ensemble.compare_results(results)
# Returns: {
#   'gemini_result': {...},
#   'claude_result': {...},
#   'deepseek_result': {...},
#   'agreement_score': 0.87,
#   'consensus_result': {...}
# }
```

### 3. Intelligent Selection
```python
selected, strategy, confidence = ensemble.select_best_result(
    results=results,
    strategy='consensus'  # or 'voting', 'confidence', 'weighted'
)
```

### 4. Agreement Scoring
```python
agreement = ensemble.calculate_agreement_score(results)
# Returns: 0.0-1.0 (how much models agree)
```

## Selection Strategies

### Voting Strategy
- Selects most common result
- Best for: Diverse test cases
- Confidence: Based on agreement

### Confidence Strategy
- Selects highest confidence result
- Best for: When models have clear winner
- Confidence: Model's own confidence score

### Consensus Strategy
- Requires 2+ models to agree
- Falls back to highest confidence if no consensus
- Best for: Critical test cases
- Confidence: Agreement score

### Weighted Strategy
- Weights by model performance history
- Gemini: 40%, Claude: 35%, Deepseek: 25%
- Best for: Production deployments
- Confidence: Weighted score

## Database Schema

### model_ensemble_results
```sql
CREATE TABLE model_ensemble_results (
    id SERIAL PRIMARY KEY,
    test_case_id INTEGER REFERENCES test_cases(id),
    step_number INTEGER,
    gemini_result JSONB,
    claude_result JSONB,
    deepseek_result JSONB,
    agreement_score FLOAT,
    selected_result JSONB,
    selection_strategy VARCHAR(50),
    created_at TIMESTAMP
);
```

## Usage Examples

### Example 1: Generate with Consensus
```python
ensemble = ModelEnsemble()

# Generate with all models
results = ensemble.generate_with_all_models(
    prompt="Generate step to fill login form",
    context={'test_case_id': 101}
)

# Compare results
comparison = ensemble.compare_results(results)
print(f"Agreement: {comparison['agreement_score']:.2%}")

# Select best result
selected, strategy, confidence = ensemble.select_best_result(
    results=results,
    strategy='consensus'
)

# Store results
ensemble.store_ensemble_result(
    test_case_id=101,
    step_number=1,
    results=results,
    selected_result=selected,
    selection_strategy=strategy
)
```

### Example 2: Compare Strategies
```python
# Try different strategies
for strategy in ['voting', 'confidence', 'consensus', 'weighted']:
    selected, used_strategy, confidence = ensemble.select_best_result(
        results=results,
        strategy=strategy
    )
    print(f"{strategy}: confidence={confidence:.2%}")
```

### Example 3: Analyze Ensemble Performance
```python
stats = ensemble.get_ensemble_statistics(limit=1000)
print(f"Total results: {stats['total_results']}")
print(f"Average agreement: {stats['avg_agreement']:.2%}")
for strategy, data in stats['by_strategy'].items():
    print(f"{strategy}: {data['count']} results, "
          f"avg_agreement={data['avg_agreement']:.2%}")
```

## Agreement Score Calculation

The agreement score measures how much models agree on the result:

```
1. Compare results pairwise
2. Calculate similarity for each pair (0.0-1.0)
3. Average all similarities
4. Result: 0.0 (no agreement) to 1.0 (perfect agreement)
```

**Similarity Metric**: Key overlap in JSON structures
- Intersection of keys / Union of keys

## Model Performance Weights

Default weights based on historical performance:

| Model | Weight | Rationale |
|-------|--------|-----------|
| Gemini | 40% | Most reliable, best at complex tasks |
| Claude | 35% | Excellent reasoning, good consistency |
| Deepseek | 25% | Good performance, emerging model |

Weights can be adjusted based on:
- Historical success rates
- Confidence calibration
- Domain-specific performance
- Cost considerations

## Benefits

### Reliability
- Single model failure doesn't break system
- Consensus improves correctness
- Fallback strategies ensure results

### Reduced Bias
- Different models have different biases
- Ensemble averages out model-specific quirks
- More robust to model updates

### Better Coverage
- Different models excel at different tasks
- Ensemble captures strengths of each
- Improved handling of edge cases

### Confidence Calibration
- Agreement score indicates reliability
- Can adjust thresholds based on agreement
- Better decision making

## Performance Considerations

### Latency
- Parallel calls to all models: ~3-5 seconds
- Sequential calls: ~10-15 seconds
- Caching reduces repeat calls

### Cost
- 3x API calls (3 models)
- Offset by reduced failures and retries
- ROI positive for critical tests

### Optimization
- Cache common prompts
- Batch process similar requests
- Use cheaper models for simple tasks

## Monitoring

### Key Metrics
- Agreement score distribution
- Selection strategy effectiveness
- Model success rates
- Latency by model
- Cost per test

### Alerts
- Agreement score < 0.5 (low consensus)
- Model API failures
- Latency > 10 seconds
- Cost anomalies

## Integration Points

### With PromptOptimizer
- Test prompts with all models
- Measure agreement improvement
- Select best prompt variant

### With AgentMonitoring
- Track agreement scores over time
- Monitor model performance
- Alert on degradation

### With TestRunner
- Use ensemble for critical steps
- Fall back to single model for simple steps
- Adjust strategy based on confidence

## Future Enhancements

1. **More Models**: Add GPT-4, Llama, etc.
2. **Dynamic Weighting**: Adjust weights based on performance
3. **Contextual Strategy**: Different strategies for different test types
4. **Ensemble Fine-tuning**: Fine-tune models to agree more
5. **Explanation Generation**: Explain why ensemble selected result
6. **Confidence Thresholds**: Require high agreement for critical tests

## API Endpoints (Future)

```
POST /api/ensemble/generate
  Generate with all models

GET /api/ensemble/results/{test_case_id}
  View ensemble results

GET /api/ensemble/statistics
  Get ensemble performance stats

POST /api/ensemble/strategies/{strategy}/test
  Test specific strategy
```

## Troubleshooting

### Low Agreement Score
- Models disagree on approach
- Prompt may be ambiguous
- Consider clarifying prompt
- Review results manually

### High Latency
- API rate limiting
- Network issues
- Consider caching
- Use faster models for simple tasks

### Model Failures
- Check API credentials
- Verify rate limits
- Check error logs
- Implement retry logic

## Best Practices

1. **Use Consensus for Critical Tests**: Require agreement
2. **Monitor Agreement Trends**: Alert on degradation
3. **Adjust Weights Regularly**: Based on performance
4. **Cache Results**: Reduce API calls
5. **Test Strategies**: Find best for your use case
6. **Document Decisions**: Track why strategies chosen
