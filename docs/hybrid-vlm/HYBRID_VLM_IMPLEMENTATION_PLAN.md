# 🤖 Hybrid VLM Implementation Plan
## Self-Healing Test Automation with Vision Language Models

**Document Version:** 1.0  
**Created:** November 23, 2025  
**Status:** Planning Phase  
**Estimated Duration:** 4 weeks  

---

## 📋 Executive Summary

This document outlines the implementation of a **Hybrid VLM (Vision Language Model) + Traditional Locator** approach for self-healing test automation. The system will:

- Use **traditional Selenium locators** for fast, reliable execution (primary path)
- Fall back to **VLM-based visual element detection** when locators fail (fallback path)
- **Automatically extract and update locators** from successful VLM detections
- **Track all healing events** for analytics and optimization
- Maintain **backward compatibility** with existing test infrastructure

### Key Benefits
✅ Self-healing tests that adapt to UI changes  
✅ Reduced maintenance overhead  
✅ Better reliability and robustness  
✅ Cost-effective (VLM only on failure)  
✅ Backward compatible with existing tests  

---

## 🏗️ Architecture Overview

### Current Flow (Traditional)
```
Test Generation (AI) → Static Locators → Test Execution (Selenium) → ❌ Breaks on UI change
```

### New Flow (Hybrid)
```
Test Generation (AI) → Static Locators + Visual Description
                           ↓
Test Execution:
  1. Try Traditional Locator (fast)
     ✅ Success → Execute
     ❌ Fail → VLM Fallback
  2. Take Screenshot
  3. VLM Analyzes Screenshot
  4. VLM Finds Element Coordinates
  5. Execute Action at Coordinates
  6. Extract New Locator
  7. Log Healing Event
  8. Update Test Step (optional)
```

---

## 📊 Implementation Phases

### Phase 1: Foundation (Week 1)
**Objective:** Database schema, core services, and hybrid executor

#### 1.1 Database Migration
**File:** `/auroqa/migrations/20251124_add_vlm_hybrid_support.sql`

**Changes to `test_steps` table:**
```sql
ALTER TABLE test_steps 
ADD COLUMN visual_description TEXT,
ADD COLUMN enable_vlm_fallback BOOLEAN DEFAULT TRUE,
ADD COLUMN vlm_confidence_threshold FLOAT DEFAULT 0.8;
```

**New table: `test_step_healing_events`**
```sql
CREATE TABLE test_step_healing_events (
    id BIGSERIAL PRIMARY KEY,
    test_step_id INTEGER NOT NULL REFERENCES test_steps(id),
    test_run_id BIGINT NOT NULL REFERENCES test_runs(id),
    
    -- Original attempt
    original_locator VARCHAR(500),
    locator_type VARCHAR(50),
    locator_failed BOOLEAN,
    failure_reason TEXT,
    
    -- VLM recovery
    vlm_used BOOLEAN,
    vlm_confidence FLOAT,
    vlm_found_location JSONB,  -- {x, y, width, height}
    vlm_success BOOLEAN,
    
    -- Updated locator
    new_locator VARCHAR(500),
    new_locator_type VARCHAR(50),
    
    -- Metadata
    screenshot_before BYTEA,
    screenshot_after BYTEA,
    ai_request_id BIGINT REFERENCES ai_request_logs(id),
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Indexes
CREATE INDEX idx_healing_events_test_step_id ON test_step_healing_events(test_step_id);
CREATE INDEX idx_healing_events_test_run_id ON test_step_healing_events(test_run_id);
CREATE INDEX idx_healing_events_vlm_used ON test_step_healing_events(vlm_used);
CREATE INDEX idx_healing_events_vlm_success ON test_step_healing_events(vlm_success);
CREATE INDEX idx_healing_events_created_at ON test_step_healing_events(created_at);

-- View for analytics
CREATE VIEW vlm_healing_statistics AS
SELECT 
    ts.id as test_step_id,
    ts.locator,
    COUNT(*) as total_executions,
    SUM(CASE WHEN she.locator_failed THEN 1 ELSE 0 END) as failures,
    SUM(CASE WHEN she.vlm_used THEN 1 ELSE 0 END) as vlm_fallbacks,
    SUM(CASE WHEN she.vlm_success THEN 1 ELSE 0 END) as vlm_successes,
    ROUND(100.0 * SUM(CASE WHEN she.vlm_success THEN 1 ELSE 0 END) / 
          NULLIF(SUM(CASE WHEN she.vlm_used THEN 1 ELSE 0 END), 0), 2) as vlm_success_rate,
    AVG(she.vlm_confidence) as avg_vlm_confidence
FROM test_steps ts
LEFT JOIN test_step_healing_events she ON ts.id = she.test_step_id
GROUP BY ts.id, ts.locator;
```

