#!/bin/bash
# Deploy Lab Backup System using Podman Pod

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEPLOY_DIR="/opt/backup-deployment"

echo "========================================="
echo "Deploying Lab Backup System v1.0.0"
echo "========================================="

# Check if running as root
if [ "$EUID" -ne 0 ]; then
  echo "❌ Error: This script must be run as root"
  exit 1
fi

# Ensure we're in the deployment directory
if [ ! -d "$DEPLOY_DIR" ]; then
  echo "❌ Error: Deployment directory $DEPLOY_DIR does not exist"
  exit 1
fi

cd "$DEPLOY_DIR"

# Create required directories
echo "Creating required directories..."
mkdir -p /opt/backup-deployment/data/postgres
mkdir -p /opt/backup-deployment/data/redis
mkdir -p /opt/backup-deployment/certs
mkdir -p /opt/backup-deployment/logs
mkdir -p /srv/backups

# Set permissions
chmod 700 /opt/backup-deployment/data/postgres
chmod 700 /opt/backup-deployment/data/redis
chmod 755 /opt/backup-deployment/certs
chmod 755 /opt/backup-deployment/logs
chmod 755 /srv/backups

# Check if pod already exists
if podman pod exists lab-backup; then
  echo "⚠️  Pod 'lab-backup' already exists"
  read -p "Stop and remove existing pod? (y/N): " response
  if [[ "$response" =~ ^[Yy]$ ]]; then
    echo "Stopping existing pod..."
    podman pod stop lab-backup || true
    echo "Removing existing pod..."
    podman pod rm -f lab-backup
  else
    echo "❌ Deployment aborted"
    exit 1
  fi
fi

# Generate SECRET_KEY if not already set
if ! grep -q "^SECRET_KEY=" .env 2>/dev/null || grep -q "^SECRET_KEY=REPLACE" .env 2>/dev/null; then
  echo "Generating SECRET_KEY..."
  SECRET_KEY=$(openssl rand -base64 48)
  sed -i "s|SECRET_KEY=.*|SECRET_KEY=$SECRET_KEY|" .env || echo "SECRET_KEY=$SECRET_KEY" >> .env
fi

# Deploy the pod
echo ""
echo "Deploying pod from YAML..."
podman play kube deployment/podman/lab-backup-pod.yaml

# Wait for containers to start
echo ""
echo "Waiting for containers to start..."
sleep 10

# Check pod status
echo ""
echo "Pod status:"
podman pod ps
echo ""
echo "Container status:"
podman ps --pod --filter pod=lab-backup

echo ""
echo "✅ Deployment complete!"
echo ""
echo "Next steps:"
echo "  1. Verify SSL certificates in /opt/backup-deployment/certs/"
echo "  2. Access web UI at https://backup01.lab.towerbancorp.com:8443"
echo "  3. Login with default credentials: admin/admin"
echo "  4. Change the default password immediately!"
echo ""
echo "Monitor logs with: podman logs -f lab-backup-api"
echo "Check pod status: podman pod ps"
