#!/bin/bash
set -e

echo "🚀 Starting Lab Backup System..."

# Generate .env file if it doesn't exist
if [ ! -f /app/.env ]; then
    echo "📝 Generating configuration file..."
    python3 /app/generate-env.py
fi

# Run database migrations
echo "🗄️  Running database migrations..."
alembic upgrade head

# Start the application
echo "✨ Starting application..."
exec "$@"
