# Phase 4 Implementation Guide

## Overview
This guide provides step-by-step instructions for implementing Phase 4 components in the AuroQA AI agent system.

## Prerequisites
- Phase 1-3 components fully implemented and tested
- Database migrations applied
- Backend and frontend running
- All dependencies installed

## Implementation Roadmap

### Week 1: Foundation (Days 1-3)

#### Day 1: Database Setup
```bash
# Apply Phase 4 migration
psql -h localhost -p 5432 -U postgres -d postgres \
  -f auroqa/migrations/20251130_phase4_optimization.sql

# Verify tables created
psql -h localhost -p 5432 -U postgres -d postgres \
  -c "\dt prompt_variants ab_test_results model_ensemble_results"
```

**Checklist**:
- [ ] Migration applied successfully
- [ ] All tables created
- [ ] Indexes created
- [ ] Vector extension enabled

#### Day 2: PromptOptimizer Implementation
```bash
# Create PromptOptimizer service
touch auroqa/Services/PromptOptimizer.py

# Add to imports in main.py
# from Services.PromptOptimizer import PromptOptimizer

# Create API endpoints
# POST /api/prompt-variants
# GET /api/prompt-variants
# POST /api/ab-tests
# GET /api/ab-tests/{id}
```

**Checklist**:
- [ ] PromptOptimizer.py created
- [ ] All methods implemented
- [ ] API endpoints added
- [ ] Tests passing

#### Day 3: ModelEnsemble Implementation
```bash
# Create ModelEnsemble service
touch auroqa/Services/ModelEnsemble.py

# Add to imports in main.py
# from Services.ModelEnsemble import ModelEnsemble

# Create API endpoints
# POST /api/ensemble/generate
# GET /api/ensemble/results/{test_case_id}
# GET /api/ensemble/statistics
```

**Checklist**:
- [ ] ModelEnsemble.py created
- [ ] All methods implemented
- [ ] API endpoints added
- [ ] Tests passing

### Week 1: Foundation (Days 4-5)

#### Day 4: AgentMonitoring Implementation
```bash
# Create AgentMonitoring service
touch auroqa/Services/AgentMonitoring.py

# Implement metrics collection
# - generation_success_rate
# - confidence_calibration
# - error_category_distribution
# - recovery_rate
# - model_agreement
# - pattern_hit_rate
# - planning_accuracy
# - tool_usage_distribution
# - latency_by_operation
```

**Checklist**:
- [ ] AgentMonitoring.py created
- [ ] Metrics collection working
- [ ] Dashboard components created
- [ ] Real-time updates working

#### Day 5: PerformanceOptimizer Implementation
```bash
# Create PerformanceOptimizer service
touch auroqa/Services/PerformanceOptimizer.py

# Implement optimizations
# - Embedding cache
# - Batch processing
# - Query optimization
# - Lazy loading
# - Async operations
```

**Checklist**:
- [ ] PerformanceOptimizer.py created
- [ ] Caching working
- [ ] Batch processing implemented
- [ ] Performance targets met

### Week 2: Advanced Features (Days 1-3)

#### Day 1: FineTuningService Implementation
```bash
# Create FineTuningService
touch auroqa/Services/FineTuningService.py

# Implement methods
# - collect_successful_tests()
# - extract_training_examples()
# - format_for_finetuning()
# - submit_finetuning_job()
# - get_job_status()
# - deploy_model()
```

**Checklist**:
- [ ] FineTuningService.py created
- [ ] Data collection working
- [ ] Fine-tuning job submission working
- [ ] Model deployment working

#### Day 2: ContinuousImprovement Implementation
```bash
# Create ContinuousImprovement service
touch auroqa/Services/ContinuousImprovement.py

# Implement weekly cycle
# - analyze_failures()
# - identify_problematic_prompts()
# - optimize_confidence_thresholds()
# - analyze_tool_usage()

# Implement monthly cycle
# - analyze_ab_test_results()
# - analyze_ensemble_performance()
# - analyze_error_categories()
# - analyze_planning_accuracy()
```

