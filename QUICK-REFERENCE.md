# Lab Backup System - Quick Reference

## Default Credentials

**After running `docker-compose up -d`, a default admin account is automatically created:**

- **Username:** `admin`
- **Password:** `admin`
- **Email:** `admin@localhost`

⚠️ **SECURITY WARNING:** These are default credentials for convenience. **Change the password immediately** after first login!

## What is the SECRET_KEY?

The `SECRET_KEY` is used for:

1. **JWT Token Signing** - Signs authentication tokens so they can't be forged
2. **Session Security** - Encrypts session data
3. **Data Integrity** - Ensures tokens and sessions haven't been tampered with

### How It Works

When you login:
1. Your credentials are verified against the database
2. A JWT token is generated and **signed** with the SECRET_KEY
3. This token is sent to you and used for all future API calls
4. The server verifies the token signature using the same SECRET_KEY

**If someone knows your SECRET_KEY, they can:**
- Create fake admin tokens
- Impersonate any user
- Gain full access to your system

### Default Behavior

The system **auto-generates** a secure random SECRET_KEY on first run:

```bash
# Automatically done by docker/entrypoint.sh
python3 generate-env.py  # Creates .env with random 32-character key
```

### Manual Generation (If Needed)

If you need to generate a new key manually:

```bash
# Using Python
python3 -c "import secrets; print(secrets.token_urlsafe(32))"

# Using PowerShell (Windows)
$bytes = New-Object byte[] 32
[Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
[Convert]::ToBase64String($bytes)

# Using OpenSSL (Linux/Mac)
openssl rand -base64 32
```

Then update your `.env` file:
```bash
SECRET_KEY=your-new-random-key-here
```

And restart:
```bash
docker-compose restart api
```

## Changing the Admin Password

### Option 1: Via API

```powershell
# Login
$response = Invoke-RestMethod -Uri "http://localhost:8000/api/v1/auth/login" `
  -Method Post -ContentType "application/x-www-form-urlencoded" `
  -Body "username=admin&password=admin"

$token = $response.access_token

# Update password (create new endpoint for this)
# TODO: Add password change endpoint
```

### Option 2: Via Database

```bash
# Connect to container
docker-compose exec api python3

# Then run:
from backend.models.base import SyncSessionLocal
from backend.models.user import User
from backend.core.security import get_password_hash

db = SyncSessionLocal()
admin = db.query(User).filter_by(username='admin').first()
admin.password_hash = get_password_hash('your-new-secure-password')
db.commit()
print("Password updated!")
```

### Option 3: Create New Admin and Delete Default

```powershell
# Login as default admin
$response = Invoke-RestMethod -Uri "http://localhost:8000/api/v1/auth/login" `
  -Method Post -ContentType "application/x-www-form-urlencoded" `
  -Body "username=admin&password=admin"

$token = $response.access_token
$headers = @{"Authorization"="Bearer $token"; "Content-Type"="application/json"}

# Create new admin user
$newAdmin = @{
  username = "yourusername"
  email = "you@example.com"
  password = "your-secure-password"
  role = "admin"
} | ConvertTo-Json

Invoke-RestMethod -Uri "http://localhost:8000/api/v1/auth/register" `
  -Method Post -Headers $headers -Body $newAdmin

# Login as new admin and delete default admin user
# (User deletion endpoint would need to be added)
```

## First-Time Setup Checklist

After running `docker-compose up -d`:

- [ ] ✅ System starts automatically
- [ ] ✅ Database migrations run
- [ ] ✅ Default admin user created (admin/admin)
- [ ] ✅ Random SECRET_KEY generated
- [ ] ⚠️ **Login and verify system works**
- [ ] ⚠️ **Change default admin password**
- [ ] ⚠️ **Verify SECRET_KEY is random (check logs)**
- [ ] ✅ Add KVM hosts
- [ ] ✅ Add storage backends
- [ ] ✅ Create backup schedules
- [ ] ✅ Test a backup

## Security Best Practices

1. **Change Default Credentials** - First thing after installation
2. **Use Strong Passwords** - Minimum 12 characters with mixed case, numbers, symbols
3. **Secure the SECRET_KEY** - Never commit it to git, never share it
4. **Use HTTPS in Production** - Put nginx/traefik in front with SSL certificate
5. **Restrict Network Access** - Use firewall rules to limit who can access port 8000
6. **Regular Updates** - Keep Docker images and dependencies updated
7. **Backup Your Database** - The PostgreSQL database contains all your configuration
8. **Monitor Logs** - Check for suspicious login attempts

## Troubleshooting

### "Invalid token" errors after restart

**Cause:** The SECRET_KEY changed between restarts.

**Solution:** The SECRET_KEY should persist in the `.env` file. If it keeps changing:
```bash
# Check if .env file exists
docker-compose exec api ls -la /app/.env

# Verify SECRET_KEY persists
docker-compose exec api cat /app/.env | grep SECRET_KEY

# If missing, the .env file isn't being saved properly
# Make sure you're not mounting a volume that's read-only
```

### Can't login with admin/admin

**Check the logs:**
```bash
docker-compose logs api | grep "Default admin user"
```

You should see:
```
✅ Default admin user created!
   Username: admin
   Password: admin
```

If you see "✅ Admin user already exists", the default user wasn't created because an admin already exists.

### Need to reset everything

```bash
# Stop and remove all data
docker-compose down -v

# Start fresh
docker-compose up -d

# Default admin/admin will be recreated
```

## Quick Start Summary

```powershell
# 1. Start everything
docker-compose up -d

# 2. Wait for startup (check logs)
docker-compose logs -f api

# 3. Login (default credentials)
$response = Invoke-RestMethod -Uri "http://localhost:8000/api/v1/auth/login" `
  -Method Post -ContentType "application/x-www-form-urlencoded" `
  -Body "username=admin&password=admin"

$token = $response.access_token

# 4. Start configuring
# See SETUP-WINDOWS.md for detailed examples
```

That's it! No manual configuration needed! 🎉
