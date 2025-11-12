# SSL/TLS Configuration Guide

Lab Backup System includes built-in HTTPS support with automatic certificate generation for secure communications.

## Table of Contents

- [Overview](#overview)
- [Quick Start](#quick-start)
- [Configuration Options](#configuration-options)
- [Self-Signed Certificates](#self-signed-certificates)
- [Custom Certificates](#custom-certificates)
- [Disabling HTTPS](#disabling-https)
- [Certificate Management](#certificate-management)
- [Troubleshooting](#troubleshooting)
- [Production Best Practices](#production-best-practices)

## Overview

HTTPS/TLS encryption protects data in transit between clients and the Lab Backup System API. The system supports:

- **Automatic self-signed certificate generation** (default for internal lab use)
- **Custom CA-signed certificates** (recommended for production)
- **Persistent certificate storage** (survives container restarts)
- **Automatic certificate validation and expiry warnings**

## Quick Start

### Default Configuration (Self-Signed)

By default, the system automatically generates a self-signed SSL certificate on first startup:

```bash
docker-compose up -d
```

Access the web UI at:
- **HTTPS:** https://localhost:8443 (recommended)
- **HTTP:** http://localhost:8000 (fallback)

**Note:** Browsers will show a security warning for self-signed certificates. This is expected for internal lab use.

### Accept Self-Signed Certificate in Browser

**Chrome/Edge:**
1. Navigate to https://localhost:8443
2. Click "Advanced"
3. Click "Proceed to localhost (unsafe)"

**Firefox:**
1. Navigate to https://localhost:8443
2. Click "Advanced"
3. Click "Accept the Risk and Continue"

## Configuration Options

SSL/TLS behavior is controlled via environment variables in `docker-compose.yml` or `.env` file:

```yaml
environment:
  # Enable/disable SSL (default: true)
  - ENABLE_SSL=true

  # Hostname for certificate generation
  - SSL_HOSTNAME=backup.lab.towerbancorp.com

  # Certificate directory (default: /app/certs)
  - SSL_CERT_DIR=/app/certs

  # HTTPS port (default: 8443)
  - SSL_PORT=8443

  # HTTP fallback port (default: 8000)
  - HTTP_PORT=8000

  # Custom certificate files (optional)
  - SSL_CERT_FILE=/app/certs/custom.crt
  - SSL_KEY_FILE=/app/certs/custom.key
```

## Self-Signed Certificates

### Automatic Generation

On first startup with `ENABLE_SSL=true`, the system automatically generates a self-signed certificate valid for 365 days.

The certificate includes Subject Alternative Names (SANs) for:
- The configured hostname (`SSL_HOSTNAME`)
- `localhost`
- `127.0.0.1`
- `::1`

### Manual Regeneration

To regenerate the self-signed certificate:

```bash
# Remove existing certificates
docker volume rm lab-backup_ssl_certs

# Restart containers
docker-compose down
docker-compose up -d
```

### Custom Hostname

To generate a certificate for your lab domain:

```yaml
# In docker-compose.yml or .env
environment:
  - SSL_HOSTNAME=backup.lab.towerbancorp.com
```

## Custom Certificates

### Using CA-Signed Certificates

For production use, obtain a certificate from a trusted Certificate Authority (Let's Encrypt, DigiCert, etc.).

**1. Place certificate files in the `ssl_certs` volume:**

```bash
# Create temporary container to access volume
docker run --rm -v lab-backup_ssl_certs:/certs -v $(pwd):/source alpine sh -c "
  cp /source/your-certificate.crt /certs/server.crt
  cp /source/your-private-key.key /certs/server.key
  chmod 600 /certs/server.key
"
```

**2. Restart the API container:**

```bash
docker-compose restart api
```

### Certificate Chain

If your certificate requires an intermediate CA chain:

```bash
# Combine certificate with chain
cat your-certificate.crt intermediate-ca.crt root-ca.crt > server.crt

# Copy to volume
docker run --rm -v lab-backup_ssl_certs:/certs -v $(pwd):/source alpine sh -c "
  cp /source/server.crt /certs/server.crt
  cp /source/your-private-key.key /certs/server.key
  chmod 600 /certs/server.key
"
```

### Custom Certificate Paths

To use certificates in a custom location:

```yaml
environment:
  - SSL_CERT_FILE=/custom/path/to/certificate.crt
  - SSL_KEY_FILE=/custom/path/to/private.key

volumes:
  - /host/path/to/certs:/custom/path/to
```

## Disabling HTTPS

### Temporary Disable

To temporarily disable HTTPS (not recommended for production):

```yaml
# In docker-compose.yml
environment:
  - ENABLE_SSL=false
```

Then restart:

```bash
docker-compose restart api
```

Access the web UI at: http://localhost:8000

### Permanent HTTP-Only

For development environments where HTTPS is not needed:

```yaml
environment:
  - ENABLE_SSL=false

ports:
  - "8000:8000"
  # Remove or comment out HTTPS port
  # - "8443:8443"
```

## Certificate Management

### Check Certificate Status

View certificate details in the API logs:

```bash
docker logs lab-backup-api
```

Look for:
```
✅ SSL certificates ready
   ⚠️  Using self-signed certificate
   ℹ️  Browsers will show security warnings
```

### Certificate Expiry

The system automatically checks certificate expiry on startup and warns if:
- Certificate has expired
- Certificate expires within 30 days

```
⚠️  Certificate expires in 15 days
```

### Renewal

**Self-Signed Certificates:**
```bash
# Remove old certificates
docker volume rm lab-backup_ssl_certs
docker-compose down
docker-compose up -d
```

**CA-Signed Certificates:**
Follow your CA's renewal process, then replace the certificate files as described in [Custom Certificates](#custom-certificates).

## Troubleshooting

### Certificate Not Found

**Error:**
```
⚠️  SSL enabled but certificates not found, falling back to HTTP
```

**Solution:**
Ensure certificates exist in the correct location:

```bash
docker exec lab-backup-api ls -la /app/certs/
```

### Invalid Certificate

**Error:**
```
❌ Certificate validation failed: [error details]
```

**Solution:**
1. Check certificate format (must be PEM)
2. Verify certificate and key match
3. Check file permissions (key should be 600)

### Port Already in Use

**Error:**
```
Error: bind: address already in use
```

**Solution:**
Change the SSL port:

```yaml
environment:
  - SSL_PORT=9443

ports:
  - "9443:9443"
```

### Browser Certificate Error

**Issue:** Browser shows "Your connection is not private"

**For Self-Signed Certificates:**
This is expected. Click "Advanced" and proceed, or add the certificate to your browser's trusted certificates.

**For CA-Signed Certificates:**
1. Verify the certificate chain is complete
2. Check that the certificate's Common Name or SAN matches the hostname you're using
3. Ensure the certificate is not expired

## Production Best Practices

### 1. Use Valid CA-Signed Certificates

For production deployments, use certificates from a trusted CA:

- **Let's Encrypt** (free, automated)
- **Internal CA** (for enterprise environments)
- **Commercial CA** (DigiCert, GlobalSign, etc.)

### 2. Disable HTTP

Once HTTPS is working, consider disabling HTTP entirely:

```yaml
ports:
  # - "8000:8000"  # Disable HTTP
  - "8443:8443"      # HTTPS only
```

### 3. Use Strong TLS Configuration

The system uses Python's SSL defaults, which include:
- TLS 1.2 and 1.3 only
- Strong cipher suites
- Forward secrecy

### 4. Regular Certificate Rotation

- Monitor certificate expiry
- Set up automated renewal (Let's Encrypt recommended)
- Test renewals in staging environment first

### 5. Secure Certificate Storage

- Restrict file system access to certificate directory
- Use secrets management for private keys in production
- Never commit certificates to version control

### 6. Use Proper Hostname

Set `SSL_HOSTNAME` to your actual domain:

```yaml
environment:
  - SSL_HOSTNAME=backup.yourdomain.com
```

### 7. Consider Reverse Proxy

For advanced deployments, use a reverse proxy (nginx, Traefik) for:
- Centralized SSL termination
- Load balancing
- Advanced rate limiting
- WAF integration

Example nginx configuration:

```nginx
server {
    listen 443 ssl http2;
    server_name backup.yourdomain.com;

    ssl_certificate /path/to/certificate.crt;
    ssl_certificate_key /path/to/private.key;

    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;
    ssl_prefer_server_ciphers on;

    location / {
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

## Future Enhancements

Planned features for SSL/TLS support:

- **Let's Encrypt Integration:** Automatic certificate acquisition and renewal via ACME protocol
- **Certificate Monitoring API:** Endpoint to check certificate status programmatically
- **Multi-Certificate Support:** Different certificates for different domains
- **OCSP Stapling:** Improved certificate validation performance
- **Certificate Pinning:** Enhanced security for API clients

## Support

For issues or questions:
- Check application logs: `docker logs lab-backup-api`
- Review this documentation
- Check GitHub issues: https://github.com/anthropics/lab-backup/issues
