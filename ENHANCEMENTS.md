# Lab Backup - Feature Enhancements

This document tracks feature requests and enhancements for the Lab Backup system.

## Requested Features

### Backup Progress Percentage Display

**Priority**: High
**Status**: Requested
**Date**: 2025-11-24

**Description**:
Display real-time backup completion percentage during backup operations, especially for large disk backups.

**Current Behavior**:
- Backup jobs show generic "in progress" status
- No visibility into actual progress during large disk exports
- Users cannot estimate time remaining for backup completion
- Large RBD disk backups (30GB+) can take 30+ minutes with no progress indication

**Proposed Enhancement**:
- Show percentage completion during backup operations
- Display current backup phase (e.g., "Exporting disk sda - 45%")
- Show transfer speed and estimated time remaining
- Real-time progress updates in the UI
- Progress bar visualization in backup job details

**Technical Considerations**:
- Backend: Add progress tracking to `KVMBackupService.create_backup()` method
- Stream progress updates from disk export subprocess (qemu-img, SSH transfer)
- Use WebSocket or polling mechanism to push progress to frontend
- Store progress in job metadata or separate progress table
- Handle multiple concurrent disk exports with individual progress tracking

**Benefits**:
- Improved user experience during long-running backups
- Ability to identify stuck or slow backups
- Better visibility into backup system performance
- Reduced user uncertainty about backup status

---

## Completed Features

_(Features will be moved here when implemented)_
