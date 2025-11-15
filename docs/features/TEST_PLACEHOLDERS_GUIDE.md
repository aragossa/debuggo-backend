# Test Placeholders Guide

## Overview

AuroQA supports dynamic placeholders in test steps to generate realistic, unique test data at runtime. This eliminates hardcoded values and prevents duplicate data conflicts during test execution.

## Placeholder Syntax

Placeholders use the format: `%placeholder_name%` or `%placeholder_name:parameter%`

## Available Placeholders

### 1. Environment Variables

Standard environment variables from your project configuration:

| Placeholder | Description | Example Output |
|------------|-------------|----------------|
| `%base_url%` | Base URL for the application | `https://app.example.com` |
| `%login%` | Login username/email | `admin@example.com` |
| `%password%` | Login password | `SecurePass123!` |

**Usage Example:**
```json
{
  "action": "navigate",
  "value": "%base_url%/login"
}
```

---

### 2. Unique Identifiers (Cached)

Generate unique identifiers that remain consistent throughout a test run (cached):

| Placeholder | Description | Example Output |
|------------|-------------|----------------|
| `%unique_name%` | Random 8-character alphanumeric | `a7b3c9d2` |
| `%unique_name:Client%` | With prefix | `Client_a7b3c9d2` |
| `%unique_name:User:Test%` | With prefix and suffix | `User_a7b3c9d2_Test` |
| `%timestamp_name%` | Timestamp-based | `20250129_143052` |
| `%timestamp_name:Group%` | Timestamp with prefix | `Group_20250129_143052` |
| `%uuid_name:Client%` | Short UUID (8 chars) | `Client_a7b3c9d2` |
| `%uuid_name:Client:false%` | Full UUID | `Client_a7b3c9d2-e5f1-4a8b-9c3d-2e6f7a8b9c0d` |

**⚡ Important:** These placeholders are **cached per test run**. Using the same placeholder multiple times will return the same value:

```json
// Step 5: Create entity
{"action": "type", "value": "%unique_name:Client%"}  // Generates: "Client_a7b3c9d2"

// Step 10: Verify entity
{"element_path": "//td[text()='%unique_name:Client%']"}  // Uses: "Client_a7b3c9d2" (same!)

// Step 15: Delete entity
{"element_path": "//tr[td='%unique_name:Client%']//button[@title='Delete']"}  // Uses: "Client_a7b3c9d2"
```

---

### 3. Personal Information

Generate realistic personal data using the Faker library:

| Placeholder | Description | Example Output |
|------------|-------------|----------------|
| `%random_name%` | Full name | `John Smith` |
| `%random_first_name%` | First name only | `John` |
| `%random_last_name%` | Last name only | `Smith` |
| `%random_email%` | Email address | `john.smith@example.com` |
| `%random_phone%` | Phone number (E.164 format) | `+12025551234` |
| `%random_username%` | Username | `john_smith_123` |

**Usage Example:**
```json
{
  "step": "Fill user registration form",
  "steps": [
    {"selector": "#firstName", "value": "%random_first_name%"},
    {"selector": "#lastName", "value": "%random_last_name%"},
    {"selector": "#email", "value": "%random_email%"},
    {"selector": "#phone", "value": "%random_phone%"}
  ]
}
```

---

### 4. Location Information

Generate realistic location data:

| Placeholder | Description | Example Output |
|------------|-------------|----------------|
| `%random_address%` | Street address | `742 Evergreen Terrace` |
| `%random_city%` | City name | `Springfield` |
| `%random_country%` | Country name | `United States` |

**Usage Example:**
```json
{
  "action": "type",
  "selector": "#address",
  "value": "%random_address%, %random_city%, %random_country%"
}
```

---

### 5. Business Information

Generate realistic business data:

| Placeholder | Description | Example Output |
|------------|-------------|----------------|
| `%random_company%` | Company name (alphabetic only) | `AcmeCorporation` |
| `%random_job_title%` | Job title | `Software Engineer` |

**⚠️ Note:** `%random_company%` strips all non-alphabetic characters to comply with strict API validation rules.

---

### 6. Generic Data

General-purpose data generation:

