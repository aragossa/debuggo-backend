# API Documentation Conflict Detection System

## Overview

This system automatically detects conflicts between API documentation (Swagger/OpenAPI) and actual API behavior during test generation. When a conflict is detected, test generation pauses and the user is notified to make a decision.

## Problem Solved

**Issue**: API returns different status codes or responses than documented in Swagger/OpenAPI specs.

**Example**: 
- Documentation says: `POST /api/auth` with invalid credentials returns `401 Unauthorized`
- Reality: API returns `500 Internal Server Error` with `{'error': 'Invalid login or password'}`

## How It Works

### 1. Conflict Detection Flow

```
Test Generation → API Call → Error Response → Conflict Detection
                                                      ↓
                                            Gemini AI Analysis
                                                      ↓
                                    Is request correct per docs?
                                    Does response match docs?
                                                      ↓
                                            YES = CONFLICT!
                                                      ↓
                                        Create Notification
                                                      ↓
                                        PAUSE Generation
                                                      ↓
                                        Wait for User
```

### 2. User Decision Points

When a conflict is detected, the user sees:

1. **Conflict Description**: AI-generated explanation of the mismatch
2. **Request Details**: Method, endpoint, headers, body
3. **Expected vs Actual**: Side-by-side comparison
   - What documentation says (e.g., 401)
   - What API actually returns (e.g., 500)
4. **Suggested Resolution**: AI-proposed corrected expected result
5. **Action Buttons**:
   - ✅ **Apply Corrected Result & Continue**: Accept reality, resume generation
   - ❌ **Cancel Test Generation**: Stop the test case

### 3. Resume After Approval

When user approves:
1. Notification marked as `approved`
2. Test generation resumes from saved state
3. Corrected expected result used going forward
4. No infinite retry loops!

## Database Schema

### `api_conflict_notifications` Table

```sql
CREATE TABLE api_conflict_notifications (
    id SERIAL PRIMARY KEY,
    test_case_id INTEGER NOT NULL,
    client_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    
    -- Conflict details
    step_number INTEGER NOT NULL,
    conflict_type VARCHAR(50), -- 'status_mismatch', 'schema_mismatch'
    
    -- Request/Response
    request_method VARCHAR(10),
    request_endpoint TEXT,
    request_body JSONB,
    expected_status INTEGER,
    actual_status INTEGER,
    actual_response JSONB,
    
    -- AI Analysis
    conflict_description TEXT,
    suggested_resolution TEXT,
    corrected_expected_status INTEGER,
    corrected_expected_response JSONB,
    
    -- User Decision
    status VARCHAR(20) DEFAULT 'pending', -- pending, approved, cancelled
    user_decision TEXT,
    resolved_at TIMESTAMP,
    
    -- Resume State
    generation_state JSONB, -- execution_history, extracted_variables, etc.
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

## Backend Implementation

### Key Methods in `ApiSchemaService`

#### 1. `_detect_documentation_conflict()`

```python
def _detect_documentation_conflict(
    self,
    test_case_id: int,
    step: dict,
    execution_result: dict,
    schema_content: str
) -> Optional[dict]:
    """
    Uses Gemini AI to analyze if there's a conflict between:
    - API documentation (Swagger/OpenAPI)
    - Actual API response
    
    Returns conflict details if detected, None otherwise.
    """
```

**Gemini Prompt**:
- Analyzes request correctness per documentation
- Compares expected vs actual status codes
- Identifies genuine conflicts (not test errors)
- Returns structured JSON with conflict details

#### 2. `_create_conflict_notification()`

```python
def _create_conflict_notification(
    self,
    test_case_id: int,
    client_id: str,
    user_id: int,
    step_number: int,
    step: dict,
    execution_result: dict,
    conflict_details: dict,
    generation_state: dict
) -> Optional[int]:
    """
    Creates notification in database with:
    - Full request/response details
    - AI conflict analysis
    - Suggested resolution
    - Saved generation state for resume
    """