**Checklist**:
- [ ] ContinuousImprovement.py created
- [ ] Weekly cycle working
- [ ] Monthly cycle working
- [ ] Automated tasks scheduled

#### Day 3: Integration Testing
```bash
# Test all components together
python -m pytest tests/phase4/test_integration.py

# Verify:
# - PromptOptimizer + ModelEnsemble
# - AgentMonitoring + PerformanceOptimizer
# - FineTuningService + ContinuousImprovement
# - End-to-end workflows
```

**Checklist**:
- [ ] All integration tests passing
- [ ] No performance degradation
- [ ] Monitoring dashboard working
- [ ] Alerts configured

### Week 2: Advanced Features (Days 4-5)

#### Day 4: Frontend Dashboard
```bash
# Create Phase 4 monitoring dashboard
touch auroqa-ui/src/components/Phase4Dashboard.js

# Components:
# - PromptOptimizer dashboard
# - ModelEnsemble statistics
# - Performance metrics
# - Improvement recommendations
# - Fine-tuning job status
```

**Checklist**:
- [ ] Dashboard created
- [ ] Real-time updates working
- [ ] Charts displaying correctly
- [ ] Responsive design

#### Day 5: Documentation & Testing
```bash
# Create comprehensive documentation
touch auroqa/docs/ai-agents/phase4/DEPLOYMENT_GUIDE.md

# Run full test suite
python -m pytest tests/phase4/ -v

# Performance testing
python scripts/phase4_performance_test.py

# Load testing
python scripts/phase4_load_test.py
```

**Checklist**:
- [ ] All documentation complete
- [ ] All tests passing
- [ ] Performance benchmarks met
- [ ] Load testing successful

## Component Integration

### PromptOptimizer Integration
```python
# In main.py
from Services.PromptOptimizer import PromptOptimizer

optimizer = PromptOptimizer()

@app.post("/api/prompt-variants")
async def create_variant(request: CreateVariantRequest):
    variant = optimizer.create_prompt_variant(
        base_prompt=request.base_prompt,
        variant_name=request.variant_name,
        variant_type=request.variant_type,
        variation_description=request.variation_description,
        created_by=current_user.id
    )
    return variant
```

### ModelEnsemble Integration
```python
# In AIHelper or test generation
from Services.ModelEnsemble import ModelEnsemble

ensemble = ModelEnsemble()

# Generate with all models
results = ensemble.generate_with_all_models(prompt, context)

# Select best result
selected, strategy, confidence = ensemble.select_best_result(
    results=results,
    strategy='consensus'
)

# Store results
ensemble.store_ensemble_result(
    test_case_id=test_case_id,
    step_number=step_number,
    results=results,
    selected_result=selected,
    selection_strategy=strategy
)
```

### AgentMonitoring Integration
```python
# In test execution
from Services.AgentMonitoring import AgentMonitoring

monitor = AgentMonitoring()

# Track metrics
monitor.record_metric('generation_success_rate', success_rate)
monitor.record_metric('avg_confidence', avg_confidence)
monitor.record_metric('error_category', error_type)

# Get statistics
stats = monitor.get_statistics()
```

### PerformanceOptimizer Integration
```python
# In pattern search
from Services.PerformanceOptimizer import PerformanceOptimizer

optimizer = PerformanceOptimizer()

# Check cache
cached = optimizer.get_cached_embedding(content_hash)
if cached:
    return cached

# Compute and cache
embedding = compute_embedding(content)
optimizer.cache_embedding(content_hash, embedding)
```

## Testing Strategy

### Unit Tests
```bash
# Test each component independently
pytest tests/phase4/test_prompt_optimizer.py
pytest tests/phase4/test_model_ensemble.py
pytest tests/phase4/test_agent_monitoring.py
pytest tests/phase4/test_performance_optimizer.py
pytest tests/phase4/test_finetuning_service.py
pytest tests/phase4/test_continuous_improvement.py
```

