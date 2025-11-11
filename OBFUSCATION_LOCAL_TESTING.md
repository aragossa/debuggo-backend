# 🔒 Local Testing with Obfuscated Code

This guide explains how to test your obfuscated AuroQA backend locally, connecting to your existing PostgreSQL, Redis, and Kafka services.

---

## 📋 Prerequisites

Before starting, ensure you have:
- ✅ Docker and Docker Compose installed
- ✅ PostgreSQL running locally (port 5432)
- ✅ Redis running locally (port 6379)
- ✅ Kafka running locally (port 9092)
- ✅ `.env` file configured with your credentials

---

## 🚀 Quick Start (Automated)

The easiest way to test:

```bash
cd /Users/aragossa/dzrprj/auroqa/auroqa

# Make script executable (one time only)
chmod +x test-obfuscated-local.sh

# Run the test script
./test-obfuscated-local.sh
```

This script will:
1. ✅ Build the obfuscated Docker image
2. ✅ Verify code obfuscation
3. ✅ Start the container with docker-compose
4. ✅ Test the application health
5. ✅ Show you all relevant URLs and commands

---

## 🔧 Manual Setup (Step by Step)

### Step 1: Build the Obfuscated Image

```bash
cd /Users/aragossa/dzrprj/auroqa/auroqa

docker build -f Dockerfile.obfuscated -t auroqa:obfuscated-local .
```

**Build time:** ~5-10 minutes (depends on your machine)

### Step 2: Verify Obfuscation Worked

```bash
# Check obfuscation statistics
docker run --rm auroqa:obfuscated-local bash -c "
    echo 'Total .pyc files:' \$(find /app -name '*.pyc' | wc -l)
    echo 'Source .py files:' \$(find /app -name '*.py' ! -path '*/migrations/*' | wc -l)
"

# Expected output:
# Total .pyc files: 100+ (depends on your codebase)
# Source .py files: 2-3 (only __init__.py and main.py)
```

### Step 3: Start the Container

```bash
docker-compose -f docker-compose.local.yml up -d
```

### Step 4: Wait for Startup

```bash
# Wait 20-30 seconds for application to start
sleep 30

# Check logs
docker-compose -f docker-compose.local.yml logs -f
```

### Step 5: Test the Application

```bash
# Test health endpoint
curl http://localhost:9000/api/health

# Expected response:
# {"status":"healthy"}
```

---

## 📊 Configuration Details

### docker-compose.local.yml

This file connects your obfuscated container to local services:

```yaml
environment:
  DB_HOST: host.docker.internal      # Connects to your Mac's PostgreSQL
  REDIS_HOST: host.docker.internal   # Connects to your Mac's Redis
  KAFKA_HOST: host.docker.internal   # Connects to your Mac's Kafka
```

**How it works:**
- `host.docker.internal` is a special Docker hostname that resolves to your host machine
- All ports (5432, 6379, 9092) are loaded from your `.env` file
- Credentials (DB_USER, DB_PASSWORD, etc.) come from `.env`

### Port Mapping

- **Container Port:** 8000 (internal)
- **Host Port:** 9000 (external)
- **Access URL:** `http://localhost:9000`

---

## 🔍 Verify Code is Obfuscated

### Check Inside the Container

```bash
# Enter the running container
docker exec -it auroqa-obfuscated-local bash

# Try to view source files (should fail)
cat /app/Services/ApiSchemaService.py
# Output: No such file or directory ✅

# Check bytecode files exist
ls /app/Services/*.pyc
# Output: List of .pyc files ✅

# Try to read bytecode (unreadable)
head -n 5 /app/Services/ApiSchemaService.pyc
# Output: Binary gibberish ✅

exit
```

### What's Protected

✅ **Obfuscated (source removed):**
- All files in `/app/Services/`
- All files in `/app/Utils/`
- All custom business logic

✅ **Preserved (not removed):**
- `main.py` - Application entry point
- `__init__.py` - Python package markers
- `/app/migrations/*.py` - Database migrations

---

## 📝 Common Commands

### View Logs

```bash
# Follow logs in real-time
docker-compose -f docker-compose.local.yml logs -f

# View last 50 lines
docker-compose -f docker-compose.local.yml logs --tail=50

# View logs for specific time
docker-compose -f docker-compose.local.yml logs --since 10m
```

### Restart Application

```bash
# Restart the container
docker-compose -f docker-compose.local.yml restart

# Full restart (rebuilds)
docker-compose -f docker-compose.local.yml down
docker-compose -f docker-compose.local.yml up -d
```

### Stop Application

