# API Test Execution Guide

## Overview

AuroQA now supports complete API test execution with automatic routing, environment variable substitution, and comprehensive test result tracking.

## How to Run API Tests

### 1. Create an Environment

Before running API tests, you need to create an environment with:

- **Base URL**: The API base URL (e.g., `https://api.example.com`)
- **Login/Password**: Authentication credentials
- **Custom Variables**: Any additional variables needed for your tests
- **Authorization Headers**: Headers like `Authorization: Bearer {{auth_token}}`

Navigate to **Environments** tab and create a new environment for your project.

### 2. Create API Test Cases

You have two options:

#### Option A: Upload API Schema (Recommended)
1. Navigate to **API Testing** tab
2. Click "Upload Schema"
3. Upload OpenAPI/Swagger/Postman collection
4. System automatically generates test case flows with `test_type='api'`

#### Option B: Manual Creation
1. Create a test case in the test tree
2. Set `test_type='api'` when creating
3. Click "Generate with AI" to generate test steps

### 3. Generate Test Steps

For API test cases:
1. Select the API test case in the tree
2. Click **"Generate with AI"** button
3. System uses the endpoint: `POST /api/test-cases/{id}/generate-api-steps`
4. AI generates steps with proper JSON structure

### 4. Execute the Test

1. Select your API test case
2. Click **"Run Test"** button
3. Select an environment from the dropdown
4. Optionally select a test execution to link results
5. Click "Run"

The system will:
- Detect the test case type is `api`
- Route to `ApiTestExecutor` (not browser automation)
- Execute API requests with variable substitution
- Store results in `test_runs` table

## API Test Step Structure

API test steps are stored in the `test_steps` table with JSON data in the `description` field:

```json
{
  "method": "POST",
  "endpoint": "/api/auth/login",
  "headers": {
    "Content-Type": "application/json"
  },
  "body": {
    "username": "{{login}}",
    "password": "{{password}}"
  },
  "expected_status": 200,
  "extract_variables": {
    "access_token": "token"
  }
}
```

### Supported Actions

- `api_request` - Generic HTTP request
- `api_auth` - Authentication request
- `api_get` - GET request
- `api_post` - POST request
- `api_put` - PUT request
- `api_delete` - DELETE request
- `api_patch` - PATCH request
- `wait` - Wait for specified seconds
- `assert` - Assertion validation

## Variable Substitution

### Environment Variables

Available in all API requests:
- `{{base_url}}` - From environment configuration
- `{{login}}` - From environment configuration
- `{{password}}` - From environment configuration
- `{{custom_variable_name}}` - From environment custom_variables

### Session Variables

Extracted during test execution:
- `{{access_token}}` - Extracted from authentication response
- `{{auth_token}}` - Alias for access_token
- `{{token}}` - Alias for access_token
- Any variable defined in `extract_variables`

### Authorization Headers

Headers are automatically applied from environment configuration:

```javascript
// In environment custom_variables.authorization_headers:
[
  {
    "name": "Authorization",
    "value": "Bearer {{auth_token}}"
  },
  {
    "name": "X-API-Key",
    "value": "{{api_key}}"
  }
]
```

The executor automatically handles token variable aliases:
- `{{auth_token}}` → uses `access_token` from session
- `{{access_token}}` → uses `auth_token` from session
- `{{token}}` → uses `access_token` from session

## Example Test Flow

### 1. Authentication Step
```json
{
  "step_order": 1,
  "action": "api_request",
  "description": {
    "method": "POST",
    "endpoint": "/api/auth/login",
    "headers": {"Content-Type": "application/json"},
    "body": {
      "username": "{{login}}",
      "password": "{{password}}"
    },
    "expected_status": 200,
    "extract_variables": {
      "access_token": "token"
    }
  }
}
```

### 2. Authenticated Request
```json
{
  "step_order": 2,
  "action": "api_request",
  "description": {
    "method": "GET",
    "endpoint": "/api/users",
    "headers": {
      "Authorization": "Bearer {{access_token}}"
    },
    "expected_status": 200
  }
}
```

### 3. Create Resource
```json
{
  "step_order": 3,
  "action": "api_request",
  "description": {
    "method": "POST",
    "endpoint": "/api/users",
    "headers": {
      "Authorization": "Bearer {{access_token}}",
      "Content-Type": "application/json"
    },
    "body": {
      "name": "Test User",
      "email": "test@example.com"
    },
    "expected_status": 201,
    "extract_variables": {
      "user_id": "id"
    }
  }
}
```

## Execution Flow

```
1. User clicks "Run Test" on API test case
   ↓
2. Backend checks test_type from database
   ↓
3. test_type == 'api' → Route to ApiTestExecutor
   ↓
4. ApiTestExecutor loads test steps from database
   ↓
5. For each step:
   - Parse JSON from description field
   - Substitute environment variables
   - Apply authorization headers
   - Make HTTP request
   - Validate response status
   - Extract variables for next steps
   ↓
6. Store results in test_runs table
   ↓
7. Return success/failure to frontend
```

## Database Schema

### Test Steps Table
```sql
CREATE TABLE test_steps (
    id SERIAL PRIMARY KEY,
    test_case_id INTEGER REFERENCES test_cases(id),
    step_order INTEGER NOT NULL,
    action TEXT NOT NULL,  -- 'api_request', 'api_get', etc.
    description TEXT,      -- JSON with request details
    expected_result TEXT,  -- Human-readable summary
    element_path TEXT,     -- Optional: endpoint path
    value TEXT,            -- Optional: additional data
    ...
);
```

### Test Runs Table
```sql
CREATE TABLE test_runs (
    id SERIAL PRIMARY KEY,
    test_case_id INTEGER REFERENCES test_cases(id),
    run_date TIMESTAMP DEFAULT NOW(),
    result VARCHAR(20),    -- 'passed', 'failed', 'running'
    error_message TEXT,
    execution_id INTEGER REFERENCES test_executions(id),
    ...
);
```

## API Endpoints

### Execute Test Case
```
POST /api/run_test_case/{id}
Body: {
  "environment_id": 123,
  "execution_id": 456  // optional
}
```

### Generate API Test Steps
```
POST /api/test-cases/{test_case_id}/generate-api-steps
```

### Get Test Results
```
GET /api/test_runs/{test_run_id}
```

## Troubleshooting

### Test Not Executing
- Verify test case has `test_type='api'` in database
- Check that environment is selected before running
- Ensure environment has required variables (base_url, login, password)

### Variable Not Substituting
- Check variable name matches exactly (case-sensitive)
- Verify variable exists in environment or was extracted in previous step
- Use `{{variable_name}}` format with double curly braces

### Authorization Header Not Applied
- Verify headers are stored in `custom_variables.authorization_headers`
- Check that token was extracted in authentication step
- Review logs for "Applied authorization header" messages

### Request Failing
- Check `expected_status` matches actual API response
- Verify endpoint path is correct (relative to base_url)
- Review request body format (JSON vs string)

## Best Practices

1. **Always authenticate first** - Extract tokens in step 1
2. **Use variable extraction** - Store IDs/tokens for subsequent steps
3. **Validate responses** - Set appropriate expected_status codes
4. **Clean up resources** - Add delete steps at the end if needed
5. **Use environments** - Don't hardcode URLs or credentials
6. **Test incrementally** - Start with simple flows, add complexity

## Next Steps

- Review generated test steps before execution
- Create multiple environments (dev, staging, prod)
- Link test runs to test executions for organized reporting
- Monitor test results in the test runs history