**Update `ai_request_logs`:**
```sql
ALTER TABLE ai_request_logs
ADD COLUMN request_subtype VARCHAR(100),
ADD COLUMN healing_event_id BIGINT REFERENCES test_step_healing_events(id);
```

**Responsibilities:**
- [ ] Create migration file
- [ ] Test migration on staging
- [ ] Document schema changes

---

#### 1.2 VLMNavigationService
**File:** `/auroqa/Services/VLMNavigationService.py`

**Key Methods:**

1. **`detect_element_from_screenshot()`**
   - Input: Screenshot (base64), instruction (natural language)
   - Output: Element location {x, y, width, height}, confidence score
   - Uses: Gemini 2.0 Flash (fast VLM)
   - Logs: AI request with VLM subtype

2. **`extract_new_locator()`**
   - Input: Screenshot, element location
   - Output: CSS selector or XPath
   - Purpose: Generate new locator from found element
   - Reliability threshold: 0.7

3. **`validate_visual_state()`**
   - Input: Screenshot, expected state description
   - Output: Matches boolean, confidence, differences
   - Purpose: Visual assertions (e.g., "Dashboard is visible")

**Implementation Details:**
- Temperature: 0.3 (accuracy over creativity)
- Max tokens: 500 (element detection), 300 (locator extraction)
- Error handling: Graceful fallback on VLM failure
- Logging: Track all VLM requests for cost analytics

**Responsibilities:**
- [ ] Create VLMNavigationService class
- [ ] Implement all three methods
- [ ] Add comprehensive error handling
- [ ] Add logging and monitoring
- [ ] Write unit tests

---

#### 1.3 HybridSeleniumExecutor
**File:** `/auroqa/Utils/BrowserAutomation/HybridSeleniumExecutor.py`

**Core Method: `execute_step_with_fallback()`**

Flow:
```python
1. Try traditional locator
   ├─ Success → Return {success: True, method: 'traditional'}
   └─ Fail → Continue to step 2

2. Check if VLM fallback enabled
   └─ If disabled → Return {success: False}

3. Take screenshot

4. Call VLM to find element
   ├─ Success (confidence > threshold) → Continue
   └─ Fail → Return {success: False}

5. Execute action at VLM coordinates

6. Try to extract new locator
   └─ Save if reliability > 0.7

7. Return {success: True, method: 'vlm_fallback', healing_event: {...}}
```

**Return Structure:**
```python
{
    'success': bool,
    'method': 'traditional' | 'vlm_fallback',
    'healing_event': {
        'original_locator': str,
        'locator_type': str,
        'locator_failed': bool,
        'vlm_used': bool,
        'vlm_confidence': float,
        'vlm_found_location': dict,
        'vlm_success': bool,
        'new_locator': str,
        'new_locator_type': str,
        'screenshot_before': base64,
        'screenshot_after': base64,
        'ai_request_id': int
    },
    'error': str (if failed)
}
```

