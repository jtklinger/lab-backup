# Lab Backup System Architecture

## Overview
Enterprise-grade web-based backup solution for KVM virtual machines and Podman containers with support for multiple storage backends, incremental backups, and automated retention management.

## Technology Stack

### Backend
- **Framework:** FastAPI (Python 3.11+)
  - Async support for better performance
  - Automatic OpenAPI documentation
  - Type hints and validation with Pydantic
- **Database:** PostgreSQL 15+
  - SQLAlchemy 2.0 ORM
  - Alembic for migrations
- **Task Queue:** Celery 5+ with Redis
  - Distributed task execution
  - Scheduled jobs with Celery Beat
  - Real-time progress tracking

### Virtualization & Container APIs
- **KVM/QEMU:** libvirt Python bindings
  - Native API for VM snapshots and backups
  - Incremental backup support via block jobs
- **Podman:** Podman Python API
  - Container export and volume backup
  - Checkpoint/restore support

### Storage Backends
- **Local:** Direct filesystem access
- **SMB/NFS:** Network filesystem mounting
- **S3-Compatible:** boto3 for AWS S3, Backblaze B2, MinIO
  - Multipart uploads for large files
  - Server-side encryption support

### Frontend
- **Framework:** React 18+ with TypeScript
- **UI Library:** Material-UI (MUI)
- **State Management:** React Query + Context API
- **Real-time Updates:** WebSocket for job progress

### Monitoring & Logging
- **Application Logs:** Python logging with syslog support
- **Metrics:** Prometheus-compatible metrics
- **Alerting:** Email notifications via SMTP
- **Remote Logging:** Syslog, rsyslog support

## System Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     Web Frontend (React)                     │
│  Dashboard │ Jobs │ Schedules │ Storage │ Recovery │ Users  │
└─────────────────────┬───────────────────────────────────────┘
                      │ HTTPS/WebSocket
┌─────────────────────▼───────────────────────────────────────┐
│                   API Gateway (FastAPI)                      │
│         Authentication │ Authorization │ Rate Limiting       │
└─────────────────────┬───────────────────────────────────────┘
                      │
    ┌─────────────────┼─────────────────┬──────────────────┐
    │                 │                 │                  │
┌───▼────┐    ┌───────▼──────┐  ┌──────▼─────┐  ┌────────▼────────┐
│Backup  │    │  Recovery    │  │ Scheduler  │  │   Monitoring    │
│Service │    │   Service    │  │  (Celery)  │  │    Service      │
└───┬────┘    └──────┬───────┘  └─────┬──────┘  └────────┬────────┘
    │                │                 │                  │
    │    ┌───────────┴─────────────────┤                  │
    │    │                             │                  │
┌───▼────▼───┐              ┌──────────▼──────────┐  ┌────▼────────┐
│  libvirt   │              │   Podman API        │  │  Prometheus │
│    API     │              │                     │  │   Metrics   │
└─────┬──────┘              └──────────┬──────────┘  └─────────────┘
      │                                │
┌─────▼────────────────────────────────▼──────┐
│         KVM VMs    │    Podman Containers   │
└────────────────────────────────────────────┬┘
                                             │
        ┌────────────────────────────────────┼────────────────┐
        │                                    │                │
┌───────▼────────┐              ┌────────────▼──────┐  ┌──────▼──────┐
│ Local Storage  │              │   SMB/NFS Share   │  │  S3 Storage │
│  /backups/     │              │  //nas/backups    │  │  (Backblaze)│
└────────────────┘              └───────────────────┘  └─────────────┘
```

## Core Components

### 1. Backup Service
**Responsibilities:**
- Execute backup jobs for VMs and containers
- Create incremental snapshots using native APIs
- Compress and encrypt backup data
- Upload to configured storage backends
- Track backup metadata in database

**KVM Backup Flow:**
1. Create VM snapshot using libvirt
2. Export disk images (qcow2) with incremental support
3. Export VM XML configuration
4. Compress backup bundle
5. Upload to storage backend
6. Record metadata and update database

**Podman Backup Flow:**
1. Export container filesystem
2. Backup container configuration
3. Backup associated volumes
4. Create checkpoint (if supported)
5. Compress and upload
6. Record metadata

### 2. Storage Abstraction Layer
**Interface:** Common storage interface for all backends
```python
class StorageBackend:
    def upload(path, data, metadata)
    def download(path, destination)
    def delete(path)
    def list(prefix)
    def get_usage()
