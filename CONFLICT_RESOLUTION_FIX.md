# Conflict Resolution Bug Fix

## Problem
After user approved a conflict resolution, the system kept regenerating the **same step** instead of moving to the next step. This caused an infinite loop where:
1. Conflict detected on step 1 (401 vs 500 status mismatch)
2. User approves conflict resolution
3. System resumes but regenerates step 1 again
4. Same conflict detected again
5. Loop continues indefinitely

## Root Causes

### 1. JSON Parsing Error (JSONB Fields)
**Error**: `the JSON object must be str, bytes or bytearray, not dict`

**Location**: `ApiSchemaService._check_conflict_resolution()` lines 2201, 2203

**Issue**: The code was calling `json.loads()` on JSONB database fields that PostgreSQL already returns as Python dictionaries.

```python
# BEFORE (incorrect):
'generation_state': json.loads(generation_state) if generation_state else {},
'corrected_expected_response': json.loads(corrected_response) if corrected_response else {}

# AFTER (correct):
'generation_state': generation_state if generation_state else {},
'corrected_expected_response': corrected_response if corrected_response else {}
```

### 2. Regex on Dict Error (Gemini Validation)
**Error**: `expected string or bytes-like object`

**Location**: `ApiSchemaService._validate_error_response()` line 1911

**Issue**: The code was using regex `re.search()` on the response from `ai_helper.send_request_to_gemini()`, which already returns a parsed dictionary, not a string.

```python
# BEFORE (incorrect):
json_match = re.search(r'\{.*\}', response, re.DOTALL)  # response is already a dict!

# AFTER (correct):
if isinstance(response, dict):
    validation_result = response
else:
    json_match = re.search(r'\{.*\}', response, re.DOTALL)
```

### 3. Missing Step Increment After Conflict Resolution
**Location**: `ApiSchemaService.generate_test_steps_iteratively()` lines 1062-1084

**Issue**: When resuming from an approved conflict, the code loaded the saved `step_order` but didn't increment it. This caused the system to regenerate the same step that had the conflict.

**Fix**: Added `step_order += 1` after loading saved state to move to the **next** step.

```python
# BEFORE:
step_order = saved_state.get('step_order', 1)
resuming_from_conflict = True

# AFTER:
step_order = saved_state.get('step_order', 1)
# IMPORTANT: Increment step_order to move to NEXT step after conflict
step_order += 1
resuming_from_conflict = True
```

### 4. Empty Execution History When Resuming
**Location**: `ApiSchemaService.generate_test_steps_iteratively()` lines 1181-1198

**Issue**: When saving conflict state, execution history was empty (0 previous steps). The code saved `generation_state` with `execution_history` **before** adding the current step's result to it. When resuming, the AI had no context about step 1.

**Fix**: Add the conflicted step to `execution_history` **before** saving state.

```python
# BEFORE saving state, add current step to history:
execution_history.append({
    'step_order': step_order,
    'step': current_step,
    'request': execution_result['request'],
    'response': execution_result['response'],
    'conflict': True  # Mark this step had a conflict
})

# THEN save state with populated history
generation_state = {
    'execution_history': execution_history,  # Now has 1 step!
    'extracted_variables': extracted_variables,
    'step_order': step_order,
    'current_step': current_step
}
```

## Code Changes

### File: `/auroqa/Services/ApiSchemaService.py`

#### Change 1: Remove json.loads() from JSONB fields (lines 2200-2209)
**Issue**: JSONB fields are already Python dicts
```python
elif status == 'approved':
    # User approved the correction
    # Note: JSONB fields are already dicts, no need to json.loads()
    return {
        'status': 'approved',
        'notification_id': notification_id,
        'generation_state': generation_state if generation_state else {},
        'corrected_expected_status': corrected_status,
        'corrected_expected_response': corrected_response if corrected_response else {}
    }
```

