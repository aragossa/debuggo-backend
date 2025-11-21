# Phase 4 API Quick Start Guide

## Getting Started

### Prerequisites
- Valid JWT token with admin role
- Base URL: `http://localhost:9000/api/phase4/`
- Content-Type: `application/json`

### Authentication Header
```
Authorization: Bearer <your_jwt_token>
```

---

## Quick Reference

### Performance Optimizer

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/performance/cache-embedding` | POST | Cache embeddings |
| `/performance/cache-stats` | GET | Get cache statistics |
| `/performance/batch-process` | POST | Process items in batches |
| `/performance/query-logs` | GET | View query performance logs |
| `/performance/optimization-recommendations` | GET | Get optimization suggestions |
| `/performance/index-analysis` | GET | Analyze database indexes |

### Fine-Tuning Service

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/finetuning/collect-successful-tests` | GET | Collect training data |
| `/finetuning/submit-job` | POST | Submit fine-tuning job |
| `/finetuning/job-status/{job_id}` | GET | Check job status |
| `/finetuning/deploy-model` | POST | Deploy fine-tuned model |
| `/finetuning/job-history` | GET | View job history |
| `/finetuning/evaluate-model` | POST | Evaluate model performance |

### Continuous Improvement

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/improvement/analyze-failures` | POST | Analyze test failures |
| `/improvement/generate-weekly-report` | POST | Generate weekly report |
| `/improvement/generate-monthly-report` | POST | Generate monthly report |
| `/improvement/improve-prompts` | POST | Get prompt improvements |
| `/improvement/confidence-calibration` | GET | Analyze confidence scores |
| `/improvement/tool-usage-analysis` | GET | Analyze tool effectiveness |
| `/improvement/ab-test-analysis` | GET | Analyze A/B test results |
| `/improvement/ensemble-performance` | GET | Analyze ensemble performance |
| `/improvement/error-categories` | GET | Analyze error patterns |
| `/improvement/planning-accuracy` | GET | Analyze planning accuracy |

---

## Common Tasks

### Task 1: Collect Data and Fine-Tune a Model

```bash
# Step 1: Collect successful tests
curl -X GET "http://localhost:9000/api/phase4/finetuning/collect-successful-tests?min_success_rate=0.95&limit=1000" \
  -H "Authorization: Bearer $TOKEN"

# Step 2: Submit fine-tuning job
curl -X POST "http://localhost:9000/api/phase4/finetuning/submit-job" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "model_id": "gemini-pro",
    "training_data": [{"input": "...", "output": "..."}],
    "hyperparameters": {
      "epochs": 3,
      "learning_rate": 0.0001,
      "batch_size": 32
    },
    "job_name": "Weekly Fine-Tuning"
  }'

# Step 3: Monitor job progress
curl -X GET "http://localhost:9000/api/phase4/finetuning/job-status/ft_job_abc123" \
  -H "Authorization: Bearer $TOKEN"

# Step 4: Deploy to staging
curl -X POST "http://localhost:9000/api/phase4/finetuning/deploy-model" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "model_id": "ft_model_abc123",
    "environment": "staging",
    "version": "1.0.0"
  }'
```

### Task 2: Generate Weekly Improvement Report

```bash
curl -X POST "http://localhost:9000/api/phase4/improvement/generate-weekly-report" \
  -H "Authorization: Bearer $TOKEN"
```

### Task 3: Analyze Failures and Get Recommendations

```bash
# Analyze failures from last 7 days
curl -X POST "http://localhost:9000/api/phase4/improvement/analyze-failures" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "days_back": 7,
    "include_recovery": true
  }'

# Get optimization recommendations
curl -X GET "http://localhost:9000/api/phase4/performance/optimization-recommendations?analysis_type=all" \
  -H "Authorization: Bearer $TOKEN"
