# 🎨 UI Local Testing Guide

Complete guide for building and testing the production React frontend locally with Docker.

---

## 📋 Overview

The UI setup creates a production-optimized React build served by nginx. Unlike the backend, React code is:
- **Already minified** by webpack during build
- **Already optimized** with code splitting and tree shaking
- **Publicly visible** in the browser (source maps can be disabled for production)

This setup focuses on:
- Production-ready build
- Optimized static file serving with nginx
- Easy local testing
- Connection to local or remote backend

---

## 🚀 Quick Start

### Automated (Recommended)

```bash
cd /Users/aragossa/dzrprj/auroqa/auroqa-ui

# Make script executable
chmod +x test-ui-local.sh

# Run the test
./test-ui-local.sh
```

This will:
1. ✅ Build the production React app
2. ✅ Create optimized static files
3. ✅ Start nginx to serve the app
4. ✅ Test availability
5. ✅ Show all relevant URLs

---

## 🔧 Manual Setup

### Step 1: Configure Environment

Edit `.env` file:

```bash
# For local backend
REACT_APP_API_URL=http://localhost:9000

# For production backend
# REACT_APP_API_URL=https://debuggo.app
```

### Step 2: Build Production Image

```bash
cd /Users/aragossa/dzrprj/auroqa/auroqa-ui

docker build -f Dockerfile.production -t auroqa-ui:production-local .
```

**Build time:** ~3-5 minutes (includes npm install and React build)

### Step 3: Start Container

#### Option A: UI Only (Backend Separate)

```bash
docker-compose -f docker-compose.local.yml up -d auroqa-ui-local
```

#### Option B: Full-Stack (UI + Backend)

```bash
docker-compose -f docker-compose.local.yml up -d
```

This starts both frontend and backend containers.

### Step 4: Access the UI

Open browser: http://localhost:3000

---

## 📊 Configuration Details

### docker-compose.local.yml

The compose file has two services:

#### 1. Frontend Service (auroqa-ui-local)
- **Port:** 3000 → 80
- **Access:** http://localhost:3000
- **Server:** nginx
- **Health check:** Checks for index.html

#### 2. Backend Service (auroqa-backend-local) - Optional
- **Port:** 9000 → 8000
- **Access:** http://localhost:9000
- **Connects to:** Local PostgreSQL, Redis, Kafka via `host.docker.internal`
- **Health check:** Checks `/api/health` endpoint

### Environment Variables

The React app uses `.env` at **build time**:

```bash
REACT_APP_API_URL=http://localhost:9000
```

**Important:** Changes to `.env` require rebuilding the Docker image!

```bash
# After changing .env
docker build -f Dockerfile.production -t auroqa-ui:production-local .
docker-compose -f docker-compose.local.yml up -d
```

---

## 🎯 Testing Modes

### Mode 1: UI Only (Separate Backend)

Use this if your backend is running elsewhere:

```bash
# 1. Make sure backend is running
curl http://localhost:9000/api/health

# 2. Start UI only
docker-compose -f docker-compose.local.yml up -d auroqa-ui-local

# 3. Access UI
open http://localhost:3000
```

### Mode 2: Full-Stack Local

Use this to run both frontend and backend together:

```bash
# 1. Make sure you have the backend image built
cd /Users/aragossa/dzrprj/auroqa/auroqa
docker build -f Dockerfile.obfuscated -t auroqa:obfuscated-local .

# 2. Start both services
cd /Users/aragossa/dzrprj/auroqa/auroqa-ui
docker-compose -f docker-compose.local.yml up -d

# 3. Access
# Frontend: http://localhost:3000
# Backend:  http://localhost:9000
```

### Mode 3: UI with Production Backend

Point to your production backend:

```bash
# 1. Edit .env
echo "REACT_APP_API_URL=https://debuggo.app" > .env

# 2. Rebuild (environment is baked into the build)
docker build -f Dockerfile.production -t auroqa-ui:production-local .

# 3. Start UI
docker-compose -f docker-compose.local.yml up -d auroqa-ui-local

# 4. Access
open http://localhost:3000
```

---

## 📝 Common Commands

### View Logs

```bash
# Follow logs in real-time
docker-compose -f docker-compose.local.yml logs -f auroqa-ui-local

# View last 50 lines
docker-compose -f docker-compose.local.yml logs --tail=50 auroqa-ui-local

# View both UI and backend logs
docker-compose -f docker-compose.local.yml logs -f
```

### Restart Services

```bash
# Restart UI only
docker-compose -f docker-compose.local.yml restart auroqa-ui-local

# Restart both
docker-compose -f docker-compose.local.yml restart
```

### Stop Services

```bash
# Stop all services
docker-compose -f docker-compose.local.yml down

# Stop and remove volumes
docker-compose -f docker-compose.local.yml down -v
```

### Rebuild After Changes

```bash
# Rebuild UI image
docker build -f Dockerfile.production -t auroqa-ui:production-local .

# Restart with new image
docker-compose -f docker-compose.local.yml up -d auroqa-ui-local
```

### Access Container Shell

```bash
# Get shell in nginx container
docker exec -it auroqa-ui-local sh

# View served files
ls -la /usr/share/nginx/html/

# Check nginx config
cat /etc/nginx/conf.d/default.conf

exit
```

---

## 🔍 Verify Build

### Check Build Output

