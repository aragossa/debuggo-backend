# 🚀 Full-Stack Local Setup Guide

Complete guide for running the entire AuroQA stack locally with Docker - obfuscated backend + production-optimized frontend.

---

## 📋 Overview

This guide shows you how to run both the backend and frontend together in a local Docker environment:

- **Backend:** Obfuscated Python code (bytecode) connected to local PostgreSQL, Redis, Kafka
- **Frontend:** Production-optimized React build served by nginx

---

## 🎯 Prerequisites

Before starting, ensure you have:

### Required Services Running Locally
- ✅ **PostgreSQL** - Port 5432
- ✅ **Redis** - Port 6379
- ✅ **Kafka** - Port 9092 (optional for some features)

### Verify Services

```bash
# Test PostgreSQL
psql -h localhost -U postgres -d postgres -p 5432 -c "SELECT version();"

# Test Redis
redis-cli ping
# Should return: PONG

# Test Kafka (optional)
telnet localhost 9092
```

### Required Tools
- ✅ Docker Desktop installed
- ✅ Docker Compose installed
- ✅ curl or httpie for testing

---

## 🚀 Quick Start (Full Stack)

### Option 1: Use Individual Scripts (Recommended)

```bash
# Terminal 1: Start Backend
cd /Users/aragossa/dzrprj/auroqa/auroqa
chmod +x test-obfuscated-local.sh
./test-obfuscated-local.sh

# Terminal 2: Start Frontend
cd /Users/aragossa/dzrprj/auroqa/auroqa-ui
chmod +x test-ui-local.sh
./test-ui-local.sh
```

**Access:**
- Frontend: http://localhost:3000
- Backend: http://localhost:9000

---

### Option 2: Use Docker Compose (Full Stack)

```bash
# 1. Build backend image
cd /Users/aragossa/dzrprj/auroqa/auroqa
docker build -f Dockerfile.obfuscated -t auroqa:obfuscated-local .

# 2. Start full stack
cd /Users/aragossa/dzrprj/auroqa/auroqa-ui
docker-compose -f docker-compose.local.yml up -d
```

**Access:**
- Frontend: http://localhost:3000
- Backend: http://localhost:9000

---

## 📦 Directory Structure

```
/Users/aragossa/dzrprj/auroqa/
├── auroqa/                          # Backend
│   ├── Dockerfile.obfuscated        # Obfuscated backend build
│   ├── docker-compose.local.yml     # Backend compose file
│   ├── test-obfuscated-local.sh     # Backend test script
│   └── .env                         # Backend environment
│
├── auroqa-ui/                       # Frontend
│   ├── Dockerfile.production        # Production UI build
│   ├── docker-compose.local.yml     # UI compose file (includes backend)
│   ├── test-ui-local.sh             # UI test script
│   └── .env                         # UI environment
│
└── FULL_STACK_LOCAL_SETUP.md       # This guide
```

---

## 🔧 Configuration

### Backend Configuration

**File:** `/Users/aragossa/dzrprj/auroqa/auroqa/.env`

```bash
# Database (local PostgreSQL)
DB_HOST=127.0.0.1
DB_PORT=5432
DB_NAME=postgres
DB_USER=postgres
DB_PASSWORD=eYuUm57C!

# Redis (local)
REDIS_HOST=redis
REDIS_PORT=6379

# Kafka (local)
KAFKA_HOST=localhost
KAFKA_PORT=9092

# Google OAuth
GOOGLE_CLIENT_ID=your_client_id
GOOGLE_CLIENT_SECRET=your_secret
GOOGLE_REDIRECT_URI=http://localhost:9000/api/auth/google/callback

# Frontend URL
FRONTEND_URL=http://localhost:3000

# AI Models
AI_MODEL=gemini
GEMINI_API=your_api_key
```

**Note:** `DB_HOST`, `REDIS_HOST`, and `KAFKA_HOST` are automatically overridden to `host.docker.internal` in docker-compose.

---

### Frontend Configuration

**File:** `/Users/aragossa/dzrprj/auroqa/auroqa-ui/.env`

```bash
# Point to local backend
REACT_APP_API_URL=http://localhost:9000

# For production backend
# REACT_APP_API_URL=https://debuggo.app
```

**⚠️ Important:** Frontend `.env` is baked into the build. Changes require rebuild!

---

## 🎯 Step-by-Step Setup

### Step 1: Backend Setup

```bash
cd /Users/aragossa/dzrprj/auroqa/auroqa

# 1. Check backend .env is configured
cat .env | grep -E "(DB_HOST|REDIS_HOST|KAFKA_HOST)"

# 2. Build obfuscated backend
docker build -f Dockerfile.obfuscated -t auroqa:obfuscated-local .

# 3. Start backend
docker-compose -f docker-compose.local.yml up -d

# 4. Wait for startup (30 seconds)
sleep 30

# 5. Test backend
curl http://localhost:9000/api/health
# Expected: {"status":"healthy"}
```

