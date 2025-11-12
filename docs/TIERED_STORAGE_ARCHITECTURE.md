# Tiered Storage Architecture

## Overview

The Lab Backup System supports a tiered storage architecture for enterprise-grade backup strategies, combining fast local recovery with immutable cloud storage for ransomware protection and long-term retention.

## Storage Tiers

### Tier 1: Primary Storage (SMB/Local)
**Purpose**: Fast backups and quick restores

- **Target**: SMB network shares or local storage
- **Use Case**: Daily operational backups, rapid recovery
- **Retention**: Short to medium term (7-30 days)
- **Performance**: High-speed LAN access
- **Cost**: One-time hardware investment

**Benefits**:
- Fastest backup speeds (1-10 Gbps LAN)
- Instant local restores
- No cloud egress fees
- Air-gapped from internet threats

### Tier 2: Secondary Storage (S3)
**Purpose**: Immutable, long-term, off-site backups

- **Target**: S3-compatible object storage (AWS S3, MinIO, Wasabi, etc.)
- **Use Case**: Disaster recovery, compliance, ransomware protection
- **Retention**: Long term (months to years)
- **Performance**: Slower but sufficient for DR scenarios
- **Cost**: Pay-as-you-go storage

**Benefits**:
- Geographic redundancy
- Immutability with Object Lock (prevents deletion/modification)
- Unlimited scalability
- Built-in versioning
- Compliance-ready (WORM storage)

## Backup Workflows

### Workflow 1: Direct-to-S3 Backup
```
VM/Container → Backup → S3 Storage
```

**When to use**:
- Cloud-first infrastructure
- Limited local storage
- Primary backups already on-site (physical storage)
- Compliance requires immediate off-site storage

**Configuration**:
- Storage Backend Type: S3
- Backup Schedule points to S3 backend

### Workflow 2: Tiered Backup (SMB → S3)
```
VM/Container → Backup → SMB Storage → Replication → S3 Storage
```

**When to use** (Recommended):
- Enterprise environments with local NAS/SAN
- Fast local recovery requirements
- Ransomware protection strategy
- Cost optimization (local for hot data, S3 for cold data)

**Configuration**:
- Primary Storage Backend Type: SMB
- Secondary Storage Backend Type: S3
- Enable "Tier to S3" on storage backend
- Configure replication schedule

### Workflow 3: Multi-Site Replication
```
VM/Container → Backup → SMB Storage (Site A) → Replication → SMB Storage (Site B)
                                              → Replication → S3 Storage
```

**When to use**:
- Multi-datacenter environments
- Geographic redundancy requirements
- Maximum availability

## Storage Backend Configuration

### SMB Backend with S3 Tiering

```json
{
  "name": "Primary NAS",
  "type": "smb",
  "config": {
    "server": "nas.lab.local",
    "share": "backups",
    "username": "backup_user",
    "password": "secure_password",
    "path": "/lab-backups"
  },
  "tier_to_storage_id": 2,  // ID of S3 backend
  "tier_policy": {
    "enabled": true,
    "age_days": 7,  // Replicate to S3 after 7 days
    "keep_local": true,  // Keep local copy or delete after replication
    "schedule": "0 3 * * *"  // Daily at 3 AM
  }
}
```

### S3 Backend with Immutability

```json
{
  "name": "AWS S3 Archive",
  "type": "s3",
  "config": {
    "bucket": "lab-backups-archive",
    "region": "us-east-1",
    "access_key": "AKIAEXAMPLE",
    "secret_key": "secret",
    "storage_class": "STANDARD_IA",  // or GLACIER for long-term
    "object_lock": {
      "enabled": true,
      "mode": "COMPLIANCE",  // or GOVERNANCE
      "retention_days": 90
    }
  }
}
```

## Data Flow

### Initial Backup
1. Backup job executes
2. VM/Container snapshot created
3. Archive created (compressed + optionally encrypted)
4. Upload to Primary Storage (SMB)
5. Backup record created with `tier_status: 'pending'`

### Tiering Process
1. Nightly tier scheduler runs (`tier_backups` task)
2. Identifies backups meeting tier criteria:
   - Age > configured days
   - Status = completed
   - Tier status = pending
   - Primary storage has tier_to_storage_id configured
3. For each eligible backup:
   - Download from primary storage
   - Upload to secondary storage
   - Verify checksum matches
   - Update backup record with secondary storage path
   - Update tier_status to 'tiered'
   - Optionally delete from primary (based on keep_local setting)

### Restore Process
1. User requests restore
2. System checks tier_status:
   - If 'local' → restore from primary storage
   - If 'tiered' → check if still on primary (keep_local=true)
   - If only on secondary → download from S3, then restore
