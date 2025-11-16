#!/bin/bash
# Build the Lab Backup container image using Podman

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

echo "==================================="
echo "Building Lab Backup Container Image"
echo "==================================="

cd "$PROJECT_ROOT"

# Build the image
echo "Building image..."
podman build \
  -f docker/Dockerfile \
  -t localhost/lab-backup:latest \
  -t localhost/lab-backup:1.0.0 \
  .

echo ""
echo "✅ Image built successfully!"
echo "   Tags: localhost/lab-backup:latest, localhost/lab-backup:1.0.0"
echo ""
echo "Verify with: podman images | grep lab-backup"