**Responsibilities:**
- [ ] Create HybridSeleniumExecutor class
- [ ] Implement execute_step_with_fallback()
- [ ] Add action execution methods (click, type, submit)
- [ ] Add coordinate-based action execution
- [ ] Add screenshot capture
- [ ] Write integration tests

---

### Phase 2: Integration (Week 2)
**Objective:** Connect hybrid executor to existing pipeline

#### 2.1 Update AIRequestLogger
**File:** `/auroqa/Services/AIRequestLogger.py`

**New Method: `log_vlm_request()`**
```python
def log_vlm_request(
    self,
    ai_model_id: int,
    client_id: Optional[str],
    request_subtype: str,  # 'vlm_element_detection', 'vlm_validation'
    input_tokens: int,
    output_tokens: int,
    total_cost: float,
    healing_event_id: Optional[int] = None,
    generation_job_id: Optional[str] = None,
    metadata: Optional[Dict] = None
) -> int:
    """Log VLM request with healing event tracking"""
```

**Responsibilities:**
- [ ] Add log_vlm_request() method
- [ ] Update log_request() to support request_subtype
- [ ] Add healing_event_id tracking
- [ ] Update cost calculation for VLM requests

---

#### 2.2 Update KafkaMessageConsumer
**File:** `/auroqa/Utils/Connectors/KafkaMessageConsumer.py`

**Changes in `process_test_execution()`:**

1. Initialize HybridSeleniumExecutor:
```python
from auroqa.Utils.BrowserAutomation.HybridSeleniumExecutor import HybridSeleniumExecutor
hybrid_executor = HybridSeleniumExecutor(enable_vlm_fallback=True)
```

2. Replace step execution loop:
```python
for test_step in test_steps:
    result = hybrid_executor.execute_step_with_fallback(
        driver=driver,
        test_step=test_step,
        client_id=client_id,
        generation_job_id=generation_job_id
    )
    
    if not result['success']:
        # Handle failure
        break
    
    # Save healing event if VLM was used
    if result['healing_event']:
        save_healing_event_to_db(result['healing_event'])
        
        # Optionally update test step with new locator
        if result['healing_event'].get('new_locator'):
            update_test_step_locator(
                test_step['id'],
                result['healing_event']['new_locator'],
                result['healing_event']['new_locator_type']
            )
```

**Responsibilities:**
- [ ] Import HybridSeleniumExecutor
- [ ] Update step execution loop
- [ ] Add healing event persistence
- [ ] Add optional locator update logic
- [ ] Add logging for debugging

---

#### 2.3 Update AIHelper
**File:** `/auroqa/Utils/AIHelper/AIHelper.py`

**Add Vision Support:**
```python
def send_vision_request(
    self,
    prompt: str,
    image_base64: str,
    model_name: str = "gemini-2.0-flash-exp",
    temperature: float = 0.3,
    max_tokens: int = 500
) -> Dict:
    """Send vision request to Gemini with image"""
```

**Responsibilities:**
- [ ] Add send_vision_request() method
- [ ] Handle image encoding/decoding
- [ ] Add token counting for vision requests
- [ ] Add cost calculation for vision requests

---

### Phase 3: Frontend & Analytics (Week 3)
**Objective:** UI for VLM settings and analytics dashboard

#### 3.1 Update TestCaseSteps.js
**File:** `/auroqa-ui/src/components/TestCaseSteps.js`

**New UI Section:**
```javascript
<div className="vlm-settings-section">
  <h4>🤖 Self-Healing Settings</h4>
  
  <label>
    <input 
      type="checkbox" 
      checked={enableVLMFallback}
      onChange={(e) => setEnableVLMFallback(e.target.checked)}
    />
    Enable VLM Fallback (Self-Healing)
  </label>
  
  {enableVLMFallback && (
    <>
      <div className="form-group">
        <label>Visual Description (for VLM):</label>
        <textarea
          value={visualDescription}
          onChange={(e) => setVisualDescription(e.target.value)}
          placeholder="e.g., 'Blue login button at bottom right with white text'"
          rows="3"
        />
        <small>Describe what the element looks like visually</small>
      </div>
      
      <div className="form-group">
        <label>VLM Confidence Threshold:</label>
        <input
          type="range"
          min="0.5"
          max="1"
          step="0.05"
          value={vlmConfidenceThreshold}
          onChange={(e) => setVlmConfidenceThreshold(parseFloat(e.target.value))}
        />
        <span>{(vlmConfidenceThreshold * 100).toFixed(0)}%</span>
      </div>
    </>
  )}
</div>
```