```bash
# Check what's in the container
docker run --rm auroqa-ui:production-local ls -lh /usr/share/nginx/html/

# Check build size
docker run --rm auroqa-ui:production-local du -sh /usr/share/nginx/html/

# Count files
docker run --rm auroqa-ui:production-local find /usr/share/nginx/html -type f | wc -l
```

### Test Static Files

```bash
# Test index.html
curl http://localhost:3000/index.html

# Test a JS bundle (replace with actual filename)
curl http://localhost:3000/static/js/main.*.js | head -c 100

# Test CSS bundle
curl http://localhost:3000/static/css/main.*.css | head -c 100
```

---

## 🐛 Troubleshooting

### Issue: Cannot connect to backend

**Error in browser console:**
```
Failed to fetch http://localhost:9000/api/...
```

**Solutions:**

1. Check if backend is running:
```bash
curl http://localhost:9000/api/health
```

2. Verify `.env` has correct API URL:
```bash
cat .env | grep REACT_APP_API_URL
```

3. Rebuild if you changed `.env`:
```bash
docker build -f Dockerfile.production -t auroqa-ui:production-local .
docker-compose -f docker-compose.local.yml up -d
```

### Issue: Port 3000 already in use

**Error:**
```
Bind for 0.0.0.0:3000 failed: port is already allocated
```

**Solutions:**

1. Check what's using port 3000:
```bash
lsof -i :3000
```

2. Stop the process or change port in docker-compose.local.yml:
```yaml
ports:
  - "3001:80"  # Change 3000 to 3001
```

### Issue: Build fails with npm errors

**Error:**
```
npm ERR! code ELIFECYCLE
```

**Solutions:**

1. Make sure package.json exists:
```bash
ls -la package.json
```

2. Try clearing npm cache:
```bash
rm -rf node_modules package-lock.json
npm install
docker build -f Dockerfile.production -t auroqa-ui:production-local .
```

### Issue: White screen / blank page

**Browser shows blank page**

**Solutions:**

1. Check browser console for errors (F12)

2. Verify index.html exists:
```bash
docker exec auroqa-ui-local cat /usr/share/nginx/html/index.html | head -20
```

3. Check nginx logs:
```bash
docker logs auroqa-ui-local
```

4. Verify build output:
```bash
docker exec auroqa-ui-local ls -la /usr/share/nginx/html/
```

### Issue: Backend CORS errors

**Error in console:**
```
Access to fetch at 'http://localhost:9000' has been blocked by CORS policy
```

**Solution:**

Backend needs CORS headers. Check backend's `main.py` has:
```python
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

---

## 📦 Build Optimization

The production build includes:

### Webpack Optimizations (Automatic)
- ✅ Code minification
- ✅ Tree shaking (removes unused code)
- ✅ Code splitting (separate chunks)
- ✅ Asset optimization
- ✅ Gzip compression (by nginx)

### Nginx Optimizations
- ✅ Static file serving
- ✅ Gzip compression enabled
- ✅ Browser caching headers
- ✅ SPA routing support

### What's NOT Included
- ❌ Source maps (can be enabled for debugging)
- ❌ Hot module replacement
- ❌ Development server

---

## 🚀 Production Deployment

Once local testing is complete:

### Step 1: Update Production Dockerfile

```bash
cd /Users/aragossa/dzrprj/auroqa/auroqa-ui

# Backup original
cp Dockerfile Dockerfile.original

# Use production version
cp Dockerfile.production Dockerfile
```

### Step 2: Update Environment

```bash
# Edit .env for production
echo "REACT_APP_API_URL=https://your-production-api.com" > .env
```

### Step 3: Build and Deploy

```bash
# Build production image
docker build -t your-registry/auroqa-ui:latest .

# Push to registry
docker push your-registry/auroqa-ui:latest

# Deploy (method depends on your hosting)
# Example for direct deployment:
# docker pull your-registry/auroqa-ui:latest
# docker run -d -p 80:80 your-registry/auroqa-ui:latest
```

---

## 🎯 Testing Checklist

- [ ] **Build:** Image builds without errors
- [ ] **Size:** Build output is reasonable (typically 1-5 MB)
- [ ] **Files:** index.html and bundles present
- [ ] **Startup:** Container starts successfully
- [ ] **Access:** Can access at http://localhost:3000
- [ ] **Loading:** Page loads without blank screen
- [ ] **Backend:** Can connect to backend API
- [ ] **Login:** Authentication works
- [ ] **Features:** All main features work
- [ ] **Console:** No errors in browser console
- [ ] **Network:** API calls succeed

---

## 💡 Tips

1. **Fast rebuilds:** Only rebuild if you change code or `.env`
2. **Development mode:** Use `npm start` for hot-reload during development
3. **Production testing:** Use this Docker setup to test production build locally
4. **Backend compatibility:** Make sure backend CORS is configured
5. **Browser cache:** Hard refresh (Ctrl+Shift+R) if you see old UI after rebuild

---

## 📚 Files Created

- `Dockerfile.production` - Production build with nginx
- `docker-compose.local.yml` - Compose file for local testing
- `test-ui-local.sh` - Automated build and test script
- `UI_LOCAL_TESTING.md` - This documentation

---

## ❓ Need Help?

1. Check logs: `docker-compose -f docker-compose.local.yml logs -f`
2. Check browser console (F12)
3. Verify backend is running
4. Check `.env` configuration
5. Try rebuilding from scratch

---

**Last Updated:** November 6, 2025
**Author:** AuroQA Development Team
