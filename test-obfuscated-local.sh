#!/bin/bash
# Script to build and test obfuscated Docker image locally
# Connects to your local PostgreSQL, Redis, and Kafka instances

set -e

echo "🔒 AuroQA Obfuscated Code - Local Testing"
echo "=========================================="
echo ""

# Configuration
IMAGE_NAME="auroqa:obfuscated-local"
CONTAINER_NAME="auroqa-obfuscated-local"
DOCKERFILE="Dockerfile.obfuscated"
COMPOSE_FILE="docker-compose.local.yml"

# Function to print colored output
print_info() {
    echo -e "\033[1;34m[INFO]\033[0m $1"
}

print_success() {
    echo -e "\033[1;32m[SUCCESS]\033[0m $1"
}

print_error() {
    echo -e "\033[1;31m[ERROR]\033[0m $1"
}

print_warning() {
    echo -e "\033[1;33m[WARNING]\033[0m $1"
}

# Check if Dockerfile exists
if [ ! -f "$DOCKERFILE" ]; then
    print_error "Dockerfile not found: $DOCKERFILE"
    exit 1
fi

# Check if docker-compose file exists
if [ ! -f "$COMPOSE_FILE" ]; then
    print_error "Docker Compose file not found: $COMPOSE_FILE"
    exit 1
fi

# Check if .env exists
if [ ! -f ".env" ]; then
    print_error ".env file not found"
    exit 1
fi

echo ""
print_info "Step 1: Building obfuscated Docker image..."
echo "   Dockerfile: $DOCKERFILE"
echo "   Image name: $IMAGE_NAME"
echo ""

# Build the image
docker build -f "$DOCKERFILE" -t "$IMAGE_NAME" . || {
    print_error "Failed to build Docker image"
    exit 1
}

print_success "Docker image built successfully!"
echo ""

# Verify obfuscation
print_info "Step 2: Verifying code obfuscation..."
docker run --rm "$IMAGE_NAME" bash -c "
    echo '  📊 Obfuscation Statistics:'
    echo '    Total .pyc files: \$(find /app -name '*.pyc' -type f | wc -l)'
    echo '    Source .py files (should be minimal): \$(find /app -name '*.py' -type f ! -path '*/migrations/*' | wc -l)'
    echo ''
    echo '  🔍 Sample check - Services directory:'
    if ls /app/Services/*.py 2>/dev/null | head -5; then
        echo '    ⚠️  Warning: Source files still present'
    else
        echo '    ✅ Source files removed'
    fi
    if ls /app/Services/*.pyc 2>/dev/null | head -5; then
        echo '    ✅ Bytecode files present'
    else
        echo '    ❌ No bytecode files found'
    fi
"
echo ""

print_info "Step 3: Starting services with Docker Compose..."
echo ""

# Stop existing containers
docker-compose -f "$COMPOSE_FILE" down 2>/dev/null || true

# Start services
docker-compose -f "$COMPOSE_FILE" up -d

print_success "Services started!"
echo ""

# Wait for application to start
print_info "Step 4: Waiting for application to start (30 seconds)..."
sleep 30

# Check health
print_info "Step 5: Testing application health..."
if curl -f -s http://localhost:9000/api/health > /dev/null; then
    print_success "Application is healthy!"
else
    print_warning "Health check failed. Check logs below."
fi

echo ""
echo "=========================================="
echo "🎉 Setup Complete!"
echo "=========================================="
echo ""
echo "📍 Application URLs:"
echo "   Health Check:  http://localhost:9000/api/health"
echo "   API Base:      http://localhost:9000/api/"
echo "   Google Login:  http://localhost:9000/api/login/google"
echo ""
echo "📊 Management Commands:"
echo "   View logs:     docker-compose -f $COMPOSE_FILE logs -f"
echo "   Stop:          docker-compose -f $COMPOSE_FILE down"
echo "   Restart:       docker-compose -f $COMPOSE_FILE restart"
echo "   Shell access:  docker exec -it $CONTAINER_NAME bash"
echo ""
echo "🔍 Verify Obfuscation:"
echo "   docker exec $CONTAINER_NAME ls /app/Services/*.pyc | head -5"
echo "   docker exec $CONTAINER_NAME ls /app/Services/*.py 2>&1 | head -5"
echo ""
echo "📝 View Recent Logs:"
docker-compose -f "$COMPOSE_FILE" logs --tail=20
echo ""