**Backend Running:**
- ✅ Port 9000
- ✅ Connected to local PostgreSQL
- ✅ Connected to local Redis
- ✅ Connected to local Kafka

---

### Step 2: Frontend Setup

```bash
cd /Users/aragossa/dzrprj/auroqa/auroqa-ui

# 1. Check frontend .env
cat .env
# Should have: REACT_APP_API_URL=http://localhost:9000

# 2. Build production UI
docker build -f Dockerfile.production -t auroqa-ui:production-local .

# 3. Start frontend (UI only, backend already running)
docker-compose -f docker-compose.local.yml up -d auroqa-ui-local

# 4. Wait for startup (15 seconds)
sleep 15

# 5. Test frontend
curl http://localhost:3000/index.html
# Should return HTML
```

**Frontend Running:**
- ✅ Port 3000
- ✅ Serving production React build
- ✅ Connected to backend at port 9000

---

### Step 3: Verify Full Stack

```bash
# Test backend health
curl http://localhost:9000/api/health

# Test frontend
open http://localhost:3000

# Test login flow
# 1. Open http://localhost:3000
# 2. Click "Login with Google"
# 3. Should redirect to Google OAuth
# 4. After auth, should redirect back to dashboard
```

---

## 📊 Port Mapping

| Service | Container Port | Host Port | Access URL |
|---------|---------------|-----------|------------|
| **Backend** | 8000 | 9000 | http://localhost:9000 |
| **Frontend** | 80 | 3000 | http://localhost:3000 |
| **PostgreSQL** | 5432 | 5432 | localhost:5432 (host) |
| **Redis** | 6379 | 6379 | localhost:6379 (host) |
| **Kafka** | 9092 | 9092 | localhost:9092 (host) |

---

## 📝 Common Commands

### View All Logs

```bash
# Backend logs
cd /Users/aragossa/dzrprj/auroqa/auroqa
docker-compose -f docker-compose.local.yml logs -f

# Frontend logs
cd /Users/aragossa/dzrprj/auroqa/auroqa-ui
docker-compose -f docker-compose.local.yml logs -f auroqa-ui-local
```

### Restart Services

```bash
# Restart backend
cd /Users/aragossa/dzrprj/auroqa/auroqa
docker-compose -f docker-compose.local.yml restart

# Restart frontend
cd /Users/aragossa/dzrprj/auroqa/auroqa-ui
docker-compose -f docker-compose.local.yml restart auroqa-ui-local
```

### Stop All Services

```bash
# Stop backend
cd /Users/aragossa/dzrprj/auroqa/auroqa
docker-compose -f docker-compose.local.yml down

# Stop frontend
cd /Users/aragossa/dzrprj/auroqa/auroqa-ui
docker-compose -f docker-compose.local.yml down
```

### Rebuild After Changes

```bash
# Rebuild backend (after code changes)
cd /Users/aragossa/dzrprj/auroqa/auroqa
docker build -f Dockerfile.obfuscated -t auroqa:obfuscated-local .
docker-compose -f docker-compose.local.yml up -d

# Rebuild frontend (after code or .env changes)
cd /Users/aragossa/dzrprj/auroqa/auroqa-ui
docker build -f Dockerfile.production -t auroqa-ui:production-local .
docker-compose -f docker-compose.local.yml up -d auroqa-ui-local
```

---

## 🔍 Verification Checklist

### Backend Verification

```bash
# Health check
curl http://localhost:9000/api/health
# ✅ Should return: {"status":"healthy"}

# Check obfuscation
docker exec auroqa-obfuscated-local ls /app/Services/*.py 2>&1
# ✅ Should return: "No such file or directory"

docker exec auroqa-obfuscated-local ls /app/Services/*.pyc | head -5
# ✅ Should list .pyc files

# Database connection
docker logs auroqa-obfuscated-local | grep "Database connection pool initialized"
# ✅ Should see success message
```

### Frontend Verification

```bash
# Check served files
curl http://localhost:3000/index.html | head -20
# ✅ Should return HTML

# Check JS bundle loads
curl -I http://localhost:3000/static/js/main.*.js
# ✅ Should return 200 OK

# Check in browser
open http://localhost:3000
# ✅ Should see login page, no white screen
# ✅ Browser console should have no errors
```

### Integration Verification

1. **Login Flow:**
   - Open http://localhost:3000
   - Click "Login with Google"
   - Complete OAuth flow
   - Should land on dashboard ✅

2. **API Communication:**
   - Check browser DevTools Network tab
   - Should see requests to http://localhost:9000/api/
   - All requests should return 200 OK (or appropriate status) ✅

3. **Test Creation:**
   - Create a new test case
   - Generate steps with AI
   - Run the test
   - All should work ✅

