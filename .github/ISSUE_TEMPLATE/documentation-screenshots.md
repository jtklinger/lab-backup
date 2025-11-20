---
name: Documentation Screenshots
about: Add screenshots to documentation for better visual guidance
title: 'Enhancement: Add screenshots to documentation'
labels: documentation, enhancement, good first issue
assignees: ''

---

## Description

Add screenshots to documentation files to provide visual guidance for new users. This will make it easier for people to understand the web interface and get started quickly.

## Required Screenshots

### High Priority (Getting Started Guide)

1. **Login Page** - Show the initial login screen at http://localhost:3000
2. **Dashboard** - Main dashboard showing system overview, stats, and recent activity
3. **Add KVM Host Dialog** - Form for adding a new KVM host
4. **Storage Configuration** - Adding a storage backend (show one type, e.g., Local or S3)
5. **Create Schedule** - Backup schedule creation form
6. **Backup List** - Page showing completed backups with filters
7. **Job Details** - Detailed view of a running/completed backup job

### Medium Priority (Feature Documentation)

8. **Infrastructure Page** - KVM Hosts and Podman Hosts tabs
9. **Restore Dialog** - VM restore interface
10. **User Management** - Admin panel for managing users
11. **Settings Page** - System settings and configuration
12. **Notifications Configuration** - Email notification setup

### Low Priority (Nice to Have)

13. **Dark Mode Toggle** - Show the interface in dark mode
14. **Mobile View** - Responsive design on mobile/tablet
15. **Celery Flower** - Task monitoring interface
16. **API Documentation** - Swagger UI at http://localhost:8000/docs

## Acceptance Criteria

- [ ] Screenshots are high quality (at least 1920x1080 or similar)
- [ ] Screenshots show realistic data (not all empty)
- [ ] Screenshots are annotated with arrows/highlights where helpful
- [ ] Screenshots are saved in `docs/screenshots/` directory
- [ ] Screenshots are added to appropriate documentation files:
  - [ ] GETTING-STARTED.md
  - [ ] README.md (at least dashboard screenshot)
  - [ ] SETUP-WINDOWS.md (login + dashboard)
- [ ] Create docs/SCREENSHOTS.md with organized gallery of all screenshots
- [ ] File naming convention: `01-login-page.png`, `02-dashboard.png`, etc.

## Implementation Notes

### Tools for Screenshots

- Use browser's built-in screenshot tool (F12 → DevTools → ... → Capture screenshot)
- Use Windows Snipping Tool or Snip & Sketch (Win + Shift + S)
- Use third-party tools like ShareX for annotations

### Screenshot Guidelines

1. **Clean data** - Use realistic but not sensitive data
2. **Consistent sizing** - All screenshots should be similar dimensions
3. **Light theme** - Use light theme for consistency (unless showing dark mode)
4. **No sensitive info** - Remove any real IP addresses, passwords, etc.
5. **Annotations** - Add arrows, boxes, or highlights to draw attention to key features

### Markdown Example

```markdown
## Dashboard Overview

![Dashboard Screenshot](docs/screenshots/02-dashboard.png)

The dashboard provides a real-time overview of:
- Total VMs and containers being backed up
- Recent backup activity and success rate
- Storage usage across all backends
- Active schedules and upcoming backups
```

## Additional Context

This enhancement will significantly improve the user experience for new users by providing visual confirmation they're on the right track during setup.

Priority: **Low** (nice to have, not blocking)
Effort: **Medium** (2-3 hours to capture and document all screenshots)
Impact: **High** (greatly improves documentation usability)

## Related Files

- GETTING-STARTED.md
- README.md
- SETUP-WINDOWS.md
- docs/ directory (create screenshots/ subdirectory)
