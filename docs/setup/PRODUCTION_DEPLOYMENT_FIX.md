# Production Deployment Fix - Service Connectivity Issues

## Problems
Multiple DNS resolution errors preventing inter-service communication:

1. **Selenium Hub**: `Failed to resolve 'selenium-hub' ([Errno -2] Name or service not known)`
2. **Kafka**: `DNS lookup failed for kafka:9092`
3. **General**: All containers unable to communicate with each other

## Root Cause
The `docker-compose.prod.yml` had the network configured as `external: true`, expecting a pre-existing network named `auroqa_auroqa_network`. If this network doesn't exist, containers can't communicate via hostname resolution.

## Solution Applied
Changed the network configuration from:
```yaml
networks:
  auroqa_network:
    external: true
    name: auroqa_auroqa_network
```

To:
```yaml
networks:
  auroqa_network:
    driver: bridge
```

This allows Docker Compose to create and manage the network automatically.

### Additional Improvements Applied

1. **Health Checks**: Added health checks for Zookeeper and Kafka to ensure they're ready before dependent services start
2. **Proper Dependencies**: Updated service dependencies with conditions:
   - `auroqa` now waits for postgres, redis (healthy), kafka, and selenium-hub
   - `kafka` now waits for zookeeper (healthy)
3. **Startup Order**: Services now start in the correct order with proper readiness checks

## Deployment Steps on Production Server

### 1. SSH into Production Server
```bash
ssh your-production-server
```

### 2. Navigate to Deployment Directory
```bash
cd /opt/auroqa
```

### 3. Update docker-compose.prod.yml
Pull the latest changes or manually update the file:
```bash
# If using git
git pull origin main

# OR manually edit the file
nano docker-compose.prod.yml
```

Update the networks section (lines 170-173) to:
```yaml
networks:
  auroqa_network:
    driver: bridge
```

### 4. Stop All Services
```bash
docker-compose -f docker-compose.prod.yml down
```

### 5. Remove Old Network (if exists)
```bash
# Check existing networks
docker network ls | grep auroqa

# Remove old network if exists
docker network rm auroqa_auroqa_network 2>/dev/null || true
```

### 6. Start Services with New Configuration
```bash
docker-compose -f docker-compose.prod.yml up -d
```

### 7. Verify Services are Running
```bash
# Check all containers
docker-compose -f docker-compose.prod.yml ps

# Expected output should show:
# - auroqa (backend)
# - selenium-hub
# - chrome1
# - chrome2
# - postgres
# - redis
# - kafka
# - zookeeper
# All should be "Up"
```

### 8. Verify Network Connectivity
```bash
# Check if auroqa container can resolve all service hostnames
docker exec auroqa ping -c 2 selenium-hub
docker exec auroqa ping -c 2 kafka
docker exec auroqa ping -c 2 postgres
docker exec auroqa ping -c 2 redis

# All should show successful ping responses
```

### 9. Check Service Status

**Selenium Hub:**
```bash
# View selenium-hub logs
docker logs selenium-hub

# Check if hub is ready
curl http://localhost:4444/wd/hub/status

# Should return JSON with "ready": true
```

**Kafka:**
```bash
# View kafka logs
docker logs auroqa-kafka

# Check kafka topics (should not error)
docker exec auroqa-kafka kafka-topics --bootstrap-server localhost:9092 --list
```

**Zookeeper:**
```bash
# Check zookeeper status
docker exec auroqa-zookeeper nc -z localhost 2181
echo $?  # Should return 0
```

### 10. Verify Backend Logs
```bash
# Check backend logs for connectivity issues
docker logs auroqa | grep -E "(selenium-hub|kafka|NoBrokersAvailable|DNS)"

# Should NOT see any DNS resolution errors
```

### 11. Test a Test Case
Try running a test case from the UI to verify the complete fix worked.

## Verification Checklist

- [ ] All containers are running (`docker-compose ps` shows all "Up")
- [ ] Network created: `docker network ls` shows `auroqa_auroqa_network`
- [ ] Selenium hub accessible: `curl http://localhost:4444/wd/hub/status` returns ready
- [ ] Kafka accessible: `docker exec auroqa-kafka kafka-topics --bootstrap-server localhost:9092 --list` works
- [ ] Backend can resolve all services: `docker exec auroqa ping selenium-hub/kafka/postgres/redis` all work
- [ ] No DNS errors in backend logs: `docker logs auroqa | grep DNS` returns empty
- [ ] Backend starts without "NoBrokersAvailable" error
- [ ] Test case execution works without hostname resolution errors

## Rollback (if needed)

If something goes wrong:
```bash
# Stop services
docker-compose -f docker-compose.prod.yml down

# Restore from backup (if you made one)
cp docker-compose.prod.yml.backup docker-compose.prod.yml

# Start with old config
docker-compose -f docker-compose.prod.yml up -d
```

## Additional Checks

### Check Backend Environment Variables
Ensure `/opt/auroqa/app/.env` contains:
```bash
SELENIUM_GRID_URL=http://selenium-hub:4444/wd/hub
```

Verify inside container:
```bash
docker exec auroqa cat /app/.env | grep SELENIUM_GRID_URL
```

### Monitor Logs
```bash
# Backend logs
docker logs -f auroqa

# Selenium hub logs
docker logs -f selenium-hub

# Chrome node logs
docker logs -f chrome1
docker logs -f chrome2
```

## Why This Fix Works

### Network Configuration
1. **Before**: Network was marked as `external: true`, requiring manual creation
2. **After**: Network is created automatically by Docker Compose with `driver: bridge`
3. **Result**: All services on the same network can resolve each other by service name

### Service Communication
All containers now share the `auroqa_network` bridge network, enabling DNS resolution:
- `auroqa` container can resolve `selenium-hub:4444`
- `auroqa` container can resolve `kafka:9092`
- `auroqa` container can resolve `postgres:5432`
- `auroqa` container can resolve `redis:6379`
- `kafka` container can resolve `zookeeper:2181`
- `chrome1/chrome2` nodes can resolve `selenium-hub:4442/4443`

### Health Checks & Dependencies
With proper health checks and dependency conditions:
- Zookeeper starts first and becomes healthy before Kafka starts
- Kafka starts and becomes ready before the backend connects
- Redis is healthy before the backend starts
- Selenium Hub is running before test execution begins
- Startup failures are more predictable and easier to debug

## Future Prevention

- Always test network connectivity after deployment
- Use health checks in docker-compose to verify service readiness
- Consider using a single `docker-compose.yml` with environment-specific overrides

## Support

If issues persist after following these steps:
1. Check docker logs: `docker-compose -f docker-compose.prod.yml logs`
2. Verify network: `docker network inspect auroqa_auroqa_network`
3. Check DNS resolution: `docker exec auroqa nslookup selenium-hub`
