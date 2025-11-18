# Disaster Recovery Guide

## Overview

This guide provides procedures for recovering the Lab Backup System from various disaster scenarios, including:
- Complete system failure (container destroyed)
- Database corruption
- Storage backend failure
- Encryption key loss

**Critical Components to Protect:**
1. PostgreSQL database (contains all metadata, configuration, encryption keys)
2. `.env` file (contains `SECRET_KEY` and master encryption key)
3. Storage backend credentials
4. VM/Container backup files

---

## Daily Automated Backups

The system automatically backs up the PostgreSQL database daily at 1:00 AM to all configured storage backends.

**Backup Details:**
- **Schedule**: Daily at 1:00 AM (Celery Beat task: `backup-database`)
- **Format**: PostgreSQL custom format (`.sql.gz` - compressed)
- **Encryption**: Encrypted if `BACKUP_ENCRYPTION_ENABLED=true`
- **Location**: `database-backups/database-backup-YYYYMMDD_HHMMSS.sql.gz[.encrypted]`
- **Retention**: Recommended 30 days minimum

**Verify Backups:**
```bash
# Verify latest backup
python scripts/verify-database-backup.py --storage <storage-name> --latest

# Verify all backups
python scripts/verify-database-backup.py --storage <storage-name> --all
```

---

## Encryption Key Management (NEW - Issue #7)

**CRITICAL**: Starting with the key management update, encryption keys are stored in the database and can be exported/imported separately for disaster recovery.

### Understanding the Key Architecture

The system uses **envelope encryption** with two levels of keys:

1. **Master KEK (Key Encryption Key)**
   - Stored in `.env` as `ENCRYPTION_KEY`
   - Encrypts all Data Encryption Keys (DEKs) in database
   - **NEVER changes** - changing this makes all keys unrecoverable
   - Must be backed up separately from database

2. **Data Encryption Keys (DEKs)**
   - Stored encrypted in the database (`encryption_keys` table)
   - Decrypted on-demand using Master KEK
   - Can be GLOBAL, per-storage-backend, per-VM, or per-container
   - Exported/imported for disaster recovery

### Exporting Encryption Keys

**When to Export:**
- After initial system setup
- After key rotation
- Before major system changes
- Monthly as part of DR testing

**How to Export:**

```bash
# Export all encryption keys to encrypted bundle
python scripts/export-keys.py --output /secure/keys-backup-$(date +%Y%m%d).encrypted

# You will be prompted for a passphrase
# Store this passphrase SEPARATELY from the encrypted bundle!

# Verify export was successful
python scripts/import-keys.py --input /secure/keys-backup-*.encrypted --verify-only
```

**Storage Recommendations:**
- **Encrypted Bundle**: Store in password manager, encrypted USB, or secure cloud storage
- **Passphrase**: Store in DIFFERENT password manager or write down and lock in safe
- **Never** store bundle and passphrase together
- Keep multiple copies in different physical locations

### Importing Encryption Keys (Disaster Recovery)

**Scenario**: Fresh container deployment, need to restore encryption keys

```bash
# After deploying fresh container and restoring database
python scripts/import-keys.py --input /secure/keys-backup-20251117.encrypted

# Enter the passphrase when prompted
# Keys will be re-encrypted with current Master KEK from .env
```

### Migration from Legacy .env-Only Encryption

If upgrading from older version that only used `ENCRYPTION_KEY` in .env:

```bash
# Run ONE TIME after upgrade
python scripts/migrate-keys-to-database.py

# This creates a GLOBAL key in database from .env
# All existing backups will be marked as using GLOBAL encryption
```

### Key Rotation

Rotating keys improves security by limiting exposure if a key is compromised:

```python
# Example: Rotate GLOBAL encryption key
from backend.services.key_management import KeyManagementService
from backend.models.encryption import EncryptionKeyType

async with AsyncSessionLocal() as db:
    key_service = KeyManagementService(db)
    old_key, new_key = await key_service.rotate_key(
        EncryptionKeyType.GLOBAL,
        reference_id=None
    )
    await db.commit()
    print(f"Rotated: v{old_key.key_version} -> v{new_key.key_version}")

# IMPORTANT: Export keys after rotation!
# python scripts/export-keys.py --output keys-backup-rotated.encrypted
```