```

#### 3. `_check_conflict_resolution()`

```python
def _check_conflict_resolution(self, test_case_id: int) -> Optional[dict]:
    """
    Checks if there's a pending conflict for this test case.
    
    Returns:
    - {'status': 'waiting'} - Still pending user decision
    - {'status': 'approved', 'generation_state': {...}} - Resume generation
    - {'status': 'cancelled'} - Stop generation
    - None - No conflicts
    """
```

### Integration in Test Generation Loop

```python
while step_order <= max_steps:
    # Check for pending conflicts
    conflict_resolution = self._check_conflict_resolution(test_case_id)
    if conflict_resolution:
        if conflict_resolution['status'] == 'waiting':
            return False  # Pause generation
        elif conflict_resolution['status'] == 'approved':
            # Resume from saved state
            execution_history = saved_state['execution_history']
            extracted_variables = saved_state['extracted_variables']
    
    # Execute step
    execution_result = self._execute_step_for_feedback(...)
    
    # Check for conflicts on first error
    if execution_result.get('error') and retry_count == 0:
        conflict_details = self._detect_documentation_conflict(...)
        
        if conflict_details:
            # Create notification and pause
            notification_id = self._create_conflict_notification(...)
            return False  # PAUSE - wait for user
```

## API Endpoints

### 1. Get Pending Notifications

```http
GET /api/conflict-notifications/pending
Authorization: Bearer <token>
```

**Response**:
```json
{
  "success": true,
  "notifications": [
    {
      "id": 1,
      "test_case_id": 974,
      "test_case_name": "Invalid Login Test",
      "step_number": 1,
      "conflict_type": "status_mismatch",
      "request": {
        "method": "POST",
        "endpoint": "/api/auth",
        "body": {"email": "...", "password": "wrong"}
      },
      "expected_status": 401,
      "actual_status": 500,
      "actual_response": {"error": "Invalid login or password"},
      "conflict_description": "Documentation specifies 401 for invalid credentials, but API returns 500",
      "suggested_resolution": "Update expected status to 500 to match actual API behavior",
      "corrected_expected_status": 500,
      "created_at": "2025-10-17T21:05:39Z"
    }
  ],
  "count": 1
}
```

### 2. Approve Conflict Resolution

```http
POST /api/conflict-notifications/{notification_id}/approve
Authorization: Bearer <token>
```

**Response**:
```json
{
  "success": true,
  "message": "Conflict resolution approved. Test generation will resume.",
  "notification_id": 1,
  "test_case_id": 974
}
```

**Side Effects**:
- Notification marked as `approved`
- Kafka message sent to resume test generation
- Generation resumes from saved state with corrected expectations

### 3. Reject Conflict Resolution

```http
POST /api/conflict-notifications/{notification_id}/reject
Authorization: Bearer <token>
```

**Response**:
```json
{
  "success": true,
  "message": "Conflict resolution rejected. Test generation cancelled.",
  "notification_id": 1,
  "test_case_id": 974
}
```

**Side Effects**:
- Notification marked as `cancelled`
- Test generation permanently stopped for this test case

## Frontend Component

### `ConflictNotifications.js`

**Features**:
- Auto-polls for pending conflicts every 10 seconds
- Displays conflict cards with expandable details
- Side-by-side comparison of expected vs actual
- Approve/Reject buttons with confirmation
- Real-time updates after user decision

**Usage**:
```jsx
import ConflictNotifications from './components/ConflictNotifications';