3. Restore executes

## Database Schema Updates

### Storage Backends Table
```sql
ALTER TABLE storage_backends ADD COLUMN tier_to_storage_id INTEGER REFERENCES storage_backends(id);
ALTER TABLE storage_backends ADD COLUMN tier_policy JSONB;
```

### Backups Table
```sql
ALTER TABLE backups ADD COLUMN tier_status VARCHAR(20) DEFAULT 'local';
ALTER TABLE backups ADD COLUMN tier_started_at TIMESTAMP;
ALTER TABLE backups ADD COLUMN tier_completed_at TIMESTAMP;
ALTER TABLE backups ADD COLUMN secondary_storage_id INTEGER REFERENCES storage_backends(id);
ALTER TABLE backups ADD COLUMN secondary_storage_path VARCHAR(500);
```

Tier statuses:
- `local`: Backup only on primary storage
- `pending`: Eligible for tiering, not yet started
- `tiering`: Replication in progress
- `tiered`: Successfully replicated to secondary
- `failed`: Tiering failed

## Security Considerations

### Immutability (WORM - Write Once Read Many)
- S3 Object Lock prevents deletion and modification
- Protects against:
  - Ransomware encryption
  - Accidental deletion
  - Malicious data corruption
  - Compromised credentials

### Encryption
- **In-Transit**: TLS for all transfers (SMB 3.0+, HTTPS for S3)
- **At-Rest Primary**:
  - SMB: Filesystem encryption (BitLocker, LUKS)
  - Application-level encryption before upload (optional)
- **At-Rest Secondary**:
  - S3: Server-Side Encryption (SSE-S3, SSE-KMS)
  - Client-side encryption before upload (recommended)

### Access Control
- **SMB**: Network ACLs, share permissions, NTFS permissions
- **S3**: IAM policies, bucket policies, SCPs
- **Principle of Least Privilege**: Separate credentials for:
  - Backup operations (write-only)
  - Restore operations (read-only)
  - Tier operations (read from primary, write to secondary)

## Cost Optimization

### Storage Classes
- **S3 Standard**: Hot data, frequent access
- **S3 Standard-IA**: Infrequent access (30+ day retention)
- **S3 Glacier Flexible**: Long-term archive (90+ days)
- **S3 Glacier Deep Archive**: Compliance archives (years)

### Lifecycle Policies
```
Day 0-7: SMB (primary)
Day 7-30: S3 Standard (replicated)
Day 30-90: S3 Standard-IA (transitioned)
Day 90+: S3 Glacier Flexible (transitioned)
Year 7+: S3 Glacier Deep Archive or deletion
```

### Bandwidth Optimization
- **Dedupe**: Store only changed blocks (incremental)
- **Compression**: zstd before upload
- **Throttling**: Rate-limit tier replication during business hours
- **Scheduling**: Off-peak tier transfers

## Monitoring & Alerting

### Metrics to Track
- Tier replication success rate
- Time to tier (age when replicated)
- Storage costs (primary vs secondary)
- Tier queue depth
- Failed tier attempts
- S3 Object Lock status

### Alerts
- Tier replication failure > 3 attempts
- S3 Object Lock expiring soon
- Secondary storage unavailable
- Bandwidth limits exceeded
- Cost anomalies

## Future Enhancements

1. **Intelligent Tiering**
   - ML-based prediction of restore likelihood
   - Auto-tier less likely to be restored data

2. **Multi-Cloud Support**
   - Azure Blob Storage
   - Google Cloud Storage
   - Multiple S3-compatible providers

3. **Bandwidth Management**
   - QoS integration
   - WAN optimization
   - Resumable transfers

4. **Compliance Reporting**
   - Audit trail of all tier operations
   - Immutability verification
   - Retention policy enforcement reports

5. **Cost Analytics**
   - Per-VM/container storage costs
   - Tier vs retention cost optimization
   - Cloud cost forecasting

## Implementation Phases

### Phase 1: Core Tiering (Current)
- [x] SMB storage backend
- [ ] Storage backend tier configuration
- [ ] Tier status in backup records
- [ ] Manual tier job trigger

### Phase 2: Automated Tiering
- [ ] Tier scheduler (Celery beat task)
- [ ] Tier policy enforcement
- [ ] Tier queue management
- [ ] Retry logic for failures

### Phase 3: Advanced Features
- [ ] Restore from tiered backups
- [ ] Lifecycle transitions (S3 storage classes)
- [ ] Tier analytics dashboard
- [ ] Cost reporting

### Phase 4: Enterprise Features
- [ ] Multi-site replication
- [ ] Bandwidth throttling
- [ ] Immutability verification
- [ ] Compliance reporting