**Note**: Old backups continue using old key version. Key rotation does NOT re-encrypt existing backups.

---

## Disaster Recovery Scenarios

### Scenario 1: Complete System Failure (Container Destroyed)

**Situation**: Docker/Podman container destroyed, no access to application or database.

**Recovery Steps:**

#### Step 1: Deploy Fresh Container
```bash
# Clone repository
git clone https://github.com/jtklinger/lab-backup.git
cd lab-backup

# Deploy with Docker Compose
docker-compose up -d --build
```

#### Step 2: Restore .env File
**Option A: From backup (recommended)**
```bash
# Restore .env from secure backup location
cp /secure/backup/.env .env
```

**Option B: Regenerate keys (⚠️ WARNING: Cannot decrypt old backups!)**
```bash
# Generate new keys
python generate-env.py

# ⚠️ This creates NEW encryption keys - existing backups will be unreadable!
```

#### Step 3: Restore Database
```bash
# List available database backups
python scripts/restore-database.py --storage <storage-name>

# Restore latest backup
python scripts/restore-database.py --storage <storage-name> --latest --yes

# Or restore specific backup by date
python scripts/restore-database.py --storage <storage-name> --date 2025-01-15
```

#### Step 4: Verify System
```bash
# Check database connection
docker-compose exec api python -c "from backend.models.base import engine; print('Database OK')"

# Access web UI
curl http://localhost:8000/health

# Verify backups are decryptable
python scripts/verify-database-backup.py --storage <storage-name> --latest
```

#### Step 5: Resume Operations
```bash
# Restart all services
docker-compose restart

# Verify Celery worker is running
docker-compose logs worker
```

---

### Scenario 2: Database Corruption

**Situation**: Database is corrupted but container is running.

**Recovery Steps:**

```bash
# 1. Stop application to prevent new writes
docker-compose stop api worker

# 2. Create safety backup (optional but recommended)
docker-compose exec postgres pg_dump -U labbackup -d lab_backup -Fc -f /tmp/safety-backup.sql.gz

# 3. Restore from backup
python scripts/restore-database.py --storage <storage-name> --latest

# 4. Restart services
docker-compose start api worker

# 5. Verify application functionality
curl http://localhost:8000/api/v1/vms
```

---

### Scenario 3: Encryption Key Loss

**Situation**: Master KEK lost (`.env` file destroyed), cannot decrypt database encryption keys.

**⚠️ CRITICAL**: If BOTH the Master KEK AND encrypted key bundle are lost, encrypted backups are **permanently unrecoverable**.

### Recovery Options

#### Option A: Encrypted Key Bundle Available (RECOMMENDED)

If you have the encrypted key bundle from `export-keys.py`:

```bash
# 1. Deploy fresh container with database restored
docker-compose up -d

# 2. Set NEW Master KEK in .env
# Generate new Fernet key:
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

# Add to .env:
ENCRYPTION_KEY=<new-key-from-above>

# 3. Import encryption keys from bundle
python scripts/import-keys.py --input /secure/keys-backup-20251117.encrypted

# Keys will be re-encrypted with NEW Master KEK
# All backups will now be decryptable!
```

**Success**: All backups can be decrypted because the bundle contained the DEKs.

#### Option B: .env Backup Available

If you backed up the `.env` file:

```bash
# 1. Restore .env file to container
cp /secure/backup/.env /path/to/lab-backup/.env

# 2. Restart container
docker-compose restart

# All encryption keys in database can now be decrypted
# All backups are immediately accessible
```

**Success**: Complete recovery with no data loss.

#### Option C: Both Master KEK and Bundle Lost (WORST CASE)

If BOTH `.env` and encrypted key bundle are lost:

- **Encrypted backups**: Permanently unrecoverable
- **Unencrypted backups**: Can still be restored
- **Database backups**: Usable for metadata only (keys are encrypted)
- **Must start fresh**: Generate new encryption keys

```bash
# Generate new encryption system
python scripts/migrate-keys-to-database.py

# All future backups will use new keys
# Old encrypted backups are unrecoverable
```

### Prevention Strategy (CRITICAL)

To avoid permanent data loss:

