#!/usr/bin/env python3
"""
Auto-generate .env file with secure random secret key.
"""
import secrets
import os
from pathlib import Path


def generate_env():
    """Generate .env file if it doesn't exist."""
    env_file = Path(__file__).parent / ".env"

    # Don't overwrite existing .env file
    if env_file.exists():
        print("✓ .env file already exists")
        return

    # Generate secure random secret key
    secret_key = secrets.token_urlsafe(32)

    # Read template
    template_file = Path(__file__).parent / ".env.minimal"
    if not template_file.exists():
        print("✗ .env.minimal template not found")
        return

    template_content = template_file.read_text()

    # Replace placeholder with actual secret key
    env_content = template_content.replace(
        "CHANGE_THIS_TO_A_RANDOM_SECRET_KEY",
        secret_key
    )

    # Write .env file
    env_file.write_text(env_content)

    print("✓ Generated .env file with secure secret key")
    print(f"✓ Secret key: {secret_key[:16]}...")
    print("\n🎉 Configuration complete! All other settings can be configured via web UI.")


if __name__ == "__main__":
    generate_env()