```

**Implementations:**
- LocalStorage: Direct filesystem operations
- SMBStorage: SMB protocol via smbprotocol
- NFSStorage: NFS mount with filesystem operations
- S3Storage: boto3 S3 operations

### 3. Scheduler Service
**Celery Tasks:**
- Periodic backup jobs (cron-style)
- Retention policy enforcement
- Storage cleanup
- Health checks
- Report generation

**Celery Beat Schedule:**
- User-defined backup schedules
- Daily retention checks
- Hourly storage monitoring
- Weekly report generation

### 4. Retention Policy Engine
**Grandfather-Father-Son Strategy:**
- **Daily (Son):** Keep last N daily backups (e.g., 7 days)
- **Weekly (Father):** Keep last N weekly backups (e.g., 4 weeks)
- **Monthly (Grandfather):** Keep last N monthly backups (e.g., 12 months)
- **Yearly:** Keep last N yearly backups (e.g., 5 years)
- **Long-Term Archival:** Keep indefinitely with manual deletion only

**Retention Logic:**
1. Tag each backup with type(s) based on schedule
2. Evaluate retention rules daily
3. Mark expired backups for deletion
4. Execute cleanup with grace period
5. Verify deletions and update metrics

### 5. Recovery Service
**Capabilities:**
- List available backups with filters
- Download backup from storage
- Restore VM to original or new KVM host
- Restore with overwrite or rename
- Validate backup integrity before restore
- Progress tracking and logging

**Recovery Flow:**
1. Select backup and target host
2. Download backup data from storage
3. Connect to target libvirt host
4. Import VM configuration (rename if needed)
5. Restore disk images
6. Start VM (optional)
7. Verify successful restoration

### 6. Multi-User System
**Authentication:**
- JWT-based authentication
- Password hashing with bcrypt
- Session management with Redis

**Authorization (RBAC):**
- **Admin:** Full system access
- **Operator:** Create/manage backups and schedules
- **Viewer:** Read-only access to backups and reports

**User Features:**
- Per-user notification preferences
- Activity audit logs
- API token management

### 7. Monitoring & Alerting
**Metrics Collected:**
- Backup job success/failure rates
- Backup duration and size
- Storage usage per backend
- System resource usage
- API response times

**Alerts:**
- Backup job failures
- Storage threshold exceeded (e.g., 80% full)
- Scheduled job missed
- System errors
- Authentication failures

**Notification Channels:**
- Email (SMTP)
- Webhook (future)
- Syslog for log aggregation

## Database Schema

### Core Tables
```sql
-- Users and Authentication
users (id, username, email, password_hash, role, created_at, last_login)
api_tokens (id, user_id, token_hash, name, expires_at, created_at)

-- KVM Hosts and VMs
kvm_hosts (id, name, uri, username, auth_type, config, enabled, created_at)
vms (id, kvm_host_id, name, uuid, vcpus, memory, disk_size, state, created_at)

-- Podman Hosts and Containers
podman_hosts (id, name, uri, config, enabled, created_at)
containers (id, podman_host_id, name, container_id, image, state, created_at)

-- Storage Backends
storage_backends (id, name, type, config, enabled, capacity, used, threshold, created_at)

-- Backup Schedules
backup_schedules (
  id, name, source_type, source_id,
  schedule_type, cron_expression, retention_config,
  storage_backend_id, enabled, created_at
)

-- Backups
backups (
  id, schedule_id, source_type, source_id, source_name,
  backup_type, tags, status, size, compressed_size,
  storage_backend_id, storage_path, checksum,
  started_at, completed_at, expires_at, metadata
)

-- Jobs and Logs
jobs (id, type, status, started_at, completed_at, error, metadata)
job_logs (id, job_id, timestamp, level, message)

-- Notifications
notification_configs (id, user_id, type, config, enabled)
notifications (id, user_id, type, subject, message, sent_at, read_at)

