# Backup Verification API Documentation

## Overview

The Backup Verification API provides automated testing of backup integrity through isolated test pod restoration. This endpoint allows administrators to verify that backups can be successfully restored before they're needed for disaster recovery.

**Base URL**: `http://localhost:8000/api/v1/backups`

**Authentication**: Required (Bearer token or session cookie)

**Authorization**: Requires `OPERATOR` role or higher

---

## Endpoints

### 1. Trigger Backup Verification

Initiates an automated verification of a backup by restoring it to an isolated test environment.

**Endpoint**: `POST /api/v1/backups/{backup_id}/verify`

**Method**: `POST`

**URL Parameters**:
- `backup_id` (integer, required): ID of the backup to verify

**Request Headers**:
```http
Authorization: Bearer <token>
Content-Type: application/json
```

**Request Body**: None

**Response**: `202 Accepted`

```json
{
  "message": "Backup verification job queued successfully",
  "backup_id": 123,
  "task_id": "a7f3c8e9-4b21-4d5a-9f2e-1c8d7e3a9b4f",
  "status": "Verification in progress - check backup verification_status for results"
}
```

**Response Fields**:
- `message` (string): Human-readable status message
- `backup_id` (integer): ID of backup being verified
- `task_id` (string): Celery task ID for monitoring progress
- `status` (string): Current status description

**Error Responses**:

| Status Code | Description | Response Example |
|-------------|-------------|------------------|
| `400 Bad Request` | Backup is not in COMPLETED status | `{"detail": "Cannot verify backup with status: pending. Only completed backups can be verified."}` |
| `401 Unauthorized` | Missing or invalid authentication | `{"detail": "Not authenticated"}` |
| `403 Forbidden` | Insufficient permissions | `{"detail": "Insufficient permissions"}` |
| `404 Not Found` | Backup does not exist | `{"detail": "Backup not found"}` |
| `500 Internal Server Error` | Server error during verification | `{"detail": "Internal server error"}` |

---

### 2. Get Backup Details (with Verification Status)

Retrieve backup details including verification results.

**Endpoint**: `GET /api/v1/backups/{backup_id}`

**Method**: `GET`

**URL Parameters**:
- `backup_id` (integer, required): ID of the backup

**Request Headers**:
```http
Authorization: Bearer <token>
```

**Response**: `200 OK`

```json
{
  "id": 123,
  "schedule_id": 5,
  "source_name": "vm-webserver",
  "source_type": "vm",
  "backup_type": "daily",
  "backup_mode": "full",
  "parent_backup_id": null,
  "status": "completed",
  "size": 5368709120,
  "compressed_size": 2147483648,
  "storage_path": "vms/vm-webserver/vm-webserver-20251117_120000.tar.gz.encrypted",
  "started_at": "2025-11-17T12:00:00Z",
  "completed_at": "2025-11-17T12:15:00Z",
  "expires_at": "2025-12-17T12:00:00Z",
  "verified": true,
  "verification_date": "2025-11-17T14:30:00Z",
  "verification_status": "passed",
  "verification_error": null,
  "verified_table_count": 47,
  "verified_size_bytes": 2456789123,
  "verification_duration_seconds": 45
}
```

**Verification Fields**:
- `verified` (boolean): Whether backup has been verified
- `verification_date` (datetime|null): When verification last ran
- `verification_status` (string|null): `"passed"` or `"failed"`
- `verification_error` (string|null): Error message if verification failed
- `verified_table_count` (integer|null): Number of tables restored in test
- `verified_size_bytes` (integer|null): Size of restored database in bytes
- `verification_duration_seconds` (integer|null): How long verification took

---

### 3. List Backups (with Verification Filter)

List backups with optional filtering by verification status.

**Endpoint**: `GET /api/v1/backups`

**Method**: `GET`

**Query Parameters**:
- `status` (string, optional): Filter by backup status (`pending`, `running`, `completed`, `failed`, `cancelled`)
- `limit` (integer, optional): Maximum number of results (default: 100)
- `offset` (integer, optional): Number of results to skip (default: 0)

**Request Headers**:
```http
Authorization: Bearer <token>
```

**Response**: `200 OK`

```json
[
  {
    "id": 123,
    "source_name": "vm-webserver",
    "status": "completed",
    "verified": true,
    "verification_status": "passed",
    "verification_date": "2025-11-17T14:30:00Z",
    ...
  },
  {
    "id": 124,
    "source_name": "vm-database",
    "status": "completed",
    "verified": false,
    "verification_status": null,
    "verification_date": null,
    ...
  }
]
```

