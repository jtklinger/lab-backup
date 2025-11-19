# Lab Backup System

Enterprise-grade web-based backup solution for KVM virtual machines and Podman containers with support for multiple storage backends, incremental backups, and automated retention management using the grandfather-father-son rotation strategy.

> **🎉 NEW: Zero-Configuration Setup!**
> No more manual `.env` file editing! Just run `docker-compose up -d` and configure everything through the web interface.
> **Windows users:** See [SETUP-WINDOWS.md](SETUP-WINDOWS.md) for 3-step quick start guide.

## Features

### Core Functionality
- ✅ **KVM VM Backup** - Full and incremental backups using native libvirt API
- ✅ **Podman Container Backup** - Container filesystem, volumes, and configuration backup
- ✅ **Multiple Storage Backends** - Local, SMB/NFS, and S3-compatible storage (Backblaze B2, MinIO, AWS S3)
- ✅ **Scheduled Backups** - Flexible cron-based scheduling for Daily, Weekly, Monthly, Yearly, and Archival backups
- ✅ **Intelligent Retention** - Grandfather-father-son rotation with configurable retention periods
- ✅ **Incremental Backups** - Reduce storage usage with incremental snapshots
- ✅ **Compression** - gzip, zstd, or uncompressed backups
- ✅ **Multi-User Support** - Role-based access control (Admin, Operator, Viewer)

### Management & Monitoring
- ✅ **RESTful API** - Complete API for automation and integration
- ✅ **Real-time Job Tracking** - Monitor backup progress and status
- ✅ **Email Notifications** - Alerts for completion, failure, and status updates
- ✅ **Storage Monitoring** - Track usage and set threshold alerts
- ✅ **Comprehensive Logging** - Local logs with optional remote syslog support
- ✅ **Task Scheduler** - Celery-based distributed task execution
- ✅ **Metrics & Monitoring** - Prometheus-compatible metrics via Flower

### Security & Authentication
- ✅ **SSH Key Management** - Upload, generate, and manage SSH keys per KVM host via web UI
- ✅ **Encrypted Key Storage** - Private keys encrypted at rest using Fernet (AES-128)
- ✅ **Automatic Key Deployment** - System configures SSH client with database-stored keys
- ✅ **Flexible Authentication** - Support for default SSH keys or database-managed keys
- ✅ **SSL/TLS Support** - Self-signed or custom certificates for HTTPS
- ✅ **Role-Based Access Control** - Admin, Operator, and Viewer roles

### Recovery & Restoration
- ✅ **VM Recovery** - Restore to original or different KVM host
- ✅ **Flexible Restore Options** - Overwrite existing or create new with different name
- ✅ **Container Recovery** - Full container restoration with volumes
- ✅ **Backup Verification** - Checksum validation for data integrity

## Architecture

See [ARCHITECTURE.md](ARCHITECTURE.md) for detailed system architecture, component design, and technology stack.

## Documentation

**Setup & Configuration:**
- [SETUP-WINDOWS.md](SETUP-WINDOWS.md) - Windows 11 setup guide
- [QUICK-REFERENCE.md](QUICK-REFERENCE.md) - Quick reference for common operations
- [docs/SSL_TLS_CONFIGURATION.md](docs/SSL_TLS_CONFIGURATION.md) - SSL/TLS certificate setup

**Feature Guides:**
- [docs/SSH_KEY_MANAGEMENT.md](docs/SSH_KEY_MANAGEMENT.md) - SSH key management for KVM hosts
- [docs/TIERED_STORAGE_ARCHITECTURE.md](docs/TIERED_STORAGE_ARCHITECTURE.md) - Tiered storage configuration

## Quick Start

### Prerequisites

- Docker or Podman with Docker Compose
- Access to KVM/libvirt host (local or remote)
- Access to Podman host (optional, if backing up containers)
- PostgreSQL 15+ (included in docker-compose)
- Redis 7+ (included in docker-compose)

### Installation

#### Option 1: Zero-Configuration Setup (Recommended)

1. **Clone and start**
   ```bash
   git clone <repository-url>
   cd lab-backup
   docker-compose up -d
   ```