### Integration Tests
```bash
# Test component interactions
pytest tests/phase4/test_integration.py

# Test workflows
pytest tests/phase4/test_workflows.py
```

### Performance Tests
```bash
# Test performance targets
pytest tests/phase4/test_performance.py

# Benchmark operations
python scripts/phase4_benchmark.py
```

### Load Tests
```bash
# Test under load
locust -f tests/phase4/locustfile.py --host=http://localhost:8000
```

## Deployment Checklist

### Pre-Deployment
- [ ] All tests passing
- [ ] Code review completed
- [ ] Documentation updated
- [ ] Performance benchmarks met
- [ ] Security review completed
- [ ] Database backups created

### Deployment
- [ ] Apply database migration
- [ ] Deploy backend code
- [ ] Deploy frontend code
- [ ] Verify all services running
- [ ] Run smoke tests
- [ ] Monitor metrics

### Post-Deployment
- [ ] Monitor error rates
- [ ] Monitor performance
- [ ] Monitor user feedback
- [ ] Verify all features working
- [ ] Document any issues
- [ ] Plan follow-up improvements

## Rollback Plan

### If Issues Occur
1. Stop new deployments
2. Revert database migration (if possible)
3. Revert backend code
4. Revert frontend code
5. Verify system stability
6. Investigate root cause
7. Plan fix

### Rollback Commands
```bash
# Revert database migration
psql -h localhost -p 5432 -U postgres -d postgres \
  -f auroqa/migrations/20251130_phase4_optimization_rollback.sql

# Revert backend
git revert <commit-hash>
docker-compose restart backend

# Revert frontend
git revert <commit-hash>
npm run build
docker-compose restart frontend
```

## Success Criteria

### Phase 4 Success
- ✅ All components deployed
- ✅ Monitoring dashboard operational
- ✅ A/B testing framework functional
- ✅ Model ensemble working with 85%+ agreement
- ✅ Performance within SLA targets
- ✅ No critical issues

### Metrics Targets
- Generation success rate: 95%+
- Confidence calibration: >0.9
- Model ensemble agreement: 85%+
- Error recovery rate: 80%+
- Latency per step: <2s
- Pattern hit rate: 70%+

## Support & Troubleshooting

### Common Issues

#### Issue: Database Migration Fails
**Solution**:
1. Check PostgreSQL is running
2. Verify credentials
3. Check disk space
4. Review migration logs

#### Issue: API Endpoints Return 500
**Solution**:
1. Check backend logs
2. Verify database connection
3. Check API request format
4. Verify authentication

#### Issue: Performance Degradation
**Solution**:
1. Check cache hit rate
2. Analyze slow queries
3. Review resource utilization
4. Check for connection leaks

#### Issue: Model Ensemble Low Agreement
**Solution**:
1. Check model API status
2. Verify prompt quality
3. Review model weights
4. Check for API errors

## Next Steps

After Phase 4 completion:
1. Gather user feedback
2. Analyze metrics
3. Plan Phase 5 enhancements
4. Document lessons learned
5. Schedule optimization review

## Resources

- Phase 4 Overview: `/auroqa/docs/ai-agents/phase4/PHASE4_OVERVIEW.md`
- PromptOptimizer: `/auroqa/docs/ai-agents/phase4/PROMPT_OPTIMIZER.md`
- ModelEnsemble: `/auroqa/docs/ai-agents/phase4/MODEL_ENSEMBLE.md`
- Performance: `/auroqa/docs/ai-agents/phase4/PERFORMANCE_OPTIMIZATION.md`
- Fine-tuning: `/auroqa/docs/ai-agents/phase4/FINETUNING_SERVICE.md`
- Continuous Improvement: `/auroqa/docs/ai-agents/phase4/CONTINUOUS_IMPROVEMENT.md`

## Contact & Support

For questions or issues:
1. Check documentation
2. Review code comments
3. Check logs
4. Contact team lead
5. Create issue ticket