**State Management:**
```javascript
const [enableVLMFallback, setEnableVLMFallback] = useState(true);
const [visualDescription, setVisualDescription] = useState('');
const [vlmConfidenceThreshold, setVlmConfidenceThreshold] = useState(0.8);
```

**Form Submission:**
```javascript
// Include in test_step data
{
  ...testStep,
  enable_vlm_fallback: enableVLMFallback,
  visual_description: visualDescription,
  vlm_confidence_threshold: vlmConfidenceThreshold
}
```

**Responsibilities:**
- [ ] Add VLM settings section to form
- [ ] Add state management for VLM fields
- [ ] Update form submission to include VLM data
- [ ] Add help text and tooltips
- [ ] Add CSS styling

---

#### 3.2 Create SelfHealingAnalytics Component
**File:** `/auroqa-ui/src/components/SelfHealingAnalytics.js`

**Features:**

1. **Statistics Cards:**
   - Total Executions
   - Locator Failures
   - VLM Fallbacks Used
   - VLM Success Rate (%)
   - Tests Self-Healed
   - Avg VLM Confidence (%)

2. **Healing Events Table:**
   - Test Step Name
   - Failure Reason
   - VLM Confidence
   - Status (Healed/Failed)
   - New Locator Found (Y/N)
   - Date

3. **Filters:**
   - Time Period (Today, Week, Month, Year)
   - Project
   - Status (All, Healed, Failed)

4. **Charts:**
   - Healing Success Rate Over Time
   - VLM Confidence Distribution
   - Failure Types Breakdown

**Responsibilities:**
- [ ] Create component structure
- [ ] Add API endpoint calls
- [ ] Add statistics cards
- [ ] Add healing events table
- [ ] Add filters and date range
- [ ] Add charts/visualizations
- [ ] Add CSS styling

---

#### 3.3 Create Backend Analytics Endpoint
**File:** `/auroqa/main.py`

**New Endpoint: `GET /api/analytics/self-healing`**

```python
@app.get("/api/analytics/self-healing")
async def get_self_healing_analytics(
    project_id: int = Query(...),
    period: str = Query("week"),  # day, week, month, year
    current_user: User = Depends(check_admin_access)
):
    """Get self-healing statistics and events"""
    
    # Query vlm_healing_statistics view
    # Filter by project_id and time period
    # Return statistics and recent events
```

**Response Structure:**
```json
{
    "data": {
        "total_executions": 1250,
        "total_failures": 45,
        "vlm_fallbacks": 42,
        "vlm_successes": 39,
        "vlm_success_rate": 92.86,
        "tests_healed": 39,
        "avg_vlm_confidence": 0.87,
        "recent_events": [
            {
                "id": 1,
                "test_step_name": "Click Login Button",
                "failure_reason": "NoSuchElementException",
                "vlm_confidence": 0.92,
                "vlm_success": true,
                "new_locator": "button.login-btn",
                "created_at": "2025-11-23T10:30:00Z"
            }
        ]
    }
}
```

**Responsibilities:**
- [ ] Create endpoint
- [ ] Query healing statistics
- [ ] Filter by time period
- [ ] Return formatted response
- [ ] Add error handling

---

### Phase 4: Configuration & Deployment (Week 4)
**Objective:** Feature flags, testing, and production deployment

#### 4.1 Configuration Management
**File:** `/auroqa/config/vlm_config.py`

