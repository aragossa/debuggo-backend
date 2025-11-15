# Placeholder Syntax Guide for Gemini AI

## 🔴 CRITICAL RULE
**ALL placeholders MUST be wrapped with `%` on BOTH sides: `%placeholder_name%`**

## ✅ Correct Syntax Examples

### Environment Variables
```
%base_url%     → Uses the project's base URL
%login%        → Uses the project's login credential
%password%     → Uses the project's password credential
```

### Unique Identifiers (cached per test run)
```
%unique_name%                  → "a7b3c9d2"
%unique_name:Client%           → "Client_a7b3c9d2"
%unique_name:P@ssword1!%       → "P@ssword1!_a7b3c9d2"
%unique_name:User:Test%        → "User_a7b3c9d2_Test"
%timestamp_name%               → "20250129_143052"
%timestamp_name:Group%         → "Group_20250129_143052"
%uuid_name%                    → "550e8400-e29b-41d4-a716-446655440000"
```

### Random Personal Data (new value each time)
```
%random_name%          → "John Smith"
%random_first_name%    → "John"
%random_last_name%     → "Smith"
%random_email%         → "john.smith@example.com"
%random_username%      → "john_smith_123"
%random_phone%         → "+1-555-234-5678"
```

### Random Location Data
```
%random_address%       → "742 Evergreen Terrace"
%random_city%          → "Springfield"
%random_country%       → "United States"
```

### Random Business Data
```
%random_company%       → "Acme Corporation"
%random_job_title%     → "Software Engineer"
```

### Random Technical Data
```
%random_string%        → "AbC123XyZ0" (10 chars)
%random_string:5%      → "Ab1X9" (5 chars)
%random_number%        → 4275 (1-10000)
%random_number:1:100%  → 42 (1-100)
%random_url%           → "https://www.example.com"
%random_ip%            → "192.168.1.42"
%random_uuid%          → Full UUID
%random_color%         → "blue"
%random_date%          → "2025-01-29"
%random_boolean%       → true or false
%random_text%          → Paragraph of text
%random_text:5%        → 5 sentences of text
```

## ❌ Wrong Syntax (Will NOT Work)

```
%unique_name:P@ssword1!    ← Missing closing %
random_email%              ← Missing opening %
unique_name                ← No % signs at all
%login                     ← Missing closing %
password%                  ← Missing opening %
```

## How It Works

The `EnvHelper.process_variables()` method uses this regex pattern:
```python
pattern = r'%([^%]+)%'
```

This pattern **requires both opening AND closing `%` signs** to match.

### Example:
```python
# Input with correct syntax
value = "%unique_name:P@ssword1!%"
# After processing
value = "P@ssword1!_a7b3c9d2"

# Input with missing closing %
value = "%unique_name:P@ssword1!"
# After processing (NOT replaced!)
value = "%unique_name:P@ssword1!"
```

## Common Mistakes

### 1. Forgetting Closing %
```json
❌ WRONG:
{
  "action": "type",
  "value": "%unique_name:Password123"
}

✅ CORRECT:
{
  "action": "type",
  "value": "%unique_name:Password123%"
}
```

### 2. Forgetting Opening %
```json
❌ WRONG:
{
  "action": "type",
  "value": "random_email%"
}

✅ CORRECT:
{
  "action": "type",
  "value": "%random_email%"
}
```

### 3. Using Hardcoded Values
```json
❌ WRONG:
{
  "action": "type",
  "value": "test@test.com"
}

✅ CORRECT:
{
  "action": "type",
  "value": "%random_email%"
}
```

## Best Practices

1. **Always double-check** that your placeholder has `%` on **both sides**
2. **Use `%unique_name:Prefix%`** for entities that need consistency across multiple steps
3. **Use `%random_*%`** for realistic data that doesn't need to be referenced later
4. **Never hardcode** values like emails, names, or IDs
5. **Special characters** in prefixes are allowed (e.g., `%unique_name:P@ssword1!%`)

## Testing Your Placeholders

To verify a placeholder will work:
1. Check it starts with `%`
2. Check it ends with `%`
3. Check there's a valid placeholder name between the `%` signs
4. If using a prefix/suffix, use `:` to separate (e.g., `%unique_name:prefix:suffix%`)

## Summary

**Remember this simple rule:**
> **If you can't see a `%` at the start AND end of your placeholder, it will NOT work!**

✅ `%placeholder%` = Works  
❌ `%placeholder` = Broken  
❌ `placeholder%` = Broken  
❌ `placeholder` = Broken