-- Audit Logs
audit_logs (id, user_id, action, resource_type, resource_id, details, timestamp)
```

## Security Considerations

### 1. Authentication & Authorization
- Strong password requirements
- JWT tokens with short expiration
- Refresh token rotation
- Role-based access control
- API rate limiting

### 2. Data Protection
- Encryption at rest for sensitive configs (KVM credentials)
- TLS/HTTPS for all API communications
- Optional backup encryption before upload
- Secure credential storage (HashiCorp Vault integration option)

### 3. Network Security
- Firewall rules for KVM/libvirt connections
- VPN support for remote hosts
- Network isolation for backup traffic

### 4. Audit & Compliance
- Comprehensive audit logging
- Backup integrity verification
- Compliance reports
- GDPR-compliant data handling

## Deployment Architecture

### Container-Based Deployment (Recommended)
```yaml
services:
  api:
    image: lab-backup-api:latest
    ports: ["8000:8000"]
    environment:
      - DATABASE_URL
      - REDIS_URL
    volumes:
      - /etc/libvirt:/etc/libvirt:ro
      - /var/run/libvirt:/var/run/libvirt
      - /backups:/backups

  celery-worker:
    image: lab-backup-api:latest
    command: celery -A app.worker worker
    volumes:
      - /var/run/libvirt:/var/run/libvirt
      - /backups:/backups

  celery-beat:
    image: lab-backup-api:latest
    command: celery -A app.worker beat

  frontend:
    image: lab-backup-frontend:latest
    ports: ["3000:80"]

  postgres:
    image: postgres:15
    volumes:
      - postgres-data:/var/lib/postgresql/data

  redis:
    image: redis:7-alpine
    volumes:
      - redis-data:/data
```

### Upgrade Strategy
1. Database migrations with Alembic (automatic)
2. Rolling updates for API containers
3. Backup/restore configuration
4. Version compatibility checks
5. Rollback capability

## Incremental Backup Strategy

### KVM Incremental Backups
- Use libvirt block commit/pull operations
- QCOW2 backing file chains
- Changed Block Tracking (CBT) via dirty bitmaps
- Store only changed blocks between backups

### Podman Incremental Backups
- Layer-based container image backups
- Volume diff tracking
- Checkpoint incremental support

## API Design

### RESTful Endpoints
```
# Authentication
POST   /api/v1/auth/login
POST   /api/v1/auth/logout
POST   /api/v1/auth/refresh

# KVM Hosts & VMs
GET    /api/v1/kvm/hosts
POST   /api/v1/kvm/hosts
GET    /api/v1/kvm/hosts/{id}/vms
GET    /api/v1/kvm/vms

# Podman Hosts & Containers
GET    /api/v1/podman/hosts
POST   /api/v1/podman/hosts
GET    /api/v1/podman/hosts/{id}/containers

# Storage Backends
GET    /api/v1/storage
POST   /api/v1/storage
PUT    /api/v1/storage/{id}
GET    /api/v1/storage/{id}/usage

# Backup Schedules
GET    /api/v1/schedules
POST   /api/v1/schedules
PUT    /api/v1/schedules/{id}
DELETE /api/v1/schedules/{id}
POST   /api/v1/schedules/{id}/run

# Backups
GET    /api/v1/backups
GET    /api/v1/backups/{id}
DELETE /api/v1/backups/{id}
POST   /api/v1/backups/{id}/restore

# Jobs & Monitoring
GET    /api/v1/jobs
GET    /api/v1/jobs/{id}
GET    /api/v1/jobs/{id}/logs
GET    /api/v1/metrics

# Users
GET    /api/v1/users
POST   /api/v1/users
PUT    /api/v1/users/{id}

# Reports
GET    /api/v1/reports/backup-status
GET    /api/v1/reports/storage-usage
GET    /api/v1/reports/job-history
```

### WebSocket Endpoints
```
WS /api/v1/ws/jobs/{id} - Real-time job progress
WS /api/v1/ws/notifications - User notifications
```

## Performance Considerations

### 1. Async Operations
- All I/O operations are async
- Non-blocking backup uploads
- Parallel backup job execution

### 2. Caching
- Redis cache for frequently accessed data
- VM/container metadata caching
- Storage usage caching

### 3. Optimization
- Compression before upload (gzip, zstd)
- Deduplication at block level
- Multipart uploads for large files
- Connection pooling for databases

## Future Enhancements
- Bare-metal server backup support
- Kubernetes pod backup
- Backup verification and testing
- Disaster recovery orchestration
- Multi-site replication
- Immutable backups (WORM storage)
- Ransomware protection features
- Advanced reporting and analytics