---

## Verification Workflow

### Step-by-Step Process

1. **Trigger Verification**
   ```bash
   curl -X POST http://localhost:8000/api/v1/backups/123/verify \
     -H "Authorization: Bearer $TOKEN"
   ```

2. **Backend Creates Verification Job**
   - Job type: `VERIFICATION`
   - Job status: `RUNNING`
   - Celery task queued

3. **Automated Verification Process**
   - Download backup from storage
   - Decrypt if encrypted
   - Create isolated Docker Compose test pod
   - Restore backup to temporary PostgreSQL database
   - Run validation queries (table count, database size)
   - Tear down test pod
   - Update backup record with results
   - Send email notification

4. **Poll for Results**
   ```bash
   # Check backup verification status
   curl http://localhost:8000/api/v1/backups/123 \
     -H "Authorization: Bearer $TOKEN"
   ```

5. **Review Verification Results**
   - Check `verification_status`: `"passed"` or `"failed"`
   - Review metrics: `verified_table_count`, `verified_size_bytes`
   - Check email for detailed report

### Verification Timeline

| Phase | Duration | Description |
|-------|----------|-------------|
| Download | 1-10 min | Download backup from storage (varies by size and network) |
| Decryption | 30s-2 min | Decrypt backup if encrypted |
| Test Pod Startup | 10-30s | Start isolated PostgreSQL container |
| Restoration | 2-15 min | Restore backup to test database (varies by size) |
| Validation | 5-10s | Run integrity checks |
| Cleanup | 5-10s | Tear down test environment |
| **Total** | **5-30 min** | Typical verification time |

---

## Monitoring Verification Progress

### Option 1: Poll Backup Endpoint

```bash
while true; do
  curl -s http://localhost:8000/api/v1/backups/123 \
    -H "Authorization: Bearer $TOKEN" | \
    jq '.verification_status, .verified'
  sleep 10
done
```

### Option 2: Check Job Status

```bash
# Get job ID from verification response
JOB_ID=$(curl -X POST http://localhost:8000/api/v1/backups/123/verify \
  -H "Authorization: Bearer $TOKEN" | jq -r '.job_id')

# Poll job status
curl http://localhost:8000/api/v1/jobs/$JOB_ID \
  -H "Authorization: Bearer $TOKEN"
```

### Option 3: Check Celery Task

```bash
# Get task ID from verification response
TASK_ID=$(curl -X POST http://localhost:8000/api/v1/backups/123/verify \
  -H "Authorization: Bearer $TOKEN" | jq -r '.task_id')

# Check Celery Flower
curl http://localhost:5555/api/task/info/$TASK_ID
```

### Option 4: Email Notification

Verification completion automatically sends email report to configured recipients.

---

## Automated Scheduling

Backups are automatically verified weekly via Celery Beat.

**Schedule**: Every Sunday at 5:00 AM UTC

**Logic**:
- Finds most recent completed backup for each VM/container
- Skips backups verified within last 7 days
- Queues verification for each qualifying backup
- Sends email report for each verification

**Manual Trigger** (via Celery):
```bash
docker-compose exec worker celery -A backend.worker call \
  backend.worker.verify_recent_backups
```

---

## Email Notifications

### Configuration

Add to `.env`:
```ini
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=backups@example.com
SMTP_PASSWORD=your-app-password
SMTP_FROM=Lab Backup System <backups@example.com>
SMTP_TO=admin@example.com,ops-team@example.com
SMTP_TLS=true
```

### Email Report Contents

**Subject**: `✓ Backup Verification PASSED: vm-webserver` or `✗ Backup Verification FAILED: vm-webserver`

**HTML Email Includes**:
- ✓/✗ Status indicator with color coding
- Backup details (source, ID, file, dates)
- Verification metrics (tables, size, duration)
- Error details if failed
- Recommended actions

**Plain Text Email**: Fallback for non-HTML email clients

---

## Integration Examples

### Python (requests)

```python
import requests
import time

API_BASE = "http://localhost:8000/api/v1"
TOKEN = "your-bearer-token"
headers = {"Authorization": f"Bearer {TOKEN}"}

# Trigger verification
response = requests.post(
    f"{API_BASE}/backups/123/verify",
    headers=headers
)
print(f"Verification queued: {response.json()}")

# Poll for results
backup_id = 123
while True:
    response = requests.get(
        f"{API_BASE}/backups/{backup_id}",
        headers=headers
    )
    backup = response.json()

    if backup['verified'] and backup['verification_date']:
        print(f"Verification {backup['verification_status']}")
        print(f"Tables: {backup['verified_table_count']}")
        print(f"Size: {backup['verified_size_bytes']} bytes")
        print(f"Duration: {backup['verification_duration_seconds']}s")
        break

    time.sleep(10)
```

