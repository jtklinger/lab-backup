# SMB Storage Configuration - backup01

## Overview

This document describes the SMB share configuration on `backup01.lab.towerbancorp.com` for backup storage.

## Server Information

- **Hostname:** backup01.lab.towerbancorp.com
- **OS:** Rocky Linux 9.6 (Blue Onyx)
- **Samba Version:** 4.21.3-14.el9_6

## Storage Details

### Share Configuration

- **Share Name:** `backups_v1`
- **Path:** `/home/smb/backups_v1`
- **Storage Location:** `/home` partition
- **Available Space:** 868GB (as of configuration date)
- **Target Size:** 200GB (soft limit)
- **Permissions:** Group `smbusers` with read/write access
- **Access Control:** User authentication required (no guest access)

### Directory Permissions

```bash
drwxrwxr-x. 2 root smbusers 6 Nov 12 11:33 /home/smb/backups_v1
```

- Owner: root
- Group: smbusers
- Mode: 775 (rwxrwxr-x)
- Create mask: 0664
- Directory mask: 0775

## Samba Configuration

The share is configured in `/etc/samba/smb.conf`:

```ini
[backups_v1]
	comment = Backups V1 Share (200GB)
	path = /home/smb/backups_v1
	browseable = yes
	writable = yes
	read only = no
	guest ok = no
	create mask = 0664
	directory mask = 0775
	valid users = @smbusers
```

## User Configuration

### Current Users

#### backup-admin
- **Username:** `backup-admin`
- **Password:** `25tbc/4u!!`
- **System UID:** 1001
- **Groups:** backup-admin (1002), smbusers (1001)
- **Shell:** /sbin/nologin (no interactive login)
- **Samba Status:** Enabled

### Adding Additional Users

To add new users to the SMB share:

```bash
# 1. Create a system user (no login shell)
sudo useradd -M -s /sbin/nologin <username>

# 2. Add user to smbusers group
sudo usermod -aG smbusers <username>

# 3. Set Samba password for the user
sudo smbpasswd -a <username>

# 4. Enable the Samba user
sudo smbpasswd -e <username>
```

## Services

### Active Services

- **smb.service** - Samba SMB Daemon
- **nmb.service** - Samba NetBIOS Name Server

Both services are:
- Active and running
- Enabled at boot

```bash
# Service management commands
sudo systemctl status smb nmb
sudo systemctl restart smb nmb
sudo systemctl enable smb nmb
```

### Firewall Configuration

Samba service is permitted through firewalld:

```bash
sudo firewall-cmd --permanent --add-service=samba
sudo firewall-cmd --reload
```

## Client Access

### Windows

#### Map Network Drive (GUI)
1. Open File Explorer
2. Right-click "This PC" → "Map network drive"
3. Enter path: `\\backup01.lab.towerbancorp.com\backups_v1`
4. Check "Connect using different credentials"
5. Enter username: `backup-admin`
6. Enter password: `25tbc/4u!!`

#### Command Line
```cmd
net use Z: \\backup01.lab.towerbancorp.com\backups_v1 /user:backup-admin
```

### Linux

#### Interactive Access
```bash
smbclient //backup01.lab.towerbancorp.com/backups_v1 -U backup-admin
```

#### Mount as Filesystem
```bash
# One-time mount
sudo mount -t cifs //backup01.lab.towerbancorp.com/backups_v1 /mnt/backups \
  -o username=backup-admin,password='25tbc/4u!!'

# Persistent mount (add to /etc/fstab)
//backup01.lab.towerbancorp.com/backups_v1 /mnt/backups cifs username=backup-admin,password=25tbc/4u!!,uid=1000,gid=1000 0 0
```

**Note:** For production use, consider using a credentials file instead of plain text passwords:

```bash
# Create credentials file
sudo nano /etc/samba/credentials

# Content:
username=backup-admin
password=25tbc/4u!!

# Secure the file
sudo chmod 600 /etc/samba/credentials

# Mount using credentials file
sudo mount -t cifs //backup01.lab.towerbancorp.com/backups_v1 /mnt/backups \
  -o credentials=/etc/samba/credentials
```

### macOS

#### Finder
1. Open Finder
2. Press Cmd+K (Go → Connect to Server)
3. Enter: `smb://backup01.lab.towerbancorp.com/backups_v1`
4. Click Connect
5. Enter username: `backup-admin`
6. Enter password: `25tbc/4u!!`

#### Command Line
```bash
mount -t smbfs //backup-admin:25tbc/4u!!@backup01.lab.towerbancorp.com/backups_v1 /Volumes/backups_v1
```

## Verification

### Test Share Availability
```bash
# List available shares
smbclient -L backup01.lab.towerbancorp.com -N

# Test authentication and access
smbclient //backup01.lab.towerbancorp.com/backups_v1 -U backup-admin
```

### Check Samba Configuration
```bash
# Validate Samba configuration
sudo testparm -s

# View Samba users
sudo pdbedit -L
```

### Monitor Connection Status
```bash
# View active connections
sudo smbstatus

# View open files
sudo smbstatus --shares
```

## Maintenance

### Disk Space Monitoring

Monitor the `/home` partition to ensure adequate space:

```bash
df -h /home
```

**Note:** While the target size is 200GB, there is no hard quota enforced. Implement filesystem quotas if strict size limits are required.

### Backup Considerations

- Regular backups of the share contents should be performed
- Consider implementing snapshot functionality if using Btrfs or ZFS
- Monitor disk usage to prevent filling the partition

### Log Files

Samba logs are located at:
- `/var/log/samba/log.smbd` - SMB daemon log
- `/var/log/samba/log.nmbd` - NetBIOS name server log

## Troubleshooting

### Cannot Connect to Share

1. Verify services are running:
   ```bash
   sudo systemctl status smb nmb
   ```

2. Check firewall rules:
   ```bash
   sudo firewall-cmd --list-services
   ```

3. Test local connectivity:
   ```bash
   smbclient -L localhost -N
   ```

### Permission Denied

1. Verify user is in smbusers group:
   ```bash
   id backup-admin
   ```

2. Check Samba user status:
   ```bash
   sudo pdbedit -L | grep backup-admin
   ```

3. Verify directory permissions:
   ```bash
   ls -ld /home/smb/backups_v1
   ```

### Password Issues

Reset Samba password:
```bash
sudo smbpasswd -a backup-admin
```

## Security Considerations

1. **Password Security:** The current password is documented for operational purposes. Consider:
   - Using a password manager
   - Implementing key-based authentication where possible
   - Regular password rotation

2. **Network Security:**
   - SMB traffic is on the internal lab network
   - Consider implementing SMB signing for additional security
   - Restrict access via firewall rules if needed

3. **Audit Logging:**
   - Enable Samba audit logging for compliance:
   ```ini
   [backups_v1]
   ...
   vfs objects = full_audit
   full_audit:prefix = %u|%I|%m|%S
   full_audit:success = mkdir rename unlink rmdir pwrite pread
   full_audit:failure = connect
   full_audit:facility = local5
   full_audit:priority = notice
   ```

## Configuration Date

- **Initial Configuration:** November 12, 2025
- **Last Updated:** November 12, 2025
- **Configured By:** System Administrator via Claude Code

## Related Documentation

- [Samba Documentation](https://www.samba.org/samba/docs/)
- [Rocky Linux Samba Guide](https://docs.rockylinux.org/guides/file_sharing/samba/)
- Lab Network Documentation (if available)
