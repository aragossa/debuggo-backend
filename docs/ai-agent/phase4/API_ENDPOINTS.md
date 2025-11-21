# Phase 4 API Endpoints Documentation

## Overview

This document provides comprehensive documentation for all Phase 4 API endpoints. All endpoints require admin authentication and are prefixed with `/api/phase4/`.

**Base URL**: `http://localhost:9000/api/phase4/`

**Authentication**: All endpoints require valid JWT token with admin role

---

## Performance Optimizer Endpoints

### 1. Cache Embedding
**Endpoint**: `POST /performance/cache-embedding`

Cache an embedding in the database for later retrieval.

**Request Body**:
```json
{
  "content_hash": "abc123def456",
  "embedding": [0.1, 0.2, 0.3, ...],
  "metadata": {
    "type": "selector",
    "source": "ui_element"
  }
}
```

**Response**:
```json
{
  "status": "success",
  "success": true,
  "cache_key": "abc123def456",
  "timestamp": "2025-01-29T10:30:00.000Z"
}
```

**Use Cases**:
- Cache embeddings for frequently used selectors
- Store embeddings for API flows
- Cache error resolution patterns

---

### 2. Get Cache Statistics
**Endpoint**: `GET /performance/cache-stats`

Retrieve cache performance metrics and statistics.

**Response**:
```json
{
  "status": "success",
  "data": {
    "total_cached": 1250,
    "cache_hit_rate": 0.87,
    "avg_access_time": 2.5,
    "memory_usage": "125MB",
    "cache_ttl": 3600
  },
  "timestamp": "2025-01-29T10:30:00.000Z"
}
```

---

### 3. Batch Process
**Endpoint**: `POST /performance/batch-process`

Process items in batches for optimization.

**Request Body**:
```json
{
  "items": [
    {"id": 1, "data": "..."},
    {"id": 2, "data": "..."}
  ],
  "batch_size": 32
}
```

**Response**:
```json
{
  "status": "success",
  "data": {
    "processed_count": 1000,
    "batch_count": 32,
    "processing_time": 45.2
  },
  "timestamp": "2025-01-29T10:30:00.000Z"
}
```

---

### 4. Get Query Logs
**Endpoint**: `GET /performance/query-logs?limit=100`

Retrieve query performance logs.

**Query Parameters**:
- `limit`: Maximum number of logs (1-1000, default 100)

**Response**:
```json
{
  "status": "success",
  "data": {
    "logs": [
      {
        "query": "SELECT * FROM test_cases WHERE...",
        "execution_time": 125,
        "timestamp": "2025-01-29T10:30:00.000Z"
      }
    ],
    "slow_queries": 5,
    "avg_query_time": 45.2
  },
  "timestamp": "2025-01-29T10:30:00.000Z"
}
```

---

### 5. Get Optimization Recommendations
**Endpoint**: `GET /performance/optimization-recommendations?analysis_type=all`

Get optimization recommendations based on system analysis.

**Query Parameters**:
- `analysis_type`: `cache`, `query`, `index`, or `all` (default: all)

**Response**:
```json
{
  "status": "success",
  "data": {
    "recommendations": [
      {
        "type": "cache",
        "priority": "high",
        "description": "Add caching for frequently accessed selectors",
        "estimated_improvement": 15
      }
    ]
  },
  "timestamp": "2025-01-29T10:30:00.000Z"
}
```

---

### 6. Analyze Indexes
**Endpoint**: `GET /performance/index-analysis`

Analyze database indexes for optimization opportunities.

**Response**:
```json
{
  "status": "success",
  "data": {
    "used_indexes": ["idx_test_cases_client_id", "idx_test_steps_test_case_id"],
    "unused_indexes": ["idx_old_column"],
    "missing_indexes": ["test_cases.created_at", "test_runs.status"]
  },
  "timestamp": "2025-01-29T10:30:00.000Z"
}
```

---

## Fine-Tuning Service Endpoints

### 1. Collect Successful Tests
**Endpoint**: `GET /finetuning/collect-successful-tests?min_success_rate=0.95&limit=1000`

Collect successful test cases for fine-tuning.

