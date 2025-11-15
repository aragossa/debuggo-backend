# Monitoring & Testing Documentation

Guides for monitoring dashboard setup and API testing.

## 📋 Files

### Monitoring Dashboard
- **PHASE1_MONITORING_DASHBOARD.md** - Complete monitoring dashboard documentation
- **PHASE1_MONITORING_BACKEND.md** - Backend monitoring service setup

### API Testing
- **MONITORING_API_TESTING.md** - API testing guide with curl examples

---

## 🎯 Quick Start

### Setup Monitoring Dashboard
1. Read [PHASE1_MONITORING_DASHBOARD.md](PHASE1_MONITORING_DASHBOARD.md)
2. Follow backend setup in [PHASE1_MONITORING_BACKEND.md](PHASE1_MONITORING_BACKEND.md)
3. Access dashboard at `/monitoring` (admin only)

### Test Monitoring APIs
1. Review [MONITORING_API_TESTING.md](MONITORING_API_TESTING.md)
2. Get admin token
3. Run test commands

---

## 📊 Dashboard Features

### Endpoints
- `/api/monitoring/health` - System health status
- `/api/monitoring/metrics` - All metrics
- `/api/monitoring/validation` - Validation metrics
- `/api/monitoring/confidence` - Confidence metrics
- `/api/monitoring/feedback` - Feedback metrics
- `/api/monitoring/retry` - Retry metrics
- `/api/monitoring/alerts` - Active alerts
- `/api/monitoring/trends` - Historical trends

### Access
- **URL**: `http://localhost:3000/monitoring`
- **Role**: Admin only
- **Auth**: JWT token required

---

## 🔗 Related Documentation
- [AI Agent Phase 1](../ai-agent/INDEX.md)
- [Setup Guides](../setup/INDEX.md)
