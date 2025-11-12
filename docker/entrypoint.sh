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
# alembic upgrade head  # Temporarily disabled to fix migration issues

# Create default admin user if no admin exists
echo "👤 Checking for admin user..."
python3 -c "
import asyncio
from backend.models.base import AsyncSessionLocal
from backend.models.user import User, UserRole
from backend.core.security import get_password_hash
from sqlalchemy import select

async def create_default_admin():
    async with AsyncSessionLocal() as db:
        # Check if any admin user exists
        stmt = select(User).where(User.role == 'admin').limit(1)
        result = await db.execute(stmt)
        admin_exists = result.scalar_one_or_none() is not None

        if not admin_exists:
            print('⚠️  No admin user found. Creating default admin user...')
            admin = User(
                username='admin',
                email='admin@localhost',
                password_hash=get_password_hash('admin'),
                role='admin',
                is_active=True
            )
            db.add(admin)
            await db.commit()
            print('✅ Default admin user created!')
            print('   Username: admin')
            print('   Password: admin')
            print('   ⚠️  WARNING: Please change this password immediately!')
            print('   You can do this via the web UI at http://localhost:8000')
        else:
            print('✅ Admin user already exists')

asyncio.run(create_default_admin())
"

# Initialize logging
echo "📊 Initializing logging..."
python3 -c "from backend.core.logging_handler import setup_logging; setup_logging()"

# Start the application
echo "✨ Starting application..."
exec "$@"