**1. Export Encryption Keys Monthly**
```bash
# Create encrypted bundle
python scripts/export-keys.py --output /secure/keys-$(date +%Y%m).encrypted

# Store in password manager or secure cloud storage
```

**2. Backup .env File**
```bash
# Backup to multiple locations
cp .env /secure/location1/.env.backup-$(date +%Y%m%d)
cp .env /secure/location2/.env.backup-$(date +%Y%m%d)

# Encrypt with GPG
gpg --encrypt --recipient your@email.com .env
mv .env.gpg /secure/location3/
```

**3. Test Recovery Quarterly**
```bash
# Verify encrypted bundle is valid
python scripts/import-keys.py \
  --input /secure/keys-backup.encrypted \
  --verify-only

# Verify .env backup is readable
cat /secure/location1/.env.backup | grep ENCRYPTION_KEY
```

**4. Store Credentials Separately**
- **Encrypted Bundle**: Password manager A, secure USB drive
- **Bundle Passphrase**: Password manager B, written down in safe
- **.env Backup**: Encrypted cloud storage, offline backup
- **Never** store all three together

---

### Scenario 4: Storage Backend Failure

**Situation**: Primary storage backend is unavailable or corrupted.

**Recovery Steps:**

```bash
# 1. Check if backups exist in other storage backends
python scripts/verify-database-backup.py --storage <alternate-storage> --all

# 2. Restore from alternate storage backend
python scripts/restore-database.py --storage <alternate-storage> --latest

# 3. Update storage backend configuration in UI
# Navigate to Settings → Storage Backends
# Disable failed backend, add new backend

# 4. Verify new storage backend
curl http://localhost:8000/api/v1/storage-backends/test/<backend-id>
```

---

## Manual Database Backup

In addition to automated backups, you can create manual backups:

```bash
# Create immediate database backup
docker-compose exec worker celery -A backend.worker call backend.worker.backup_database

# Or use pg_dump directly
docker-compose exec postgres pg_dump -U labbackup -d lab_backup -Fc -f /tmp/manual-backup-$(date +%Y%m%d).sql.gz

# Copy from container to host
docker cp lab-backup_postgres_1:/tmp/manual-backup-20250115.sql.gz ./
```

---

## Database Restore Options

### Restore from Local File
```bash
python scripts/restore-database.py --file /path/to/backup.sql.gz
```

### Restore from Storage Backend (Latest)
```bash
python scripts/restore-database.py --storage s3-backend --latest --yes
```

### Restore from Storage Backend (Specific Date)
```bash
python scripts/restore-database.py --storage local-storage --date 2025-01-15
```

### Restore Encrypted Backup
```bash
python scripts/restore-database.py --file /path/to/backup.sql.gz.encrypted --encrypted
```

### Skip Safety Backup (Faster but Risky)
```bash
python scripts/restore-database.py --storage s3-backend --latest --no-safety-backup --yes
```

---

## Verification and Testing

### Verify Database Backups Regularly
```bash
# Weekly verification of all backups
0 3 * * 0 python scripts/verify-database-backup.py --storage s3-backend --all

# Daily verification of latest backup
0 2 * * * python scripts/verify-database-backup.py --storage s3-backend --latest
```

### Test Disaster Recovery Procedure
**Recommended: Quarterly**

1. **Create test environment:**
   ```bash
   # Clone repository to test location
   git clone https://github.com/jtklinger/lab-backup.git /tmp/dr-test
   cd /tmp/dr-test

   # Use different ports to avoid conflicts
   sed -i 's/8000:8000/8001:8000/g' docker-compose.yml

   # Deploy
   docker-compose up -d
   ```

2. **Restore latest backup:**
   ```bash
   python scripts/restore-database.py --storage <storage> --latest --yes
   ```

3. **Verify functionality:**
   ```bash
   # Check all VMs are present
   curl http://localhost:8001/api/v1/vms

   # Check backups are listed
   curl http://localhost:8001/api/v1/backups

   # Verify encryption works
   python scripts/verify-database-backup.py --storage <storage> --latest
   ```

4. **Document results and cleanup:**
   ```bash
   # Cleanup test environment
   docker-compose down -v
   ```

---

## Retention Recommendations

