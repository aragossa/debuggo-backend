# Python Code Obfuscation - Quick Start Guide

## 🚀 Quick Implementation (5 minutes)

### Option A: Use PyArmor in Dockerfile (Recommended)

**Step 1:** Replace your current Dockerfile
```bash
cd /Users/aragossa/dzrprj/auroqa/auroqa
mv Dockerfile Dockerfile.original
mv Dockerfile.obfuscated Dockerfile
```

**Step 2:** Deploy as usual
```bash
cd /Users/aragossa/dzrprj/auroqa
./deploy-backend.sh
```

That's it! Your code will be automatically obfuscated during the Docker build.

---

### Option B: Pre-obfuscate with Script

**Step 1:** Run obfuscation script
```bash
cd /Users/aragossa/dzrprj/auroqa/auroqa
chmod +x obfuscate.sh
./obfuscate.sh
```

**Step 2:** Build from obfuscated directory
```bash
cd obfuscated
docker build -t thelisdeep/auroqa:latest .
```

**Step 3:** Deploy the obfuscated image
```bash
cd /Users/aragossa/dzrprj/auroqa
./deploy-backend.sh
```

---

## 🔍 Verify Obfuscation Works

### Test Locally First

```bash
# Build obfuscated image
cd /Users/aragossa/dzrprj/auroqa/auroqa
docker build -t auroqa:obfuscated-test .

# Run with your environment variables
docker run -p 9000:8000 \
  -e DATABASE_URL="your_db_url" \
  -e REDIS_URL="redis://localhost:6379" \
  -e GEMINI_API="your_api_key" \
  auroqa:obfuscated-test

# Test API
curl http://localhost:9000/api/health
```

### Verify Code is Obfuscated

```bash
# Enter running container
docker exec -it <container_id> bash

# Try to view a Python file
cat main.py
# Should see obfuscated/encrypted content, not readable source code
```

---

## ⚙️ Configuration Options

### Exclude Specific Files/Folders

Edit `Dockerfile.obfuscated` line 23-28:
```dockerfile
RUN pyarmor gen \
    --enable-rft \
    --enable-jit \
    --exclude "migrations/*" \
    --exclude "tests/*" \
    --exclude "config.py" \
    .
```

### Add Machine-Specific License

To restrict obfuscated code to production server only:

```dockerfile
# Add to Dockerfile.obfuscated after the pyarmor gen command:
RUN pyarmor gen \
    --bind-ipv4 "34.165.86.166" \
    --bind-mac "your-server-mac-address" \
    .
```

---

## 🐛 Troubleshooting

### Issue: "pyarmor: command not found"

**Solution:** PyArmor is installed in the builder stage. Check Dockerfile line 7:
```dockerfile
RUN pip install pyarmor
```

### Issue: Import errors after obfuscation

**Solution:** Add problematic modules to exclusion list:
```dockerfile
--exclude "problematic_module.py" \
```

### Issue: Application doesn't start

**Solution:** Check if PyArmor runtime is installed in final image (Dockerfile line 87):
```dockerfile
RUN pip install pyarmor
```

---

## 📊 What Gets Obfuscated?

✅ **Obfuscated:**
- All `.py` files in application code
- Business logic in Services/
- Utility functions in Utils/
- API endpoints and routes
- Database queries and logic

❌ **NOT Obfuscated:**
- SQL migration files (migrations/*.sql)
- Configuration files (.env, .json, .yaml)
- requirements.txt
- Static files

---

## 🔒 Security Notes

1. **Obfuscation is NOT encryption** - it makes code harder to read, not impossible
2. **Keep original source private** - never commit obfuscated code to git
3. **Use environment variables** for secrets (API keys, passwords)
4. **Implement proper authentication** - obfuscation is an additional layer
5. **Monitor production logs** for suspicious activity

---

## 📈 Performance Impact

- **PyArmor:** ~5-10% slower than original code (negligible for web APIs)
- **Build time:** Adds ~2-3 minutes to Docker build
- **Image size:** Slightly larger due to PyArmor runtime (~5-10MB)

---

## 🔄 Reverting to Non-Obfuscated

If you need to revert:

```bash
cd /Users/aragossa/dzrprj/auroqa/auroqa
mv Dockerfile Dockerfile.obfuscated.backup
mv Dockerfile.original Dockerfile
./deploy-backend.sh
```

---

## ✅ Checklist

Before deploying obfuscated code to production:

- [ ] Tested locally with obfuscated image
- [ ] Verified all API endpoints work
- [ ] Checked error handling still works
- [ ] Confirmed database migrations apply correctly
- [ ] Tested with actual production environment variables
- [ ] Documented which files are excluded from obfuscation
- [ ] Backed up original Dockerfile
- [ ] Ensured source code is in version control

---

## 🆘 Need Help?

1. **Check logs:** `docker logs <container_id>`
2. **Review guide:** See `/docs/PYTHON_CODE_OBFUSCATION_GUIDE.md`
3. **Test without obfuscation:** Use `Dockerfile.original`
4. **Check PyArmor docs:** https://pyarmor.readthedocs.io/

---

## 📞 Quick Commands Reference

```bash
# Build obfuscated image
docker build -t auroqa:obfuscated .

# Run obfuscated container
docker run -p 9000:8000 --env-file .env auroqa:obfuscated

# View obfuscated code in container
docker exec -it <container> cat main.py

# Deploy to production
./deploy-backend.sh

# Revert to original
mv Dockerfile.original Dockerfile
```
