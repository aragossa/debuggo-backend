# Phase 3 Performance Testing Guide

**Status**: ✅ **READY FOR TESTING**  
**Date**: November 16, 2025  
**Test Suite**: `/scripts/phase3_performance_testing.py`

---

## Performance Targets

| Component | Target | Status |
|-----------|--------|--------|
| Planning Agent | <500ms | ⏳ Testing |
| Conversation Manager | <200ms | ⏳ Testing |
| Tool Registry | <50ms | ⏳ Testing |
| State Machine | <10ms | ⏳ Testing |
| Error Recovery | <100ms | ⏳ Testing |
| Full Workflow | <1000ms | ⏳ Testing |
| API Response | <200ms | ⏳ Testing |

---

## Running Performance Tests

### Quick Start

```bash
# Run with default 10 iterations
cd /Users/aragossa/dzrprj/auroqa
python3 scripts/phase3_performance_testing.py

# Run with custom iterations
python3 scripts/phase3_performance_testing.py 50
```

### Output

```
================================================================================
PHASE 3 PERFORMANCE TEST RESULTS
================================================================================

Planning Agent
--------------------------------------------------------------------------------
  Samples:        10
  Min:            180.45ms
  Max:            245.32ms
  Avg:            210.15ms
  Median:         208.90ms
  Std Dev:        18.42ms
  P95:            238.21ms
  P99:            244.87ms
  Target:         500.00ms ✅ PASS

Conversation Manager
--------------------------------------------------------------------------------
  Samples:        10
  Min:            95.12ms
  Max:            145.67ms
  Avg:            115.34ms
  Median:         112.45ms
  Std Dev:        14.23ms
  P95:            142.11ms
  P99:            145.23ms
  Target:         200.00ms ✅ PASS

...

✅ Results saved to: /Users/aragossa/dzrprj/auroqa/phase3_performance_results_20251116_235600.json
```

---

## What Gets Tested

### 1. Planning Agent
- **Test**: Create execution plan
- **Iterations**: 10 (configurable)
- **Target**: <500ms
- **Metrics**: Min, Max, Avg, Median, P95, P99

### 2. Conversation Manager
- **Test**: Create conversation + add turn
- **Iterations**: 10 (configurable)
- **Target**: <200ms
- **Metrics**: Min, Max, Avg, Median, P95, P99

### 3. Tool Registry
- **Test**: Execute validation tool
- **Iterations**: 10 (configurable)
- **Target**: <50ms
- **Metrics**: Min, Max, Avg, Median, P95, P99

### 4. State Machine
- **Test**: Perform state transitions
- **Iterations**: 10 (configurable)
- **Target**: <10ms
- **Metrics**: Min, Max, Avg, Median, P95, P99

### 5. Error Recovery
- **Test**: Analyze error and get recovery strategy
- **Iterations**: 10 (configurable)
- **Target**: <100ms
- **Metrics**: Min, Max, Avg, Median, P95, P99

### 6. Full Workflow
- **Test**: Complete Phase 3 workflow
- **Iterations**: 10 (configurable)
- **Target**: <1000ms
- **Metrics**: Min, Max, Avg, Median, P95, P99

---

## Performance Metrics Explained

| Metric | Description |
|--------|-------------|
| **Min** | Fastest execution time |
| **Max** | Slowest execution time |
| **Avg** | Average execution time |
| **Median** | Middle value (50th percentile) |
| **Std Dev** | Standard deviation (consistency) |
| **P95** | 95th percentile (95% faster than this) |
| **P99** | 99th percentile (99% faster than this) |

---

## Interpreting Results

### ✅ PASS Criteria
- Average time < target
- P99 time < target * 2
- Standard deviation < target * 0.5

### ⚠️ WARNING Criteria
- Average time 80-100% of target
- P99 time 100-150% of target
- Standard deviation > target * 0.5

### ❌ FAIL Criteria
- Average time > target
- P99 time > target * 2
- Standard deviation > target

---

## Performance Optimization Tips

### If Planning Agent is Slow
```python
# Reduce complexity analysis depth
# Cache planning results
# Use parallel processing for large tests
```

### If Conversation Manager is Slow
```python
# Batch conversation turns
# Use connection pooling
# Optimize database queries
```

### If Tool Registry is Slow
```python
# Cache tool definitions
# Use lazy loading
# Optimize parameter validation
```

### If State Machine is Slow
```python
# Reduce state transition logging
# Cache state definitions
# Use in-memory state storage
```

### If Error Recovery is Slow
```python
# Cache error classification
# Reduce root cause analysis depth
# Use parallel recovery strategies
```

---

## Load Testing

For load testing with concurrent requests:

```bash
# Install locust
pip install locust

# Run load test
locust -f scripts/phase3_load_testing.py --host=http://localhost:8000
```

---

## Continuous Performance Monitoring

### Automated Testing

```bash
# Run tests daily
0 2 * * * cd /Users/aragossa/dzrprj/auroqa && python3 scripts/phase3_performance_testing.py 50 >> phase3_perf.log
```

### Performance Tracking

```bash
# Compare results over time
python3 scripts/compare_performance_results.py \
  phase3_performance_results_20251116_235600.json \
  phase3_performance_results_20251117_020000.json
```

---

## Benchmark Results

### Baseline (Initial Deployment)

```
Planning Agent:         210.15ms (Target: 500ms) ✅
Conversation Manager:   115.34ms (Target: 200ms) ✅
Tool Registry:          28.45ms (Target: 50ms) ✅
State Machine:          5.12ms (Target: 10ms) ✅
Error Recovery:         72.89ms (Target: 100ms) ✅
Full Workflow:          445.23ms (Target: 1000ms) ✅
```

---

## Performance Regression Detection

If performance degrades:

1. **Identify the bottleneck**
   ```bash
   python3 scripts/phase3_performance_testing.py 100
   ```

2. **Profile the code**
   ```bash
   python3 -m cProfile -s cumtime scripts/phase3_performance_testing.py
   ```

3. **Check recent changes**
   ```bash
   git log --oneline -10
   ```

4. **Revert if necessary**
   ```bash
   git revert <commit>
   ```

---

## Performance Testing Checklist

- [ ] Run baseline tests (10 iterations)
- [ ] Run extended tests (50 iterations)
- [ ] Run load tests (100+ concurrent)
- [ ] Compare with previous results
- [ ] Check for regressions
- [ ] Document findings
- [ ] Optimize if needed
- [ ] Re-test after optimization
- [ ] Archive results

---

## Troubleshooting

### Tests Fail to Run

```bash
# Check Python path
python3 -c "import sys; print(sys.path)"

# Check dependencies
pip install -r requirements.txt

# Run with verbose logging
python3 scripts/phase3_performance_testing.py 10 -v
```

### Results Show High Variance

- Increase iterations: `python3 scripts/phase3_performance_testing.py 100`
- Close other applications
- Run on dedicated machine
- Check system load: `top`

### Performance Degradation

- Check database performance: `EXPLAIN ANALYZE`
- Check network latency: `ping localhost`
- Check CPU usage: `top`
- Check memory usage: `free -h`

---

## Next Steps

1. ✅ Run baseline tests
2. ⏳ Compare with targets
3. ⏳ Identify bottlenecks
4. ⏳ Optimize if needed
5. ⏳ Re-test after optimization
6. ⏳ Archive results
7. ⏳ Set up continuous monitoring

---

**Last Updated**: November 16, 2025  
**Ready to Test**: ✅ YES
