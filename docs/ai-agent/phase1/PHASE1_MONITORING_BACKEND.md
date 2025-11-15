# Phase 1 Monitoring - Backend Setup

## 1. Create Monitoring Service

**File**: `/auroqa/Services/AgentMonitoring.py`

```python
import logging
from datetime import datetime
from typing import Dict, Any
from auroqa.Utils.Connectors.db_utils import get_db_connection_context

class AgentMonitoring:
    """Monitors Phase 1 agent metrics."""
    
    def __init__(self):
        self.logger = logging.getLogger('AgentMonitoring')
    
    def get_validation_metrics(self, client_id: str, hours: int = 24) -> Dict[str, Any]:
        """Get validation metrics."""
        try:
            with get_db_connection_context() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("""
                        SELECT 
                            COUNT(*) as total,
                            SUM(CASE WHEN is_valid THEN 1 ELSE 0 END) as valid,
                            AVG(confidence) as avg_conf
                        FROM validation_results vr
                        JOIN test_cases tc ON vr.test_case_id = tc.id
                        WHERE tc.client_id = %s 
                        AND vr.created_at > NOW() - INTERVAL '%s hours'
                    """, (client_id, hours))
                    
                    row = cursor.fetchone()
                    total = row[0] or 0
                    valid = row[1] or 0
                    
                    return {
                        'total_validations': total,
                        'valid_steps': valid,
                        'invalid_steps': total - valid,
                        'success_rate': (valid / total * 100) if total > 0 else 0,
                        'avg_confidence': row[2] or 0
                    }
        except Exception as e:
            self.logger.error(f"Error: {str(e)}")
            return {}
    
    def get_feedback_metrics(self, client_id: str, hours: int = 24) -> Dict[str, Any]:
        """Get feedback metrics."""
        try:
            with get_db_connection_context() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("""
                        SELECT 
                            COUNT(*) as total_failures,
                            COUNT(DISTINCT error_type) as error_categories
                        FROM execution_feedback ef
                        JOIN test_cases tc ON ef.test_case_id = tc.id
                        WHERE tc.client_id = %s 
                        AND ef.created_at > NOW() - INTERVAL '%s hours'
                    """, (client_id, hours))
                    
                    row = cursor.fetchone()
                    
                    return {
                        'total_failures': row[0] or 0,
                        'error_categories': row[1] or 0
                    }
        except Exception as e:
            self.logger.error(f"Error: {str(e)}")
            return {}
    
    def get_confidence_metrics(self, client_id: str, hours: int = 24) -> Dict[str, Any]:
        """Get confidence metrics."""
        try:
            with get_db_connection_context() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("""
                        SELECT 
                            AVG(overall_confidence) as avg_overall,
                            COUNT(CASE WHEN risk_level = 'low' THEN 1 END) as low_risk,
                            COUNT(CASE WHEN risk_level = 'medium' THEN 1 END) as medium_risk,
                            COUNT(CASE WHEN risk_level = 'high' THEN 1 END) as high_risk
                        FROM confidence_scores cs
                        JOIN test_cases tc ON cs.test_case_id = tc.id
                        WHERE tc.client_id = %s 
                        AND cs.created_at > NOW() - INTERVAL '%s hours'
                    """, (client_id, hours))
                    
                    row = cursor.fetchone()
                    
                    return {
                        'avg_confidence': row[0] or 0,
                        'low_risk': row[1] or 0,
                        'medium_risk': row[2] or 0,
                        'high_risk': row[3] or 0
                    }
        except Exception as e:
            self.logger.error(f"Error: {str(e)}")
            return {}
    
    def get_all_metrics(self, client_id: str, hours: int = 24) -> Dict[str, Any]:
        """Get all metrics."""
        return {
            'timestamp': datetime.utcnow().isoformat(),
            'period_hours': hours,
            'validation': self.get_validation_metrics(client_id, hours),
            'feedback': self.get_feedback_metrics(client_id, hours),
            'confidence': self.get_confidence_metrics(client_id, hours)
        }
```

## 2. Add Endpoints to main.py

Add these endpoints to `/auroqa/main.py`:

```python
from auroqa.Services.AgentMonitoring import AgentMonitoring

monitoring = AgentMonitoring()

@app.get("/api/agent/metrics")
async def get_agent_metrics(
    hours: int = 24,
    current_user: User = Depends(get_current_user)
):
    """Get Phase 1 agent metrics."""
    metrics = monitoring.get_all_metrics(str(current_user.client_id), hours)
    return metrics

@app.get("/api/agent/validation-metrics")
async def get_validation_metrics(
    hours: int = 24,
    current_user: User = Depends(get_current_user)
):
    """Get validation metrics."""
    return monitoring.get_validation_metrics(str(current_user.client_id), hours)

@app.get("/api/agent/feedback-metrics")
async def get_feedback_metrics(
    hours: int = 24,
    current_user: User = Depends(get_current_user)
):
    """Get feedback metrics."""
    return monitoring.get_feedback_metrics(str(current_user.client_id), hours)

@app.get("/api/agent/confidence-metrics")
async def get_confidence_metrics(
    hours: int = 24,
    current_user: User = Depends(get_current_user)
):
    """Get confidence metrics."""
    return monitoring.get_confidence_metrics(str(current_user.client_id), hours)
```

## 3. Test Endpoints

```bash
# Get all metrics
curl -X GET "http://localhost:8000/api/agent/metrics?hours=24" \
  -H "Authorization: Bearer YOUR_TOKEN"

# Get validation metrics
curl -X GET "http://localhost:8000/api/agent/validation-metrics?hours=24" \
  -H "Authorization: Bearer YOUR_TOKEN"

# Get feedback metrics
curl -X GET "http://localhost:8000/api/agent/feedback-metrics?hours=24" \
  -H "Authorization: Bearer YOUR_TOKEN"

# Get confidence metrics
curl -X GET "http://localhost:8000/api/agent/confidence-metrics?hours=24" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

## 4. Expected Response Format

```json
{
  "timestamp": "2025-11-15T18:50:00.000000",
  "period_hours": 24,
  "validation": {
    "total_validations": 150,
    "valid_steps": 135,
    "invalid_steps": 15,
    "success_rate": 90.0,
    "avg_confidence": 75.5
  },
  "feedback": {
    "total_failures": 25,
    "error_categories": 5
  },
  "confidence": {
    "avg_confidence": 75.5,
    "low_risk": 100,
    "medium_risk": 40,
    "high_risk": 10
  }
}
```

## 5. Key Metrics to Track

| Metric | Target | Description |
|--------|--------|-------------|
| Validation Success Rate | >90% | % of steps that pass validation |
| Avg Confidence | >75% | Average confidence score |
| Low Risk Steps | >70% | % of steps with low risk |
| Error Categories | <10 | Number of unique error types |
| Total Failures | <20% | % of steps that fail execution |

## 6. Monitoring Best Practices

1. **Track Over Time**: Monitor metrics hourly/daily to identify trends
2. **Set Alerts**: Alert when success rate drops below 85%
3. **Analyze Patterns**: Identify most common error types
4. **Adjust Thresholds**: Fine-tune validation rules based on metrics
5. **Review Recommendations**: Check if recommendations are helpful