**Query Parameters**:
- `min_success_rate`: Minimum success rate (0.0-1.0, default 0.95)
- `limit`: Maximum tests to collect (1-10000, default 1000)

**Response**:
```json
{
  "status": "success",
  "collected_count": 250,
  "data": [
    {
      "id": 1,
      "name": "Login Test",
      "description": "Test successful login flow",
      "step_count": 5,
      "success_rate": 0.98,
      "avg_confidence": 0.92
    }
  ],
  "timestamp": "2025-01-29T10:30:00.000Z"
}
```

---

### 2. Submit Fine-Tuning Job
**Endpoint**: `POST /finetuning/submit-job`

Submit a fine-tuning job for model training.

**Request Body**:
```json
{
  "model_id": "gemini-pro",
  "training_data": [
    {
      "input": "Click login button",
      "output": "//button[@id='login']"
    }
  ],
  "hyperparameters": {
    "epochs": 3,
    "learning_rate": 0.0001,
    "batch_size": 32
  },
  "job_name": "Selector Fine-Tuning v1"
}
```

**Response**:
```json
{
  "status": "success",
  "job_id": "ft_job_abc123",
  "job_status": "submitted",
  "timestamp": "2025-01-29T10:30:00.000Z"
}
```

---

### 3. Get Job Status
**Endpoint**: `GET /finetuning/job-status/{job_id}`

Get the status of a fine-tuning job.

**Path Parameters**:
- `job_id`: ID of the fine-tuning job

**Response**:
```json
{
  "status": "success",
  "data": {
    "job_id": "ft_job_abc123",
    "status": "processing",
    "progress": 45,
    "error_message": null
  },
  "timestamp": "2025-01-29T10:30:00.000Z"
}
```

---

### 4. Deploy Model
**Endpoint**: `POST /finetuning/deploy-model`

Deploy a fine-tuned model to an environment.

**Request Body**:
```json
{
  "model_id": "ft_model_abc123",
  "environment": "staging",
  "version": "1.0.0"
}
```

**Response**:
```json
{
  "status": "success",
  "deployment_id": "deploy_xyz789",
  "environment": "staging",
  "timestamp": "2025-01-29T10:30:00.000Z"
}
```

---

### 5. Get Job History
**Endpoint**: `GET /finetuning/job-history?limit=50`

Get history of fine-tuning jobs.

**Query Parameters**:
- `limit`: Maximum jobs to return (1-500, default 50)

**Response**:
```json
{
  "status": "success",
  "total_jobs": 15,
  "data": [
    {
      "job_id": "ft_job_abc123",
      "model_id": "gemini-pro",
      "status": "completed",
      "created_at": "2025-01-28T10:00:00.000Z",
      "completed_at": "2025-01-28T12:30:00.000Z"
    }
  ],
  "timestamp": "2025-01-29T10:30:00.000Z"
}
```

---

### 6. Evaluate Model
**Endpoint**: `POST /finetuning/evaluate-model?model_id=ft_model_abc123`

Evaluate a fine-tuned model on test data.

**Query Parameters**:
- `model_id`: ID of the model to evaluate

**Request Body**:
```json
[
  {
    "input": "Click submit button",
    "expected_output": "//button[@type='submit']"
  }
]
```

**Response**:
```json
{
  "status": "success",
  "model_id": "ft_model_abc123",
  "metrics": {
    "accuracy": 0.94,
    "precision": 0.92,
    "recall": 0.96,
    "f1_score": 0.94
  },
  "timestamp": "2025-01-29T10:30:00.000Z"
}
```

---

## Continuous Improvement Endpoints

### 1. Analyze Failures
**Endpoint**: `POST /improvement/analyze-failures`

Analyze test failures to identify patterns.

**Request Body**:
```json
{
  "days_back": 7,
  "include_recovery": true
}
```

**Response**:
```json
{
  "status": "success",
  "total_failures": 45,
  "data": [
    {
      "error_type": "element_not_found",
      "count": 15,
      "recovery_success_rate": 0.73,
      "examples": ["//button[@id='submit']", "//input[@name='email']"]
    }
  ],
  "timestamp": "2025-01-29T10:30:00.000Z"
}
```

---

