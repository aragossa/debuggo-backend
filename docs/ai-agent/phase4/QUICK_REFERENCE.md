# Phase 4: Quick Reference Guide

## File Locations

### Documentation
```
auroqa/docs/ai-agents/phase4/
├── PHASE4_OVERVIEW.md              # High-level overview
├── PROMPT_OPTIMIZER.md             # A/B testing framework
├── MODEL_ENSEMBLE.md               # Multi-model generation
├── PERFORMANCE_OPTIMIZATION.md     # Performance strategies
├── FINETUNING_SERVICE.md          # Model fine-tuning
├── CONTINUOUS_IMPROVEMENT.md      # Weekly/monthly improvements
├── IMPLEMENTATION_GUIDE.md        # Step-by-step guide
├── PHASE4_SUMMARY.md              # Implementation status
└── QUICK_REFERENCE.md             # This file
```

### Database
```
auroqa/migrations/
└── 20251130_phase4_optimization.sql
```

### Services
```
auroqa/Services/
├── PromptOptimizer.py             # ✅ Complete
├── ModelEnsemble.py               # ✅ Complete
├── PerformanceOptimizer.py        # ⏳ To implement
├── FineTuningService.py           # ⏳ To implement
└── ContinuousImprovement.py       # ⏳ To implement
```

## Key Concepts

### Prompt Optimizer
- **Purpose**: Improve prompts through A/B testing
- **Key Method**: `run_ab_test(variant_a_id, variant_b_id, test_cases)`
- **Output**: Winner with confidence score
- **Use Case**: Test instruction clarity, example formats, constraints

### Model Ensemble
- **Purpose**: Generate with multiple models for reliability
- **Key Method**: `generate_with_all_models(prompt, context)`
- **Output**: Results from Gemini, Claude, Deepseek
- **Use Case**: Critical test generation, high-confidence requirements

### Agent Monitoring
- **Purpose**: Track system performance metrics
- **Key Method**: `record_metric(metric_name, value)`
- **Output**: Real-time metrics and alerts
- **Use Case**: Performance monitoring, anomaly detection

### Performance Optimizer
- **Purpose**: Optimize latency and throughput
- **Key Method**: `cache_embedding(key, embedding)`
- **Output**: Cached results, faster responses
- **Use Case**: Embedding caching, batch processing

### Fine-tuning Service
- **Purpose**: Specialize models for domain
- **Key Method**: `submit_finetuning_job(model, training_data)`
- **Output**: Fine-tuned model ID
- **Use Case**: Domain-specific optimization, improved accuracy

### Continuous Improvement
- **Purpose**: Automate system improvements
- **Key Method**: `analyze_failures(start_date, end_date)`
- **Output**: Recommendations and improvements
- **Use Case**: Weekly/monthly optimization cycles

## Common Tasks

### 1. Create Prompt Variant
```python
from Services.PromptOptimizer import PromptOptimizer

optimizer = PromptOptimizer()
variant = optimizer.create_prompt_variant(
    base_prompt="Generate test steps",
    variant_name="detailed_v1",
    variant_type="instruction_clarity",
    variation_description="detailed",
    created_by=1
)
```

### 2. Run A/B Test
```python
result = optimizer.run_ab_test(
    variant_a_id=1,
    variant_b_id=2,
    test_case_ids=[101, 102, 103],
    test_runner_callback=test_runner.run
)
```

### 3. Generate with Ensemble
```python
from Services.ModelEnsemble import ModelEnsemble

ensemble = ModelEnsemble()
results = ensemble.generate_with_all_models(
    prompt="Generate login test",
    context={'test_type': 'login'}
)
selected, strategy, confidence = ensemble.select_best_result(
    results=results,
    strategy='consensus'
)
```

### 4. Record Metric
```python
from Services.AgentMonitoring import AgentMonitoring

monitor = AgentMonitoring()
monitor.record_metric('generation_success_rate', 0.95)
monitor.record_metric('avg_confidence', 0.87)
```

### 5. Cache Embedding
```python
from Services.PerformanceOptimizer import PerformanceOptimizer

optimizer = PerformanceOptimizer()
optimizer.cache_embedding(
    key="login_page_analysis",
    embedding=[0.1, 0.2, 0.3, ...]
)
```

### 6. Submit Fine-tuning Job
```python
from Services.FineTuningService import FineTuningService

finetuner = FineTuningService()
job = finetuner.submit_finetuning_job(
    model='gemini',
    training_data=training_data,
    job_name='gemini_finetuned_v1'
)
```

### 7. Analyze Failures
```python
from Services.ContinuousImprovement import ContinuousImprovement

improvement = ContinuousImprovement()
failures = improvement.analyze_failures(
    start_date=datetime.now() - timedelta(days=7),
    end_date=datetime.now()
)
```

## Database Tables

### prompt_variants
```sql
SELECT * FROM prompt_variants WHERE variant_type = 'instruction_clarity';
```

### ab_test_results
```sql
SELECT * FROM ab_test_results WHERE winner = 'A' ORDER BY created_at DESC;
```

### model_ensemble_results
```sql
SELECT * FROM model_ensemble_results WHERE test_case_id = 101;
```

### agent_metrics
```sql
SELECT metric_name, AVG(metric_value) FROM agent_metrics 
GROUP BY metric_name;
```

### performance_logs
```sql
SELECT operation, AVG(duration_ms) FROM performance_logs 
GROUP BY operation;
```