```python
class VLMConfig:
    """VLM Hybrid Execution Configuration"""
    
    # Global settings
    ENABLE_VLM_FALLBACK = True
    VLM_MODEL = "gemini-2.0-flash-exp"
    DEFAULT_CONFIDENCE_THRESHOLD = 0.8
    
    # Performance
    CACHE_VLM_RESULTS = True
    CACHE_TTL_SECONDS = 3600
    
    # Logging
    LOG_HEALING_EVENTS = True
    SAVE_SCREENSHOTS = True
    SCREENSHOT_COMPRESSION = True
    
    # Cost optimization
    ENABLE_LOCATOR_UPDATE = True
    MIN_RELIABILITY_FOR_UPDATE = 0.7
    
    # Per-client overrides
    CLIENT_VLM_SETTINGS = {}
    
    @classmethod
    def get_client_settings(cls, client_id: str) -> Dict:
        """Get VLM settings for specific client"""
        return cls.CLIENT_VLM_SETTINGS.get(client_id, {
            'enabled': cls.ENABLE_VLM_FALLBACK,
            'confidence_threshold': cls.DEFAULT_CONFIDENCE_THRESHOLD,
            'model': cls.VLM_MODEL
        })
```

**Responsibilities:**
- [ ] Create VLMConfig class
- [ ] Add environment variable support
- [ ] Add per-client settings
- [ ] Add feature flags

---

#### 4.2 Testing & Validation

**Unit Tests:**
- [ ] VLMNavigationService methods
- [ ] Element detection accuracy
- [ ] Locator extraction reliability
- [ ] Error handling

**Integration Tests:**
- [ ] HybridSeleniumExecutor with real browser
- [ ] Traditional locator path
- [ ] VLM fallback path
- [ ] Healing event persistence
- [ ] Locator update logic

**Performance Tests:**
- [ ] Traditional execution speed (baseline)
- [ ] VLM fallback latency
- [ ] Screenshot capture time
- [ ] Database write performance

**Cost Analysis:**
- [ ] VLM request costs per test
- [ ] Comparison: Traditional vs Hybrid
- [ ] ROI analysis (maintenance savings vs VLM costs)

**Test Files:**
```
/tests/
  ├── test_vlm_navigation_service.py
  ├── test_hybrid_executor.py
  ├── test_healing_events.py
  └── test_analytics_endpoint.py
```

**Responsibilities:**
- [ ] Write unit tests
- [ ] Write integration tests
- [ ] Run performance benchmarks
- [ ] Document results
- [ ] Create test report

---

#### 4.3 Documentation

**Files to Create/Update:**
1. **VLM Feature Guide** - `/docs/VLM_HYBRID_GUIDE.md`
   - Overview and benefits
   - Configuration options
   - Usage examples
   - Troubleshooting

2. **API Documentation** - Update `/docs/API.md`
   - New analytics endpoint
   - Healing events schema
   - Response examples

3. **Migration Guide** - `/docs/MIGRATION_VLM.md`
   - Database migration steps
   - Backward compatibility notes
   - Rollback procedure

4. **Architecture Document** - `/docs/ARCHITECTURE_VLM.md`
   - System design
   - Component interactions
   - Data flow diagrams

**Responsibilities:**
- [ ] Write VLM feature guide
- [ ] Update API documentation
- [ ] Create migration guide
- [ ] Create architecture document
- [ ] Add code comments and docstrings

---

#### 4.4 Deployment Strategy

**Phase 1: Staging (Week 4, Day 1-2)**
- [ ] Deploy to staging environment
- [ ] Run full test suite
- [ ] Performance testing
- [ ] Load testing

**Phase 2: Pilot (Week 4, Day 3-4)**
- [ ] Enable for 1-2 pilot clients
- [ ] Monitor healing events
- [ ] Collect feedback
- [ ] Fix issues