2. **Open browser and complete setup wizard**
   - Visit http://localhost:8000
   - Follow the 3-step setup wizard
   - Configure admin account, email (optional), and retention policies
   - **Done!** Everything else is configured via web UI

3. **Access the application**
   - API: http://localhost:8000
   - API Docs: http://localhost:8000/docs
   - Celery Flower: http://localhost:5555

See [SETUP-WINDOWS.md](SETUP-WINDOWS.md) for detailed Windows 11 guide.

#### Option 2: Manual Configuration (Advanced)

1. **Clone the repository**
   ```bash
   git clone <repository-url>
   cd lab-backup
   ```

2. **Create environment configuration**
   ```bash
   cp .env.example .env
   # Edit .env with your configuration
   nano .env
   ```

3. **Generate a secret key**
   ```bash
   python3 -c "import secrets; print(secrets.token_urlsafe(32))"
   # Add the output to SECRET_KEY in .env
   ```

4. **Start the services**
   ```bash
   docker-compose up -d
   ```

5. **Run database migrations** (auto-runs with zero-config setup)
   ```bash
   docker-compose exec api alembic upgrade head
   ```

6. **Create initial admin user** (or use setup wizard)
   ```bash
   docker-compose exec api python -c "
   from backend.models.base import SyncSessionLocal
   from backend.models.user import User, UserRole
   from backend.core.security import get_password_hash

   db = SyncSessionLocal()
   admin = User(
       username='admin',
       email='admin@example.com',
       password_hash=get_password_hash('admin123'),
       role=UserRole.ADMIN,
       is_active=True
   )
   db.add(admin)
   db.commit()
   print('Admin user created: admin / admin123')
   "
   ```

7. **Access the application**
   - API: http://localhost:8000
   - API Docs: http://localhost:8000/docs
   - Celery Flower: http://localhost:5555

## Configuration

### Environment Variables

Key environment variables (see `.env.example` for full list):

```bash
# Security
SECRET_KEY=your-secret-key-here

# Database
DATABASE_URL=postgresql+asyncpg://user:pass@host:5432/dbname

# Redis & Celery
REDIS_URL=redis://localhost:6379/0
CELERY_BROKER_URL=redis://localhost:6379/1

# Storage
BACKUP_BASE_PATH=/backups
BACKUP_COMPRESSION=zstd

# Email
SMTP_HOST=smtp.example.com
SMTP_PORT=587
SMTP_USER=your-email@example.com
SMTP_PASSWORD=your-password

# Retention (in days)
RETENTION_DAILY=7
RETENTION_WEEKLY=28
RETENTION_MONTHLY=365
RETENTION_YEARLY=1825
```

## Usage

### API Authentication

1. **Login to get access token**
   ```bash
   curl -X POST http://localhost:8000/api/v1/auth/login \
     -H "Content-Type: application/x-www-form-urlencoded" \
     -d "username=admin&password=admin123"
   ```

2. **Use token in subsequent requests**
   ```bash
   curl http://localhost:8000/api/v1/kvm/hosts \
     -H "Authorization: Bearer <your-token>"
   ```

### Adding a KVM Host

```bash
curl -X POST http://localhost:8000/api/v1/kvm/hosts \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "kvm-host-1",
    "uri": "qemu+ssh://user@host/system",
    "auth_type": "ssh"
  }'
```

### Syncing VMs from KVM Host

```bash
curl http://localhost:8000/api/v1/kvm/hosts/1/vms?sync=true \
  -H "Authorization: Bearer <token>"
```

### Adding a Storage Backend

**Local Storage:**
```bash
curl -X POST http://localhost:8000/api/v1/storage \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "local-storage",
    "type": "local",
    "config": {
      "base_path": "/backups/local"
    },
    "threshold": 80
  }'
```

**S3 Storage (Backblaze B2):**
```bash
curl -X POST http://localhost:8000/api/v1/storage \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "backblaze-b2",
    "type": "s3",
    "config": {
      "endpoint_url": "https://s3.us-west-002.backblazeb2.com",
      "aws_access_key_id": "your-key-id",
      "aws_secret_access_key": "your-secret",
      "bucket_name": "my-backups",
      "region": "us-west-002",
      "prefix": "lab-backup/"
    },
    "threshold": 80
  }'
```