// In Dashboard or main component
<ConflictNotifications />
```

**UI Elements**:
- 🚨 Critical notification badge
- 📖 Expected (Documentation) section
- 🔍 Actual (Reality) section
- 💡 AI-suggested resolution
- ✅ Approve button (green)
- ❌ Reject button (red)

## Retry Limit Integration

The conflict detection works alongside the retry limit system:

1. **First error** (retry_count = 0): Check for documentation conflict
2. **If conflict detected**: Pause immediately, notify user
3. **If no conflict**: Continue with normal retry logic (max 3 retries)
4. **After max retries**: Move to next step (no more conflict checks)

This prevents:
- ❌ Infinite loops from retrying the same failing request
- ❌ Unnecessary conflict checks on every retry
- ✅ Smart detection on first error only
- ✅ User intervention when truly needed

## Example Scenario

### Scenario: Lucy API Invalid Login

**Documentation** (`lucy-swagger.json`):
```json
{
  "paths": {
    "/auth": {
      "post": {
        "responses": {
          "401": {
            "description": "Unauthorized"
          }
        }
      }
    }
  }
}
```

**Reality**:
```bash
curl -X POST https://lucyqa.lucysecurity.com/api/auth \
  -d '{"email":"test@test.com","password":"wrong"}' \
  -H "Content-Type: application/json"

# Response: 500 Internal Server Error
# Body: {"error": "Invalid login or password"}
```

**System Behavior**:

1. ✅ Test generation starts
2. ✅ Step 1 executes: POST /api/auth with wrong password
3. ⚠️ Response: 500 (not 401 as documented)
4. 🤖 Gemini analyzes: "Request is correct, but status doesn't match docs"
5. 🚨 Conflict detected! Create notification
6. ⏸️ Test generation PAUSED
7. 📧 User receives notification with details
8. 👤 User reviews and clicks "Apply Corrected Result"
9. ✅ Notification approved, generation resumes
10. ✅ Future steps expect 500 for invalid login (not 401)

## Benefits

1. **No Infinite Loops**: Pauses instead of retrying forever
2. **User Control**: User decides how to handle conflicts
3. **AI-Powered**: Gemini intelligently detects genuine conflicts
4. **Stateful Resume**: Generation continues from exact point it paused
5. **Audit Trail**: All conflicts logged in database
6. **Flexible**: User can approve or cancel per conflict

## Configuration

No configuration needed! System automatically:
- Detects conflicts during test generation
- Creates notifications
- Pauses generation
- Resumes on approval

## Monitoring

Check conflict notifications:
```sql
SELECT 
    cn.id,
    tc.name as test_case,
    cn.conflict_type,
    cn.status,
    cn.created_at,
    cn.resolved_at
FROM api_conflict_notifications cn
JOIN test_cases tc ON cn.test_case_id = tc.id
WHERE cn.status = 'pending'
ORDER BY cn.created_at DESC;
```

## Future Enhancements

- [ ] Email notifications for critical conflicts
- [ ] Bulk approve/reject for similar conflicts
- [ ] Conflict pattern learning (auto-approve known conflicts)
- [ ] Documentation update suggestions
- [ ] Conflict statistics dashboard
- [ ] Export conflict reports

## Files Modified

### Backend:
- `/auroqa/migrations/20251017_add_api_conflict_notifications.sql` - Database schema
- `/auroqa/Services/ApiSchemaService.py` - Conflict detection logic
- `/auroqa/main.py` - API endpoints

### Frontend:
- `/auroqa-ui/src/components/ConflictNotifications.js` - UI component
- `/auroqa-ui/src/components/ConflictNotifications.css` - Styling

### Documentation:
- `/auroqa/docs/API_CONFLICT_DETECTION_SYSTEM.md` - This file

## Testing

1. **Apply migration**:
```bash
psql -h localhost -p 5432 -U postgres -d postgres -f migrations/20251017_add_api_conflict_notifications.sql
```

2. **Start backend**:
```bash
cd /Users/aragossa/dzrprj/auroqa/auroqa
python3 main.py
```

3. **Upload API schema** with known conflicts (e.g., Lucy Swagger)

4. **Generate test steps** for invalid login test case

5. **Check for notification**:
```bash
curl -H "Authorization: Bearer <token>" \
  http://localhost:9000/api/conflict-notifications/pending
```

6. **Open frontend** and navigate to Conflict Notifications page

7. **Approve/Reject** the conflict

8. **Verify** test generation resumes or stops accordingly

## Status

✅ **COMPLETE** - Fully implemented and ready for production use.
