# Iterative API Test Generation - Implementation Guide

## Overview

Changed the API test generation flow from **batch generation with post-validation** to **iterative step-by-step generation with real-time execution feedback**.

---

## Old Flow vs New Flow

### ❌ Old Flow (Batch Generation):
1. User uploads schema → Gemini creates route list
2. Gemini generates test cases
3. User clicks "Generate Steps" → **Gemini generates ALL steps at once**
4. System tries to execute all steps
5. If errors occur → System sends request to Gemini to fix them
6. **Problem**: Gemini makes assumptions without seeing actual API responses

### ✅ New Flow (Iterative Generation):
1. User uploads schema → Gemini creates route list
2. Gemini generates test cases
3. User clicks "Generate Steps" → **Gemini generates FIRST step only**
4. System executes the step immediately
5. System collects request (body, headers, URL, params) and response
6. System sends execution results to Gemini
7. Gemini generates expected result for this step + next step
8. **Repeat steps 4-7** until test flow is complete
9. **Benefit**: Gemini sees actual API behavior and adapts accordingly

---

## Implementation Details

### 1. New Main Method: `generate_test_steps_iteratively()`

**Location**: `/Users/aragossa/dzrprj/auroqa/auroqa/Services/ApiSchemaService.py` (lines 984-1116)

**Key Features**:
- Generates one step at a time
- Executes each step immediately after generation
- Collects real request/response data
- Passes execution history to Gemini for next step generation
- Stops when test flow is complete (max 20 steps safety limit)

**Flow**:
```python
while step_order <= max_steps:
    # Generate step (first or next based on history)
    current_step = _generate_first_step() or _generate_next_step(execution_history)
    
    # Save to database
    _save_single_step(test_case_id, current_step, client_id)
    
    # Execute immediately
    execution_result = _execute_step_for_feedback(test_case_id, current_step, project_id, client_id)
    
    # Add to history for next iteration
    execution_history.append({
        'step': current_step,
        'request': execution_result['request'],
        'response': execution_result['response']
    })
    
    # Check if complete
    if _is_test_flow_complete(execution_history):
        break
```

---

### 2. Helper Methods

#### `_generate_first_step()` (lines 1118-1175)
- Generates the first step (usually authentication)
- Looks for 🔒 [REQUIRES AUTHENTICATION] markers in schema
- Uses EXACT HTTP methods from schema (PUT vs POST)
- Includes extract_variables for capturing tokens/IDs

**Prompt Structure**:
- ⚠️ CRITICAL WARNING about non-standard REST conventions
- Test case name and description
- Full API schema summary
- Rules for first step generation
- Returns single JSON object (not array)

#### `_generate_next_step()` (lines 1177-1255)
- Generates next step based on execution history
- Receives ALL previous requests and responses
- Gemini can see actual API behavior
- Can return `{"complete": true}` to end test flow

**Prompt Structure**:
- ⚠️ CRITICAL WARNING about HTTP methods
- Test case context
- API schema
- **EXECUTION HISTORY** with full request/response details
- Rules for next step generation
- Can signal completion

#### `_execute_step_for_feedback()` (lines 1275-1391)
- Executes a single step against real API
- Gets environment variables (base_url, login, password)
- Substitutes variables in endpoint, headers, body
- Makes actual HTTP request
- Returns structured request/response data

**Returns**:
```python
{
    'request': {
        'method': 'POST',
        'url': 'https://api.example.com/auth',
        'headers': {...},
        'body': {...}
    },
    'response': {
        'status': 200,
        'headers': {...},
        'body': {...}
    }
}
```

#### `_parse_single_step_response()` (lines 1257-1273)
- Parses Gemini's JSON response
- Handles markdown code blocks
- Returns step dict or None

#### `_save_single_step()` (lines 1393-1414)
- Saves individual step to database
- Called immediately after generation

#### `_is_test_flow_complete()` (lines 1416-1434)
- Heuristic to determine if test is complete
- Checks for DELETE with 200/204 (cleanup step)
- Limits to 5+ steps maximum

---

### 3. Kafka Integration

**File**: `/Users/aragossa/dzrprj/auroqa/auroqa/Utils/Connectors/KafkaMessageConsumer.py` (line 157)

**Changed**:
```python
# OLD:
success = service.generate_test_steps_for_flow(...)

# NEW:
success = service.generate_test_steps_iteratively(...)
```