| Placeholder | Description | Example Output |
|------------|-------------|----------------|
| `%random_string%` | Random string (10 chars) | `k7m2p9x4q1` |
| `%random_string:5%` | Custom length | `a8c3z` |
| `%random_number%` | Random number (1-10000) | `7543` |
| `%random_number:1:100%` | Custom range | `47` |
| `%random_url%` | URL | `https://www.example.com` |
| `%random_color%` | Color name | `blue` |
| `%random_date%` | Date (YYYY-MM-DD) | `2024-03-15` |
| `%random_date:%d/%m/%Y%` | Custom date format | `15/03/2024` |
| `%random_boolean%` | Boolean value | `True` or `False` |
| `%random_ip%` | IP address | `192.168.1.42` |
| `%random_uuid%` | UUID | `a7b3c9d2-e5f1-4a8b-9c3d-2e6f7a8b9c0d` |
| `%random_text%` | Text paragraph (3 sentences) | `Lorem ipsum dolor...` |
| `%random_text:5%` | Custom sentence count | `Five sentences...` |

**Usage Example:**
```json
{
  "action": "type",
  "selector": "#description",
  "value": "Test description %random_text:2% - Created on %random_date%"
}
```

---

### 7. Special Placeholders

#### Dropdown Selection

| Placeholder | Description | Usage |
|------------|-------------|-------|
| `%random_option%` | Randomly selects a valid dropdown option | Use in `select` actions |

**Usage Example:**
```json
{
  "action": "select",
  "element_path": "//select[@id='clientId']",
  "value": "%random_option%",
  "description": "Select random client from dropdown"
}
```

**⚠️ When to Use:**
- ✅ When any valid option satisfies the test requirement
- ✅ When dropdown data varies between environments
- ✅ When testing general functionality (create, edit, delete)
- ❌ When testing specific option behavior (use explicit value)

---

## API Testing Placeholders

For API tests, use double curly braces `{{variable}}` format:

| Placeholder | Description | Example |
|------------|-------------|---------|
| `{{auth_token}}` | Authentication token | Bearer token from login |
| `{{access_token}}` | Access token (alias) | Same as auth_token |
| `{{token}}` | Generic token (alias) | Same as auth_token |
| `{{client_id}}` | Extracted client ID | From previous response |
| `{{user_id}}` | Extracted user ID | From previous response |

**Usage Example:**
```json
{
  "headers": {
    "Authorization": "Bearer {{auth_token}}",
    "Content-Type": "application/json"
  },
  "url": "/api/clients/{{client_id}}/users"
}
```

---

## Best Practices

### ✅ DO:

1. **Use Dynamic Placeholders** instead of hardcoded values:
   ```json
   // ✅ Good
   {"value": "%random_email%"}
   
   // ❌ Bad
   {"value": "test@test.com"}
   ```

2. **Use Cached Placeholders** for consistency within a test:
   ```json
   // Step 1: Create
   {"value": "%unique_name:Client%"}  // Generates: "Client_abc123"
   
   // Step 5: Verify
   {"element_path": "//td[text()='%unique_name:Client%']"}  // Uses: "Client_abc123"
   
   // Step 10: Delete
   {"element_path": "//tr[td='%unique_name:Client%']"}  // Uses: "Client_abc123"
   ```

3. **Use %random_option%** for dropdowns with dynamic data:
   ```json
   {"action": "select", "value": "%random_option%"}
   ```

4. **Combine Placeholders** for complex values:
   ```json
   {"value": "%unique_name%@test.com"}  // -> "a7b3c9d2@test.com"
   {"value": "Test %random_company% - %timestamp_name%"}
   ```

### ❌ DON'T:

1. **Don't hardcode** names, emails, or IDs:
   ```json
   // ❌ Bad - will fail on duplicate
   {"value": "Test Client"}
   {"value": "test@test.com"}
   {"value": "35"}
   ```

2. **Don't use specific dropdown values** unless testing that specific option:
   ```json
   // ❌ Bad - ID 35 might not exist
   {"action": "select", "value": "35"}
   
   // ✅ Good - works with any valid option
   {"action": "select", "value": "%random_option%"}
   ```

3. **Don't mix cached and non-cached** placeholders for the same entity:
   ```json
   // ❌ Bad - creates two different names
   {"value": "%unique_name:Client%"}  // -> "Client_abc123"
   {"element_path": "//td[text()='%random_name%']"}  // -> "John Smith" (different!)
   ```

---

## Common Use Cases

### User Registration Flow
```json
{
  "test_name": "User Registration",
  "steps": [
    {"action": "navigate", "value": "%base_url%/register"},
    {"action": "type", "selector": "#firstName", "value": "%random_first_name%"},
    {"action": "type", "selector": "#lastName", "value": "%random_last_name%"},
    {"action": "type", "selector": "#email", "value": "%unique_name%@test.com"},
    {"action": "type", "selector": "#phone", "value": "%random_phone%"},
    {"action": "type", "selector": "#company", "value": "%random_company%"},
    {"action": "click", "selector": "#submitBtn"}
  ]
}
```

