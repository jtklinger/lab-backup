# Podman Deployment Guide

This directory contains configuration for deploying Lab Backup System v1.0.0 using Podman pods and systemd.

## Prerequisites

- Rocky Linux 9.6 or compatible
- Podman 5.4.0+ installed
- Git installed
- Root access
- At least 70GB available disk space

## Quick Start

### 1. Prepare the Server

```bash
# Install git (if not already installed)
sudo dnf install -y git

# Create deployment directory
sudo mkdir -p /opt/backup-deployment
cd /opt/backup-deployment

# Clone repository
sudo git clone https://github.com/jtklinger/lab-backup .
sudo git checkout v1.0.0
```

### 2. Build Container Image

```bash
cd /opt/backup-deployment
sudo bash deployment/podman/build-image.sh
```

This builds the container image locally as `localhost/lab-backup:latest`.

### 3. Configure Environment

```bash
# Copy production environment template
sudo cp deployment/podman/.env.production .env

# Generate strong SECRET_KEY
SECRET_KEY=$(openssl rand -base64 48)

# Edit .env file
sudo vi .env

# At minimum, set:
# - SECRET_KEY (generated above)
# - Database password (if changing from default)
# - SSL settings
# - SMTP settings (if using email notifications)
```

### 4. Setup SSL Certificates

#### Option A: Use Certificates from cert01

```bash
# Copy certificates from cert01
sudo scp root@cert01.lab.towerbancorp.com:/path/to/backup01.crt /opt/backup-deployment/certs/server.crt
sudo scp root@cert01.lab.towerbancorp.com:/path/to/backup01.key /opt/backup-deployment/certs/server.key

# Set permissions
sudo chmod 644 /opt/backup-deployment/certs/server.crt
sudo chmod 600 /opt/backup-deployment/certs/server.key
```

#### Option B: Auto-generate Self-Signed

The system will auto-generate self-signed certificates on first startup if none are present.

### 5. Deploy the Pod

```bash
cd /opt/backup-deployment
sudo bash deployment/podman/deploy.sh
```

This will:
- Create required directories
- Generate SECRET_KEY if not set
- Deploy the pod with all containers
- Display deployment status

### 6. Install Systemd Service (Optional but Recommended)

```bash
# Copy service file
sudo cp deployment/podman/lab-backup.service /etc/systemd/system/

# Reload systemd
sudo systemctl daemon-reload

# Enable on boot
sudo systemctl enable lab-backup.service

# Start service
sudo systemctl start lab-backup.service

# Check status
sudo systemctl status lab-backup.service
```

### 7. Verify Deployment

```bash
# Check pod status
sudo podman pod ps

# Check containers
sudo podman ps --pod --filter pod=lab-backup

# View API logs
sudo podman logs lab-backup-api

# View worker logs
sudo podman logs lab-backup-celery-worker

# Test health endpoint
curl -k https://backup01.lab.towerbancorp.com:8443/health
```

### 8. Initial Configuration

1. Access web UI: https://backup01.lab.towerbancorp.com:8443
2. Login with default credentials: `admin` / `admin`
3. **IMMEDIATELY change the default password!**
4. Configure your first KVM host
5. Configure storage backend
6. Test a backup operation

## File Structure

```
deployment/podman/
├── lab-backup-pod.yaml       # Podman Kube YAML (pod definition)
├── lab-backup.service         # Systemd service file
├── build-image.sh             # Script to build container image
├── deploy.sh                  # Script to deploy pod
├── .env.production            # Production environment template
└── README.md                  # This file
```

## Container Architecture

The pod contains 6 containers:

1. **postgres** - PostgreSQL 16 database
2. **redis** - Redis 7 (cache and message broker)
3. **api** - FastAPI web server (HTTPS on port 8443)
4. **celery-worker** - Background task processor
5. **celery-beat** - Task scheduler
6. **flower** - Celery monitoring (port 5555)

## Volume Mounts