### 2. Generate Weekly Report
**Endpoint**: `POST /improvement/generate-weekly-report`

Generate a comprehensive weekly improvement report.

**Response**:
```json
{
  "status": "success",
  "report_id": "report_abc123",
  "data": {
    "period": "2025-01-22 to 2025-01-29",
    "key_metrics": {
      "total_tests": 500,
      "success_rate": 0.92,
      "avg_confidence": 0.88
    },
    "recommendations": [
      "Improve selector specificity for modal dialogs",
      "Add wait_for_element_to_be_visible for dynamic content"
    ]
  },
  "timestamp": "2025-01-29T10:30:00.000Z"
}
```

---

### 3. Generate Monthly Report
**Endpoint**: `POST /improvement/generate-monthly-report`

Generate a comprehensive monthly improvement report.

**Response**:
```json
{
  "status": "success",
  "report_id": "report_xyz789",
  "data": {
    "period": "January 2025",
    "key_metrics": {
      "total_tests": 2000,
      "success_rate": 0.91,
      "improvement_vs_previous": 0.05
    },
    "trend_analysis": {
      "success_rate_trend": "increasing",
      "confidence_trend": "stable"
    },
    "strategic_recommendations": [
      "Implement ensemble learning for better accuracy",
      "Expand pattern library for common UI elements"
    ]
  },
  "timestamp": "2025-01-29T10:30:00.000Z"
}
```

---

### 4. Improve Prompts
**Endpoint**: `POST /improvement/improve-prompts`

Generate prompt improvement suggestions.

**Request Body**:
```json
{
  "analysis_type": "weekly",
  "focus_areas": ["selector_generation", "error_handling"]
}
```

**Response**:
```json
{
  "status": "success",
  "data": {
    "improvements": [
      {
        "area": "selector_generation",
        "current_prompt": "Generate XPath selector...",
        "suggested_prompt": "Generate both XPath and CSS selectors...",
        "estimated_improvement": 8
      }
    ]
  },
  "timestamp": "2025-01-29T10:30:00.000Z"
}
```

---

### 5. Get Confidence Calibration
**Endpoint**: `GET /improvement/confidence-calibration`

Get confidence score calibration analysis.

**Response**:
```json
{
  "status": "success",
  "data": {
    "calibration_score": 85,
    "overconfident_areas": ["modal_dialogs", "dynamic_content"],
    "underconfident_areas": ["form_validation"],
    "recommendations": [
      "Increase confidence thresholds for simple selectors",
      "Add explicit wait steps for dynamic content"
    ]
  },
  "timestamp": "2025-01-29T10:30:00.000Z"
}
```

---

### 6. Tool Usage Analysis
**Endpoint**: `GET /improvement/tool-usage-analysis`

Analyze tool usage patterns and effectiveness.

**Response**:
```json
{
  "status": "success",
  "data": {
    "tools": [
      {
        "name": "wait_for_element_to_be_visible",
        "usage_count": 450,
        "success_rate": 0.94
      }
    ],
    "most_used": ["click", "type", "wait_for_element_to_be_visible"],
    "most_effective": ["wait_for_modal", "wait_for_clickable"],
    "recommendations": [
      "Increase usage of wait_for_modal for dialog handling",
      "Consider deprecating old wait actions"
    ]
  },
  "timestamp": "2025-01-29T10:30:00.000Z"
}
```

---

### 7. A/B Test Analysis
**Endpoint**: `GET /improvement/ab-test-analysis`

Analyze A/B test results.

**Response**:
```json
{
  "status": "success",
  "data": {
    "active_tests": 3,
    "completed_tests": [
      {
        "test_id": "ab_test_1",
        "variant_a": "prompt_v1",
        "variant_b": "prompt_v2",
        "winner": "variant_b",
        "confidence": 0.95
      }
    ],
    "winners": ["prompt_v2", "selector_strategy_b"]
  },
  "timestamp": "2025-01-29T10:30:00.000Z"
}
```

---

### 8. Ensemble Performance
**Endpoint**: `GET /improvement/ensemble-performance`

Analyze model ensemble performance.