### Client CRUD Operations
```json
{
  "test_name": "Client Lifecycle",
  "steps": [
    // Create
    {"action": "type", "selector": "#clientName", "value": "%unique_name:Client%"},
    {"action": "type", "selector": "#email", "value": "%random_email%"},
    {"action": "select", "selector": "#category", "value": "%random_option%"},
    {"action": "click", "selector": "#save"},
    
    // Verify
    {"action": "wait_for_element", "selector": "//td[text()='%unique_name:Client%']"},
    
    // Edit
    {"action": "click", "selector": "//tr[td='%unique_name:Client%']//button[@title='Edit']"},
    {"action": "type", "selector": "#clientName", "value": "%unique_name:Client%_Updated"},
    {"action": "click", "selector": "#save"},
    
    // Delete
    {"action": "click", "selector": "//tr[td='%unique_name:Client%_Updated']//button[@title='Delete']"},
    {"action": "click", "selector": "//button[text()='Confirm']"},
    
    // Verify deletion
    {"action": "verify_not_exists", "selector": "//td[text()='%unique_name:Client%_Updated']"}
  ]
}
```

### API Test with Dynamic Data
```json
{
  "test_name": "Create User via API",
  "steps": [
    {
      "action": "api_call",
      "method": "POST",
      "url": "%base_url%/api/users",
      "headers": {"Authorization": "Bearer {{auth_token}}"},
      "body": {
        "name": "%random_name%",
        "email": "%random_email%",
        "phone": "%random_phone%",
        "company": "%random_company%",
        "address": "%random_address%"
      }
    }
  ]
}
```

---

## Troubleshooting

### Placeholder Not Replaced

**Problem:** Placeholder appears as literal text (e.g., `%random_name%` instead of `John Smith`)

**Solutions:**
1. Check spelling - placeholders are case-sensitive
2. Verify placeholder is supported (see tables above)
3. Ensure EnvHelper is initialized for the test run
4. Check logs for variable processing errors

### Cache Not Working

**Problem:** Same placeholder generates different values

**Solutions:**
1. Verify exact placeholder syntax matches (spaces matter)
2. Check if cache was cleared between steps
3. Ensure using cached placeholders (`%unique_name%`, not `%random_name%`)
4. Review test run logs for cache operations

### Dropdown Selection Fails

**Problem:** `%random_option%` throws "option not found" error

**Solutions:**
1. Check if dropdown has any valid options (not empty)
2. Verify dropdown is loaded before selection (add `wait_for_element`)
3. Check browser automation logs for available options
4. Ensure dropdown has `<option>` elements with values

### Environment Variables Not Found

**Problem:** `%base_url%`, `%login%`, or `%password%` not replaced

**Solutions:**
1. Verify environment is configured in project settings
2. Check environment is selected for test run
3. Confirm variable names match exactly (case-sensitive)
4. Test environment variables are stored in database

---

## Advanced Usage

### Custom Date Formats
```json
{"value": "%random_date:%d/%m/%Y%"}  // -> "15/03/2024"
{"value": "%random_date:%B %d, %Y%"}  // -> "March 15, 2024"
```

### Custom String Lengths
```json
{"value": "%random_string:5%"}  // -> "a8c3z"
{"value": "%random_string:20%"}  // -> "k7m2p9x4q1z5y8n3b6t7"
```

### Custom Number Ranges
```json
{"value": "%random_number:1:100%"}  // -> 47
{"value": "%random_number:1000:9999%"}  // -> 5432
```

### Multiple Placeholders in One Value
```json
{
  "value": "%random_first_name% %random_last_name% (%unique_name%)"
}
// Output: "John Smith (a7b3c9d2)"
```

---

## See Also

- [Dynamic Name Generation](DYNAMIC_NAME_GENERATION.md)
- [Dynamic Dropdown Selection](DYNAMIC_DROPDOWN_SELECTION.md)
- [Dynamic Data Placeholders](DYNAMIC_DATA_PLACEHOLDERS.md)
- [Variable Replacement Debug Guide](VARIABLE_REPLACEMENT_DEBUG.md)

---

**Last Updated:** November 11, 2025  
**Version:** 2.0
