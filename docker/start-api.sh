#!/bin/bash
# API server startup script with SSL/TLS support

set -e

# SSL Configuration
SSL_ENABLED="${ENABLE_SSL:-true}"
SSL_CERT_DIR="${SSL_CERT_DIR:-/app/certs}"
SSL_CERT_FILE="${SSL_CERT_FILE:-$SSL_CERT_DIR/server.crt}"
SSL_KEY_FILE="${SSL_KEY_FILE:-$SSL_CERT_DIR/server.key}"
SSL_PORT="${SSL_PORT:-8443}"
HTTP_PORT="${HTTP_PORT:-8000}"

# Uvicorn configuration
HOST="${HOST:-0.0.0.0}"
LOG_LEVEL="${LOG_LEVEL:-info}"
WORKERS="${WORKERS:-1}"

# Build uvicorn command
UVICORN_CMD="uvicorn backend.main:app --host $HOST --log-level $LOG_LEVEL"

if [ "$WORKERS" -gt 1 ]; then
    UVICORN_CMD="$UVICORN_CMD --workers $WORKERS"
fi

# Check if SSL should be enabled
if [ "$SSL_ENABLED" = "true" ] && [ -f "$SSL_CERT_FILE" ] && [ -f "$SSL_KEY_FILE" ]; then
    echo "🔒 Starting API server with HTTPS on port $SSL_PORT"
    echo "   Certificate: $SSL_CERT_FILE"
    echo "   Private Key: $SSL_KEY_FILE"

    # Start with SSL
    exec $UVICORN_CMD \
        --port $SSL_PORT \
        --ssl-keyfile "$SSL_KEY_FILE" \
        --ssl-certfile "$SSL_CERT_FILE"
else
    if [ "$SSL_ENABLED" = "true" ]; then
        echo "⚠️  SSL enabled but certificates not found, falling back to HTTP"
    fi

    echo "🌐 Starting API server with HTTP on port $HTTP_PORT"
    echo "   ⚠️  HTTPS is disabled - traffic will not be encrypted"
    echo "   ℹ️  For production use, enable HTTPS by setting ENABLE_SSL=true"

    # Start without SSL
    exec $UVICORN_CMD --port $HTTP_PORT
fi
