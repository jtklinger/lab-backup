---
name: Missing Frontend Features
about: Implement missing Settings page and SSH key management UI
title: 'Feature: Implement Settings page and SSH key management'
labels: enhancement, frontend, high-priority
assignees: ''

---

## Description

The React frontend is missing several critical features that are documented and fully implemented in the backend API. This issue tracks the implementation of the most important missing features.

## Current State

The frontend implements approximately **50% of the backend API**. Core CRUD operations work, but advanced features and the entire Settings infrastructure are missing.

## Missing Features

### 1. Settings Page (CRITICAL - High Priority)

**Status:** ❌ NOT IMPLEMENTED despite documentation claiming it exists

**Documentation Claims:**
- README.md: "Settings: Configure email notifications, retention policies, and system settings"
- GETTING-STARTED.md: "Go to 'Settings' (gear icon)", "Settings → Notifications", etc.

**Backend API:** ✅ Fully implemented (`/api/v1/settings/*`)

**What needs to be built:**
- New page: `frontend/src/pages/Settings.tsx`
- Navigation item with gear icon
- Tabbed interface with 5 tabs:
  1. **Email/SMTP** - Server, port, credentials, TLS settings
  2. **Retention** - Daily, weekly, monthly, yearly backup retention
  3. **Alerts** - Storage thresholds, failure notifications
  4. **Security** - Session timeout settings
  5. **Logging** - Log retention, levels, database/file settings

**API Endpoints to Connect:**
```
GET    /api/v1/settings/categories           # List all categories
GET    /api/v1/settings/category/{category}  # Get settings by category
PUT    /api/v1/settings/{key}                # Update setting
PUT    /api/v1/settings/bulk                 # Bulk update
```

### 2. SSH Key Management UI (HIGH Priority)

**Status:** ❌ NOT IMPLEMENTED (backend fully ready)

**Current State:**
- KVM host management exists in Admin panel
- Can add/edit/delete hosts
- **Missing:** SSH key upload, generation, viewing

**Backend API:** ✅ Fully implemented (`/api/v1/kvm/hosts/{id}/ssh-keys/*`)

**What needs to be built:**
- Component: `frontend/src/components/infrastructure/SSHKeyManagement.tsx`
- Features needed:
  - Upload existing SSH private key
  - Generate new SSH key pair
  - View/copy public key for installation on target host
  - Delete SSH keys
  - List all keys for a host

**API Endpoints to Connect:**
```
POST   /api/v1/kvm/hosts/{host_id}/ssh-keys            # Upload key
POST   /api/v1/kvm/hosts/{host_id}/ssh-keys/generate   # Generate new key
GET    /api/v1/kvm/hosts/{host_id}/ssh-keys            # List keys
DELETE /api/v1/kvm/hosts/{host_id}/ssh-keys/{key_id}   # Delete key
GET    /api/v1/kvm/hosts/{host_id}/ssh-keys/{key_id}/public  # Get public key
```

### 3. Infrastructure Navigation Restructure (MEDIUM Priority)

**Current State:**
- KVM and Podman hosts are in Admin panel tabs
- Documentation claims "Infrastructure → KVM Hosts"

**Recommendation:**
- Move KVM/Podman hosts out of Admin panel
- Create dedicated "Infrastructure" navigation item
- Separate pages: `/infrastructure/kvm` and `/infrastructure/podman`
- Admin panel focuses only on: Users and Audit Logs

### 4. Other Missing Features (LOWER Priority)

These have backend APIs but no frontend UI:
- **Compliance Dashboard** - Monitor backup compliance status
- **Application Logs Viewer** - View system logs with filtering
- **Advanced Backup Features** - Verify integrity, immutability, backup chains

## Implementation Plan

### Phase 1: Critical Features (Week 1)

