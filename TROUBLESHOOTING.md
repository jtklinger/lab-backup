# Troubleshooting Guide

Common issues and their solutions for the Lab Backup System.

## Table of Contents
- [Cannot Access Web Interface](#cannot-access-web-interface)
- [Login Fails](#login-fails)
- [API Connection Errors](#api-connection-errors)
- [Docker Containers Not Starting](#docker-containers-not-starting)
- [SSL/TLS Certificate Issues](#ssltls-certificate-issues)
- [Port Conflicts](#port-conflicts)
- [Storage Backend Connection Failures](#storage-backend-connection-failures)
- [Backup Jobs Failing](#backup-jobs-failing)
- [Performance Issues](#performance-issues)
- [Database Issues](#database-issues)

---

## Cannot Access Web Interface

### Symptom
- Browser shows "Can't reach this page" or "Connection refused" when visiting http://localhost:3000

### Solutions

**1. Check if containers are running:**
```bash
docker-compose ps
```

**Expected output:**
```
lab-backup-frontend     Up      0.0.0.0:3000->80/tcp
lab-backup-api          Up      0.0.0.0:8000->8000/tcp, 0.0.0.0:8443->8443/tcp
```

**2. If frontend container is not running:**
```bash
# View logs
docker logs lab-backup-frontend

# Restart the container
docker-compose restart frontend
```

**3. If port 3000 is already in use:**
```bash
# Windows: Check what's using port 3000
netstat -ano | findstr :3000

# Stop the conflicting process or change the port in docker-compose.yml:
# ports:
#   - "3001:80"  # Change 3000 to 3001
```

**4. Check Docker Desktop is running (Windows/Mac):**
- Ensure Docker Desktop app is running
- Check the Docker icon in your system tray

---

## Login Fails

### Symptom
- "Invalid credentials" error when using default admin/admin
- "Network Error" when attempting to login
- Login button doesn't respond

### Solutions

**1. Network Error - SSL Certificate Not Accepted:**

The most common issue! The frontend can't connect to the API because you haven't accepted the SSL certificate.

**Fix:**
1. Open a new browser tab
2. Visit: `https://localhost:8443`
3. Click "Advanced" → "Accept the Risk and Continue" (wording varies by browser)
4. You should see: `{"status":"healthy"}`
5. Return to http://localhost:3000 and try logging in again

**2. Check API is responding:**
```bash
# Should return: {"status":"healthy"}
curl -k https://localhost:8443/health
```

**3. Check frontend can reach API:**

Open browser developer tools (F12), go to Console tab, and look for errors like:
```
net::ERR_CERT_AUTHORITY_INVALID
```

This confirms you need to accept the SSL certificate (see Solution #1).

**4. Verify default admin account exists:**
```bash
# Check API logs for admin account creation
docker logs lab-backup-api | grep -i "admin"
```

**5. Reset admin password (if needed):**
```bash
# Connect to database container
docker exec -it lab-backup-db psql -U labbackup -d lab_backup

# Run SQL to reset password to 'admin'
UPDATE users SET password_hash = '$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewY5NU7dqbSmVHLu' WHERE username = 'admin';
\q
```

---

## API Connection Errors

### Symptom
- Frontend shows errors like "Failed to fetch" or "Network Error"
- Browser console shows CORS errors
- "Unable to connect to API" messages

### Solutions

**1. Check API container health:**
```bash
docker-compose ps api

# Should show "healthy" status
# If unhealthy, check logs:
docker logs lab-backup-api --tail 50
```

**2. Verify API is responding:**
```bash
# HTTP endpoint
curl http://localhost:8000/health

# HTTPS endpoint (should work after accepting certificate)
curl -k https://localhost:8443/health
```

**3. Check frontend environment variable:**
```bash
# The frontend should be configured to use localhost:8443
docker exec lab-backup-frontend env | grep VITE_API_URL

# Should show: VITE_API_URL=https://localhost:8443
```

**4. If VITE_API_URL is wrong:**

Edit `docker-compose.yml`:
```yaml
frontend:
  environment:
    - VITE_API_URL=https://localhost:8443  # Must be localhost, not 'api'
```

Then rebuild:
```bash
docker-compose up -d --build frontend
```

---

## Docker Containers Not Starting

### Symptom
- Containers show "Exited" status
- `docker-compose up` fails with errors
- PostgreSQL or Redis containers failing

### Solutions

**1. Check container status:**
```bash
docker-compose ps
```

**2. View logs for failed containers:**
```bash
# Check all logs
docker-compose logs

# Check specific service
docker logs lab-backup-db
docker logs lab-backup-redis
docker logs lab-backup-api
```

**3. Common error: Port already in use**

```
Error starting userland proxy: listen tcp4 0.0.0.0:5432: bind: address already in use
```

**Fix:**
```bash
# Windows: Find what's using the port
netstat -ano | findstr :5432

# Option 1: Stop the conflicting service
# Option 2: Change the port in docker-compose.yml:
ports:
  - "5433:5432"  # Use different external port
```

**4. PostgreSQL data corruption:**
```bash
# Stop containers
docker-compose down

# Remove postgres volume (WARNING: Deletes all data!)
docker volume rm lab-backup_postgres_data

# Start fresh
docker-compose up -d
```

**5. Docker Desktop out of resources (Windows/Mac):**
- Open Docker Desktop → Settings → Resources
- Increase Memory to at least 4GB
- Increase CPU to at least 2 cores
- Click "Apply & Restart"

**6. Linux-specific mounts on Windows:**

If you see errors about `/var/run/libvirt` or `/var/run/podman`, these are Linux-specific paths that don't exist on Windows.

**Fix:** These should already be commented out in docker-compose.yml. If not:
```yaml
volumes:
  # - /var/run/libvirt:/var/run/libvirt  # Comment out on Windows
  # - /var/run/podman:/var/run/podman    # Comment out on Windows
```

---

## SSL/TLS Certificate Issues

### Symptom
- Browser warnings about untrusted certificate
- "NET::ERR_CERT_AUTHORITY_INVALID" errors
- Cannot access https://localhost:8443

### Solutions

**1. Accept self-signed certificate (most common):**

This is normal and expected! The system uses a self-signed certificate.

**Steps:**
1. Visit `https://localhost:8443` in your browser
2. Click "Advanced" or "More Information"
3. Click "Accept the Risk and Continue" or "Proceed to localhost (unsafe)"
4. You only need to do this once per browser

**2. Generate new certificate if corrupted:**
```bash
# The certificate is auto-generated on first start
# To regenerate, delete the volume and restart:
docker-compose down
docker volume rm lab-backup_ssl_certs
docker-compose up -d
```

**3. Use HTTP instead (less secure):**

If you're only using this in a lab environment, you can use the HTTP endpoint:

Update frontend `docker-compose.yml`:
```yaml
frontend:
  environment:
    - VITE_API_URL=http://localhost:8000  # HTTP instead of HTTPS
```

---

## Port Conflicts

### Symptom
- `Error: address already in use`
- Cannot start containers due to port conflicts

### Solutions

**Ports used by Lab Backup System:**
- 3000 - Frontend (Nginx)
- 8000 - API HTTP
- 8443 - API HTTPS
- 5432 - PostgreSQL
- 6379 - Redis
- 5555 - Flower (Celery monitoring)

**1. Find conflicting processes:**

**Windows:**
```powershell
netstat -ano | findstr :3000
netstat -ano | findstr :8000
netstat -ano | findstr :5432
```

**Linux/Mac:**
```bash
lsof -i :3000
lsof -i :8000
lsof -i :5432
```

**2. Change ports in docker-compose.yml:**

```yaml
frontend:
  ports:
    - "3001:80"  # Changed from 3000

api:
  ports:
    - "8001:8000"   # Changed HTTP port
    - "8444:8443"   # Changed HTTPS port

postgres:
  ports:
    - "5433:5432"  # Changed Postgres port
```

**3. Update frontend API URL if you change API ports:**
```yaml
frontend:
  environment:
    - VITE_API_URL=https://localhost:8444  # Match new HTTPS port
```

---

## Storage Backend Connection Failures

### Symptom
- "Connection test failed" when adding storage
- Backup jobs fail with storage errors
- "Permission denied" or "Access denied" errors

### Solutions

**1. Local Storage Issues:**

```bash
# Check permissions on backup volume
docker exec -it lab-backup-api ls -la /backups

# Should show ownership: labbackup:labbackup
# If not, restart the API container:
docker-compose restart api
```

**2. SMB/CIFS Storage Issues:**

**Common problems:**
- Wrong credentials
- Share not accessible from Docker network
- Firewall blocking SMB ports (445)

**Test connection from container:**
```bash
docker exec -it lab-backup-api bash
apt update && apt install -y smbclient
smbclient //server/share -U username
```

See [SMB-STORAGE.md](SMB-STORAGE.md) for detailed SMB setup.

**3. S3 Storage Issues:**

**Common problems:**
- Wrong access keys
- Wrong endpoint URL
- Bucket doesn't exist
- Bucket region mismatch

**Test with AWS CLI:**
```bash
docker exec -it lab-backup-api bash
pip install awscli
aws configure set aws_access_key_id YOUR_KEY
aws configure set aws_secret_access_key YOUR_SECRET
aws s3 ls --endpoint-url=https://your-endpoint s3://your-bucket
```

**4. Network connectivity:**
```bash
# Test DNS resolution
docker exec -it lab-backup-api ping storage-server.example.com

# Test port connectivity
docker exec -it lab-backup-api telnet storage-server 445
```

---

## Backup Jobs Failing

### Symptom
- Backup jobs stuck in "Pending" or "Running" status
- Jobs fail with errors
- VMs not backing up despite schedules

### Solutions

**1. Check Celery worker is running:**
```bash
docker-compose ps celery-worker

# Should show "Up" status
# If not, check logs:
docker logs lab-backup-worker --tail 50
```

**2. Check job logs:**

Via Web UI:
1. Go to "Jobs" page
2. Click on the failed job
3. View detailed error logs

Via CLI:
```bash
# View worker logs
docker logs lab-backup-worker -f
```

**3. Check KVM host connectivity:**
```bash
# Test SSH connection from container
docker exec -it lab-backup-api ssh user@kvm-host

# If connection fails, check SSH keys or password
```

**4. Check storage space:**

```bash
# Check backup volume space
docker exec -it lab-backup-api df -h /backups

# If full, clean up old backups or add more storage
```

**5. Restart workers:**
```bash
docker-compose restart celery-worker celery-beat
```

**6. Check Redis connectivity:**
```bash
# Redis is the message broker for Celery
docker exec -it lab-backup-redis redis-cli ping

# Should return: PONG
```

---

## Performance Issues

### Symptom
- Web interface is slow
- Backup jobs take too long
- High CPU or memory usage

### Solutions

**1. Check Docker resource allocation:**

Docker Desktop (Windows/Mac):
- Settings → Resources
- Allocate at least 4GB RAM
- Allocate at least 2 CPU cores

**2. Check container resource usage:**
```bash
docker stats
```

**3. Check database performance:**
```bash
# Connect to database
docker exec -it lab-backup-db psql -U labbackup -d lab_backup

# Check slow queries
SELECT query, calls, total_time, mean_time
FROM pg_stat_statements
ORDER BY mean_time DESC
LIMIT 10;
```

**4. Optimize backup performance:**
- Use incremental backups instead of full
- Enable compression (zstd is fastest)
- Use faster storage backends (local SSD > SMB > S3)
- Reduce number of concurrent backup jobs

**5. Check disk I/O:**
```bash
# Monitor disk usage during backups
docker stats lab-backup-worker
```

---

## Database Issues

### Symptom
- API fails to start with database errors
- "Connection refused" errors
- Migration failures

### Solutions

**1. Check PostgreSQL is running:**
```bash
docker-compose ps postgres

# Should show "Up" and "healthy"
```

**2. Check database logs:**
```bash
docker logs lab-backup-db --tail 50
```

**3. Test database connection:**
```bash
docker exec -it lab-backup-db psql -U labbackup -d lab_backup

# If successful, you'll see:
# lab_backup=#

# List tables:
\dt

# Exit:
\q
```

**4. Reset database (WARNING: Deletes all data!):**
```bash
docker-compose down
docker volume rm lab-backup_postgres_data
docker-compose up -d
```

**5. Run migrations manually:**
```bash
docker exec -it lab-backup-api alembic upgrade head
```

**6. Check database credentials:**
```bash
# View environment variables
docker exec lab-backup-api env | grep DATABASE_URL

# Should match postgres container settings
```

---

## Still Having Issues?

### Get Help

1. **Check container logs:**
   ```bash
   docker-compose logs
   ```

2. **Check specific service logs:**
   ```bash
   docker logs lab-backup-api --tail 100
   docker logs lab-backup-frontend --tail 100
   docker logs lab-backup-worker --tail 100
   ```

3. **Check service health:**
   ```bash
   docker-compose ps
   ```

4. **Verify configuration:**
   ```bash
   docker exec lab-backup-api env
   ```

5. **Create GitHub Issue:**
   - Visit: https://github.com/jtklinger/lab-backup/issues
   - Include:
     - Error messages
     - Container logs
     - Your docker-compose.yml (remove sensitive data)
     - Steps to reproduce
     - Operating system and Docker version

### Useful Commands

```bash
# Restart all services
docker-compose restart

# Rebuild and restart specific service
docker-compose up -d --build api

# View all logs in real-time
docker-compose logs -f

# Stop everything
docker-compose down

# Stop everything and remove volumes (DELETES DATA!)
docker-compose down -v

# Check Docker version
docker --version
docker-compose --version
```

---

## Prevention Tips

### Regular Maintenance

1. **Monitor disk space:**
   - Check backup storage regularly
   - Set up threshold alerts in the web UI

2. **Review logs periodically:**
   - Check for errors in System → Logs
   - Review failed jobs in Jobs page

3. **Keep Docker updated:**
   - Update Docker Desktop regularly
   - Update container images: `docker-compose pull`

4. **Test restores:**
   - Regularly test restoring backups
   - Verify backup integrity

5. **Monitor performance:**
   - Check Celery Flower: http://localhost:5555
   - Review task execution times
   - Optimize slow operations

### Security Best Practices

1. **Change default password immediately**
2. **Use strong passwords for all accounts**
3. **Keep SSL/TLS enabled (don't disable it)**
4. **Regularly update the system**
5. **Backup your database** (the system backs up VMs, but also backup its own database!)
6. **Review audit logs** for suspicious activity

---

## Additional Resources

- [GETTING-STARTED.md](GETTING-STARTED.md) - Comprehensive setup guide
- [README.md](README.md) - Full documentation
- [SETUP-WINDOWS.md](SETUP-WINDOWS.md) - Windows-specific instructions
- [ARCHITECTURE.md](ARCHITECTURE.md) - System architecture
- [docs/SSH_KEY_MANAGEMENT.md](docs/SSH_KEY_MANAGEMENT.md) - SSH key troubleshooting
- [docs/SSL_TLS_CONFIGURATION.md](docs/SSL_TLS_CONFIGURATION.md) - SSL/TLS setup
- [SMB-STORAGE.md](SMB-STORAGE.md) - SMB storage setup and troubleshooting
