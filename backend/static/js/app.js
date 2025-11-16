/**
 * Main application controller
 */

// Check authentication on load
checkAuth();

// Current view
let currentView = 'dashboard';

// View registry
const views = {
    dashboard: renderDashboard,
    backups: renderBackups,
    schedules: renderSchedules,
    jobs: renderJobs,
    kvm: renderKVM,
    podman: renderPodman,
    storage: renderStorage,
    logs: renderLogs,
    settings: renderSettings,
};

// Initialize app
async function initApp() {
    try {
        // Load user info
        const user = await api.getCurrentUser();
        displayUserInfo(user);

        // Setup navigation
        setupNavigation();

        // Initialize session manager with default 5 minute warning
        sessionManager = new SessionManager(api, 5);
        sessionManager.start();

        // Load initial view
        const hash = window.location.hash.slice(1) || 'dashboard';
        loadView(hash);

    } catch (error) {
        console.error('Failed to initialize app:', error);
        notify.error('Failed to load application');
        api.logout();
    }
}

// Display user info in sidebar
function displayUserInfo(user) {
    const userAvatar = document.getElementById('userAvatar');
    const userName = document.getElementById('userName');
    const userRole = document.getElementById('userRole');

    userAvatar.textContent = user.username.charAt(0).toUpperCase();
    userName.textContent = user.username;
    userRole.textContent = user.role.charAt(0).toUpperCase() + user.role.slice(1);
}

// Setup navigation
function setupNavigation() {
    const navItems = document.querySelectorAll('.nav-item');

    navItems.forEach(item => {
        item.addEventListener('click', (e) => {
            e.preventDefault();
            const view = item.getAttribute('data-view');
            loadView(view);
        });
    });

    // Handle browser back/forward
    window.addEventListener('hashchange', () => {
        const hash = window.location.hash.slice(1) || 'dashboard';
        loadView(hash, false);
    });
}

// Load a view
function loadView(viewName, updateHash = true) {
    if (!views[viewName]) {
        console.error('View not found:', viewName);
        return;
    }

    // Update active navigation
    document.querySelectorAll('.nav-item').forEach(item => {
        item.classList.remove('active');
        if (item.getAttribute('data-view') === viewName) {
            item.classList.add('active');
        }
    });

    // Update hash
    if (updateHash) {
        window.location.hash = viewName;
    }

    // Update page title
    const titles = {
        dashboard: 'Dashboard',
        backups: 'Backup History',
        schedules: 'Backup Schedules',
        jobs: 'Job Monitor',
        kvm: 'KVM Infrastructure',
        podman: 'Podman Infrastructure',
        storage: 'Storage Backends',
        logs: 'Application Logs',
        settings: 'System Settings',
    };
    document.getElementById('pageTitle').textContent = titles[viewName] || viewName;

    // Render view
    currentView = viewName;
    views[viewName]();
}

// Logout handler
function handleLogout() {
    showConfirmDialog(
        'Confirm Logout',
        'Are you sure you want to logout?',
        () => {
            api.logout();
        }
    );
}

// Show backup now dialog (shared between KVM and Podman views)
async function showBackupNowDialog(sourceType, sourceId, sourceName) {
    try {
        // Load storage backends
        const storageBackends = await api.listStorageBackends();

        if (storageBackends.length === 0) {
            notify.error('No storage backends configured. Please add a storage backend first.');
            return;
        }

        // Load existing backups to check if incremental is possible
        const backups = await api.listBackups({ source_type: sourceType, source_id: sourceId });
        const hasFullBackup = backups.some(b => b.backup_mode === 'full' && b.status === 'completed');

        const modal = new Modal(`Backup ${sourceName}`, `
            <form id="backupNowForm">
                <div class="form-group">
                    <label class="form-label required">Backup Mode</label>
                    <select class="form-input" name="backup_mode" id="backup_mode" required ${!hasFullBackup ? 'disabled' : ''}>
                        <option value="full">Full Backup</option>
                        <option value="incremental" ${!hasFullBackup ? 'disabled' : ''}>Incremental Backup${!hasFullBackup ? ' (requires a completed full backup first)' : ''}</option>
                    </select>
                    ${!hasFullBackup ? '<div class="form-help" style="color: #f59e0b;">ℹ️ No full backup found. Create a full backup first to enable incremental backups.</div>' : ''}
                </div>

                <div class="form-group">
                    <label class="form-label required">Storage Backend</label>
                    <select class="form-input" name="storage_backend_id" required>
                        ${storageBackends.map(backend => `
                            <option value="${backend.id}">${backend.name} (${backend.type})</option>
                        `).join('')}
                    </select>
                </div>

                <div class="form-group">
                    <label class="form-label">Retention (days)</label>
                    <input type="number" class="form-input" name="retention_days"
                           value="30" min="1" max="3650" required>
                    <div class="form-help">Number of days to retain this backup</div>
                </div>

                <div class="form-group">
                    <label style="display: flex; align-items: center; gap: 0.5rem;">
                        <input type="checkbox" name="encryption_enabled">
                        <span>Enable encryption</span>
                    </label>
                </div>
            </form>
        `);

        modal.setOnConfirm(async () => {
            try {
                const form = document.getElementById('backupNowForm');
                const data = getFormData(form);

                // Add source info
                data.source_type = sourceType;
                data.source_id = parseInt(sourceId);

                const loading = showLoading(modal.overlay);
                const result = await api.triggerBackup(data);
                hideLoading(loading);

                notify.success(`Backup queued successfully! Backup ID: ${result.id}`);
                modal.close();

                // Optionally navigate to backups view to see the backup
                setTimeout(() => {
                    if (confirm('Backup has been queued. Would you like to view the backups page?')) {
                        loadView('backups');
                    }
                }, 500);
            } catch (error) {
                notify.error('Failed to trigger backup: ' + error.message);
            }
        });

        modal.show();
    } catch (error) {
        notify.error('Failed to load backup dialog: ' + error.message);
    }
}

// Initialize on page load
document.addEventListener('DOMContentLoaded', initApp);