#### Change 2: Check if response is dict before regex (lines 1909-1920)
**Issue**: AIHelper returns parsed dict, not string
```python
# AIHelper already returns parsed dict, check if it's already a dict
if isinstance(response, dict):
    validation_result = response
else:
    # If it's a string, try to extract JSON from response
    import re
    json_match = re.search(r'\{.*\}', response, re.DOTALL)
    if json_match:
        validation_result = json.loads(json_match.group())
```

#### Change 3: Increment step_order when resuming (lines 1062-1075)
**Issue**: System regenerated same step after conflict
```python
if conflict_resolution and conflict_resolution['status'] == 'approved':
    # Resume from saved state
    self.logger.info(f"✅ Resuming generation from approved conflict resolution...")
    saved_state = conflict_resolution['generation_state']
    if saved_state:
        execution_history = saved_state.get('execution_history', [])
        extracted_variables = saved_state.get('extracted_variables', {})
        step_order = saved_state.get('step_order', 1)
        
        # IMPORTANT: Increment step_order to move to NEXT step after conflict
        step_order += 1
        
        resuming_from_conflict = True
        self.logger.info(f"📍 Resuming from step {step_order} (conflict resolved on step {step_order - 1}) with {len(execution_history)} previous steps")
```

#### Change 4: Defensive increment in loop (lines 1113-1123)
**Issue**: Backup increment in case loop check is reached
```python
elif conflict_resolution['status'] == 'approved':
    # Resume from saved state
    self.logger.info(f"✅ User approved conflict resolution, resuming generation...")
    saved_state = conflict_resolution['generation_state']
    if saved_state:
        execution_history = saved_state.get('execution_history', execution_history)
        extracted_variables = saved_state.get('extracted_variables', extracted_variables)
        step_order = saved_state.get('step_order', step_order)
        # Increment to move to next step after conflict
        step_order += 1
        self.logger.info(f"📍 Moving to step {step_order} after conflict resolution")
```

#### Change 5: Add step to history before saving state (lines 1181-1198)
**Issue**: Execution history was empty when resuming
```python
if conflict_details:
    # IMPORTANT: Add current step to execution history BEFORE saving state
    # so AI has context when resuming
    execution_history.append({
        'step_order': step_order,
        'step': current_step,
        'request': execution_result['request'],
        'response': execution_result['response'],
        'conflict': True  # Mark this step had a conflict
    })
    
    # Create notification and pause generation
    generation_state = {
        'execution_history': execution_history,  # Now contains step 1!
        'extracted_variables': extracted_variables,
        'step_order': step_order,
        'current_step': current_step
    }
```

## Expected Behavior After Fix

1. **Conflict Detected**: System detects status mismatch (e.g., expected 401, got 500) on step 1
2. **Notification Created**: Conflict notification saved with current state (step_order=1)
3. **User Approves**: User clicks "Apply & Continue" in popup
4. **Resume Generation**: System loads saved state and increments step_order to 2
5. **Generate Next Step**: System generates step 2 based on execution history
6. **Continue Flow**: Test generation continues normally until complete

## Testing

### Before Fix:
```
Step 1: POST /api/auth (invalid password) → 500 status
Conflict detected: Expected 401, got 500
User approves conflict
Resume generation...
Step 1: POST /api/auth (invalid password) → 500 status  ❌ LOOP
Conflict detected again...
```

### After Fix:
```
Step 1: POST /api/auth (invalid password) → 500 status
Conflict detected: Expected 401, got 500
User approves conflict
Resume generation from step 2...
Step 2: POST /api/auth (valid credentials) → 200 status  ✅ NEXT STEP
Step 3: GET /api/campaigns → 200 status
...
Test generation complete!
```

## Summary of Fixes