---

## 🐛 Troubleshooting

### Backend Issues

#### Database Connection Failed

```bash
# Check PostgreSQL is running
psql -h localhost -U postgres -d postgres

# Check backend logs
docker logs auroqa-obfuscated-local | grep -i error
```

#### Redis Connection Failed

```bash
# Check Redis is running
redis-cli ping

# Should return: PONG
```

#### Port 9000 Already in Use

```bash
# Check what's using port 9000
lsof -i :9000

# Stop the process or change port in docker-compose
```

---

### Frontend Issues

#### Cannot Connect to Backend

**Browser console shows:** `Failed to fetch http://localhost:9000/api/...`

**Solutions:**

1. Verify backend is running:
```bash
curl http://localhost:9000/api/health
```

2. Check frontend .env:
```bash
cat /Users/aragossa/dzrprj/auroqa/auroqa-ui/.env
```

3. Rebuild frontend if you changed .env:
```bash
cd /Users/aragossa/dzrprj/auroqa/auroqa-ui
docker build -f Dockerfile.production -t auroqa-ui:production-local .
docker-compose -f docker-compose.local.yml up -d auroqa-ui-local
```

#### CORS Errors

**Browser console shows:** `Access to fetch ... has been blocked by CORS policy`

**Solution:** Check backend CORS configuration in `main.py`:

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

#### White Screen

**Solutions:**

1. Check browser console (F12) for JavaScript errors
2. Check frontend logs:
```bash
docker logs auroqa-ui-local
```
3. Verify build files exist:
```bash
docker exec auroqa-ui-local ls /usr/share/nginx/html/
```

---

## 📚 Documentation

### Backend
- **Setup Guide:** `auroqa/OBFUSCATION_LOCAL_TESTING.md`
- **Quick Reference:** `auroqa/OBFUSCATION_SETUP_COMPLETE.md`
- **Options Comparison:** `OBFUSCATION_OPTIONS_COMPARISON.md`

### Frontend
- **Setup Guide:** `auroqa-ui/UI_LOCAL_TESTING.md`
- **Quick Reference:** `auroqa-ui/UI_SETUP_COMPLETE.md`

### Full Stack
- **This Guide:** `FULL_STACK_LOCAL_SETUP.md`

---

## 🚀 Production Deployment

Once local testing is complete, deploy to production:

### Backend Deployment

```bash
cd /Users/aragossa/dzrprj/auroqa/auroqa

# Replace production Dockerfile
mv Dockerfile Dockerfile.original
cp Dockerfile.obfuscated Dockerfile

# Deploy (use your existing script)
cd /Users/aragossa/dzrprj/auroqa
./deploy-backend.sh
```

### Frontend Deployment

```bash
cd /Users/aragossa/dzrprj/auroqa/auroqa-ui

# Update .env for production
echo "REACT_APP_API_URL=https://your-production-api.com" > .env

# Replace production Dockerfile
mv Dockerfile Dockerfile.original
cp Dockerfile.production Dockerfile

# Build and deploy
docker build -t your-registry/auroqa-ui:latest .
docker push your-registry/auroqa-ui:latest

# Deploy to server (method depends on your hosting)
```

---

## 🎯 Testing Checklist

- [ ] **PostgreSQL** running and accessible
- [ ] **Redis** running and accessible
- [ ] **Kafka** running (optional for some features)
- [ ] **Backend** builds successfully
- [ ] **Backend** starts without errors
- [ ] **Backend** health check passes
- [ ] **Backend** code is obfuscated
- [ ] **Frontend** builds successfully
- [ ] **Frontend** serves at port 3000
- [ ] **Frontend** loads without blank screen
- [ ] **Login** works with Google OAuth
- [ ] **API calls** from frontend to backend succeed
- [ ] **Test creation** works
- [ ] **Test execution** works
- [ ] **No errors** in browser console
- [ ] **No errors** in Docker logs

---

## 💡 Tips

1. **Start backend first** - Frontend depends on backend API
2. **Use separate terminals** - Easier to see logs for each service
3. **Hard refresh browser** - Ctrl+Shift+R after frontend rebuild
4. **Check logs often** - `docker logs` is your friend
5. **Test incrementally** - Backend first, then frontend, then integration
6. **Keep services running** - PostgreSQL, Redis must be running before starting Docker containers

---

## 🎉 Success!

When everything is working:

1. ✅ Backend responds at http://localhost:9000/api/health
2. ✅ Frontend loads at http://localhost:3000
3. ✅ Can login with Google
4. ✅ Can create and run tests
5. ✅ No errors in logs or console
6. ✅ Backend code is obfuscated (source files removed)
7. ✅ Frontend is production-optimized (minified)

---

**You're ready to test the full stack locally before production deployment!** 🚀🔒✨
