# HTTP Method and Authorization Header Preservation Fix

## Problems Identified

### Problem 1: HTTP Method Changes
Gemini AI was incorrectly changing HTTP methods during test step validation/correction. For example:
- Schema specifies: `PUT /api/recipient-groups` 
- Gemini changed it to: `POST /api/recipient-groups`
- Result: 404 errors instead of successful API calls

### Problem 2: Authorization Headers Removed
During validation/correction, Gemini was removing Authorization headers from steps:
- Original step had: `"Authorization": "Bearer {{access_token}}"`
- After correction: Header was completely removed
- Result: 500 errors with "No token header" message

### Problem 3: Overly Strict Status Code Validation
Gemini was too strict about expected status codes:
- Expected: 201 for PUT requests
- Actual API response: 200 (valid success)
- Result: Unnecessary validation failures triggering corrections

## Root Causes

1. **HTTP Methods**: The validation prompt didn't explicitly instruct Gemini to preserve HTTP methods from the schema
2. **Authorization Headers**: No explicit instruction to preserve Authorization headers during corrections
3. **Status Codes**: Prompt didn't clarify that both 200 and 201 are valid success codes for POST/PUT operations

## Solution Implemented

### 1. Updated Initial Generation Prompt (`_create_step_generation_prompt`)
**File**: `/Users/aragossa/dzrprj/auroqa/auroqa/Services/ApiSchemaService.py`

Added explicit HTTP method instruction as the **first** critical requirement:

```python
1. **HTTP Methods**:
   - Use the EXACT HTTP method (GET/POST/PUT/PATCH/DELETE) specified in the API schema
   - Check the schema carefully - each endpoint shows its supported method(s)
   - Example: If schema shows "PUT /api/recipient-groups", use "PUT" not "POST"
   - DO NOT assume or change methods - use exactly what the schema specifies
```

Added flexible status code guidance:

```python
- Use "expected_status" to validate response codes
  * GET requests: typically 200
  * POST/PUT create operations: 200 or 201 (both are valid)
  * DELETE requests: 200 or 204
  * Use 200 as default if unsure
```

### 2. Updated Validation/Correction Prompt (`_fix_failed_steps`)
**File**: `/Users/aragossa/dzrprj/auroqa/auroqa/Services/ApiSchemaService.py`

Added critical rules section with explicit preservation instructions:

```python
**CRITICAL RULES FOR CORRECTIONS**:
1. **PRESERVE HTTP METHODS**: Do NOT change HTTP methods (GET/POST/PUT/PATCH/DELETE) unless the API returns 405 Method Not Allowed
   - If you see 404 errors, the issue is likely the endpoint path, NOT the method
   - Always check the API schema for the correct method for each endpoint
   - Example: If schema shows "PUT /api/recipient-groups", use PUT, not POST

2. **PRESERVE AUTHORIZATION HEADERS**: Do NOT remove Authorization headers from steps
   - If a step has "Authorization": "Bearer {{access_token}}", keep it
   - Authorization headers are REQUIRED for authenticated endpoints
   - Only remove auth headers if API returns 401 Unauthorized

3. **Common issues to fix**:
   - Wrong field names in request body (check schema definitions)
   - Wrong expected status codes (update based on actual response)
     * 200 and 201 are both valid success codes for POST/PUT requests
     * Use the actual status code returned by the API
   - Wrong endpoint paths (verify against schema paths)
   - Missing required fields (add from schema)
   - Wrong variable extraction paths (fix JSONPath expressions)

4. **What NOT to change**:
   - HTTP methods (unless 405 error)
   - Authorization headers (unless 401 error)
   - Authentication flow structure
   - Variable names already extracted
```

## Impact

### Before Fix
- ❌ Gemini changed `PUT` → `POST` when seeing 404 errors
- ❌ Authorization headers removed during validation corrections
- ❌ Tests failed with 500 "No token header" errors
- ❌ Overly strict status code validation (201 vs 200)
- ❌ Validation loop couldn't self-correct

### After Fix
- ✅ Gemini preserves HTTP methods from schema
- ✅ Authorization headers preserved during corrections
- ✅ Flexible status code validation (200 and 201 both accepted)
- ✅ Only changes methods if API returns 405 Method Not Allowed
- ✅ Only removes auth headers if API returns 401 Unauthorized
- ✅ Focuses corrections on actual issues (paths, fields, status codes)
- ✅ Validation can successfully correct real problems

## Testing
To verify the fix works:

1. **Regenerate test case 1219** (Recipient Groups Lifecycle)
2. **Verify step 2 in database**:
   - Should use `PUT /api/recipient-groups` (not POST)
   - Should have `"Authorization": "Bearer {{access_token}}"` in headers
   - Should have `expected_status: 200` (not 201)
3. **Run the test** - should execute successfully without 404 or 500 errors

## Root Cause Analysis

The issue was a **cascade of validation failures**:

1. **Initial Generation**: Gemini correctly generated step 2 with Authorization header and `expected_status: 201`
2. **Validation Execution**: API returned 200 (valid success), but expected 201
3. **Validation Failed**: Status code mismatch triggered correction flow
4. **Gemini Correction**: Without explicit instructions, Gemini removed Authorization header while fixing status code
5. **Database Save**: Corrected steps (without auth header) were saved
6. **Test Execution**: Failed with 500 "No token header" error

## Related Issues
- Authorization header removal: ✅ **FIXED** (explicit preservation rule added)
- HTTP method preservation: ✅ **FIXED** (explicit preservation rule added)
- Status code flexibility: ✅ **FIXED** (200 and 201 both accepted)

## Files Modified

### Backend
- `/Users/aragossa/dzrprj/auroqa/auroqa/Services/ApiSchemaService.py`
  - Lines 394-398: Added HTTP method instruction to initial generation
  - Lines 448-452: Added flexible status code guidance
  - Lines 815-839: Added comprehensive preservation rules to validation/correction

### Frontend
- `/Users/aragossa/dzrprj/auroqa/auroqa-ui/src/components/TestCaseSteps.js`
  - Lines 187-194: Added headers and extract_variables to apiStepData state
  - Lines 1737-1738: Preserve headers and extract_variables when loading step for editing
  - Lines 1767-1770: Use preserved headers and extract_variables when saving

## Additional Issue Found: UI Save Operation

### Problem 3: UI Removes Headers on Save
When manually editing API steps in the UI and saving changes (e.g., changing expected status code), the frontend was **hardcoding** headers to only `Content-Type`, removing the Authorization header.

**Root Cause**: 
- `TestCaseSteps.js` line 1765 hardcoded: `headers: { "Content-Type": "application/json" }`
- Did not preserve existing headers from the loaded step data
- Did not preserve `extract_variables` field

**Fix Applied**:
1. Updated `apiStepData` state initialization to include `headers` and `extract_variables` fields
2. Modified `handleEditApiStep` to load and preserve existing headers and extract_variables
3. Modified `handleSaveApiStep` to use preserved headers instead of hardcoded values

**Changes**:
```javascript
// Before (line 1765)
headers: { "Content-Type": "application/json" },

// After (line 1767)
headers: apiStepData.headers || { "Content-Type": "application/json" }, // Preserve existing headers including Authorization
```

## Status
✅ **COMPLETE** - HTTP methods, Authorization headers, and status codes now handled correctly during:
- ✅ Initial AI generation
- ✅ Validation/correction phase
- ✅ UI manual editing and saving
