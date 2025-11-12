#!/usr/bin/env python3
"""
Health check script that supports both HTTP and HTTPS.
Tries HTTPS first if SSL is enabled, falls back to HTTP.
"""
import os
import sys
import requests
from urllib3.exceptions import InsecureRequestWarning

# Suppress SSL warnings for self-signed certificates
requests.packages.urllib3.disable_warnings(InsecureRequestWarning)

def check_health():
    """Check application health via HTTP or HTTPS."""
    ssl_enabled = os.environ.get('ENABLE_SSL', 'true').lower() == 'true'
    ssl_port = int(os.environ.get('SSL_PORT', '8443'))
    http_port = int(os.environ.get('HTTP_PORT', '8000'))

    # Try HTTPS first if SSL is enabled
    if ssl_enabled:
        try:
            response = requests.get(
                f'https://localhost:{ssl_port}/health',
                timeout=5,
                verify=False  # Accept self-signed certificates
            )
            if response.status_code == 200:
                return True
        except Exception:
            pass  # Fall back to HTTP

    # Try HTTP
    try:
        response = requests.get(
            f'http://localhost:{http_port}/health',
            timeout=5
        )
        return response.status_code == 200
    except Exception:
        return False

if __name__ == '__main__':
    sys.exit(0 if check_health() else 1)
