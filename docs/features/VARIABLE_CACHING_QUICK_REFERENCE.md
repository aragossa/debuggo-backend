# Variable Caching - Quick Reference

## 🎯 What Was Fixed

**Test Case #2002 Issues**:
- ❌ Step 8 & 16: `%random_email%` generated different values
- ❌ Step 11 & 12: Password confirmation didn't match
- ✅ **NOW FIXED**: All placeholders cache automatically!

## 📝 How to Use

### Option 1: Named Variables (NEW - Recommended)

```python
# Explicitly named cached variables
Step 8:  Enter email → value="%var:user_email%"      # Generate & cache
Step 16: Login → value="%var:user_email%"            # Reuse from cache ✅

Step 11: Enter password → value="%var:user_password%"     # Generate & cache
Step 12: Confirm password → value="%var:user_password%"   # Reuse from cache ✅
```

**Smart type detection**:
- `%var:user_email%` → generates email
- `%var:admin_phone%` → generates phone
- `%var:user_password%` → generates password
- `%var:company_name%` → generates company

### Option 2: Automatic Caching (Backward Compatible)

```python
# All %random_*% automatically cache now
Step 8:  Enter email → value="%random_email%"     # Generate & cache
Step 16: Login → value="%random_email%"           # Reuse from cache ✅

Step 5:  Enter name → value="%random_name%"       # Generate & cache
Step 10: Verify → assert "%random_name%"          # Reuse from cache ✅
```

## 🔑 Cached Variables

### ✅ Always Cached
```
%unique_name:Prefix%        %random_email%          %random_string%
%timestamp_name%            %random_name%           %random_number%
%uuid_name%                 %random_phone%          %random_url%
%var:custom_name%           %random_address%        %random_date%
                            %random_company%        ... and 10+ more
```

### ⚠️ When to Use Each

| Use Case | Use This |
|----------|----------|
| **Multiple variables** | `%var:admin_email%` `%var:user_email%` |
| **Single variable** | `%random_email%` |
| **Entity names** | `%unique_name:Group%` |
| **Password fields** | `%var:password%` or `%unique_name:P@ss%` |
| **Descriptive names** | `%var:new_user_email%` |

## 🚨 Common Mistakes

### ❌ Wrong
```python
Step 8:  value="%random_email%"   # john@example.com
Step 16: value="%var:email%"      # NEW value! ❌ Different variable name
```

### ✅ Correct
```python
Step 8:  value="%random_email%"   # john@example.com
Step 16: value="%random_email%"   # john@example.com ✅ Same variable name
```

## 📊 Quick Comparison

| Syntax | First Use | Second Use | Explicit |
|--------|-----------|------------|----------|
| `%var:user_email%` | Generates | Cached | ✅ Very |
| `%random_email%` | Generates | Cached | ⚠️ Less |
| `%unique_name:User%` | Generates | Cached | ✅ Yes |

## 🔍 Examples

### User Registration + Login
```python
Step 5:  Enter email → %var:new_user_email%       # Generate once
Step 10: Enter password → %var:new_user_password% # Generate once
Step 15: Submit form
Step 20: Login email → %var:new_user_email%       # Reuse ✅
Step 25: Login password → %var:new_user_password% # Reuse ✅
```

### Password Confirmation
```python
Step 11: Password → %unique_name:P@ssword1!%      # Generate once
Step 12: Confirm → %unique_name:P@ssword1!%       # Reuse ✅
```

### Create + Delete Item
```python
Step 7:  Create group → %unique_name:Group%                              # "Group_abc123"
Step 11: Delete → "//tr[td[text()='%unique_name:Group%']]//button"      # Finds "Group_abc123" ✅
```

## 💡 Pro Tips

1. **Use `%var:name%` for clarity**: `%var:admin_email%` is clearer than `%random_email%`
2. **Same name = same value**: Exact placeholder must match
3. **Per-test caching**: New test run = new values
4. **No code changes**: Existing tests work automatically!

## 🚀 Quick Start

### For New Tests
```python
# Use descriptive %var:name% syntax
value="%var:user_email%"      # Clear intent
value="%var:admin_password%"  # Self-documenting
```

### For Existing Tests
```python
# No changes needed - auto-caching enabled!
# Your existing %random_email% already caches now ✅
```

---

**Files Modified**: 
- `EnvHelper.py` - Added caching + `%var:name%` support
- `AIHelper.py` - Updated Gemini prompts

**Documentation**:
- `VARIABLE_CACHING_SYSTEM.md` - Full guide
- This file - Quick reference

**Status**: ✅ Complete - Restart backend to apply
