# Monitoring API Testing Guide

**Date**: November 15, 2025  
**Status**: Ready for Testing  
**Endpoints**: 8 admin-only endpoints

---

## 🔐 Authentication Setup

### 1. Get Admin Token

First, login as admin user to get JWT token:

```bash
curl -X POST "http://localhost:9000/api/login" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=admin@example.com&password=admin_password"
```

**Response**:
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer"
}
```

**Save token**:
```bash
export ADMIN_TOKEN="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
```

---

## 📊 Test Endpoints

### Test 1: Health Status

**Endpoint**: `GET /api/monitoring/health`

```bash
curl -X GET "http://localhost:9000/api/monitoring/health" \
  -H "Authorization: Bearer $ADMIN_TOKEN"
```

**Expected Response** (200 OK):
```json
{
  "status": "success",
  "data": {
    "overall_status": "healthy",
    "timestamp": "2025-11-15T19:45:00.000Z",
    "tables": {
      "validation_results": {
        "exists": true,
        "record_count": 1250,
        "status": "healthy"
      },
      "execution_feedback": {
        "exists": true,
        "record_count": 45,
        "status": "healthy"
      },
      "confidence_scores": {
        "exists": true,
        "record_count": 1250,
        "status": "healthy"
      },
      "retry_attempts": {
        "exists": true,
        "record_count": 12,
        "status": "healthy"
      }
    },
    "recent_activity": {
      "validations_1h": 150,
      "failures_1h": 5,
      "retries_1h": 2
    }
  },
  "timestamp": "2025-11-15T19:45:00.000Z"
}
```

---

### Test 2: All Metrics (Last 24 Hours)

**Endpoint**: `GET /api/monitoring/metrics?hours=24`

```bash
curl -X GET "http://localhost:9000/api/monitoring/metrics?hours=24" \
  -H "Authorization: Bearer $ADMIN_TOKEN"
```

**Expected Response** (200 OK):
```json
{
  "status": "success",
  "data": {
    "timestamp": "2025-11-15T19:45:00.000Z",
    "time_period_hours": 24,
    "validation": {
      "total_validations": 1250,
      "valid_steps": 1187,
      "invalid_steps": 63,
      "success_rate": 94.96,
      "avg_confidence": 87.45,
      "min_confidence": 45.0,
      "max_confidence": 100.0,
      "error_distribution": {
        "missing_selector": 25,
        "invalid_action": 18,
        "hardcoded_value": 12,
        "api_schema_mismatch": 8
      },
      "unique_error_types": 4,
      "time_period_hours": 24
    },
    "confidence": {
      "total_scored": 1250,
      "avg_confidence": 82.34,
      "low_risk_steps": 875,
      "medium_risk_steps": 312,
      "high_risk_steps": 63,
      "low_risk_percentage": 70.0,
      "medium_risk_percentage": 24.96,
      "high_risk_percentage": 5.04,
      "factor_averages": {
        "selector": 85.2,
        "action": 88.5,
        "data": 79.8,
        "pattern": 76.3
      }
    },
    "feedback": {
      "total_failures": 45,
      "unique_error_types": 8,
      "error_categories": {
        "selector_not_found": 18,
        "element_not_clickable": 12,
        "timeout": 8,
        "stale_element": 5,
        "value_error": 2
      },
      "most_common_errors": [
        {
          "message": "no such element: Unable to locate element",
          "count": 15
        }
      ]
    },
    "retry": {
      "total_retry_attempts": 25,
      "successful_retries": 18,
      "failed_retries": 7,
      "retry_success_rate": 72.0,
      "avg_attempts_per_step": 1.8,
      "max_attempts": 3
    }
  },
  "timestamp": "2025-11-15T19:45:00.000Z"
}
```

---

### Test 3: Validation Metrics

**Endpoint**: `GET /api/monitoring/validation?hours=24`

```bash
curl -X GET "http://localhost:9000/api/monitoring/validation?hours=24" \
  -H "Authorization: Bearer $ADMIN_TOKEN"
```

**Expected Response** (200 OK):
```json
{
  "status": "success",
  "data": {
    "total_validations": 1250,
    "valid_steps": 1187,
    "invalid_steps": 63,
    "success_rate": 94.96,
    "avg_confidence": 87.45,
    "min_confidence": 45.0,
    "max_confidence": 100.0,
    "error_distribution": {
      "missing_selector": 25,
      "invalid_action": 18,
      "hardcoded_value": 12,
      "api_schema_mismatch": 8
    },
    "unique_error_types": 4,
    "time_period_hours": 24
  },
  "timestamp": "2025-11-15T19:45:00.000Z"
}
```

---

### Test 4: Confidence Metrics

**Endpoint**: `GET /api/monitoring/confidence?hours=24`

```bash
curl -X GET "http://localhost:9000/api/monitoring/confidence?hours=24" \
  -H "Authorization: Bearer $ADMIN_TOKEN"
