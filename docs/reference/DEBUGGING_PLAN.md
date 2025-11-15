# Debugging Plan: Missing Authorization Headers

## Current Status

### What We Know

1. ✅ **Gemini IS generating Authorization headers** (confirmed in text_output_1.txt)
2. ❌ **Headers are disappearing** before reaching the database
3. ❌ **Validation is NOT running** (no validation logs appear)
4. ❌ **Step 2 fails** with 404 or "No token header"

### Evidence

**Gemini's Output** (text_output_1.txt):
```json
{
  "step_order": 2,
  "headers": {
    "Content-Type": "application/json",
    "Accept": "application/json",
    "Authorization": "Bearer {{access_token}}"  // ✅ PRESENT
  }
}
```

**Database** (test_steps table):
```json
{
  "headers": {
    "Content-Type": "application/json"  // ❌ Authorization MISSING
  }
}
```

## Debugging Steps Added

### 1. Enhanced Logging in ApiSchemaService

**Added logs to track**:
- Number of steps parsed from Gemini
- Step 2 headers immediately after parsing
- Validation process start/completion
- Headers before saving to database

**Expected New Logs**:
```
INFO: 📝 Parsed 10 steps from Gemini response
INFO: 🔍 Step 2 headers from Gemini: {'Content-Type': '...', 'Authorization': 'Bearer {{access_token}}'}
INFO: 🚀 Starting validation process...
INFO: 🔍 Starting validation for test case 1219 with 10 steps...
INFO: 📋 Validation imports successful
INFO: 📡 Testing step 1: POST .../api/auth
INFO: ✅ Step 1 passed
INFO: 📡 Testing step 2: POST .../api/recipient-groups
INFO: ❌ Step 2 failed: Expected 201, got 500
INFO: 🔧 Fixing 1 failed steps...
INFO: ✅ Gemini provided corrected steps
INFO: ✅ Validation process completed
INFO: 📋 Step 2 headers before save: {'Content-Type': '...', 'Authorization': 'Bearer {{access_token}}'}
INFO: Saved step 2/10 for test case 1219
```

### 2. Possible Root Causes

#### Theory 1: AIHelper is Stripping Headers
The AIHelper's JSON parsing might be removing certain fields.

**Check**: Look at AIHelper.py's `send_request_to_gemini()` method

#### Theory 2: Validation is Silently Failing
Validation throws an exception that's caught and logged as warning.

**Check**: Look for error/warning logs during validation

#### Theory 3: Database Column Limitation
The description column might have a size limit that truncates the JSON.

**Check**: Database schema for test_steps.description column type

#### Theory 4: JSON Serialization Issue
Python's `json.dumps()` might be filtering certain keys.

**Check**: Test json.dumps() with the exact step data

## Next Steps

### Immediate Actions

1. **Regenerate test case 1219** to see new debug logs
2. **Check for validation errors** in logs
3. **Verify headers are present** after parsing
4. **Track where headers disappear** in the pipeline

### Test Command

```bash
# Regenerate test case 1219 via UI or API
# Watch logs for:
grep -E "(📝|🔍|🚀|✅|📋|📡)" auroqa.log
```

### If Headers Present After Parsing But Missing in DB

**Problem**: Validation or save is stripping them

**Solution**: 
- Check validation's `_fix_failed_steps()` return value
- Verify `json.dumps()` preserves all fields
- Check database constraints

### If Headers Missing After Parsing

**Problem**: AIHelper is stripping them

**Solution**:
- Check AIHelper's response processing
- Verify Gemini's actual response format
- Check for any response filtering

### If Validation Not Running

**Problem**: Exception during validation setup

**Solution**:
- Check environment lookup
- Verify database connection
- Check for missing imports (requests library)

## Expected Outcome

After regenerating with new logs, we should see:
1. **Where headers disappear** (parsing, validation, or save)
2. **Why validation doesn't run** (exception or skip condition)
3. **What needs to be fixed** (specific method or logic)

## Files Modified

- `/Users/aragossa/dzrprj/auroqa/auroqa/Services/ApiSchemaService.py`
  - Added debug logging in `generate_test_steps_for_flow()`
  - Added header logging in `_save_test_steps()`
  - Added validation process logging

## Action Required

**Regenerate test case 1219** and provide the full logs from generation to execution.