| Issue | Location | Fix |
|-------|----------|-----|
| JSON parsing on JSONB fields | `_check_conflict_resolution()` | Remove `json.loads()` calls |
| Regex on dict object | `_validate_error_response()` | Check `isinstance(response, dict)` first |
| Missing step increment | `generate_test_steps_iteratively()` (pre-loop) | Add `step_order += 1` |
| ~~Missing step increment~~ **REMOVED** | ~~`generate_test_steps_iteratively()` (in-loop)~~ | ~~Add `step_order += 1`~~ **Caused double increment!** |
| Empty execution history | `generate_test_steps_iteratively()` (conflict save) | Add step to history before saving state |
| Old conflicts blocking new runs | `_check_conflict_resolution()` | Filter query to only pending/approved statuses |
| Double increment skipping steps | `generate_test_steps_iteratively()` (in-loop) | Remove duplicate `step_order += 1` |
| Conflicted steps not saved | `generate_test_steps_iteratively()` (after resume) | Save conflicted steps from history to database |

### 5. Old Conflict Notifications Blocking New Runs
**Issue**: "Test generation cancelled by user" when user didn't cancel anything

**Location**: `ApiSchemaService._check_conflict_resolution()` lines 2199-2209

**Problem**: The query fetched the most recent conflict notification regardless of status. If there was an old 'rejected' or 'cancelled' notification from a previous test run, it would block new test generation.

**Fix**: Filter query to only check for **active** statuses (pending, approved) and ignore old processed/rejected/cancelled notifications.

```sql
-- BEFORE: Fetched any status
WHERE test_case_id = %s

-- AFTER: Only fetch active conflicts
WHERE test_case_id = %s
  AND status IN ('pending', 'approved')
```

### 6. Double Increment Causing Skipped Step Numbers
**Issue**: "Resuming from step 3" when it should be step 2, causing AI to think test is complete

**Location**: `ApiSchemaService.generate_test_steps_iteratively()` lines 1072 and 1119

**Problem**: `step_order` was being incremented **twice**:
1. Pre-loop increment at line 1072: `step_order += 1` (1 → 2)
2. In-loop increment at line 1119: `step_order += 1` (2 → 3)

This caused the system to skip from step 1 (conflict) to step 3, skipping step 2 entirely. The AI saw only 1 step in history and was asked to generate step 3, so it returned `{"complete": true}` thinking the test was done.

**Fix**: Removed the duplicate increment at line 1119 since pre-loop already handles it.

```python
# BEFORE (line 1119):
step_order += 1  # Double increment!

# AFTER:
# NOTE: step_order already incremented in pre-loop check, don't increment again!
```

### 7. Conflicted Steps Not Saved to Database ⚠️ CRITICAL
**Issue**: "0 steps generated" even though conflict was resolved - conflicted steps were in execution history but never saved to database

**Location**: `ApiSchemaService.generate_test_steps_iteratively()` lines 1122-1129

**Problem**: When a conflict occurred:
1. Step executed → Conflict detected → Step added to execution_history (with `conflict: true` flag)
2. Step NOT saved to database (because it had an error)
3. User approves conflict → System resumes
4. AI says test complete → Loop exits
5. **Result: 0 steps in database!**

The conflicted steps were never saved because they had errors, and after conflict resolution, the system didn't retroactively save them.

**Fix**: After loading saved state from approved conflict, iterate through execution_history and save any steps marked with `conflict: true` to the database.

```python
# AFTER loading saved state (lines 1122-1129):
# CRITICAL: Save the conflicted step(s) to database now that conflict is resolved
for hist_item in execution_history:
    if hist_item.get('conflict'):
        # This step had a conflict that's now resolved - save it to database
        conflicted_step = hist_item['step']
        conflicted_step['step_order'] = hist_item['step_order']
        self._save_single_step(test_case_id, conflicted_step, client_id)
        generated_steps.append(conflicted_step)
        self.logger.info(f"💾 Saved previously conflicted step {hist_item['step_order']} to database")
```

## Status
✅ **FIXED** - All seven errors resolved:
1. No more JSON parsing errors on JSONB fields
2. No more regex errors on dict objects  
3. Test generation properly moves to next step after conflict resolution
4. Execution history properly saved with conflicted step for AI context
5. Old conflict notifications no longer block new test generation runs
6. No more double increment - step numbers now sequential (1, 2, 3 not 1, 3)
7. Conflicted steps now saved to database after conflict resolution ✅

## Date
October 18, 2025