```

**Expected Response** (200 OK):
```json
{
  "status": "success",
  "data": {
    "total_scored": 1250,
    "avg_confidence": 82.34,
    "min_confidence": 35.0,
    "max_confidence": 100.0,
    "low_risk_steps": 875,
    "medium_risk_steps": 312,
    "high_risk_steps": 63,
    "low_risk_percentage": 70.0,
    "medium_risk_percentage": 24.96,
    "high_risk_percentage": 5.04,
    "factor_averages": {
      "selector": 85.2,
      "action": 88.5,
      "data": 79.8,
      "pattern": 76.3
    },
    "time_period_hours": 24
  },
  "timestamp": "2025-11-15T19:45:00.000Z"
}
```

---

### Test 5: Feedback Metrics

**Endpoint**: `GET /api/monitoring/feedback?hours=24`

```bash
curl -X GET "http://localhost:9000/api/monitoring/feedback?hours=24" \
  -H "Authorization: Bearer $ADMIN_TOKEN"
```

**Expected Response** (200 OK):
```json
{
  "status": "success",
  "data": {
    "total_failures": 45,
    "unique_error_types": 8,
    "error_categories": {
      "selector_not_found": 18,
      "element_not_clickable": 12,
      "timeout": 8,
      "stale_element": 5,
      "value_error": 2
    },
    "most_common_errors": [
      {
        "message": "no such element: Unable to locate element",
        "count": 15
      },
      {
        "message": "element not interactable",
        "count": 10
      },
      {
        "message": "timeout waiting for element",
        "count": 8
      },
      {
        "message": "stale element reference",
        "count": 5
      },
      {
        "message": "invalid value format",
        "count": 2
      }
    ],
    "time_period_hours": 24
  },
  "timestamp": "2025-11-15T19:45:00.000Z"
}
```

---

### Test 6: Retry Metrics

**Endpoint**: `GET /api/monitoring/retry?hours=24`

```bash
curl -X GET "http://localhost:9000/api/monitoring/retry?hours=24" \
  -H "Authorization: Bearer $ADMIN_TOKEN"
```

**Expected Response** (200 OK):
```json
{
  "status": "success",
  "data": {
    "total_retry_attempts": 25,
    "successful_retries": 18,
    "failed_retries": 7,
    "retry_success_rate": 72.0,
    "avg_attempts_per_step": 1.8,
    "max_attempts": 3,
    "time_period_hours": 24
  },
  "timestamp": "2025-11-15T19:45:00.000Z"
}
```

---

### Test 7: Alerts

**Endpoint**: `GET /api/monitoring/alerts`

```bash
curl -X GET "http://localhost:9000/api/monitoring/alerts" \
  -H "Authorization: Bearer $ADMIN_TOKEN"
```

**Expected Response** (200 OK):
```json
{
  "status": "success",
  "data": {
    "timestamp": "2025-11-15T19:45:00.000Z",
    "alert_count": 2,
    "alerts": [
      {
        "severity": "warning",
        "type": "validation_success_rate",
        "message": "Validation success rate is 85% (target: >90%)",
        "value": 85
      },
      {
        "severity": "warning",
        "type": "high_risk_steps",
        "message": "High risk steps: 35% (target: <30%)",
        "value": 35
      }
    ]
  },
  "timestamp": "2025-11-15T19:45:00.000Z"
}
```

---

### Test 8: Trends (Last 24 Hours, Hourly)

**Endpoint**: `GET /api/monitoring/trends?hours=24&interval_minutes=60`

```bash
curl -X GET "http://localhost:9000/api/monitoring/trends?hours=24&interval_minutes=60" \
  -H "Authorization: Bearer $ADMIN_TOKEN"
```

**Expected Response** (200 OK):
```json
{
  "status": "success",
  "data": {
    "timestamp": "2025-11-15T19:45:00.000Z",
    "time_period_hours": 24,
    "validation_trend": [
      {
        "timestamp": "2025-11-15T00:00:00.000Z",
        "total": 50,
        "valid": 48,
        "success_rate": 96.0,
        "avg_confidence": 89.5
      },
      {
        "timestamp": "2025-11-15T01:00:00.000Z",
        "total": 55,
        "valid": 52,
        "success_rate": 94.55,
        "avg_confidence": 87.2
      }
    ],
    "confidence_trend": [
      {
        "timestamp": "2025-11-15T00:00:00.000Z",
        "avg_confidence": 85.3,
        "low_risk": 38,
        "high_risk": 3
      }
    ],
    "failure_trend": [
      {
        "timestamp": "2025-11-15T00:00:00.000Z",
        "total_failures": 2
      }
    ]
  },
  "timestamp": "2025-11-15T19:45:00.000Z"
}
```

---

## ❌ Error Cases

### Test 9: Non-Admin User (Should Fail)

```bash
curl -X GET "http://localhost:9000/api/monitoring/health" \
  -H "Authorization: Bearer $NON_ADMIN_TOKEN"