```bash
# Stop and remove containers
docker-compose -f docker-compose.local.yml down

# Stop, remove, and clean volumes
docker-compose -f docker-compose.local.yml down -v
```

### Access Container Shell

```bash
# Get a bash shell inside the container
docker exec -it auroqa-obfuscated-local bash

# Run a one-off command
docker exec auroqa-obfuscated-local ls /app/Services/*.pyc
```

---

## 🐛 Troubleshooting

### Issue: Database Connection Failed

**Error:**
```
connection to server at "127.0.0.1", port 5432 failed
```

**Solution:**
Verify PostgreSQL is running and accessible:

```bash
# Check PostgreSQL is running
psql -h localhost -U postgres -d postgres -p 5432

# If this works, check your .env file:
cat .env | grep DB_
```

### Issue: Redis Connection Failed

**Solution:**
```bash
# Check Redis is running
redis-cli ping
# Should return: PONG

# Check Redis host in .env
cat .env | grep REDIS_
```

### Issue: Kafka Connection Warnings

**Note:** Kafka warnings are usually non-critical and don't affect the main application. If the app starts successfully, you can ignore them.

**To fix:**
```bash
# Check if Kafka is running
docker ps | grep kafka

# Test Kafka connection
telnet localhost 9092
```

### Issue: Application Won't Start

**Check logs:**
```bash
docker-compose -f docker-compose.local.yml logs
```

**Common causes:**
1. Missing environment variables in `.env`
2. Database not running
3. Port 9000 already in use

**Check port usage:**
```bash
lsof -i :9000
```

---

## 🎯 Testing Checklist

Before considering the obfuscation successful, verify:

- [ ] **Build:** Docker image builds without errors
- [ ] **Obfuscation:** Source `.py` files removed (except `main.py`, `__init__.py`)
- [ ] **Bytecode:** `.pyc` files present in all directories
- [ ] **Startup:** Application starts without errors
- [ ] **Database:** Successfully connects to PostgreSQL
- [ ] **Health:** `/api/health` endpoint returns 200
- [ ] **Login:** Google OAuth login works
- [ ] **API:** Test cases can be created and executed
- [ ] **Tests:** Run a sample UI test to verify full functionality

---

## 🚀 Next Steps: Production Deployment

Once local testing is successful:

### 1. Update Production Dockerfile

```bash
cd /Users/aragossa/dzrprj/auroqa/auroqa

# Backup original
cp Dockerfile Dockerfile.original

# Use obfuscated version for production
cp Dockerfile.obfuscated Dockerfile
```

### 2. Update Deployment Script

Edit `/Users/aragossa/dzrprj/auroqa/deploy-backend.sh` if needed (or use as-is, since Dockerfile is now obfuscated).

### 3. Deploy to Production

```bash
cd /Users/aragossa/dzrprj/auroqa
./deploy-backend.sh
```

---

## 📊 Obfuscation Level

**Protection Level:** ⭐⭐⭐ (Medium - Good for most use cases)

**What it protects against:**
- ✅ Casual code inspection
- ✅ Accidental source code exposure
- ✅ Quick copy-paste of logic

**What it doesn't protect against:**
- ❌ Determined reverse engineering (tools like `uncompyle6` exist)
- ❌ Advanced attackers with decompilation tools

**For stronger protection, consider:**
- PyArmor Pro ($99-299/year) - ⭐⭐⭐⭐⭐
- Cython compilation - ⭐⭐⭐⭐⭐ (complex setup)

---

## 💡 Best Practices

1. **Never hardcode secrets** - Always use environment variables
2. **Use `.env` file** - Keep sensitive data out of code
3. **Implement authentication** - JWT, OAuth, API keys
4. **Enable logging** - Monitor for suspicious activity
5. **Regular updates** - Keep dependencies current
6. **Rate limiting** - Prevent API abuse
7. **HTTPS only** - Encrypt data in transit

---

## 📚 Additional Resources

- **Obfuscation Options:** See `OBFUSCATION_OPTIONS_COMPARISON.md`
- **Deployment Guide:** See `OBFUSCATION_QUICKSTART.md` (if exists)
- **Docker Docs:** https://docs.docker.com/
- **Docker Compose Docs:** https://docs.docker.com/compose/

---

## ❓ Support

If you encounter issues:

1. Check logs: `docker-compose -f docker-compose.local.yml logs`
2. Verify services: PostgreSQL, Redis, Kafka running
3. Check `.env` configuration
4. Review error messages carefully
5. Test without obfuscation first (use original `Dockerfile`)

---

**Last Updated:** November 5, 2025
**Author:** AuroQA Development Team