### Creating a Backup Schedule

```bash
curl -X POST http://localhost:8000/api/v1/schedules \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Daily VM Backup",
    "source_type": "vm",
    "source_id": 1,
    "schedule_type": "daily",
    "cron_expression": "0 2 * * *",
    "retention_config": {
      "daily": 7,
      "weekly": 4,
      "monthly": 12,
      "yearly": 5
    },
    "storage_backend_id": 1
  }'
```

### Running a Backup Immediately

```bash
curl -X POST http://localhost:8000/api/v1/schedules/1/run \
  -H "Authorization: Bearer <token>"
```

### Listing Backups

```bash
curl http://localhost:8000/api/v1/backups \
  -H "Authorization: Bearer <token>"
```

### Viewing Job Logs

```bash
curl http://localhost:8000/api/v1/jobs/1/logs \
  -H "Authorization: Bearer <token>"
```

## Backup Schedule Types

- **Daily** - Run daily, keep last N days
- **Weekly** - Run weekly, keep last N weeks
- **Monthly** - Run monthly, keep last N months
- **Yearly** - Run yearly, keep last N years
- **Archival** - Long-term storage, manual deletion only

## Cron Expression Examples

```
"0 2 * * *"      # Daily at 2:00 AM
"0 3 * * 0"      # Weekly on Sunday at 3:00 AM
"0 4 1 * *"      # Monthly on the 1st at 4:00 AM
"0 5 1 1 *"      # Yearly on January 1st at 5:00 AM
"0 */6 * * *"    # Every 6 hours
"*/30 * * * *"   # Every 30 minutes
```

## Grandfather-Father-Son Retention

The system automatically implements GFS rotation:

1. **Daily (Son)** - Keep last 7 daily backups (default)
2. **Weekly (Father)** - Keep last 4 weekly backups (first backup of week)
3. **Monthly (Grandfather)** - Keep last 12 monthly backups (first backup of month)
4. **Yearly** - Keep last 5 yearly backups (first backup of year)
5. **Archival** - Keep indefinitely until manually deleted

Configure retention periods per schedule:
```json
{
  "retention_config": {
    "daily": 7,
    "weekly": 4,
    "monthly": 12,
    "yearly": 5
  }
}
```

## Development

### Running Locally

1. **Install dependencies**
   ```bash
   cd backend
   pip install -r requirements.txt
   ```

2. **Start PostgreSQL and Redis**
   ```bash
   docker-compose up -d postgres redis
   ```

3. **Run migrations**
   ```bash
   alembic upgrade head
   ```

4. **Start the API**
   ```bash
   uvicorn backend.main:app --reload
   ```

5. **Start Celery worker**
   ```bash
   celery -A backend.worker worker --loglevel=info
   ```

6. **Start Celery beat**
   ```bash
   celery -A backend.worker beat --loglevel=info
   ```

### Creating Database Migrations

```bash
# Auto-generate migration from model changes
alembic revision --autogenerate -m "description"

# Apply migrations
alembic upgrade head

# Rollback one version
alembic downgrade -1
```

### Running Tests

```bash
cd backend
pytest
pytest --cov=backend tests/
```

## API Documentation

Interactive API documentation is available at:
- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

## Monitoring

### Celery Tasks (Flower)

Monitor Celery tasks and workers at http://localhost:5555

### Logs

View application logs:
```bash
docker-compose logs -f api
docker-compose logs -f celery-worker
docker-compose logs -f celery-beat
```

### Metrics

The application exposes Prometheus-compatible metrics for monitoring.

## Troubleshooting

### libvirt Connection Issues

If you're having trouble connecting to libvirt:

1. Ensure libvirt socket is accessible
   ```bash
   ls -la /var/run/libvirt/libvirt-sock
   ```

2. Add user to libvirt group
   ```bash
   usermod -a -G libvirt $(whoami)
   ```

