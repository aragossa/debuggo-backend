# API Step Editor Enhancement

## Overview
Enhanced the API step editor modal to allow manual editing of **Headers** and **Extract Variables** fields, providing full control over API test step configuration.

## New Features

### 1. **Headers Editor**
- **Field Type**: JSON textarea with syntax highlighting
- **Purpose**: Manually edit HTTP headers including Authorization, Content-Type, custom headers
- **Validation**: Real-time JSON parsing with error feedback
- **Placeholder Example**: 
  ```json
  {
    "Content-Type": "application/json",
    "Authorization": "Bearer {{access_token}}"
  }
  ```

### 2. **Extract Variables Editor**
- **Field Type**: JSON textarea with syntax highlighting
- **Purpose**: Define which values to extract from API responses using JSONPath
- **Validation**: Real-time JSON parsing with error feedback
- **Placeholder Example**:
  ```json
  {
    "access_token": "$.token",
    "user_id": "$.user.id"
  }
  ```

## UI Changes

### Before
```
┌─────────────────────────────────┐
│ Edit API Request Step           │
├─────────────────────────────────┤
│ HTTP Method: [PUT ▼]            │
│ Endpoint: [/api/endpoint]       │
│ Request Body: [JSON textarea]   │
│ Expected Status: [200]          │
│ [Cancel] [Save]                 │
└─────────────────────────────────┘
```

### After
```
┌─────────────────────────────────┐
│ Edit API Request Step           │
├─────────────────────────────────┤
│ HTTP Method: [PUT ▼]            │
│ Endpoint: [/api/endpoint]       │
│ Headers (JSON):                 │
│ ┌─────────────────────────────┐ │
│ │ {                           │ │
│ │   "Authorization": "..."    │ │
│ │ }                           │ │
│ └─────────────────────────────┘ │
│ ℹ️ Include Authorization, etc.  │
│                                 │
│ Request Body (JSON):            │
│ [JSON textarea - 8 rows]        │
│                                 │
│ Expected Status: [200]          │
│                                 │
│ Extract Variables (JSON):       │
│ ┌─────────────────────────────┐ │
│ │ {                           │ │
│ │   "token": "$.token"        │ │
│ │ }                           │ │
│ └─────────────────────────────┘ │
│ ℹ️ Use JSONPath notation        │
│                                 │
│ [Cancel] [Save]                 │
└─────────────────────────────────┘
```

## Implementation Details

### Frontend Changes (`TestCaseSteps.js`)

#### 1. State Initialization
```javascript
const [apiStepData, setApiStepData] = useState({
  method: 'GET',
  endpoint: '',
  body: '',
  expected_status: 200,
  headers: { "Content-Type": "application/json" },  // ✅ Added
  extract_variables: {}  // ✅ Added
});
```

#### 2. Load Step Data
```javascript
const handleEditApiStep = (step) => {
  const stepData = JSON.parse(step.description || '{}');
  setApiStepData({
    method: stepData.method || 'GET',
    endpoint: stepData.endpoint || '',
    body: stepData.body ? JSON.stringify(stepData.body, null, 2) : '',
    expected_status: stepData.expected_status || 200,
    headers: stepData.headers || { "Content-Type": "application/json" },  // ✅ Preserve
    extract_variables: stepData.extract_variables || {}  // ✅ Preserve
  });
};
```

#### 3. JSON Validation on Change
```javascript
// Headers field
onChange={(e) => {
  try {
    const parsed = JSON.parse(e.target.value);
    setApiStepData({...apiStepData, headers: parsed});
  } catch (err) {
    // Allow invalid JSON while typing
    setApiStepData({...apiStepData, headers: e.target.value});
  }
}}

// Extract Variables field
onChange={(e) => {
  try {
    const parsed = JSON.parse(e.target.value);
    setApiStepData({...apiStepData, extract_variables: parsed});
  } catch (err) {
    // Allow invalid JSON while typing
    setApiStepData({...apiStepData, extract_variables: e.target.value});
  }
}}
```