### JavaScript (fetch)

```javascript
const API_BASE = 'http://localhost:8000/api/v1';
const token = 'your-bearer-token';

// Trigger verification
async function verifyBackup(backupId) {
  const response = await fetch(`${API_BASE}/backups/${backupId}/verify`, {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${token}`
    }
  });
  return response.json();
}

// Poll for results
async function getVerificationStatus(backupId) {
  const response = await fetch(`${API_BASE}/backups/${backupId}`, {
    headers: {
      'Authorization': `Bearer ${token}`
    }
  });
  const backup = await response.json();

  return {
    verified: backup.verified,
    status: backup.verification_status,
    tableCount: backup.verified_table_count,
    sizeBytes: backup.verified_size_bytes,
    duration: backup.verification_duration_seconds
  };
}

// Usage
const result = await verifyBackup(123);
console.log('Verification queued:', result.task_id);

// Poll every 10 seconds
const interval = setInterval(async () => {
  const status = await getVerificationStatus(123);
  if (status.verified && status.status) {
    console.log(`Verification ${status.status}`);
    console.log(`Tables: ${status.tableCount}`);
    console.log(`Size: ${status.sizeBytes} bytes`);
    clearInterval(interval);
  }
}, 10000);
```

### Shell Script

```bash
#!/bin/bash
# verify-backup.sh

API_BASE="http://localhost:8000/api/v1"
TOKEN="your-bearer-token"
BACKUP_ID=$1

if [ -z "$BACKUP_ID" ]; then
  echo "Usage: $0 <backup_id>"
  exit 1
fi

# Trigger verification
echo "Triggering verification for backup $BACKUP_ID..."
RESPONSE=$(curl -s -X POST "$API_BASE/backups/$BACKUP_ID/verify" \
  -H "Authorization: Bearer $TOKEN")

TASK_ID=$(echo $RESPONSE | jq -r '.task_id')
echo "Verification queued: $TASK_ID"

# Poll for results
echo "Polling for results..."
while true; do
  BACKUP=$(curl -s "$API_BASE/backups/$BACKUP_ID" \
    -H "Authorization: Bearer $TOKEN")

  VERIFIED=$(echo $BACKUP | jq -r '.verified')
  STATUS=$(echo $BACKUP | jq -r '.verification_status')

  if [ "$VERIFIED" = "true" ] && [ "$STATUS" != "null" ]; then
    echo "Verification $STATUS"
    echo "Tables: $(echo $BACKUP | jq -r '.verified_table_count')"
    echo "Size: $(echo $BACKUP | jq -r '.verified_size_bytes') bytes"
    echo "Duration: $(echo $BACKUP | jq -r '.verification_duration_seconds')s"
    exit 0
  fi

  sleep 10