### Database Backups
- **Daily**: Keep 30 days
- **Weekly**: Keep 12 weeks
- **Monthly**: Keep 12 months
- **Yearly**: Keep 7 years (compliance)

### VM Backups
- **As per backup schedule configuration**
- **Minimum 1 full backup per VM**

### Logs
- **Job logs**: Keep 90 days
- **Audit logs**: Keep 1 year (compliance)
- **System logs**: Keep 30 days

---

## Key Files to Backup

### Critical Files (MUST backup)
1. `.env` - Contains all secrets and encryption keys
2. PostgreSQL database - All metadata and configuration
3. Storage backend credentials (if not in database)

### Important Files (Should backup)
1. `docker-compose.yml` - Deployment configuration
2. Custom configuration files
3. SSL certificates (`server.crt`, `server.key`)

### Optional Files
1. `frontend/.env.production` - Frontend configuration
2. Custom scripts in `scripts/`
3. Documentation in `docs/`

---

## Emergency Contacts and Escalation

### When to Escalate
1. Cannot restore database from any backup
2. All storage backends failed
3. Encryption keys lost and backups are encrypted
4. Data corruption affecting multiple VMs

### Escalation Procedure
1. Document the issue (what failed, when, symptoms)
2. Gather logs:
   ```bash
   docker-compose logs > dr-incident-$(date +%Y%m%d).log
   ```
3. Contact system administrator
4. If needed, contact backup storage provider support

---

## Recovery Time Objectives (RTO)

| Scenario | Target RTO | Actual Steps |
|----------|-----------|--------------|
| Database restore from local file | 15 minutes | 1. Stop services (1 min)<br>2. Restore database (10 min)<br>3. Start services (4 min) |
| Database restore from S3 | 30 minutes | 1. Download backup (15 min)<br>2. Restore (15 min) |
| Complete system rebuild | 2 hours | 1. Deploy container (30 min)<br>2. Restore database (30 min)<br>3. Verify and test (1 hour) |

---

## Post-Recovery Checklist

After successful disaster recovery:

- [ ] All services are running (`docker-compose ps`)
- [ ] Database is accessible (`psql -U labbackup -d lab_backup -c "\dt"`)
- [ ] Web UI is accessible (http://localhost:8000)
- [ ] API responds to requests (`curl http://localhost:8000/health`)
- [ ] VMs are listed correctly (`curl http://localhost:8000/api/v1/vms`)
- [ ] Backups can be created (`curl -X POST http://localhost:8000/api/v1/backups`)
- [ ] Encryption works (verify backup can be decrypted)
- [ ] Storage backends are accessible
- [ ] Celery worker is processing tasks (`docker-compose logs worker`)
- [ ] Scheduled backups are running (check Celery Beat logs)
- [ ] Update incident log with resolution details

---

## Prevention Best Practices

1. **Automate backups** - Daily database backups (already configured)
2. **Test restores regularly** - Monthly verification
3. **Multiple storage backends** - Don't rely on single storage
4. **Backup .env file** - Store in password manager
5. **Monitor backup jobs** - Alert on failures
6. **Document changes** - Keep recovery procedures updated
7. **Version control** - All configuration in Git

---

## Future Enhancements (Planned)

As per GitHub Issues:

- **Issue #6**: Automated backup verification framework
- **Issue #7**: Encryption key export/import mechanism
- **Issue #8**: Compliance tracking and reporting
- **Issue #13**: Immutable backups (ransomware protection)

---

## Appendix: Quick Reference Commands

```bash
# Backup database manually
docker-compose exec worker celery -A backend.worker call backend.worker.backup_database

# Restore from latest backup
python scripts/restore-database.py --storage <name> --latest --yes

# Verify backup
python scripts/verify-database-backup.py --storage <name> --latest

# Check backup job status
curl http://localhost:8000/api/v1/jobs?type=BACKUP

# List database backups in storage
python scripts/verify-database-backup.py --storage <name>

# Test database connection
docker-compose exec postgres psql -U labbackup -d lab_backup -c "SELECT COUNT(*) FROM backups;"

# View recent logs
docker-compose logs --tail=100 --follow worker
```

---

**Last Updated**: 2025-01-17
**Version**: 1.0
**Maintained By**: System Administrator