The Kafka message handler now calls the iterative method automatically.

---

## Key Improvements

### 1. **Accurate Field Names**
- Gemini sees actual API responses
- If it uses wrong field name, next prompt includes the error
- Can self-correct based on actual API behavior

### 2. **Correct HTTP Methods**
- Even if Gemini generates POST instead of PUT
- Execution will fail with 404
- Next prompt includes the 404 error
- Gemini can see from schema that PUT is correct

### 3. **Dynamic Variable Extraction**
- Gemini sees actual response structure
- Can extract correct field names for IDs/tokens
- Uses actual JSONPath based on real responses

### 4. **Adaptive Test Flow**
- Gemini can adjust test flow based on API responses
- If API returns unexpected structure, adapts next steps
- Can handle edge cases discovered during execution

### 5. **Real-Time Feedback Loop**
```
Generate Step → Execute → See Results → Generate Next Step
     ↑                                          ↓
     └──────────────────────────────────────────┘
```

---

## Example Execution Log

```
🔄 Starting iterative step generation for test case 1292
📝 Generating first step...
🔄 Processing step 1...
▶️ Executing step 1...
✅ Step 1 executed: 200
  Request: POST /api/auth
  Response: {"token": "abc123", "user": {...}}

🔄 Processing step 2...
📝 Generating next step based on execution history...
  (Gemini sees step 1 succeeded, token extracted)
▶️ Executing step 2...
✅ Step 2 executed: 200
  Request: PUT /api/clients (Gemini used PUT, not POST!)
  Response: {"id": 456, "name": "Test Client"}

🔄 Processing step 3...
📝 Generating next step...
  (Gemini sees client created with ID 456)
▶️ Executing step 3...
✅ Step 3 executed: 200
  Request: GET /api/clients/456
  Response: {"id": 456, "name": "Test Client", ...}

... continues until test flow complete ...

✅ Iterative generation complete: 5 steps generated
```

---

## Testing the New Flow

### 1. Delete existing test steps:
```bash
PGPASSWORD=eYuUm57C! psql -h localhost -p 5432 -U postgres -d postgres -c "DELETE FROM test_steps WHERE test_case_id = 1292"
```

### 2. Trigger generation from UI:
- Go to Dashboard
- Select test case 1292
- Click "Generate with AI"
- Watch backend logs for iterative execution

### 3. Expected behavior:
- Steps generated one at a time
- Each step executed immediately
- Logs show request/response for each step
- Gemini adapts based on actual API responses

---

## Configuration

### Environment Variables Required:
- `base_url`: API base URL
- `login`: Username/email for authentication
- `password`: Password for authentication
- `custom_variables`: Any additional variables (optional)

### Safety Limits:
- **Max steps**: 20 (prevents infinite loops)
- **Request timeout**: 30 seconds
- **SSL verification**: Disabled for testing (line 1365)

---

## Backward Compatibility

The old batch generation method `generate_test_steps_for_flow()` is still available but **not used by default**.

To switch back to old method:
```python
# In KafkaMessageConsumer.py line 157
success = service.generate_test_steps_for_flow(...)  # Old method
```

---

## Future Enhancements

1. **Variable Tracking**: Improve extraction and tracking of variables across steps
2. **Smart Completion**: Better heuristics for detecting test flow completion
3. **Error Recovery**: If step fails, ask Gemini to fix and retry
4. **Parallel Execution**: Generate multiple test flows in parallel
5. **UI Progress**: Show real-time progress in frontend

---

## Files Modified

1. **`/Users/aragossa/dzrprj/auroqa/auroqa/Services/ApiSchemaService.py`**
   - Added `generate_test_steps_iteratively()` (lines 984-1116)
   - Added 6 helper methods (lines 1118-1434)

2. **`/Users/aragossa/dzrprj/auroqa/auroqa/Utils/Connectors/KafkaMessageConsumer.py`**
   - Updated `process_api_test_steps_generation()` to use iterative method (line 157)

3. **`/Users/aragossa/dzrprj/auroqa/auroqa/Services/ApiSchemaServiceIterative.py`** (NEW)
   - Reference file with helper method implementations

---

## Status

✅ **IMPLEMENTATION COMPLETE**

Ready for testing. The new iterative flow is now the default for API test step generation.