```

### Task 4: Cache Embeddings

```bash
curl -X POST "http://localhost:9000/api/phase4/performance/cache-embedding" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "content_hash": "abc123def456",
    "embedding": [0.1, 0.2, 0.3, ...],
    "metadata": {
      "type": "selector",
      "source": "ui_element"
    }
  }'
```

### Task 5: Check System Performance

```bash
# Get cache statistics
curl -X GET "http://localhost:9000/api/phase4/performance/cache-stats" \
  -H "Authorization: Bearer $TOKEN"

# Get query logs
curl -X GET "http://localhost:9000/api/phase4/performance/query-logs?limit=100" \
  -H "Authorization: Bearer $TOKEN"

# Analyze indexes
curl -X GET "http://localhost:9000/api/phase4/performance/index-analysis" \
  -H "Authorization: Bearer $TOKEN"
```

---

## Response Format

All successful responses follow this format:

```json
{
  "status": "success",
  "data": { /* endpoint-specific data */ },
  "timestamp": "2025-01-29T10:30:00.000Z"
}
```

Error responses:

```json
{
  "status": "error",
  "detail": "Error message",
  "timestamp": "2025-01-29T10:30:00.000Z"
}
```

---

## Environment Variables

Set these in your `.env` file:

```
# API Configuration
API_BASE_URL=http://localhost:9000
API_VERSION=v1

# Fine-Tuning Configuration
FINETUNING_EPOCHS=3
FINETUNING_LEARNING_RATE=0.0001
FINETUNING_BATCH_SIZE=32

# Performance Optimizer Configuration
CACHE_TTL=3600
BATCH_SIZE=32
MAX_WORKERS=4

# Continuous Improvement Configuration
FAILURE_ANALYSIS_DAYS=7
REPORT_GENERATION_ENABLED=true
```

---

## Testing Endpoints

### Using Python Requests

```python
import requests
import json

BASE_URL = "http://localhost:9000/api/phase4"
TOKEN = "your_jwt_token"

headers = {
    "Authorization": f"Bearer {TOKEN}",
    "Content-Type": "application/json"
}

# Example: Collect successful tests
response = requests.get(
    f"{BASE_URL}/finetuning/collect-successful-tests?min_success_rate=0.95&limit=1000",
    headers=headers
)

print(json.dumps(response.json(), indent=2))
```

### Using cURL

```bash
# Set token as environment variable
export TOKEN="your_jwt_token"

# Test endpoint
curl -X GET "http://localhost:9000/api/phase4/performance/cache-stats" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json"
```

### Using Postman

1. Create new collection: "Phase 4 API"
2. Add Authorization header:
   - Type: Bearer Token
   - Token: `{{token}}`
3. Set variable `token` to your JWT token
4. Import endpoints from API_ENDPOINTS.md

---

## Troubleshooting

### 401 Unauthorized
- Check JWT token is valid
- Verify token has admin role
- Token may have expired

### 403 Forbidden
- User doesn't have admin privileges
- Check user role in database

### 500 Internal Server Error
- Check server logs: `docker logs auroqa-backend`
- Verify database connection
- Check service initialization

### Slow Responses
- Check cache statistics: `/performance/cache-stats`
- Review query logs: `/performance/query-logs`
- Get optimization recommendations: `/performance/optimization-recommendations`

---

## Best Practices

1. **Always use query parameters for filtering** instead of fetching all data
2. **Cache frequently accessed data** using embedding cache
3. **Monitor job status** periodically instead of continuous polling
4. **Use batch processing** for large datasets
5. **Review weekly reports** to identify improvement opportunities
6. **Implement retry logic** for failed requests
7. **Log all API calls** for debugging

---

## Rate Limits

- Performance Optimizer: 100 req/min
- Fine-Tuning: 50 req/min
- Continuous Improvement: 30 req/min

If rate limited, wait before retrying.

---

## Support

For issues or questions:
1. Check API_ENDPOINTS.md for detailed documentation
2. Review server logs for error details
3. Contact admin for authentication issues
4. Check database connectivity

---

**Last Updated**: January 29, 2025
**Version**: 1.0.0
