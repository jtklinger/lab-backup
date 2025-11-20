# Getting Started with Lab Backup System

A modern, enterprise-grade backup solution for KVM virtual machines and Podman containers with a beautiful web interface.

## Table of Contents
- [Prerequisites](#prerequisites)
- [Installation](#installation)
- [First Login](#first-login)
- [Your First Backup](#your-first-backup)
- [Next Steps](#next-steps)
- [Accessing Different Interfaces](#accessing-different-interfaces)
- [Need Help?](#need-help)

## Prerequisites

- **Docker Desktop** (Windows/Mac) or **Docker** (Linux)
- **Minimum 4GB RAM** allocated to Docker
- **Modern web browser** (Chrome, Firefox, Edge, Safari)
- **KVM or Podman hosts** to back up (remote or local)

## Installation

### Quick Start (2 Minutes)

1. **Clone the repository:**
```bash
git clone https://github.com/jtklinger/lab-backup.git
cd lab-backup
```

2. **Start all services:**
```bash
docker-compose up -d
```

This starts:
- PostgreSQL database
- Redis cache
- FastAPI backend
- React frontend
- Celery workers
- Flower monitoring

3. **Wait for services to be ready** (about 30 seconds):
```bash
docker-compose ps
```

All services should show "Up" and "healthy" status.

## First Login

### Access the Web Interface

1. **Open your browser** and navigate to:
   ```
   http://localhost:3000
   ```

2. **Login with default credentials:**
   - Username: `admin`
   - Password: `admin`

3. **IMPORTANT: Change your password immediately!**
   - Click on your profile icon (top right)
   - Select "Change Password"
   - Enter a strong password

### Accept SSL Certificate (First Time Only)

The API uses HTTPS with a self-signed certificate. You'll need to accept it:

1. In a new browser tab, visit: `https://localhost:8443`
2. Your browser will warn about the certificate
3. Click "Advanced" and "Accept the Risk" (wording varies by browser)
4. Return to http://localhost:3000 - the API will now work

## Your First Backup

Follow these steps to create your first VM backup:

### Step 1: Add a KVM Host

1. **Navigate to Hosts:**
   - Click "Infrastructure" in the left sidebar
   - Click "KVM Hosts" tab

2. **Add Host:**
   - Click the "+ Add Host" button
   - Fill in the form:
     - **Name:** Give it a descriptive name (e.g., "Production KVM")
     - **URI:** Connection string (e.g., `qemu+ssh://user@192.168.1.10/system`)
     - **Authentication:** Choose SSH Key or Password
   - Click "Test Connection" to verify
   - Click "Save"

3. **Verify VMs are discovered:**
   - Your VMs should appear automatically
   - Click "Refresh" if needed

### Step 2: Configure Storage Backend

1. **Navigate to Storage:**
   - Click "Storage" in the left sidebar

2. **Add Storage Backend:**
   - Click "+ Add Storage" button
   - Choose your storage type:
     - **Local:** For testing or same-server storage
     - **SMB/CIFS:** For Windows file shares or Samba
     - **S3:** For object storage (AWS, MinIO, etc.)

3. **Configure based on type:**

   **For Local Storage:**
   - Name: "Local Backups"
   - Path: `/backups` (pre-configured in Docker)

   **For SMB Storage:**
   - Name: "Network Share"
   - Server: IP or hostname
   - Share: Share name
   - Username/Password: Credentials
   - See [SMB-STORAGE.md](SMB-STORAGE.md) for details

   **For S3 Storage:**
   - Name: "S3 Backups"
   - Bucket name
   - Access key / Secret key
   - Region (optional)

4. **Test and Save:**
   - Click "Test Connection"
   - If successful, click "Save"

### Step 3: Create a Backup Schedule

1. **Navigate to Schedules:**
   - Click "Schedules" in the left sidebar

2. **Create Schedule:**
   - Click "+ Create Schedule" button
   - Fill in the schedule form:
     - **Name:** Descriptive name (e.g., "Daily Production Backup")
     - **VM/Container:** Select from dropdown
     - **Storage Backend:** Choose where to store backups
     - **Schedule:** Cron expression or use the helper
       - Daily at 2 AM: `0 2 * * *`
       - Every 6 hours: `0 */6 * * *`
     - **Retention Policy:**
       - Daily: Keep last 7 days
       - Weekly: Keep last 4 weeks
       - Monthly: Keep last 12 months
     - **Backup Type:**
       - Full: Complete backup (first time)
       - Incremental: Only changed blocks (faster)
   - Click "Create"

### Step 4: Run Your First Backup (Optional - Don't Wait for Schedule)

1. **Navigate to Backups:**
   - Click "Backups" in the left sidebar

2. **Run On-Demand Backup:**
   - Click "+ One-Time Backup" button
   - Select VM and storage backend
   - Choose "Full" backup type
   - Click "Start Backup"

3. **Monitor Progress:**
   - Go to "Dashboard" or "Jobs" page
   - Watch the backup job progress in real-time
   - Status will change: Pending → Running → Completed

### Step 5: Monitor Your System

1. **Dashboard Overview:**
   - Click "Dashboard" in the sidebar
   - View system statistics:
     - Total VMs/Containers
     - Backup success rate
     - Storage usage
     - Recent jobs
     - Active schedules

2. **View Backup History:**
   - Click "Backups" in the sidebar
   - See all completed backups
   - Filter by VM, date, status
   - Click on any backup to see details

3. **Check Job Logs:**
   - Click "Jobs" in the sidebar
   - View all backup and restore operations
   - Click a job to see detailed logs
   - Filter by status, type, date

## Next Steps

Now that you have your first backup running, explore these features:

### Restore a Backup
1. Go to "Backups" page
2. Find the backup you want to restore
3. Click the "Restore" button
4. Choose target KVM host and storage type
5. Monitor restore progress in "Jobs"

### Add Podman Containers
1. Navigate to "Infrastructure" → "Podman Hosts"
2. Click "+ Add Host"
3. Configure Podman connection (similar to KVM)
4. Containers are discovered automatically
5. Create backup schedules for containers

### Configure Email Alerts
1. Go to "Settings" (gear icon)
2. Click "Notifications" tab
3. Configure SMTP settings
4. Choose which events trigger emails:
   - Backup failures
   - Storage thresholds
   - Restore completion

### Set Up Encryption
1. Go to "Settings" → "Security"
2. Enable backup encryption
3. Encryption keys are stored in the database
4. Each storage backend can have its own key

### Enable Immutable Backups (Ransomware Protection)
1. Go to "Storage" page
2. Edit your S3 storage backend
3. Enable "Object Lock" or "Immutability"
4. Set retention period
5. Backups cannot be deleted during retention period

### Configure Compliance Policies
1. Go to "Settings" → "Compliance"
2. Define retention requirements
3. Set SLA targets (RPO/RTO)
4. View compliance reports

### Advanced Features
- **Changed Block Tracking (CBT):** Incremental backups only transfer changed blocks
- **Application-Consistent Backups:** Uses QEMU Guest Agent for consistent snapshots
- **Backup Verification:** Automated integrity checks
- **Audit Logging:** Complete audit trail of all operations
- **Tiered Storage:** Automatically move old backups to cheaper storage

## Accessing Different Interfaces

The Lab Backup System provides multiple interfaces:

### 1. Web Interface (Primary) - http://localhost:3000
- **What:** React-based modern UI for daily operations
- **Use for:** Creating backups, monitoring jobs, managing hosts, viewing dashboards
- **Best for:** Administrators, operators, anyone who prefers a visual interface

### 2. API Documentation - http://localhost:8000/docs
- **What:** Interactive Swagger/OpenAPI documentation
- **Use for:** API exploration, automation, scripting, integration
- **Best for:** Developers, automation engineers, CI/CD pipelines

### 3. Celery Flower - http://localhost:5555
- **What:** Real-time monitoring of background tasks
- **Use for:** Debugging task queues, monitoring worker health
- **Best for:** System administrators, troubleshooting

### 4. Database - localhost:5432
- **What:** PostgreSQL database (credentials in `.env`)
- **Use for:** Direct database access, advanced queries, troubleshooting
- **Best for:** Database administrators, advanced troubleshooting

### 5. Redis - localhost:6379
- **What:** Cache and message broker
- **Use for:** Direct cache inspection (rarely needed)
- **Best for:** Debugging, advanced troubleshooting

## Need Help?

### Documentation
- **Full Documentation:** [README.md](README.md)
- **Windows Setup Guide:** [SETUP-WINDOWS.md](SETUP-WINDOWS.md)
- **Architecture:** [ARCHITECTURE.md](ARCHITECTURE.md)
- **Troubleshooting:** [TROUBLESHOOTING.md](TROUBLESHOOTING.md)
- **Development Guide:** [DEVELOPMENT.md](DEVELOPMENT.md)

### Specific Topics
- **SSH Key Management:** [docs/SSH_KEY_MANAGEMENT.md](docs/SSH_KEY_MANAGEMENT.md)
- **SSL/TLS Configuration:** [docs/SSL_TLS_CONFIGURATION.md](docs/SSL_TLS_CONFIGURATION.md)
- **SMB Storage Setup:** [SMB-STORAGE.md](SMB-STORAGE.md)
- **Backup Verification:** [docs/API_BACKUP_VERIFICATION.md](docs/API_BACKUP_VERIFICATION.md)
- **Disaster Recovery:** [docs/DISASTER_RECOVERY.md](docs/DISASTER_RECOVERY.md)

### Common Issues
- **Cannot access web interface:** See [TROUBLESHOOTING.md](TROUBLESHOOTING.md#cannot-access-web-interface)
- **Login fails:** See [TROUBLESHOOTING.md](TROUBLESHOOTING.md#login-fails)
- **API connection errors:** See [TROUBLESHOOTING.md](TROUBLESHOOTING.md#api-connection-errors)
- **Docker containers not starting:** See [TROUBLESHOOTING.md](TROUBLESHOOTING.md#docker-containers-not-starting)

### Support
- **GitHub Issues:** https://github.com/jtklinger/lab-backup/issues
- **Documentation:** Check this repository's docs/ folder
- **Logs:** Check container logs with `docker-compose logs [service-name]`

## Quick Reference Card

| Task | Location | Action |
|------|----------|--------|
| View dashboard | Dashboard | Overview of system status |
| Add KVM host | Infrastructure → KVM Hosts | + Add Host button |
| Add Podman host | Infrastructure → Podman Hosts | + Add Host button |
| Add storage | Storage | + Add Storage button |
| Create schedule | Schedules | + Create Schedule button |
| Run backup now | Backups | + One-Time Backup button |
| Restore backup | Backups → Select backup | Restore button |
| View job logs | Jobs → Click job | View detailed logs |
| Change password | Profile icon → Change Password | Update credentials |
| Configure email | Settings → Notifications | SMTP settings |
| View API docs | http://localhost:8000/docs | Interactive API |
| Monitor workers | http://localhost:5555 | Celery Flower |

## What's Next?

Once you're comfortable with the basics:

1. **Set up automated schedules** for all critical VMs
2. **Configure email notifications** to stay informed
3. **Test restores regularly** to ensure backups are valid
4. **Enable encryption** for sensitive data
5. **Set up tiered storage** to optimize costs
6. **Configure compliance policies** if required
7. **Integrate with monitoring** using the API

Welcome to Lab Backup System - enterprise-grade backup made simple!
