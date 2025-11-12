#!/usr/bin/env python3
"""
Auto-generate .env file with secure random keys.
"""
import secrets
import os
from pathlib import Path
# Import encryption module if available, otherwise generate manually
try:
    import sys
    sys.path.insert(0, str(Path(__file__).parent))
    from backend.core.encryption import generate_encryption_key
except ImportError:
    # Fallback if backend not available yet
    from cryptography.fernet import Fernet
    def generate_encryption_key():
        return Fernet.generate_key().decode('utf-8')


def generate_env():
    """Generate .env file if it doesn't exist."""
    env_file = Path(__file__).parent / ".env"

    # Don't overwrite existing .env file
    if env_file.exists():
        print("✓ .env file already exists")
        return

    # Generate secure random secret key for JWT
    secret_key = secrets.token_urlsafe(32)

    # Generate encryption key for backups
    encryption_key = generate_encryption_key()

    # Read template
    template_file = Path(__file__).parent / ".env.minimal"
    if not template_file.exists():
        print("✗ .env.minimal template not found")
        return

    template_content = template_file.read_text()

    # Replace placeholders with actual keys
    env_content = template_content.replace(
        "insecure-default-key-please-change-in-production",
        secret_key
    ).replace(
        "ENCRYPTION_KEY_PLACEHOLDER",
        encryption_key
    )

    # Write .env file
    env_file.write_text(env_content)

    print("✓ Generated .env file with secure keys")
    print(f"✓ JWT Secret key: {secret_key[:16]}...")
    print(f"✓ Encryption key: {encryption_key[:16]}...")
    print("\n🎉 Configuration complete! All other settings can be configured via web UI.")


if __name__ == "__main__":
    generate_env()
