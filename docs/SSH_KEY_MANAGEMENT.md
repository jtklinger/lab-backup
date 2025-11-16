# SSH Key Management for KVM Hosts

The Lab Backup System provides comprehensive SSH key management for authenticating to KVM/libvirt hosts. SSH keys can be managed through the web interface, eliminating the need for manual SSH configuration on each host.

## Table of Contents

- [Overview](#overview)
- [Authentication Methods](#authentication-methods)
- [Web UI Management](#web-ui-management)
  - [During Host Creation](#during-host-creation)
  - [Managing Existing Host Keys](#managing-existing-host-keys)
  - [Uploading Existing Keys](#uploading-existing-keys)
  - [Generating New Keys](#generating-new-keys)
  - [Viewing Public Keys](#viewing-public-keys)
  - [Deleting Keys](#deleting-keys)
- [API Usage](#api-usage)
- [Security](#security)
- [Troubleshooting](#troubleshooting)

## Overview

Lab Backup System supports two SSH authentication methods for KVM hosts:

1. **Default SSH Keys** (Phase 1) - Uses SSH keys from the host's `~/.ssh` directory (mounted into container)
2. **Database-Stored Keys** (Phase 2) - Manages SSH keys through web UI with encrypted database storage

When connecting to a KVM host, the system:
1. Checks if a database-stored SSH key exists for the host
2. If yes: Decrypts and uses the database key
3. If no: Falls back to default SSH keys from `~/.ssh`

This provides flexibility - you can use existing SSH infrastructure or manage keys through the web interface.

## Authentication Methods

### Method 1: Default SSH Keys (Mounted Directory)

**Advantages:**
- Use existing SSH infrastructure
- No additional configuration needed if keys already set up
- Familiar workflow for system administrators

**How it works:**
- The `~/.ssh` directory from the Docker host is mounted into the container
- SSH client uses keys from this directory automatically
- Host key verification uses `~/.ssh/known_hosts`

**Setup:**
1. Ensure SSH key exists on Docker host: `~/.ssh/id_ed25519` or `~/.ssh/id_rsa`
2. Add public key to target KVM host: `ssh-copy-id user@kvm-host`
3. Create KVM host in web UI with URI: `qemu+ssh://user@kvm-host/system`

### Method 2: Database-Stored Keys (Web UI Management)

**Advantages:**
- Centralized key management through web interface
- No need to access Docker host filesystem
- Keys encrypted at rest using application secret key
- Per-host key isolation
- Track key usage with last_used timestamps

**How it works:**
1. SSH keys stored in database with encrypted private keys
2. When connecting, system decrypts key and writes to temporary file
3. SSH config updated to use specific key for that host
4. Automatic cleanup after connection

**Security:**
- Private keys encrypted using Fernet (AES-128)
- Encryption key derived from `SECRET_KEY` using PBKDF2
- Keys never stored in plaintext
- Automatic secure deletion of temporary key files

## Web UI Management

### During Host Creation

When adding a new KVM host, you can configure SSH authentication directly:

1. Click **"+ Add KVM Host"** button
2. Fill in host details (Name, URI)
3. In **"SSH Authentication (Optional)"** section, choose one of:

**Option A: Use default SSH keys from ~/.ssh** (default)
- Uses mounted SSH keys from Docker host
- No additional configuration needed

**Option B: Upload existing SSH key**
1. Select key type (ed25519, RSA, ECDSA)
2. Paste your private key in PEM format:
   ```
   -----BEGIN OPENSSH PRIVATE KEY-----
   b3BlbnNzaC1rZXktdjEAAAAABG5vbmUAAAAEbm9uZQAAAA...
   -----END OPENSSH PRIVATE KEY-----
   ```
3. Paste corresponding public key:
   ```
   ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIGx... user@host
   ```
4. Click **Confirm**

**Option C: Generate new SSH key**
1. Select key type:
   - **ed25519** (Recommended) - Faster, more secure, smaller keys
   - **RSA** - Compatible with older systems
2. If RSA: Choose key size (2048 or 4096 bits)
3. Click **Confirm**
4. System generates key pair and displays public key
5. Copy public key and add to target host's `~/.ssh/authorized_keys`

**Example - Generate ed25519 key during host creation:**
```
Name: kvm-host-1
URI: qemu+ssh://root@192.168.1.100/system
SSH Authentication: Generate new SSH key
Key Type: ed25519
```

After creation, you'll see:
```
✓ KVM host added and SSH key generated

Public Key (ed25519):
ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAI...

Add this public key to ~/.ssh/authorized_keys on the target host
```

### Managing Existing Host Keys

For hosts already added, manage SSH keys through the KVM Hosts page:

1. Navigate to **KVM Hosts** in sidebar
2. Locate the host in the table
3. Click **"🔑 SSH Keys"** button
4. The SSH Keys dialog shows:
   - List of existing keys (if any)
   - Key type, creation date, last used timestamp
   - Options to add new keys

### Uploading Existing Keys

To upload an existing SSH key pair:

1. Click **"🔑 SSH Keys"** on the KVM host
2. Click **"📤 Upload Existing Key"**
3. Fill in the form:
   - **Key Type**: Select ed25519, RSA, or ECDSA
   - **Private Key**: Paste your SSH private key
   - **Public Key**: Paste your SSH public key
4. Click **Confirm**

**Security Note:** The private key is encrypted before storage. Never share private keys through insecure channels.

**Example - Upload existing ed25519 key:**

Private Key:
```
-----BEGIN OPENSSH PRIVATE KEY-----
b3BlbnNzaC1rZXktdjEAAAAABG5vbmUAAAAEbm9uZQAAAAAAAAABAAAAMwAAAAtzc2gtZW
QyNTUxOQAAACBsWvv0rXYbLqGmHHPEL6L6YHvbNPABPEQzLs+bEZBx3QAAAJh7Ps3kez7N
5AAAAAtzc2gtZWQyNTUxOQAAACBsWvv0rXYbLqGmHHPEL6L6YHvbNPABPEQzLs+bEZBx3Q
AAAECWvN3G8x...
-----END OPENSSH PRIVATE KEY-----
```

Public Key:
```
ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIGxa+/Stdhsuoaacc8QvovpAe9s0A0E8RDMuz5sRkHHd user@workstation
```

### Generating New Keys

To generate a new SSH key pair:

1. Click **"🔑 SSH Keys"** on the KVM host
2. Click **"✨ Generate New Key"**
3. Select key type:
   - **ed25519** (Recommended)
     - Faster performance
     - Better security (256-bit)
     - Smaller key size
     - Supported by OpenSSH 6.5+ (2014)
   - **RSA**
     - Maximum compatibility
     - Choose 4096 bits for best security
     - Larger key size
4. Click **Confirm**
5. Copy the displayed public key
6. Add to target host's authorized_keys:
   ```bash
   # On the target KVM host
   echo "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5..." >> ~/.ssh/authorized_keys
   chmod 600 ~/.ssh/authorized_keys
   ```

**Key Type Recommendations:**

| Scenario | Recommended Type | Key Size |
|----------|-----------------|----------|
| Modern systems (OpenSSH 6.5+) | **ed25519** | N/A (fixed 256-bit) |
| Legacy systems | RSA | 4096 bits |
| Maximum compatibility | RSA | 2048 bits (minimum) |

### Viewing Public Keys

To view or copy a public key:

1. Click **"🔑 SSH Keys"** on the KVM host
2. In the keys table, click **"📋 Public Key"**
3. The public key is displayed in a text area
4. Click **"📋 Copy to Clipboard"**
5. Paste into target host's `~/.ssh/authorized_keys`

**Installation on target host:**
```bash
# SSH into the target KVM host
ssh user@kvm-host

# Add the public key to authorized_keys
nano ~/.ssh/authorized_keys
# Paste the public key on a new line

# Set proper permissions
chmod 600 ~/.ssh/authorized_keys
chmod 700 ~/.ssh

# Verify
cat ~/.ssh/authorized_keys
```

### Deleting Keys

To delete an SSH key:

1. Click **"🔑 SSH Keys"** on the KVM host
2. In the keys table, click **"Delete"** for the key you want to remove
3. Confirm the deletion

**Important Notes:**
- Deleting a key is permanent
- The system will fall back to default SSH keys from `~/.ssh`
- If you delete the last database key, ensure default keys are configured
- Consider testing connectivity before deleting active keys

## API Usage

All SSH key management features are available via REST API.

### List SSH Keys for a Host

```bash
GET /api/v1/kvm/hosts/{host_id}/ssh-keys

curl http://localhost:8000/api/v1/kvm/hosts/1/ssh-keys \
  -H "Authorization: Bearer <token>"
```

**Response:**
```json
[
  {
    "id": 1,
    "kvm_host_id": 1,
    "public_key": "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIGxa+/Stdhsuoaacc8Qvo...",
    "key_type": "ed25519",
    "created_at": "2025-11-15T16:30:00Z",
    "last_used": "2025-11-16T10:15:00Z"
  }
]
```

### Upload SSH Key

```bash
POST /api/v1/kvm/hosts/{host_id}/ssh-keys

curl -X POST http://localhost:8000/api/v1/kvm/hosts/1/ssh-keys \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "key_type": "ed25519",
    "private_key": "-----BEGIN OPENSSH PRIVATE KEY-----\n...\n-----END OPENSSH PRIVATE KEY-----",
    "public_key": "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5... user@host"
  }'
```

**Response:**
```json
{
  "id": 1,
  "kvm_host_id": 1,
  "public_key": "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5...",
  "key_type": "ed25519",
  "created_at": "2025-11-15T16:30:00Z",
  "last_used": null
}
```

### Generate SSH Key

```bash
POST /api/v1/kvm/hosts/{host_id}/ssh-keys/generate

# Generate ed25519 key (recommended)
curl -X POST http://localhost:8000/api/v1/kvm/hosts/1/ssh-keys/generate \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "key_type": "ed25519"
  }'

# Generate RSA key with specific size
curl -X POST http://localhost:8000/api/v1/kvm/hosts/1/ssh-keys/generate \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "key_type": "rsa",
    "key_size": 4096
  }'
```

**Response:**
```json
{
  "id": 2,
  "kvm_host_id": 1,
  "public_key": "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAINvX...",
  "key_type": "ed25519",
  "created_at": "2025-11-15T16:35:00Z",
  "last_used": null
}
```

### Get Public Key

```bash
GET /api/v1/kvm/hosts/{host_id}/ssh-keys/{key_id}/public

curl http://localhost:8000/api/v1/kvm/hosts/1/ssh-keys/2/public \
  -H "Authorization: Bearer <token>"
```

**Response:**
```json
{
  "public_key": "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAINvX...",
  "key_type": "ed25519",
  "instructions": "Add this public key to ~/.ssh/authorized_keys on the target host"
}
```

### Delete SSH Key

```bash
DELETE /api/v1/kvm/hosts/{host_id}/ssh-keys/{key_id}

curl -X DELETE http://localhost:8000/api/v1/kvm/hosts/1/ssh-keys/2 \
  -H "Authorization: Bearer <token>"
```

**Response:** 204 No Content

## Security

### Encryption

**Private Key Encryption:**
- Algorithm: Fernet (symmetric encryption, AES-128 in CBC mode)
- Key Derivation: PBKDF2-HMAC-SHA256
  - 100,000 iterations
  - Fixed salt: `ssh_key_encryption_salt_v1`
  - Master key: Application `SECRET_KEY`
- Storage: Base64-encoded encrypted data in PostgreSQL TEXT column

**Decryption Flow:**
1. Retrieve encrypted private key from database
2. Derive Fernet key from `SECRET_KEY` using PBKDF2
3. Decrypt private key using Fernet
4. Write to temporary file with 0600 permissions
5. Use for SSH connection
6. Securely delete temporary file

### Key Storage

**Database Schema:**
```sql
CREATE TABLE ssh_keys (
    id SERIAL PRIMARY KEY,
    kvm_host_id INTEGER NOT NULL REFERENCES kvm_hosts(id) ON DELETE CASCADE,
    private_key_encrypted TEXT NOT NULL,  -- Fernet-encrypted, base64-encoded
    public_key TEXT NOT NULL,
    key_type VARCHAR(50) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    last_used TIMESTAMP NULL
);
```

**Filesystem Storage (Temporary):**
- Location: `~/.ssh/kvm_host_{id}_key`
- Permissions: 0600 (owner read/write only)
- Lifecycle: Written before connection, deleted after use
- SSH Config: Updated to use specific key per host

### Best Practices

**DO:**
- ✅ Use ed25519 keys for new hosts (unless compatibility required)
- ✅ Use 4096-bit RSA if ed25519 not supported
- ✅ Rotate keys periodically (e.g., annually)
- ✅ Delete unused keys
- ✅ Use strong `SECRET_KEY` (32+ random bytes)
- ✅ Limit access to Operator role or higher
- ✅ Monitor key usage via `last_used` timestamps
- ✅ Keep database backups encrypted

**DON'T:**
- ❌ Share private keys via email or chat
- ❌ Use 1024-bit or 2048-bit RSA keys (weak)
- ❌ Reuse the same key across multiple hosts (isolation)
- ❌ Store private keys in version control
- ❌ Expose `SECRET_KEY` environment variable
- ❌ Grant Viewer role access to SSH key management

### Access Control

SSH key management requires **Operator** role or higher:

| Operation | Required Role |
|-----------|--------------|
| View public keys | Viewer |
| List SSH keys | Viewer |
| Upload SSH key | Operator |
| Generate SSH key | Operator |
| Delete SSH key | Operator |

## Troubleshooting

### Connection Fails After Adding Key

**Symptom:** KVM host shows "Failed to connect" after uploading/generating SSH key

**Possible Causes:**
1. Public key not added to target host's `authorized_keys`
2. Incorrect permissions on target host
3. Wrong username in URI
4. SSH service not running on target

**Solution:**
```bash
# On target KVM host
# 1. Verify authorized_keys exists and has correct permissions
ls -la ~/.ssh/authorized_keys
chmod 600 ~/.ssh/authorized_keys

# 2. Verify public key is present
cat ~/.ssh/authorized_keys | grep "ssh-ed25519"

# 3. Verify SSH service is running
systemctl status sshd

# 4. Test SSH connection manually
ssh -i ~/.ssh/kvm_host_1_key user@kvm-host
```

### Import Error on API Startup

**Symptom:** SSH key endpoints return 404, logs show import errors

**Cause:** Incorrect import statement for `settings`

**Solution:**
```python
# Correct:
from backend.core.config import settings

# Incorrect:
from backend.core.config import get_settings  # Function doesn't exist
```

**Verification:**
```bash
docker exec lab-backup-api python3 -c "from backend.api.v1 import kvm; print('✓ Import successful')"
```

### Keys Not Listed in Dialog

**Symptom:** "No SSH keys configured" shown but keys were added

**Possible Causes:**
1. Database not migrated
2. Keys added for different host
3. Database connection issue

**Solution:**
```bash
# Check migration status
docker exec lab-backup-api alembic current

# Expected: 35ddaf609ade (add_ssh_keys_table)

# If migration pending:
docker-compose restart api

# Verify table exists
docker exec lab-backup-db psql -U labbackup -d lab_backup -c "\dt ssh_keys"
```

### Cannot Delete Last Key

**Symptom:** Warning about falling back to default keys

**Explanation:** This is expected behavior. When you delete the last database-stored key, the system automatically falls back to using default SSH keys from `~/.ssh`.

**Action Required:**
- Ensure default SSH keys are configured on Docker host
- Or keep at least one database key active

### Permission Denied Errors

**Symptom:** SSH connection fails with "Permission denied (publickey)"

**Debug:**
```bash
# Enable SSH debug logging in KVM URI
# Change: qemu+ssh://user@host/system
# To: qemu+ssh://user@host/system?keyfile=/root/.ssh/kvm_host_1_key

# Check container SSH config
docker exec lab-backup-api cat /root/.ssh/config

# Verify key file exists with correct permissions
docker exec lab-backup-api ls -la /root/.ssh/kvm_host_*
```

### Database Key Not Used

**Symptom:** System uses default keys even though database key exists

**Cause:** SSH key setup may have failed silently

**Solution:**
```bash
# Check API logs for SSH setup errors
docker-compose logs api | grep "SSH key"

# Expected output:
# ✅ Wrote database SSH key to /root/.ssh/kvm_host_1_key
# ✅ Updated SSH config for host kvm-host-1

# If errors, check:
# 1. Database connection
# 2. Encryption key (SECRET_KEY)
# 3. KVM host ID matches
```

## Migration from Default Keys

If you're currently using default SSH keys and want to migrate to database-stored keys:

### Option 1: Upload Existing Keys

1. Locate your current SSH key on Docker host:
   ```bash
   cat ~/.ssh/id_ed25519      # Private key
   cat ~/.ssh/id_ed25519.pub  # Public key
   ```

2. Upload via web UI:
   - Click **🔑 SSH Keys** on the KVM host
   - Click **📤 Upload Existing Key**
   - Paste private and public keys
   - Click **Confirm**

3. Test connection:
   - Click **Refresh** on the KVM host
   - Should connect successfully using database key

4. (Optional) Remove from `~/.ssh` after confirming it works

### Option 2: Generate New Keys

1. Generate via web UI:
   - Click **🔑 SSH Keys** on the KVM host
   - Click **✨ Generate New Key**
   - Select **ed25519**
   - Click **Confirm**

2. Copy public key to target host:
   ```bash
   ssh user@kvm-host
   nano ~/.ssh/authorized_keys
   # Paste the new public key
   chmod 600 ~/.ssh/authorized_keys
   ```

3. Test connection:
   - Click **Refresh** on the KVM host
   - Should connect using new database key

4. (Optional) Remove old keys after migration complete

### Rollback

If you need to revert to default keys:

1. Delete all database keys for the host
2. System automatically falls back to `~/.ssh` keys
3. Ensure `~/.ssh` keys are still configured on Docker host

## Related Documentation

- [ARCHITECTURE.md](../ARCHITECTURE.md) - System architecture and components
- [SSL_TLS_CONFIGURATION.md](SSL_TLS_CONFIGURATION.md) - SSL/TLS certificate management
- [README.md](../README.md) - General system documentation

## Support

For issues or questions:
1. Check logs: `docker-compose logs api`
2. Verify migration: `docker exec lab-backup-api alembic current`
3. Test import: `docker exec lab-backup-api python3 -c "from backend.api.v1 import kvm"`
4. Review [Troubleshooting](#troubleshooting) section above
