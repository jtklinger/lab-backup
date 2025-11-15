#!/bin/bash
set -e

echo "🚀 Starting Lab Backup System..."

# Generate .env file if it doesn't exist
if [ ! -f /app/.env ]; then
    echo "📝 Generating configuration file..."
    python3 /app/generate-env.py
fi

# Run database migrations (only from API container)
if [ "${RUN_MIGRATIONS:-false}" = "true" ]; then
    echo "🗄️  Running database migrations..."
    alembic upgrade head

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

    # Note: Logging is now initialized in FastAPI lifespan (backend/main.py)
    # This ensures it runs after uvicorn sets up its logging configuration

    # Setup SSH configuration for KVM host connections
    echo "🔑 Configuring SSH client..."
    mkdir -p /root/.ssh
    chmod 700 /root/.ssh 2>/dev/null || true  # Ignore error if mounted read-only

    # Create SSH config for medium security (accept-new host keys)
    cat > /root/.ssh/config <<'EOF'
# SSH configuration for KVM host connections
# Medium security: Accept new host keys automatically, but verify known ones

Host *
    StrictHostKeyChecking accept-new
    UserKnownHostsFile /root/.ssh/known_hosts
    ServerAliveInterval 60
    ServerAliveCountMax 3
    ConnectTimeout 30
EOF
    chmod 600 /root/.ssh/config

    # Ensure known_hosts exists
    touch /root/.ssh/known_hosts 2>/dev/null || touch /tmp/known_hosts
    chmod 600 /root/.ssh/known_hosts 2>/dev/null || true

    echo "✅ SSH client configured (StrictHostKeyChecking: accept-new)"

    # Setup SSL certificates if enabled
    if [ "${ENABLE_SSL:-true}" = "true" ]; then
        echo "🔒 Setting up SSL/TLS certificates..."
        python3 -c "
from backend.core.certificates import CertificateManager
import os

cert_manager = CertificateManager(cert_dir=os.getenv('SSL_CERT_DIR', '/app/certs'))
hostname = os.getenv('SSL_HOSTNAME', 'localhost')
custom_cert = os.getenv('SSL_CERT_FILE')
custom_key = os.getenv('SSL_KEY_FILE')

try:
    cert_path, key_path = cert_manager.setup_certificates(
        cert_path=custom_cert,
        key_path=custom_key,
        hostname=hostname,
        auto_generate=True
    )

    if cert_path and key_path:
        # Validate the certificate
        cert_info = cert_manager.validate_certificate(cert_path)
        if cert_info.get('valid'):
            print('✅ SSL certificates ready')
            if cert_info.get('self_signed'):
                print('   ⚠️  Using self-signed certificate')
                print('   ℹ️  Browsers will show security warnings')
                print('   ℹ️  For production, use a valid CA-signed certificate')
            if cert_info.get('expires_soon'):
                print(f'   ⚠️  Certificate expires in {cert_info[\"days_until_expiry\"]} days')
        else:
            print(f'❌ Certificate validation failed: {cert_info.get(\"error\")}')
    else:
        print('⚠️  No SSL certificates configured, HTTPS will be disabled')
except Exception as e:
    print(f'❌ Failed to setup SSL certificates: {e}')
    print('   Continuing without HTTPS...')
"
    fi
fi

# Start the application
echo "✨ Starting application..."
exec "$@"