done
```

---

## Best Practices

### When to Verify Backups

1. **Immediately After Creation** (critical backups)
   - Production database backups
   - Configuration backups
   - Critical VM backups

2. **Weekly Scheduled** (automated)
   - Verify most recent backup for each source
   - Catches storage corruption early
   - Validates backup process

3. **Before Major Changes**
   - Before system upgrades
   - Before infrastructure changes
   - Before decommissioning systems

4. **Monthly Full Verification**
   - Verify all backups in rotation
   - Ensure backup retention is working
   - Validate storage backend health

### Verification Frequency Recommendations

| Backup Type | Verification Frequency | Rationale |
|-------------|------------------------|-----------|
| Database backups | Daily | Critical data, fast verification |
| Production VMs | Weekly | High importance, longer verification |
| Development VMs | Monthly | Lower priority |
| Configuration backups | After changes | Small, quick to verify |
| Archival backups | Quarterly | Long-term storage validation |

### Handling Verification Failures

1. **Check Error Message**
   ```bash
   curl http://localhost:8000/api/v1/backups/123 | jq '.verification_error'
   ```

2. **Review Job Logs**
   ```bash
   # Get verification job ID
   JOB_ID=$(curl http://localhost:8000/api/v1/backups/123 | jq -r '.verification_job_id')

   # View job logs
   curl http://localhost:8000/api/v1/jobs/$JOB_ID/logs
   ```

3. **Common Failure Causes**
   - Corrupted backup file
   - Encryption key mismatch
   - Storage backend unavailable
   - Insufficient disk space for restoration
   - Network issues during download

4. **Remediation Steps**
   - Create new backup immediately
   - Verify storage backend connectivity
   - Check encryption key availability
   - Review disk space on verification host
   - Test manual restoration with CLI tools

---

## Security Considerations

### Test Pod Isolation

- **Network Isolation**: Test pods use isolated Docker networks with no external access
- **Temporary Storage**: All data stored in tmpfs (RAM), automatically wiped
- **Resource Limits**: CPU and memory limits prevent resource exhaustion
- **Automatic Cleanup**: Test pods destroyed immediately after verification

### Access Control

- **Authentication Required**: All endpoints require valid authentication
- **Role-Based Access**: Only `OPERATOR` role and above can trigger verification
- **Audit Logging**: All verification requests logged with user attribution

### Data Protection

- **Encryption Support**: Encrypted backups are decrypted only in isolated test environment
- **Key Security**: Encryption keys never logged or exposed in API responses
- **Storage Credentials**: Storage backend credentials protected, not exposed

---

## Troubleshooting

### Verification Stuck in Progress

**Symptom**: `verification_status` remains `null` for extended period

**Diagnosis**:
```bash
# Check Celery worker status
docker-compose logs worker

# Check for running test pods
docker ps | grep lab-backup-verify

# Check Celery task status
curl http://localhost:5555/api/tasks
```

**Solution**:
- Restart Celery worker: `docker-compose restart worker`
- Manually clean up test pods: `docker ps -a | grep lab-backup-verify | awk '{print $1}' | xargs docker rm -f`

### Verification Always Fails

**Symptom**: All verifications fail with similar errors

**Common Causes**:
1. **Docker Not Available**
   - Check: `docker ps`
   - Fix: Ensure Docker daemon is running

2. **Insufficient Permissions**
   - Check: `docker-compose exec worker docker ps`
   - Fix: Ensure worker container has Docker socket access

3. **Storage Backend Issues**
   - Check: `curl http://localhost:8000/api/v1/storage-backends`
   - Fix: Verify storage backend connectivity

4. **Encryption Key Issues**
   - Check: `.env` file has `ENCRYPTION_KEY`
   - Fix: Ensure key hasn't changed since backup creation

### Email Notifications Not Sending

**Symptom**: Verification completes but no email received

**Diagnosis**:
```bash
# Check SMTP configuration
docker-compose exec api env | grep SMTP

# Check worker logs for email errors
docker-compose logs worker | grep -i email
```

**Solution**:
- Verify SMTP credentials in `.env`
- Test SMTP connection: `telnet $SMTP_HOST $SMTP_PORT`
- Check spam folder
- Review SMTP authentication method (may need app-specific password)

---

## Performance Considerations

### Resource Usage

**Test Pod Resources**:
- Memory: 2GB limit per verification
- CPU: 2 cores limit per verification
- Storage: tmpfs (RAM-based, no disk I/O)

**Concurrent Verifications**:
- Limit concurrent verifications to avoid resource exhaustion
- Default: 1 verification at a time
- Adjust Celery concurrency: `CELERY_WORKER_CONCURRENCY=2` in `.env`

### Optimization Tips

1. **Schedule During Off-Hours**
   - Default: Sunday 5 AM
   - Adjust in `backend/worker.py` Celery Beat schedule

2. **Verify Incrementally**
   - Don't verify all backups at once
   - Spread verifications throughout the week

3. **Use Faster Storage**
   - Local storage faster than S3 for verification
   - Consider caching backups locally for verification

4. **Monitor Disk Space**
   - tmpfs uses RAM, ensure sufficient memory
   - Fallback to disk if RAM constrained

---

## API Changelog

### Version 1.0 (2025-11-17)

- Initial release of backup verification API
- Added `POST /api/v1/backups/{id}/verify` endpoint
- Added verification fields to `GET /api/v1/backups/{id}` response
- Added automated weekly verification scheduling
- Added email notification support

---

## Related Documentation

- [Disaster Recovery Guide](DISASTER_RECOVERY.md) - Manual backup restoration procedures
- [Architecture Documentation](../ARCHITECTURE.md) - System architecture overview
- [API Reference](../README.md#api-documentation) - Full API documentation

---

**Last Updated**: 2025-11-17
**Version**: 1.0
**Maintained By**: Lab Backup System Team
