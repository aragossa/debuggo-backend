#!/bin/bash
# Quick script to test obfuscated Docker image

set -e

echo "🔒 Testing Obfuscated Docker Image"
echo "=================================="

# Stop any existing containers
echo "🛑 Stopping existing containers..."
docker stop $(docker ps -q --filter ancestor=auroqa:protected-test) 2>/dev/null || true

# Check if image exists
if ! docker images | grep -q "auroqa.*protected-test"; then
    echo "❌ Image 'auroqa:protected-test' not found. Build it first:"
    echo "   docker build -f Dockerfile.pyc -t auroqa:protected-test ."
    exit 1
fi

echo ""
echo "🚀 Starting container with host network..."
echo "   App will be available at: http://localhost:8000"
echo ""

# Start container in background
docker run -d \
    --name auroqa-obfuscated-test \
    --network host \
    --env-file .env \
    auroqa:protected-test

echo ""
echo "⏳ Waiting for application to start (10 seconds)..."
sleep 10

echo ""
echo "🔍 Checking health endpoint..."
if curl -s http://localhost:8000/api/health > /dev/null; then
    echo "✅ Application is running!"
    echo ""
    echo "📍 Access URLs:"
    echo "   - Health: http://localhost:8000/api/health"
    echo "   - Login:  http://localhost:8000/api/login/google"
    echo "   - API:    http://localhost:8000/api/"
    echo ""
    echo "📊 View logs:"
    echo "   docker logs -f auroqa-obfuscated-test"
    echo ""
    echo "🛑 Stop container:"
    echo "   docker stop auroqa-obfuscated-test && docker rm auroqa-obfuscated-test"
    echo ""
    echo "🔍 Verify obfuscation:"
    echo "   docker exec auroqa-obfuscated-test ls /app/Services/*.pyc"
else
    echo "❌ Application failed to start. Check logs:"
    echo "   docker logs auroqa-obfuscated-test"
    exit 1
fi