| Volume | Host Path | Container Path | Purpose |
|--------|-----------|----------------|---------|
| backup-data | /srv/backups | /backups | Backup storage |
| ssl-certs | /opt/backup-deployment/certs | /app/certs | SSL certificates |
| log-files | /opt/backup-deployment/logs | /var/log/lab-backup | Application logs |
| postgres-data | /opt/backup-deployment/data/postgres | /var/lib/postgresql/data | Database |
| redis-data | /opt/backup-deployment/data/redis | /data | Redis persistence |
| podman-socket | /run/podman | /var/run/podman | Podman API access |

## Management Commands

### Stop the pod
```bash
sudo podman pod stop lab-backup
```

### Start the pod
```bash
sudo podman pod start lab-backup
```

### Restart the pod
```bash
sudo podman pod restart lab-backup
```

### Remove the pod (CAUTION: Does not remove data)
```bash
sudo podman pod stop lab-backup
sudo podman pod rm lab-backup
```

### View logs
```bash
# All containers
sudo podman pod logs lab-backup

# Specific container
sudo podman logs lab-backup-api
sudo podman logs lab-backup-celery-worker
```

### Update to new version
```bash
cd /opt/backup-deployment

# Pull latest code
sudo git fetch
sudo git checkout <new-version-tag>

# Rebuild image
sudo bash deployment/podman/build-image.sh

# Restart pod
sudo systemctl restart lab-backup.service
# OR
sudo podman pod restart lab-backup
```

## Troubleshooting

### Pod won't start
```bash
# Check pod status
sudo podman pod ps -a

# Check container logs
sudo podman logs lab-backup-postgres
sudo podman logs lab-backup-api

# Check systemd logs (if using service)
sudo journalctl -u lab-backup.service -f
```

### Database connection issues
```bash
# Check postgres is running
sudo podman ps | grep postgres

# Check postgres logs
sudo podman logs lab-backup-postgres

# Verify database exists
sudo podman exec lab-backup-postgres psql -U labbackup -l
```

### SSL certificate issues
```bash
# Check certificates exist
ls -la /opt/backup-deployment/certs/

# Verify certificate
openssl x509 -in /opt/backup-deployment/certs/server.crt -text -noout

# Check API can read certificates
sudo podman exec lab-backup-api ls -la /app/certs/
```

### Cannot access web UI
```bash
# Check port is listening
sudo ss -tlnp | grep 8443

# Check firewall
sudo firewall-cmd --list-ports
sudo firewall-cmd --add-port=8443/tcp --permanent
sudo firewall-cmd --reload

# Check SELinux (if enabled)
sudo setenforce 0  # Temporary disable for testing
sudo ausearch -m avc -ts recent  # Check for denials
```

## Security Notes

1. **Change default passwords immediately**
   - Default admin password: admin/admin
   - Database password in .env file

2. **Protect .env file**
   ```bash
   sudo chmod 600 /opt/backup-deployment/.env
   ```

3. **Use strong SECRET_KEY**
   - Minimum 32 characters
   - Generated with: `openssl rand -base64 48`

4. **SSL Certificates**
   - Use CA-signed certificates for production
   - Protect private key: `chmod 600 server.key`

5. **Firewall Configuration**
   - Only expose port 8443 externally
   - Keep 5432 (postgres), 6379 (redis), 5555 (flower) internal

## Backup and Recovery

### Backup the system
```bash
# Backup database
sudo podman exec lab-backup-postgres pg_dump -U labbackup lab_backup > /tmp/lab_backup.sql

# Backup data directories
sudo tar -czf /tmp/lab-backup-data.tar.gz /opt/backup-deployment/data /srv/backups
```

### Restore from backup
```bash
# Restore database
cat /tmp/lab_backup.sql | sudo podman exec -i lab-backup-postgres psql -U labbackup lab_backup

# Restore data
sudo tar -xzf /tmp/lab-backup-data.tar.gz -C /
```

## Support

- Documentation: https://github.com/jtklinger/lab-backup/tree/main/docs
- Issues: https://github.com/jtklinger/lab-backup/issues
- Version: 1.0.0