3. For remote connections, configure SSH authentication using either:
   - **Web UI** (recommended): Use the SSH Key Management feature - see [docs/SSH_KEY_MANAGEMENT.md](docs/SSH_KEY_MANAGEMENT.md)
   - **Manual setup**: Copy SSH keys to the target host
     ```bash
     ssh-copy-id user@kvm-host
     ```

### Podman Connection Issues

1. Ensure Podman socket is running
   ```bash
   systemctl --user enable --now podman.socket
   ```

2. Check socket location
   ```bash
   ls -la /run/podman/podman.sock
   ```

### Database Connection Issues

1. Check PostgreSQL is running
   ```bash
   docker-compose ps postgres
   ```

2. Test database connection
   ```bash
   psql postgresql://labbackup:changeme@localhost:5432/lab_backup
   ```

### Storage Backend Issues

1. Test local storage permissions
   ```bash
   ls -la /backups
   ```

2. For S3, verify credentials and bucket access
   ```bash
   aws s3 ls s3://your-bucket/ --endpoint-url=<endpoint>
   ```

## Security Considerations

1. **Change default credentials** - Update admin password and database credentials
2. **Use strong SECRET_KEY** - Generate a secure random key
3. **Enable HTTPS** - Use a reverse proxy (nginx, traefik) with TLS
4. **Secure storage credentials** - Store sensitive config in environment variables or secrets manager
5. **Network isolation** - Use firewall rules to restrict access
6. **Regular updates** - Keep dependencies and base images updated
7. **Backup encryption** - Enable backup encryption for sensitive data
8. **Audit logging** - Review audit logs regularly

## Performance Tuning

1. **Database connection pooling** - Adjust `DB_POOL_SIZE` and `DB_MAX_OVERFLOW`
2. **Celery workers** - Scale workers based on backup workload
3. **Redis persistence** - Configure Redis for backup persistence or disable for performance
4. **Compression** - Choose compression algorithm based on CPU/storage trade-off (zstd recommended)
5. **Backup scheduling** - Stagger backup schedules to avoid resource contention

## Upgrading

1. **Backup your database**
   ```bash
   docker-compose exec postgres pg_dump -U labbackup lab_backup > backup.sql
   ```

2. **Pull latest changes**
   ```bash
   git pull origin main
   ```

3. **Rebuild containers**
   ```bash
   docker-compose down
   docker-compose build
   docker-compose up -d
   ```

4. **Run migrations**
   ```bash
   docker-compose exec api alembic upgrade head
   ```

## Contributing

Contributions are welcome! Please:

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests
5. Submit a pull request

## License

[Specify your license here]

## Support

For issues, questions, or feature requests, please open an issue on the GitHub repository.

## Recently Completed Features

- ✅ **React Web Frontend** - Modern Material-UI interface with comprehensive management
- ✅ **Form Validation** - Real-time validation with helpful error messages
- ✅ **VM Restore** - Full restore functionality with flexible options
- ✅ **Container Restore** - Complete Podman container restoration
- ✅ **Backup Verification** - Automated verification and integrity checks
- ✅ **Immutable Backups** - WORM storage support for ransomware protection
- ✅ **SMB/CIFS Storage** - Network share backend implementation
- ✅ **Database Logging** - Comprehensive application logging with database storage
- ✅ **SSH Key Management** - Web-based SSH key upload, generation, and deployment
- ✅ **Password Authentication** - Alternative auth method for KVM hosts
- ✅ **Audit Logging** - Complete audit trail with SIEM integration
- ✅ **Compliance Tracking** - Automated compliance status monitoring
- ✅ **Changed Block Tracking** - Efficient incremental backups via CBT

## Roadmap

### Planned Features
- [ ] Bare-metal server backup support
- [ ] Kubernetes pod backup
- [ ] Multi-site replication
- [ ] Advanced reporting and analytics
- [ ] Webhook notifications
- [ ] Disaster recovery orchestration
- [ ] Backup encryption at rest
- [ ] Multi-tenancy support

## Acknowledgments

Built with:
- FastAPI - Modern Python web framework
- libvirt - Virtualization API
- Podman - Container management
- Celery - Distributed task queue
- PostgreSQL - Database
- Redis - Caching and message broker
- SQLAlchemy - ORM
- Alembic - Database migrations
