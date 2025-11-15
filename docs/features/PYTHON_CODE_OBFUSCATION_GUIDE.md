# Python Code Obfuscation Guide for Docker Deployment

## Overview

This guide covers different approaches to obfuscate Python code in your Docker image before deployment to production.

## ⚠️ Important Considerations

1. **Obfuscation ≠ Security**: Obfuscation makes reverse engineering harder but not impossible
2. **Performance Impact**: Some methods may affect runtime performance
3. **Debugging**: Obfuscated code is harder to debug in production
4. **Maintenance**: Keep original source code in version control

---

## Option 1: PyArmor (Recommended - Professional Grade)

**Pros:**
- ✅ Strong obfuscation with bytecode encryption
- ✅ License management (restrict to specific machines)
- ✅ Minimal performance impact
- ✅ Easy to implement

**Cons:**
- ❌ Requires PyArmor runtime in production
- ❌ Commercial license required for some features

### Implementation Steps:

1. **Add PyArmor to requirements.txt:**
```txt
pyarmor==8.5.0
```

2. **Use the provided `Dockerfile.obfuscated`**

3. **Update deploy script:**
```bash
# In deploy-backend.sh, change line 45:
docker build --no-cache --platform linux/amd64 -f Dockerfile.obfuscated -t "$BACKEND_IMAGE" .
```

4. **Test locally:**
```bash
cd /Users/aragossa/dzrprj/auroqa/auroqa
docker build -f Dockerfile.obfuscated -t auroqa-obfuscated:test .
docker run -p 8000:8000 auroqa-obfuscated:test
```

---

## Option 2: Cython Compilation (Best Performance)

**Pros:**
- ✅ Compiles to C extensions (.so files)
- ✅ Best performance (compiled code runs faster)
- ✅ Very hard to reverse engineer
- ✅ No runtime dependencies

**Cons:**
- ❌ Complex build process
- ❌ May break dynamic imports
- ❌ Platform-specific binaries

### Implementation:

Use the provided `Dockerfile.cython` (requires testing with your codebase)

---

## Option 3: pyminifier + base64 (Quick & Simple)

**Pros:**
- ✅ Easy to implement
- ✅ No additional runtime dependencies
- ✅ Good for quick obfuscation

**Cons:**
- ❌ Weaker than PyArmor/Cython
- ❌ Can break some Python features

### Implementation:

Create `Dockerfile.minified`:
```dockerfile
FROM python:3.9-slim as builder

WORKDIR /build
COPY . .

# Install pyminifier
RUN pip install pyminifier

# Minify all Python files
RUN find . -name "*.py" ! -name "__init__.py" -exec pyminifier --nonlatin --gzip {} -o {}.min \; && \
    find . -name "*.py.min" -exec bash -c 'mv "$0" "${0%.min}"' {} \;

# Continue with normal build...
FROM python:3.9-slim
# ... rest of Dockerfile
```

---

## Option 4: Compile to .pyc Only (Minimal Protection)

**Pros:**
- ✅ Very simple
- ✅ No dependencies
- ✅ No compatibility issues

**Cons:**
- ❌ Weakest protection (easily decompiled)

### Implementation:

Add to Dockerfile before CMD:
```dockerfile
# Compile all .py files to .pyc
RUN python -m compileall -b /app

# Remove source .py files (keep only .pyc)
RUN find /app -name "*.py" ! -name "__init__.py" ! -name "main.py" -delete

# Run from .pyc files
CMD ["python", "-B", "-m", "main"]
```

---

## Recommended Approach for Your Project

For AuroQA, I recommend **Option 1 (PyArmor)** because:

1. ✅ **Strong protection** without breaking functionality
2. ✅ **Easy to implement** with minimal changes
3. ✅ **License management** to restrict to your production server
4. ✅ **Minimal performance impact**
5. ✅ **Maintains debugging capability** (with proper license)

---

## Step-by-Step Implementation (PyArmor)