**Task 1.1: Settings Page**
- [ ] Create `Settings.tsx` page with tabbed layout
- [ ] Implement Email/SMTP settings tab
- [ ] Implement Retention settings tab
- [ ] Implement Alerts settings tab
- [ ] Implement Security settings tab
- [ ] Implement Logging settings tab
- [ ] Add Settings navigation item with gear icon
- [ ] Add route in App.tsx
- [ ] Form validation with zod schemas

**Task 1.2: SSH Key Management**
- [ ] Create `SSHKeyManagement.tsx` component
- [ ] Add to KVM host management (Admin → KVM Hosts)
- [ ] Implement upload key dialog
- [ ] Implement generate key dialog
- [ ] Implement view/copy public key dialog
- [ ] Implement delete confirmation
- [ ] List SSH keys per host

**Task 1.3: Navigation Updates**
- [ ] Add Settings to navigation with gear icon
- [ ] Update MainLayout.tsx
- [ ] Test role-based access (Admin only)

### Phase 2: Infrastructure Restructure (Week 2)

- [ ] Create `InfrastructureKVM.tsx` page
- [ ] Create `InfrastructurePodman.tsx` page
- [ ] Move KVM hosts tab content from Admin.tsx
- [ ] Move Podman hosts tab content from Admin.tsx
- [ ] Add Infrastructure navigation item
- [ ] Update routes
- [ ] Update Admin.tsx to only have Users and Audit Logs

### Phase 3: Additional Features (Future)

- [ ] Compliance Dashboard
- [ ] Application Logs Viewer
- [ ] Advanced Backup Features UI

## Acceptance Criteria

### Settings Page
- [ ] All 5 setting categories are accessible via tabs
- [ ] Can view current settings
- [ ] Can update individual settings
- [ ] Form validation works correctly
- [ ] Success/error notifications display
- [ ] Settings persist and reload correctly
- [ ] Gear icon in navigation leads to Settings page
- [ ] Only Admin role can access

### SSH Key Management
- [ ] Can upload existing SSH private key
- [ ] Can generate new SSH key pair (see public/private keys)
- [ ] Can view and copy public key for installation
- [ ] Can delete SSH keys with confirmation
- [ ] Keys list shows all keys for selected host
- [ ] Error handling for invalid keys
- [ ] Success notifications after operations

### Navigation
- [ ] Settings accessible from gear icon or sidebar
- [ ] Infrastructure page properly displays KVM/Podman hosts
- [ ] Admin panel only shows Users and Audit Logs
- [ ] All routes work correctly
- [ ] Breadcrumbs/titles are correct

## Technical Details

**Technology Stack:**
- React 18 with TypeScript
- Material-UI v6 (already in use)
- react-hook-form + zod for validation
- Axios for API calls

**Similar Components to Reference:**
- `Admin.tsx` - Good example of tabbed interface (1,480 lines)
- `Storage.tsx` - Good example of CRUD with dialogs
- `Schedules.tsx` - Good example of form validation

**API Client:**
- Add new methods to `frontend/src/services/api.ts`
- Use existing `handleApiError` for error handling

## Documentation Updates Needed

After implementation:
- [ ] Update README.md to confirm Settings page exists
- [ ] Update GETTING-STARTED.md with correct Settings paths
- [ ] Update SETUP-WINDOWS.md if needed
- [ ] Take screenshots for documentation (separate issue exists)

## Related Issues

- #[screenshots-issue-number] - Add screenshots to documentation

## Estimated Effort

- **Settings Page:** 8-12 hours
- **SSH Key Management:** 6-8 hours
- **Navigation Updates:** 2-4 hours
- **Testing & Documentation:** 4-6 hours

**Total:** 2-3 days of focused development

## Priority Justification

**HIGH PRIORITY because:**
1. Documentation is misleading (claims features exist that don't)
2. Settings are fundamental to system configuration
3. SSH key management is critical for security
4. Users expect these features based on docs

## Notes

- Backend APIs are fully implemented and tested
- No database changes needed
- No backend changes needed
- Pure frontend implementation
- Can be developed incrementally (Settings first, then SSH keys)