### embedding_cache
```sql
SELECT COUNT(*) as cached_embeddings, 
       AVG(access_count) as avg_accesses 
FROM embedding_cache;
```

### finetuning_data
```sql
SELECT status, COUNT(*) FROM finetuning_data GROUP BY status;
```

### finetuning_jobs
```sql
SELECT * FROM finetuning_jobs WHERE status = 'completed';
```

### improvement_logs
```sql
SELECT * FROM improvement_logs WHERE applied = true 
ORDER BY created_at DESC;
```

## API Endpoints (To Implement)

### Prompt Optimizer
```
POST /api/prompt-variants
GET /api/prompt-variants?type=instruction_clarity
POST /api/ab-tests
GET /api/ab-tests/{id}
GET /api/ab-tests/history
```

### Model Ensemble
```
POST /api/ensemble/generate
GET /api/ensemble/results/{test_case_id}
GET /api/ensemble/statistics
```

### Agent Monitoring
```
GET /api/metrics/current
GET /api/metrics/history?metric=generation_success_rate
GET /api/metrics/alerts
```

### Performance Optimizer
```
GET /api/performance/metrics
GET /api/performance/slow-queries
POST /api/performance/optimize
GET /api/performance/cache-stats
```

### Fine-tuning Service
```
POST /api/finetuning/jobs
GET /api/finetuning/jobs/{job_id}
GET /api/finetuning/jobs
POST /api/finetuning/models/{model_id}/deploy
```

### Continuous Improvement
```
GET /api/improvements/weekly-report
GET /api/improvements/monthly-report
GET /api/improvements/recommendations
POST /api/improvements/apply
```

## Performance Targets

| Metric | Target |
|--------|--------|
| Generation Success Rate | 95%+ |
| Confidence Calibration | >0.9 |
| Model Ensemble Agreement | 85%+ |
| Error Recovery Rate | 80%+ |
| Latency per Step | <2s |
| Pattern Hit Rate | 70%+ |
| Cache Hit Rate | 70%+ |
| A/B Test Confidence | >0.8 |

## Implementation Checklist

### Week 1
- [ ] Apply database migration
- [ ] Implement PromptOptimizer
- [ ] Implement ModelEnsemble
- [ ] Integrate AgentMonitoring
- [ ] Implement PerformanceOptimizer

### Week 2
- [ ] Implement FineTuningService
- [ ] Implement ContinuousImprovement
- [ ] Create monitoring dashboard
- [ ] Run integration tests
- [ ] Performance benchmarking

### Week 3
- [ ] A/B testing with real data
- [ ] Model ensemble evaluation
- [ ] Fine-tuning job submission
- [ ] Continuous improvement cycle
- [ ] Production deployment

## Troubleshooting

### Issue: Database Migration Fails
```bash
# Check PostgreSQL
psql -h localhost -p 5432 -U postgres -d postgres -c "SELECT version();"

# Check migration file
cat auroqa/migrations/20251130_phase4_optimization.sql | head -20

# Apply with verbose output
psql -h localhost -p 5432 -U postgres -d postgres -f \
  auroqa/migrations/20251130_phase4_optimization.sql -v ON_ERROR_STOP=1
```

### Issue: API Endpoint Returns 500
```bash
# Check backend logs
docker logs auroqa-backend | tail -100

# Verify database connection
psql -h localhost -p 5432 -U postgres -d postgres -c "\dt prompt_variants"

# Test API directly
curl -X GET http://localhost:8000/api/prompt-variants
```

### Issue: Low Model Ensemble Agreement
```sql
-- Check ensemble results
SELECT selection_strategy, AVG(agreement_score) 
FROM model_ensemble_results 
GROUP BY selection_strategy;

-- Check model success rates
SELECT 
  CASE WHEN gemini_result IS NOT NULL THEN 1 ELSE 0 END as gemini_success,
  CASE WHEN claude_result IS NOT NULL THEN 1 ELSE 0 END as claude_success,
  CASE WHEN deepseek_result IS NOT NULL THEN 1 ELSE 0 END as deepseek_success,
  COUNT(*) 
FROM model_ensemble_results 
GROUP BY gemini_success, claude_success, deepseek_success;
```

### Issue: Performance Degradation
```sql
-- Check cache hit rate
SELECT 
  COUNT(*) as total_accesses,
  SUM(CASE WHEN access_count > 1 THEN 1 ELSE 0 END) as cache_hits,
  ROUND(100.0 * SUM(CASE WHEN access_count > 1 THEN 1 ELSE 0 END) / COUNT(*), 2) as hit_rate
FROM embedding_cache;

-- Check slow queries
SELECT operation, AVG(duration_ms), MAX(duration_ms), COUNT(*)
FROM performance_logs
WHERE duration_ms > 1000
GROUP BY operation
ORDER BY AVG(duration_ms) DESC;
```

## Resources

- **Documentation**: `/auroqa/docs/ai-agents/phase4/`
- **Code**: `/auroqa/Services/`
- **Database**: `/auroqa/migrations/20251130_phase4_optimization.sql`
- **Tests**: `/tests/phase4/`
- **Scripts**: `/scripts/phase4_*.py`

## Contact

For questions or issues:
1. Check documentation
2. Review code comments
3. Check logs
4. Create issue ticket
5. Contact team lead

## Version History

- **v1.0** (Nov 2025): Initial Phase 4 documentation and foundation
- **v1.1** (TBD): Service implementations
- **v1.2** (TBD): API endpoints
- **v1.3** (TBD): Frontend dashboard
- **v2.0** (TBD): Production deployment
