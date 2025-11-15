# Root Cause Analysis: Inconsistent Authorization Headers

## Problem Summary

Test case 1219 shows **inconsistent behavior** between runs:
- **Run 224**: Step 2 has Authorization header → Success (200)
- **Run 225**: Step 2 missing Authorization header → Failure (500 "No token header")

## Root Cause

### 1. Gemini Not Generating Authorization Headers Consistently

**Database Evidence**:
```sql
-- Step 2 in database (id 585):
{
  "headers": {"Content-Type": "application/json"},  // ❌ Missing Authorization
  "expected_status": 200
}
```

Gemini AI is **not consistently including** the `Authorization: Bearer {{access_token}}` header in steps that require authentication.

### 2. Environment Header Injection (Unreliable)

The `ApiTestExecutor._apply_authorization_headers()` method injects headers from environment configuration:

```python
# Line 289-312 in ApiTestExecutor.py
env_auth_headers = self.environment_vars.get('custom_variables', {}).get('authorization_headers', [])
```

**Current Environment State**:
```sql
SELECT custom_variables FROM environments WHERE project_id = 3;
-- Result: {} (empty)
```

This explains the inconsistency:
- **Run 224**: May have had environment headers configured temporarily
- **Run 225**: Environment headers were empty/removed

### 3. Validation System Not Running

The validation system (`_validate_and_fix_steps`) was added but **no logs appear** during test generation:
- Expected: `🔍 Starting validation for test case...`
- Actual: No validation logs found

**Possible Reasons**:
1. Test case 1219 was generated **before** validation code was deployed
2. Silent exception during validation (caught and ignored)
3. Validation skipped due to missing environment

## Impact

### Critical Issues

1. **Unreliable Test Generation**: Tests work randomly based on environment state
2. **False Positives**: Tests pass when they shouldn't (due to environment injection)
3. **False Negatives**: Tests fail when they shouldn't (when environment is empty)
4. **Inconsistent Behavior**: Same test case produces different results

### Affected Components

- ✅ **Step 1 (Auth)**: Always works correctly
- ❌ **Step 2 (Create Group)**: Missing Authorization header
- ❌ **Steps 3-10**: All depend on Step 2's group_id extraction

## Solutions Implemented

### Immediate Fix

**Fixed Step 2** to include Authorization header:
```sql
UPDATE test_steps 
SET description = '{
  "headers": {
    "Authorization": "Bearer {{access_token}}"  // ✅ Added
  },
  "extract_variables": {
    "group_id": "$.recipient-group.id"  // ✅ Added
  }
}'
WHERE test_case_id = 1219 AND step_order = 2;
```

### Long-term Solutions Needed

#### 1. Improve Gemini Prompt

Add explicit instruction to **always include Authorization headers** for authenticated endpoints:

```
CRITICAL: For all endpoints except /auth, include:
"headers": {
  "Authorization": "Bearer {{access_token}}"
}
```

#### 2. Enable Validation Logging

Ensure validation runs and logs are visible:
- Check why validation logs don't appear
- Add error tracking for validation failures
- Make validation mandatory for API test generation

#### 3. Remove Environment Header Injection

The `_apply_authorization_headers()` method creates confusion:
- Headers should be **explicit in test steps**
- Environment injection masks missing headers
- Makes debugging harder

**Recommendation**: Remove or make it opt-in only.

#### 4. Add Step Validation on Save

Validate test steps when saving:
```python
def validate_api_step(step):
    if step['endpoint'] != '/auth':
        if 'Authorization' not in step['headers']:
            raise ValidationError("Missing Authorization header")
```

## Testing Plan

### 1. Test Current Fix

Run test case 1219 multiple times:
```bash
# Should pass consistently now
curl -X POST http://localhost:8000/api/test-cases/1219/run
```

### 2. Generate New Test Case

Generate a new test case and verify:
- Validation logs appear
- Authorization headers are included
- All steps work on first try

### 3. Monitor Validation

Check logs for:
```
INFO: 🔍 Starting validation for test case...
INFO: 📡 Testing step 1: POST .../api/auth
INFO: ✅ Step 1 passed
INFO: 📡 Testing step 2: PUT .../api/recipient-groups
WARNING: ❌ Step 2 failed: Expected 200, got 500
INFO: 🔧 Fixing 1 failed steps...
INFO: ✅ Gemini provided corrected steps
```

## Recommendations

### Priority 1 (Critical)

1. ✅ Fix test case 1219 Step 2 (DONE)
2. 🔄 Improve Gemini prompt to always include auth headers
3. 🔄 Investigate why validation doesn't run
4. 🔄 Add validation error logging

### Priority 2 (Important)

1. Remove or disable environment header injection
2. Add step validation on save
3. Create test to verify auth headers in all steps
4. Document expected step structure

### Priority 3 (Nice to Have)

1. Add UI warning when steps missing auth headers
2. Create step template system
3. Add step linting/validation tool
4. Improve error messages

## Conclusion

The root cause is **Gemini not consistently generating Authorization headers**, masked by **unreliable environment header injection**. The validation system should catch this but isn't running.

**Immediate action**: Test case 1219 is now fixed and should work consistently.

**Next steps**: 
1. Verify validation system is working
2. Improve Gemini prompt
3. Remove environment header injection to avoid confusion