### 1. Create obfuscation configuration

```bash
cd /Users/aragossa/dzrprj/auroqa/auroqa

# Create .pyarmor_config.json
cat > .pyarmor_config.json << 'EOF'
{
  "obf_module": 1,
  "obf_code": 1,
  "wrap_mode": 1,
  "advanced_mode": 1,
  "enable_suffix": 0,
  "exclude": [
    "migrations/*",
    "tests/*",
    "*.txt",
    "*.md",
    "*.json",
    "*.yaml",
    "*.yml"
  ]
}
EOF
```

### 2. Update Dockerfile

```bash
# Rename current Dockerfile as backup
mv Dockerfile Dockerfile.original

# Use the obfuscated version
cp Dockerfile.obfuscated Dockerfile
```

### 3. Update deploy script

```bash
# Edit deploy-backend.sh line 45
# No changes needed - it will use the renamed Dockerfile automatically
```

### 4. Test locally

```bash
# Build obfuscated image
docker build -t auroqa:obfuscated-test .

# Run and test
docker run -p 9000:8000 \
  -e DATABASE_URL="postgresql://..." \
  -e REDIS_URL="redis://..." \
  auroqa:obfuscated-test

# Test API endpoints
curl http://localhost:9000/api/health
```

### 5. Deploy to production

```bash
# Use your existing deploy script
./deploy-backend.sh
```

---

## Advanced: Machine-Locked License

To restrict obfuscated code to your production server only:

```bash
# Generate machine-specific license
pyarmor gen --bind-machine \
  --bind-mac "production-mac-address" \
  --bind-ipv4 "34.165.86.166" \
  --output /build/obfuscated \
  .
```

Add to Dockerfile.obfuscated after RUN pyarmor gen:
```dockerfile
# Copy license file to restrict to production server
COPY pyarmor.lic /app/
```

---

## Troubleshooting

### Issue: Import errors after obfuscation

**Solution:** Add modules to exclude list in `.pyarmor_config.json`

### Issue: Performance degradation

**Solution:** Use `--no-wrap` flag in pyarmor command

### Issue: Dynamic imports breaking

**Solution:** Exclude dynamically imported modules from obfuscation

---

## Security Best Practices

1. **Never commit obfuscated code** to git (only source code)
2. **Keep original source** in private repository
3. **Use secrets management** for API keys (not hardcoded)
4. **Implement API authentication** (obfuscation is additional layer)
5. **Monitor production logs** for unauthorized access attempts
6. **Regular security audits** of deployed code

---

## Comparison Matrix

| Method          | Protection Level | Performance | Complexity | Debugging |
|-----------------|------------------|-------------|------------|-----------|
| PyArmor         | ⭐⭐⭐⭐⭐     | ⭐⭐⭐⭐    | ⭐⭐       | ⭐⭐⭐    |
| Cython          | ⭐⭐⭐⭐⭐     | ⭐⭐⭐⭐⭐  | ⭐⭐⭐⭐    | ⭐        |
| pyminifier      | ⭐⭐⭐         | ⭐⭐⭐      | ⭐⭐       | ⭐⭐      |
| .pyc only       | ⭐⭐           | ⭐⭐⭐⭐⭐  | ⭐         | ⭐⭐⭐⭐  |

---

## Next Steps

1. **Choose your obfuscation method** (recommend PyArmor)
2. **Test in staging environment** first
3. **Verify all functionality** works after obfuscation
4. **Update deployment process** to use obfuscated Dockerfile
5. **Document any excluded files/modules** for team reference

---

## Support & Resources

- PyArmor Documentation: https://pyarmor.readthedocs.io/
- Cython Documentation: https://cython.readthedocs.io/
- Python Security Best Practices: https://python.org/dev/security/

---

## Questions?

If you need help implementing any of these approaches, refer to:
- `Dockerfile.obfuscated` - PyArmor implementation
- `Dockerfile.cython` - Cython implementation
- This guide for configuration details
