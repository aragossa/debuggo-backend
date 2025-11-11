#!/bin/bash
# Python Code Obfuscation Script
# This script obfuscates Python code before building Docker image

set -e

echo "🔐 Starting Python code obfuscation..."

# Configuration
SOURCE_DIR="."
OUTPUT_DIR="./obfuscated"
EXCLUDE_PATTERNS="migrations tests __pycache__ .git .env"

# Check if pyarmor is installed
if ! command -v pyarmor &> /dev/null; then
    echo "📦 Installing PyArmor..."
    pip install pyarmor
fi

# Clean previous obfuscation
if [ -d "$OUTPUT_DIR" ]; then
    echo "🧹 Cleaning previous obfuscation..."
    rm -rf "$OUTPUT_DIR"
fi

# Create output directory
mkdir -p "$OUTPUT_DIR"

# Build exclude arguments
EXCLUDE_ARGS=""
for pattern in $EXCLUDE_PATTERNS; do
    EXCLUDE_ARGS="$EXCLUDE_ARGS --exclude '$pattern/*'"
done

# Obfuscate code with PyArmor
echo "🔒 Obfuscating Python files..."
pyarmor gen \
    --enable-rft \
    --enable-jit \
    --obf-module 1 \
    --obf-code 1 \
    --output "$OUTPUT_DIR" \
    $EXCLUDE_ARGS \
    "$SOURCE_DIR"

# Copy non-Python files that are needed
echo "📋 Copying configuration files..."
cp requirements.txt "$OUTPUT_DIR/" 2>/dev/null || true
cp Dockerfile "$OUTPUT_DIR/" 2>/dev/null || true
cp .env.example "$OUTPUT_DIR/" 2>/dev/null || true

# Copy migrations directory (don't obfuscate SQL files)
if [ -d "migrations" ]; then
    cp -r migrations "$OUTPUT_DIR/"
fi

echo "✅ Obfuscation complete! Output: $OUTPUT_DIR"
echo ""
echo "📦 To build Docker image with obfuscated code:"
echo "   cd $OUTPUT_DIR && docker build -t auroqa:obfuscated ."
echo ""
echo "⚠️  Remember: Keep original source code in version control!"
