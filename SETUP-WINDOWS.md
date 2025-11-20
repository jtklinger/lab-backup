# Lab Backup System - Windows 11 Quick Start Guide

## 🎉 Modern Web Interface!

No command-line required - everything is managed through a beautiful React-based web interface!

## Prerequisites

1. **Install Docker Desktop for Windows**
   - Download from: https://www.docker.com/products/docker-desktop/
   - Run installer and restart your computer
   - Ensure WSL 2 is enabled
   - Allocate at least 4GB RAM to Docker (Settings → Resources)

2. **Clone the Repository**
   ```powershell
   git clone https://github.com/jtklinger/lab-backup.git
   cd lab-backup
   ```

## Installation (4 Simple Steps!)

### Step 1: Start the System

```powershell
docker-compose up -d
```

Wait about 30 seconds for all services to start. The system will:
- ✅ Auto-generate secure configuration
- ✅ Create the database
- ✅ Run migrations automatically
- ✅ Start all services (API, Frontend, Workers)

**Verify services are running:**
```powershell
docker-compose ps
```

All services should show "Up" and "healthy" status.

### Step 2: Open the Web Interface

**Open your browser and visit:**
```
http://localhost:3000
```

You should see the Lab Backup System login page.

### Step 3: Accept SSL Certificate (First Time Only)

The API uses HTTPS with a self-signed certificate. Before logging in:

1. Open a **new browser tab** and visit: `https://localhost:8443`
2. Your browser will warn about the certificate being untrusted
3. Click **"Advanced"** and **"Accept the Risk and Continue"** (wording varies by browser)
4. You'll see a simple JSON response: `{"status":"healthy"}`
5. **Close this tab** and return to http://localhost:3000

### Step 4: Login to the Web Interface

**Default Admin Credentials:**
- **Username:** `admin`
- **Password:** `admin`

**⚠️ IMPORTANT:** Change this password immediately after first login!

1. Enter the credentials and click "Login"
2. Once logged in, click your profile icon (top right)
3. Select "Change Password"
4. Enter a strong password and save

### That's It! 🎉

You're now ready to use the Lab Backup System through the modern web interface!

## What Happens Automatically

When you run `docker-compose up -d`:

1. ✅ **Configuration Auto-Generated**
   - Secure random secret key created
   - Database connection configured
   - Redis/Celery configured

2. ✅ **Database Initialized**
   - PostgreSQL started
   - Schema created automatically
   - Ready to use

3. ✅ **Default Admin User Created**
   - Username: admin
   - Password: admin
   - ⚠️ Change this immediately for security!

4. ✅ **All Services Started**
   - API server
   - Celery worker for background jobs
   - Celery beat for scheduled tasks
   - Flower for monitoring (optional)

## After Setup - Using the Web Interface

Once logged in, you can configure everything through the web interface:

### 1. Add a KVM Host (via Web UI)

1. **Navigate to Infrastructure:**
   - Click "Infrastructure" in the left sidebar
   - Click the "KVM Hosts" tab

2. **Add Host:**
   - Click the "+ Add Host" button
   - Fill in the form:
     - **Name:** Give it a descriptive name (e.g., "Production KVM")
     - **URI:** Connection string (e.g., `qemu+ssh://user@192.168.1.100/system`)
     - **Authentication:** Choose SSH Key or Password
   - Click "Test Connection" to verify
   - Click "Save"

3. **Your VMs will appear automatically!**

### 2. Add Storage Backend (via Web UI)

1. **Navigate to Storage:**
   - Click "Storage" in the left sidebar

2. **Add Storage:**
   - Click "+ Add Storage" button
   - Choose your storage type:
     - **Local:** For testing or same-server storage
     - **SMB/CIFS:** For Windows file shares or Samba
     - **S3:** For object storage (AWS, MinIO, Backblaze B2)

3. **Configure settings based on type:**
   - Fill in the form with connection details
   - Click "Test Connection" to verify
   - Click "Save"

### 3. Create a Backup Schedule (via Web UI)

1. **Navigate to Schedules:**
   - Click "Schedules" in the left sidebar

2. **Create Schedule:**
   - Click "+ Create Schedule" button
   - Fill in the schedule form:
     - **Name:** Descriptive name (e.g., "Daily Production Backup")
     - **VM/Container:** Select from dropdown
     - **Storage Backend:** Choose where to store backups
     - **Schedule:** Use cron expression or helper:
       - Daily at 2 AM: `0 2 * * *`
       - Every 6 hours: `0 */6 * * *`
     - **Retention Policy:**
       - Daily: Keep last 7 days
       - Weekly: Keep last 4 weeks
       - Monthly: Keep last 12 months
       - Yearly: Keep last 5 years
   - Click "Create"

