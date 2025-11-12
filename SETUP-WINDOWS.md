# Lab Backup System - Windows 11 Quick Start Guide

## 🎉 Zero Configuration Setup!

No need to edit environment files manually - everything is configured through a friendly web interface!

## Prerequisites

1. **Install Docker Desktop for Windows**
   - Download from: https://www.docker.com/products/docker-desktop/
   - Run installer and restart your computer
   - Ensure WSL 2 is enabled

2. **Clone the Repository**
   ```powershell
   git clone <repository-url>
   cd lab-backup
   ```

## Installation (3 Simple Steps!)

### Step 1: Start the System

```powershell
docker-compose up -d
```

That's it! No environment file editing required. The system will:
- ✅ Auto-generate secure configuration
- ✅ Create the database
- ✅ Run migrations automatically
- ✅ Start all services

### Step 2: Open Your Browser

Visit: **http://localhost:8000**

You'll be automatically redirected to the setup wizard!

### Step 3: Complete the Setup Wizard

The setup wizard will guide you through:

#### **Tab 1: Admin Account** (Required)
- Create your administrator username
- Set email address
- Choose a strong password

#### **Tab 2: Email Notifications** (Optional - can skip)
- Enable/disable email notifications
- Configure SMTP settings if you want email alerts
- Common providers (Gmail, Outlook, SendGrid) supported
- **You can skip this and configure later!**

#### **Tab 3: Retention Policy** (Has defaults)
- Set how long to keep backups (defaults provided)
- Daily: 7 days (default)
- Weekly: 4 weeks (default)
- Monthly: 12 months (default)
- Yearly: 5 years (default)

### That's It! 🎉

After completing the wizard, you'll be redirected to the API documentation page where you can start configuring your backups.

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

3. ✅ **All Services Started**
   - API server
   - Celery worker for background jobs
   - Celery beat for scheduled tasks
   - Flower for monitoring (optional)

## After Setup - Configure Via Web UI

Once setup is complete, configure everything through the API/UI:

### 1. Add KVM Host (Via API)

```powershell
# Login to get token
$response = Invoke-RestMethod -Uri "http://localhost:8000/api/v1/auth/login" `
  -Method Post `
  -ContentType "application/x-www-form-urlencoded" `
  -Body "username=admin&password=your-password"

$token = $response.access_token
$headers = @{
  "Authorization" = "Bearer $token"
  "Content-Type" = "application/json"
}

# Add your KVM host
$kvmHost = @{
  name = "my-kvm-server"
  uri = "qemu+ssh://user@192.168.1.100/system"
  auth_type = "ssh"
} | ConvertTo-Json

Invoke-RestMethod -Uri "http://localhost:8000/api/v1/kvm/hosts" `
  -Method Post -Headers $headers -Body $kvmHost
```

### 2. Add Storage Backend

```powershell
# Local storage
$storage = @{
  name = "local-backups"
  type = "local"
  config = @{
    base_path = "/backups/local"
  }
  threshold = 80
} | ConvertTo-Json

Invoke-RestMethod -Uri "http://localhost:8000/api/v1/storage" `
  -Method Post -Headers $headers -Body $storage

# Or S3/Backblaze B2
$s3storage = @{
  name = "backblaze"
  type = "s3"
  config = @{
    endpoint_url = "https://s3.us-west-002.backblazeb2.com"
    aws_access_key_id = "your-key"
    aws_secret_access_key = "your-secret"
    bucket_name = "my-backups"
    region = "us-west-002"
  }
  threshold = 80
} | ConvertTo-Json

Invoke-RestMethod -Uri "http://localhost:8000/api/v1/storage" `
  -Method Post -Headers $headers -Body $s3storage
```

### 3. Create Backup Schedule

```powershell
$schedule = @{
  name = "Daily VM Backup"
  source_type = "vm"
  source_id = 1
  schedule_type = "daily"
  cron_expression = "0 2 * * *"
  retention_config = @{
    daily = 7
    weekly = 4
    monthly = 12
    yearly = 5
  }
  storage_backend_id = 1
} | ConvertTo-Json

Invoke-RestMethod -Uri "http://localhost:8000/api/v1/schedules" `
  -Method Post -Headers $headers -Body $schedule
```

## Access Points

After setup:

- **API Documentation**: http://localhost:8000/docs
- **Celery Monitoring**: http://localhost:5555
- **Health Check**: http://localhost:8000/health

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