```

**Expected Response** (403 Forbidden):
```json
{
  "detail": "Only admin users can access monitoring endpoints"
}
```

---

### Test 10: Missing Authentication (Should Fail)

```bash
curl -X GET "http://localhost:9000/api/monitoring/health"
```

**Expected Response** (401 Unauthorized):
```json
{
  "detail": "Not authenticated"
}
```

---

### Test 11: Invalid Token (Should Fail)

```bash
curl -X GET "http://localhost:9000/api/monitoring/health" \
  -H "Authorization: Bearer invalid_token"
```

**Expected Response** (401 Unauthorized):
```json
{
  "detail": "Could not validate credentials"
}
```

---

### Test 12: Invalid Hours Parameter (Should Fail)

```bash
curl -X GET "http://localhost:9000/api/monitoring/validation?hours=1000" \
  -H "Authorization: Bearer $ADMIN_TOKEN"
```

**Expected Response** (422 Unprocessable Entity):
```json
{
  "detail": [
    {
      "loc": ["query", "hours"],
      "msg": "ensure this value is less than or equal to 720",
      "type": "value_error.number.not_le",
      "ctx": {"limit_value": 720}
    }
  ]
}
```

---

## 🧪 Test Scenarios

### Scenario 1: Daily Health Check

```bash
#!/bin/bash

# Get admin token
TOKEN=$(curl -s -X POST "http://localhost:9000/api/login" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=admin@example.com&password=admin_password" \
  | jq -r '.access_token')

# Check health
echo "=== Health Status ==="
curl -s -X GET "http://localhost:9000/api/monitoring/health" \
  -H "Authorization: Bearer $TOKEN" | jq '.'

# Check alerts
echo "=== Active Alerts ==="
curl -s -X GET "http://localhost:9000/api/monitoring/alerts" \
  -H "Authorization: Bearer $TOKEN" | jq '.data.alerts'
```

---

### Scenario 2: Weekly Metrics Review

```bash
#!/bin/bash

TOKEN=$(curl -s -X POST "http://localhost:9000/api/login" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=admin@example.com&password=admin_password" \
  | jq -r '.access_token')

# Get metrics for last 7 days
echo "=== 7-Day Metrics ==="
curl -s -X GET "http://localhost:9000/api/monitoring/metrics?hours=168" \
  -H "Authorization: Bearer $TOKEN" | jq '.data'

# Get trends for last 7 days
echo "=== 7-Day Trends ==="
curl -s -X GET "http://localhost:9000/api/monitoring/trends?hours=168&interval_minutes=1440" \
  -H "Authorization: Bearer $TOKEN" | jq '.data'
```

---

### Scenario 3: Error Analysis

```bash
#!/bin/bash

TOKEN=$(curl -s -X POST "http://localhost:9000/api/login" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=admin@example.com&password=admin_password" \
  | jq -r '.access_token')

# Get feedback metrics
echo "=== Error Analysis ==="
curl -s -X GET "http://localhost:9000/api/monitoring/feedback?hours=24" \
  -H "Authorization: Bearer $TOKEN" | jq '.data | {
    total_failures,
    unique_error_types,
    error_categories,
    most_common_errors: .most_common_errors[0:3]
  }'
```

---

## 📋 Testing Checklist

### Authentication Tests
- [ ] Admin user can access endpoints
- [ ] Non-admin user gets 403 Forbidden
- [ ] Missing token gets 401 Unauthorized
- [ ] Invalid token gets 401 Unauthorized

### Endpoint Tests
- [ ] Health endpoint returns data
- [ ] Metrics endpoint returns all metrics
- [ ] Validation endpoint returns validation metrics
- [ ] Confidence endpoint returns confidence metrics
- [ ] Feedback endpoint returns feedback metrics
- [ ] Retry endpoint returns retry metrics
- [ ] Alerts endpoint returns alerts
- [ ] Trends endpoint returns trends

### Parameter Tests
- [ ] Valid hours parameter works
- [ ] Invalid hours parameter fails
- [ ] Valid interval_minutes parameter works
- [ ] Invalid interval_minutes parameter fails

### Data Tests
- [ ] Metrics are accurate
- [ ] Alerts are correct
- [ ] Trends show data over time
- [ ] Error categories are populated

---

## 🔗 Useful Links

### API Documentation
- Swagger UI: `http://localhost:9000/docs`
- ReDoc: `http://localhost:9000/redoc`

### Related Files
- `/auroqa/Services/AgentMonitoring.py` - Service implementation
- `/auroqa/main.py` - API endpoints
- `/PHASE1_MONITORING_DASHBOARD.md` - Dashboard documentation

---

## 📞 Support

For issues or questions:
1. Check `/PHASE1_MONITORING_DASHBOARD.md` for endpoint details
2. Review `/auroqa/Services/AgentMonitoring.py` for implementation
3. Check logs for error messages
4. Verify admin user role in database

---

**Created**: November 15, 2025  
**Status**: Ready for Testing  
**Endpoints**: 8 admin-only endpoints  
**Test Cases**: 12 scenarios