**Phase 3: Gradual Rollout (Week 4, Day 5+)**
- [ ] Enable for 25% of clients
- [ ] Monitor metrics
- [ ] Enable for 50% of clients
- [ ] Enable for 100% of clients

**Feature Flags:**
```python
# Disable by default
ENABLE_VLM_FALLBACK = False

# Enable per client
CLIENT_VLM_SETTINGS = {
    'client_123': {'enabled': True},
    'client_456': {'enabled': True}
}
```

**Monitoring:**
- [ ] Track VLM request volume
- [ ] Monitor success rates
- [ ] Track costs
- [ ] Monitor performance
- [ ] Alert on anomalies

**Responsibilities:**
- [ ] Prepare staging environment
- [ ] Run deployment checklist
- [ ] Monitor pilot phase
- [ ] Manage gradual rollout
- [ ] Handle issues and rollback

---

## 📈 Success Metrics

### Quantitative
- **VLM Success Rate:** Target > 90%
- **Healing Event Rate:** Track % of failures recovered
- **Cost Impact:** VLM costs < 5% of traditional test maintenance savings
- **Performance:** VLM fallback latency < 3 seconds
- **Adoption:** > 50% of new tests use VLM fallback

### Qualitative
- Reduced test maintenance burden
- Improved test reliability
- Better handling of UI changes
- Positive user feedback

---

## 💰 Cost Analysis

### VLM Request Costs
- **Element Detection:** ~$0.002 per image (Gemini 2.0 Flash)
- **Locator Extraction:** ~$0.001 per request
- **Visual Validation:** ~$0.002 per request

### Cost Optimization
- Only use VLM on locator failure (~5% of executions)
- Cache results for 1 hour
- Compress screenshots before storage
- Batch requests where possible

### ROI
- **Traditional:** Manual locator updates = 2-4 hours per UI change
- **Hybrid:** Automatic healing = 0 hours per UI change
- **Breakeven:** ~100 UI changes per year

---

## 🚨 Risk Mitigation

| Risk | Mitigation |
|------|-----------|
| VLM accuracy issues | Confidence threshold, fallback to manual, testing |
| Performance degradation | Async VLM calls, caching, performance monitoring |
| Cost overruns | Cost tracking, alerts, feature flags |
| Database bloat | Screenshot compression, retention policy |
| Locator quality | Reliability threshold, manual review option |

---

## 📅 Timeline

| Week | Phase | Deliverables |
|------|-------|--------------|
| 1 | Foundation | DB schema, VLMService, HybridExecutor |
| 2 | Integration | KafkaConsumer, AILogger, AIHelper updates |
| 3 | Frontend | TestCaseSteps UI, Analytics component, Endpoint |
| 4 | Deployment | Config, Testing, Docs, Production rollout |

---

## 👥 Team Responsibilities

- **Backend Developer:** VLMService, HybridExecutor, KafkaConsumer updates
- **Frontend Developer:** TestCaseSteps UI, Analytics component
- **DevOps:** Database migration, deployment, monitoring
- **QA:** Testing, validation, performance benchmarks
- **Product:** Documentation, user communication

---

## ✅ Deployment Checklist

- [ ] Database migration tested and approved
- [ ] All unit tests passing
- [ ] Integration tests passing
- [ ] Performance benchmarks completed
- [ ] Documentation complete
- [ ] Feature flags configured
- [ ] Staging deployment successful
- [ ] Monitoring and alerts configured
- [ ] Pilot clients identified
- [ ] Rollback procedure documented
- [ ] Team trained on new features
- [ ] Production deployment approved

---

## 📞 Support & Escalation

**Issues or Questions:**
1. Check documentation
2. Review test results
3. Contact backend team
4. Escalate to tech lead if needed

**Emergency Rollback:**
1. Set `ENABLE_VLM_FALLBACK = False`
2. Restart backend services
3. Monitor for issues
4. Investigate root cause

---

**Document Owner:** AI/Automation Team  
**Last Updated:** November 23, 2025  
**Next Review:** December 7, 2025