**Response**:
```json
{
  "status": "success",
  "data": {
    "ensemble_accuracy": 0.94,
    "model_contributions": {
      "gemini": 0.35,
      "claude": 0.33,
      "deepseek": 0.32
    },
    "consensus_quality": 0.89,
    "improvement_opportunities": [
      "Increase Gemini weight for selector generation",
      "Improve Claude performance on error handling"
    ]
  },
  "timestamp": "2025-01-29T10:30:00.000Z"
}
```

---

### 9. Error Categories
**Endpoint**: `GET /improvement/error-categories`

Get analysis of error categories.

**Response**:
```json
{
  "status": "success",
  "data": {
    "error_categories": [
      {
        "category": "element_not_found",
        "frequency": 25,
        "percentage": 35
      }
    ],
    "root_causes": {
      "element_not_found": ["Dynamic content", "Timing issues"]
    },
    "recovery_strategies": {
      "element_not_found": ["Retry with wait", "Use CSS fallback"]
    },
    "prevention_recommendations": [
      "Add explicit wait steps",
      "Use dual locator strategy"
    ]
  },
  "timestamp": "2025-01-29T10:30:00.000Z"
}
```

---

### 10. Planning Accuracy
**Endpoint**: `GET /improvement/planning-accuracy`

Analyze test case planning accuracy.

**Response**:
```json
{
  "status": "success",
  "data": {
    "planning_accuracy": 0.88,
    "coverage_analysis": {
      "ui_coverage": 0.92,
      "api_coverage": 0.85,
      "error_handling_coverage": 0.78
    },
    "gap_analysis": [
      "Missing edge case tests for form validation",
      "Insufficient error handling coverage"
    ],
    "improvement_recommendations": [
      "Add more negative test cases",
      "Expand error scenario coverage"
    ]
  },
  "timestamp": "2025-01-29T10:30:00.000Z"
}
```

---

## Error Handling

All endpoints follow a consistent error response format:

```json
{
  "status": "error",
  "detail": "Error message describing what went wrong",
  "timestamp": "2025-01-29T10:30:00.000Z"
}
```

**Common HTTP Status Codes**:
- `200 OK`: Request successful
- `400 Bad Request`: Invalid request parameters
- `401 Unauthorized`: Missing or invalid authentication
- `403 Forbidden`: User lacks admin privileges
- `500 Internal Server Error`: Server error

---

## Authentication

All endpoints require a valid JWT token with admin role. Include the token in the Authorization header:

```
Authorization: Bearer <your_jwt_token>
```

---

## Rate Limiting

- Performance Optimizer endpoints: 100 requests/minute
- Fine-Tuning endpoints: 50 requests/minute
- Continuous Improvement endpoints: 30 requests/minute

---

## Examples

### Example 1: Complete Fine-Tuning Workflow

```bash
# 1. Collect successful tests
curl -X GET "http://localhost:9000/api/phase4/finetuning/collect-successful-tests?min_success_rate=0.95&limit=500" \
  -H "Authorization: Bearer YOUR_TOKEN"

# 2. Submit fine-tuning job
curl -X POST "http://localhost:9000/api/phase4/finetuning/submit-job" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "model_id": "gemini-pro",
    "training_data": [...],
    "hyperparameters": {"epochs": 3, "learning_rate": 0.0001}
  }'

# 3. Check job status
curl -X GET "http://localhost:9000/api/phase4/finetuning/job-status/ft_job_abc123" \
  -H "Authorization: Bearer YOUR_TOKEN"

# 4. Deploy model
curl -X POST "http://localhost:9000/api/phase4/finetuning/deploy-model" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "model_id": "ft_model_abc123",
    "environment": "staging"
  }'
```

### Example 2: Weekly Improvement Report

```bash
curl -X POST "http://localhost:9000/api/phase4/improvement/generate-weekly-report" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

---

## Next Steps

1. **Frontend Dashboard**: Create monitoring dashboard for Phase 4 metrics
2. **Automated Scheduling**: Set up scheduled reports (weekly/monthly)
3. **Alerting**: Implement alerts for critical metrics
4. **Integration**: Connect endpoints to frontend components
5. **Testing**: Run comprehensive endpoint tests

---

**Last Updated**: January 29, 2025
**Version**: 1.0.0
