# Test Placeholders - Quick Reference

## Syntax
- UI Tests: `%placeholder%`
- API Tests: `{{variable}}`

---

## 📋 Complete Placeholder List

### Environment Variables
```
%base_url%          → https://app.example.com
%login%             → admin@example.com
%password%          → SecurePass123!
```

### Unique Identifiers (Cached - Consistent Within Test)
```
%unique_name%                → a7b3c9d2
%unique_name:Client%         → Client_a7b3c9d2
%unique_name:User:Test%      → User_a7b3c9d2_Test
%timestamp_name%             → 20250129_143052
%timestamp_name:Group%       → Group_20250129_143052
%uuid_name:Client%           → Client_a7b3c9d2
%uuid_name:Client:false%     → Client_a7b3c9d2-e5f1-4a8b-9c3d-2e6f7a8b9c0d
```

### Personal Information
```
%random_name%               → John Smith
%random_first_name%         → John
%random_last_name%          → Smith
%random_email%              → john.smith@example.com
%random_phone%              → +12025551234
%random_username%           → john_smith_123
```

### Location
```
%random_address%            → 742 Evergreen Terrace
%random_city%               → Springfield
%random_country%            → United States
```

### Business
```
%random_company%            → AcmeCorporation
%random_job_title%          → Software Engineer
```

### Generic Data
```
%random_string%             → k7m2p9x4q1
%random_string:5%           → a8c3z
%random_number%             → 7543
%random_number:1:100%       → 47
%random_url%                → https://www.example.com
%random_color%              → blue
%random_date%               → 2024-03-15
%random_date:%d/%m/%Y%      → 15/03/2024
%random_boolean%            → True / False
%random_ip%                 → 192.168.1.42
%random_uuid%               → a7b3c9d2-e5f1-4a8b-9c3d-2e6f7a8b9c0d
%random_text%               → Lorem ipsum dolor... (3 sentences)
%random_text:5%             → Five sentences of text...
```

### Special
```
%random_option%             → Randomly selects dropdown option
```

### API Variables (Use {{}} format)
```
{{auth_token}}              → Bearer token from login
{{access_token}}            → Same as auth_token
{{token}}                   → Same as auth_token
{{client_id}}               → Extracted from response
{{user_id}}                 → Extracted from response
```

---

## ⚡ Key Concepts

### Cached vs Non-Cached

**Cached (Same value throughout test):**
- `%unique_name%` variants
- `%timestamp_name%` variants
- `%uuid_name%` variants

**Non-Cached (New value each time):**
- All `%random_*%` placeholders

### Example
```json
// Step 1
{"value": "%unique_name:Client%"}  → "Client_abc123"

// Step 5 (uses same value)
{"value": "%unique_name:Client%"}  → "Client_abc123"

// Step 10 (generates new value each time)
{"value": "%random_name%"}         → "John Smith"
{"value": "%random_name%"}         → "Jane Doe"
```

---

## 💡 Common Patterns

### User Registration
```json
{
  "firstName": "%random_first_name%",
  "lastName": "%random_last_name%",
  "email": "%unique_name%@test.com",
  "phone": "%random_phone%",
  "company": "%random_company%"
}
```

### Create/Verify/Delete Entity
```json
// Create
{"value": "%unique_name:Entity%"}

// Verify (uses same cached value)
{"element_path": "//td[text()='%unique_name:Entity%']"}

// Delete (uses same cached value)
{"element_path": "//tr[td='%unique_name:Entity%']//button[@title='Delete']"}
```

### API Request with Dynamic Data
```json
{
  "headers": {"Authorization": "Bearer {{auth_token}}"},
  "body": {
    "name": "%random_name%",
    "email": "%random_email%",
    "company": "%random_company%"
  }
}
```

### Dropdown Selection
```json
{
  "action": "select",
  "element_path": "//select[@id='clientId']",
  "value": "%random_option%"
}
```

---

## ✅ Quick Tips

1. **Always use placeholders** instead of hardcoded values
2. **Use cached placeholders** (`%unique_name%`) when you need consistency
3. **Use %random_option%** for dropdowns with dynamic data
4. **Combine placeholders**: `%unique_name%@test.com`
5. **Check spelling** - placeholders are case-sensitive

---

## 🔗 See Full Guide
[TEST_PLACEHOLDERS_GUIDE.md](TEST_PLACEHOLDERS_GUIDE.md) - Complete documentation with examples and troubleshooting

---

**Version:** 2.0 | **Last Updated:** November 11, 2025