### 4. Monitor Your Backups

1. **Dashboard:** Real-time overview of backups, storage, and system health
2. **Backups Page:** View all completed backups, filter by VM, date, status
3. **Jobs Page:** Track running and completed backup/restore operations
4. **Settings:** Configure email notifications, retention policies, and system settings

## Access Points

The system provides multiple interfaces:

| Interface | URL | Purpose |
|-----------|-----|---------|
| **Web Interface** (Primary) | http://localhost:3000 | Daily operations, configuration, monitoring |
| **API Documentation** | http://localhost:8000/docs | API reference for automation |
| **Celery Flower** | http://localhost:5555 | Task queue monitoring |

## Using the API (Optional - For Automation)

If you prefer PowerShell automation, see the [README.md](README.md#using-the-api-for-automation) for API examples.

The API is available at http://localhost:8000/docs with interactive documentation.

## Updating Settings Later

All settings can be updated through the API:

```powershell
# Update SMTP settings
$smtpSettings = @{
  settings = @{
    "smtp.enabled" = $true
    "smtp.host" = "smtp.gmail.com"
    "smtp.port" = 587
    "smtp.user" = "your-email@gmail.com"
    "smtp.password" = "your-app-password"
    "smtp.from_email" = "backups@example.com"
  }
} | ConvertTo-Json

Invoke-RestMethod -Uri "http://localhost:8000/api/v1/settings/bulk" `
  -Method Put -Headers $headers -Body $smtpSettings

# Update retention defaults
$retentionSettings = @{
  settings = @{
    "retention.daily" = 14
    "retention.weekly" = 8
    "retention.monthly" = 24
    "retention.yearly" = 10
  }
} | ConvertTo-Json

Invoke-RestMethod -Uri "http://localhost:8000/api/v1/settings/bulk" `
  -Method Put -Headers $headers -Body $retentionSettings
```

## Managing the System

```powershell
# View logs
docker-compose logs -f api

# Restart services
docker-compose restart

# Stop everything
docker-compose down

# Start again
docker-compose up -d

# View running containers
docker-compose ps
```

## Important Notes for Windows

### KVM/Podman Hosts

Since KVM and Podman don't run natively on Windows, you'll connect to **remote Linux hosts**:

1. **For KVM**: Use SSH connection
   - URI format: `qemu+ssh://user@hostname/system`
   - Ensure SSH key authentication is set up

2. **For Podman**: Use TCP connection
   - Enable Podman API on Linux host: `systemctl --user enable --now podman.socket`
   - Expose on network: `podman system service tcp:0.0.0.0:8888 --time=0`
   - URI format: `tcp://hostname:8888`

### Storage Paths

- **Local storage** in Docker: `/backups` (inside container)
- **Windows host path**: Configure via docker-compose volume mount
- **S3 storage**: Works identically on all platforms

### No Manual File Editing!

Unlike traditional setups, you **never** need to:
- ❌ Edit `.env` files
- ❌ Configure database connections
- ❌ Set up SMTP manually
- ❌ Calculate retention periods

Everything is done through the web interface! 🎉

## Troubleshooting

### Can't Access Setup Page

```powershell
# Check if services are running
docker-compose ps

# View API logs
docker-compose logs api

# Restart if needed
docker-compose restart api
```

### Database Connection Errors

```powershell
# Check if PostgreSQL is healthy
docker-compose ps postgres

# View database logs
docker-compose logs postgres

# Restart database
docker-compose restart postgres
```

### Need to Reset Setup

```powershell
# Stop all services
docker-compose down

# Remove volumes (WARNING: Deletes all data!)
docker-compose down -v

# Start fresh
docker-compose up -d
```

## Next Steps

1. ✅ **Complete Setup Wizard** - Create admin account
2. ✅ **Add KVM Hosts** - Connect to your KVM servers
3. ✅ **Configure Storage** - Set up backup destinations
4. ✅ **Create Schedules** - Define backup jobs
5. ✅ **Monitor** - Watch your backups run via Flower

## Getting Help

- **API Documentation**: http://localhost:8000/docs (interactive!)
- **View Logs**: `docker-compose logs -f api`
- **Check Status**: http://localhost:8000/health

---

**Enjoy your hassle-free backup system! No configuration files needed! 🚀**