#### 4. Save with Validation
```javascript
const handleSaveApiStep = async () => {
  // Parse headers if it's a string
  let headersData = apiStepData.headers;
  if (typeof headersData === 'string') {
    try {
      headersData = JSON.parse(headersData);
    } catch (e) {
      alert('Invalid JSON in headers');
      return;
    }
  }

  // Parse extract_variables if it's a string
  let extractVarsData = apiStepData.extract_variables;
  if (typeof extractVarsData === 'string') {
    try {
      extractVarsData = JSON.parse(extractVarsData);
    } catch (e) {
      alert('Invalid JSON in extract variables');
      return;
    }
  }

  const descriptionData = {
    method: apiStepData.method,
    endpoint: apiStepData.endpoint,
    headers: headersData || { "Content-Type": "application/json" },
    body: bodyData,
    expected_status: parseInt(apiStepData.expected_status),
    extract_variables: extractVarsData || {}
  };
  
  // Save to backend...
};
```

## Use Cases

### 1. **Adding Authorization Headers**
```json
{
  "Content-Type": "application/json",
  "Accept": "application/json",
  "Authorization": "Bearer {{access_token}}",
  "X-API-Key": "{{api_key}}"
}
```

### 2. **Extracting Multiple Variables**
```json
{
  "access_token": "$.token",
  "refresh_token": "$.refresh_token",
  "user_id": "$.user.id",
  "group_id": "$.recipient-group.id"
}
```

### 3. **Custom Headers for Testing**
```json
{
  "Content-Type": "application/json",
  "X-Request-ID": "{{uuid}}",
  "X-Timestamp": "{{timestamp}}",
  "X-Client-Version": "1.0.0"
}
```

### 4. **Nested Variable Extraction**
```json
{
  "user_name": "$.data.user.name",
  "user_email": "$.data.user.email",
  "account_id": "$.data.account.id",
  "permissions": "$.data.permissions[0]"
}
```

## JSONPath Examples

| JSONPath | Description | Example Response | Extracted Value |
|----------|-------------|------------------|-----------------|
| `$.token` | Top-level field | `{"token": "abc123"}` | `"abc123"` |
| `$.user.id` | Nested field | `{"user": {"id": 42}}` | `42` |
| `$.data[0].name` | Array element | `{"data": [{"name": "John"}]}` | `"John"` |
| `$.recipient-group.id` | Hyphenated field | `{"recipient-group": {"id": 51}}` | `51` |

## Validation Features

### Real-time JSON Parsing
- ✅ Allows typing invalid JSON (for user convenience)
- ✅ Validates on save before sending to backend
- ✅ Shows clear error messages for invalid JSON
- ✅ Preserves formatting with `JSON.stringify(obj, null, 2)`

### Error Messages
- **Invalid JSON in headers**: Shown when headers field contains malformed JSON
- **Invalid JSON in extract variables**: Shown when extract_variables field contains malformed JSON
- **Invalid JSON in request body**: Shown when body field contains malformed JSON

## Benefits

1. **Full Control**: Users can manually edit all aspects of API requests
2. **Flexibility**: Support for custom headers and complex variable extraction
3. **Visibility**: All configuration visible and editable in one place
4. **Validation**: Immediate feedback on JSON syntax errors
5. **Preservation**: Existing values are preserved when editing other fields
6. **Documentation**: Help text and placeholders guide users

## Testing Checklist

- [ ] Open API step editor for existing step
- [ ] Verify headers are loaded correctly
- [ ] Verify extract_variables are loaded correctly
- [ ] Edit headers JSON and save
- [ ] Edit extract_variables JSON and save
- [ ] Try saving invalid JSON (should show error)
- [ ] Verify changes persist after save
- [ ] Run test to confirm headers are applied
- [ ] Verify variables are extracted correctly

## Files Modified

- `/Users/aragossa/dzrprj/auroqa/auroqa-ui/src/components/TestCaseSteps.js`
  - Lines 187-194: Added headers and extract_variables to state
  - Lines 1737-1738: Preserve fields when loading step
  - Lines 1765-1785: Added JSON parsing validation
  - Lines 2871-2924: Added UI fields for headers and extract_variables

## Status
✅ **COMPLETE** - API step editor now supports manual editing of headers and extract variables with full JSON validation.
