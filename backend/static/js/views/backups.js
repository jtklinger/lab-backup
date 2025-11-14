/**
 * Backups View
 */

async function renderBackups() {
    const mainContent = document.getElementById('mainContent');
    const headerActions = document.getElementById('headerActions');

    // Add refresh button to header
    headerActions.innerHTML = `
        <button class="btn btn-secondary btn-sm" onclick="renderBackups()">
            🔄 Refresh
        </button>
    `;

    // Show loading
    mainContent.innerHTML = '<div class="spinner"></div>';

    try {
        const backups = await api.listBackups({ limit: 100 });
        renderBackupsList(backups);
    } catch (error) {
        console.error('Failed to load backups:', error);
        mainContent.innerHTML = `
            <div class="alert alert-error">
                <div class="alert-icon">✕</div>
                <div class="alert-content">
                    <div class="alert-title">Failed to load backups</div>
                    ${error.message}
                </div>
            </div>
        `;
    }
}

function renderBackupsList(backups) {
    const mainContent = document.getElementById('mainContent');

    if (backups.length === 0) {
        mainContent.innerHTML = `
            <div class="card">
                <div class="card-body">
                    <div class="empty-state">
                        <div class="empty-state-icon">💾</div>
                        <div class="empty-state-title">No backups found</div>
                        <div class="empty-state-description">
                            Backups will appear here once you create and run backup schedules
                        </div>
                        <a href="#schedules" class="btn btn-primary">Create Schedule</a>
                    </div>
                </div>
            </div>
        `;
        return;
    }

    // Group backups by status
    const statusCounts = {
        completed: backups.filter(b => b.status === 'completed').length,
        running: backups.filter(b => b.status === 'running').length,
        failed: backups.filter(b => b.status === 'failed').length,
        pending: backups.filter(b => b.status === 'pending').length,
    };

    mainContent.innerHTML = `
        <!-- Status Summary -->
        <div class="stats-grid" style="margin-bottom: 1.5rem;">
            <div class="stat-card">
                <div class="stat-icon success">✓</div>
                <div class="stat-content">
                    <div class="stat-label">Completed</div>
                    <div class="stat-value">${statusCounts.completed}</div>
                </div>
            </div>
            <div class="stat-card">
                <div class="stat-icon primary">⏳</div>
                <div class="stat-content">
                    <div class="stat-label">Running</div>
                    <div class="stat-value">${statusCounts.running}</div>
                </div>
            </div>
            <div class="stat-card">
                <div class="stat-icon error">✕</div>
                <div class="stat-content">
                    <div class="stat-label">Failed</div>
                    <div class="stat-value">${statusCounts.failed}</div>
                </div>
            </div>
            <div class="stat-card">
                <div class="stat-icon warning">⏸</div>
                <div class="stat-content">
                    <div class="stat-label">Pending</div>
                    <div class="stat-value">${statusCounts.pending}</div>
                </div>
            </div>
        </div>

        <!-- Filters -->
        <div class="card" style="margin-bottom: 1.5rem;">
            <div class="card-body">
                <div style="display: flex; gap: 1rem; align-items: center;">
                    <label style="margin: 0;">Filter by status:</label>
                    <select id="statusFilter" class="form-select" style="width: 200px;" onchange="filterBackups()">
                        <option value="">All</option>
                        <option value="completed">Completed</option>
                        <option value="running">Running</option>
                        <option value="failed">Failed</option>
                        <option value="pending">Pending</option>
                    </select>
                    <input type="text" id="searchFilter" class="form-input" placeholder="Search by name..."
                           style="width: 300px;" oninput="filterBackups()">
                </div>
            </div>
        </div>

        <!-- Backups Table -->
        <div class="card">
            <div class="card-header">
                <h3 class="card-title">All Backups</h3>
            </div>
            <div class="card-body">
                <div class="table-container">
                    <table class="table" id="backupsTable">
                        <thead>
                            <tr>
                                <th>Source</th>
                                <th>Type</th>
                                <th>Backup Type</th>
                                <th>Status</th>
                                <th>Size</th>
                                <th>Created</th>
                                <th>Completed</th>
                                <th>Actions</th>
                            </tr>
                        </thead>
                        <tbody>
                            ${backups.map(backup => `
                                <tr data-status="${backup.status}" data-name="${backup.source_name.toLowerCase()}">
                                    <td>${backup.source_name}</td>
                                    <td><span class="badge badge-primary">${backup.source_type}</span></td>
                                    <td><span class="badge badge-info">${backup.backup_type}</span></td>
                                    <td>${getStatusBadge(backup.status)}</td>
                                    <td>${formatBytes(backup.compressed_size || backup.size || 0)}</td>
                                    <td>${formatDate(backup.created_at)}</td>
                                    <td>${backup.completed_at ? formatDate(backup.completed_at) : '-'}</td>
                                    <td>
                                        <button class="btn btn-sm btn-secondary" onclick="viewBackupDetails(${backup.id})">
                                            View
                                        </button>
                                        ${backup.status === 'completed' ? `
                                            <button class="btn btn-sm btn-primary" onclick="restoreBackup(${backup.id})">
                                                Restore
                                            </button>
                                        ` : ''}
                                        <button class="btn btn-sm btn-danger" onclick="deleteBackupConfirm(${backup.id})">
                                            Delete
                                        </button>
                                    </td>
                                </tr>
                            `).join('')}
                        </tbody>
                    </table>
                </div>
            </div>
        </div>
    `;
}

function filterBackups() {
    const statusFilter = document.getElementById('statusFilter').value.toLowerCase();
    const searchFilter = document.getElementById('searchFilter').value.toLowerCase();
    const rows = document.querySelectorAll('#backupsTable tbody tr');

    rows.forEach(row => {
        const status = row.getAttribute('data-status').toLowerCase();
        const name = row.getAttribute('data-name');

        const statusMatch = !statusFilter || status === statusFilter;
        const searchMatch = !searchFilter || name.includes(searchFilter);

        row.style.display = (statusMatch && searchMatch) ? '' : 'none';
    });
}

async function viewBackupDetails(backupId) {
    try {
        const backup = await api.getBackup(backupId);

        const modal = new Modal('Backup Details', `
            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 1rem;">
                <div>
                    <strong>ID:</strong> ${backup.id}
                </div>
                <div>
                    <strong>Source:</strong> ${backup.source_name}
                </div>
                <div>
                    <strong>Type:</strong> ${backup.source_type}
                </div>
                <div>
                    <strong>Backup Type:</strong> ${backup.backup_type}
                </div>
                <div>
                    <strong>Status:</strong> ${getStatusBadge(backup.status)}
                </div>
                <div>
                    <strong>Size:</strong> ${formatBytes(backup.size || 0)}
                </div>
                <div>
                    <strong>Compressed:</strong> ${formatBytes(backup.compressed_size || 0)}
                </div>
                <div>
                    <strong>Storage Path:</strong> ${backup.storage_path || 'N/A'}
                </div>
                <div>
                    <strong>Created:</strong> ${formatDate(backup.created_at)}
                </div>
                <div>
                    <strong>Started:</strong> ${backup.started_at ? formatDate(backup.started_at) : 'N/A'}
                </div>
                <div>
                    <strong>Completed:</strong> ${backup.completed_at ? formatDate(backup.completed_at) : 'N/A'}
                </div>
                <div>
                    <strong>Expires:</strong> ${backup.expires_at ? formatDate(backup.expires_at) : 'Never'}
                </div>
                ${backup.checksum ? `
                    <div style="grid-column: 1 / -1;">
                        <strong>Checksum:</strong>
                        <code style="font-size: 0.8rem;">${backup.checksum}</code>
                    </div>
                ` : ''}
                ${backup.error_message ? `
                    <div style="grid-column: 1 / -1;">
                        <strong>Error:</strong>
                        <div class="alert alert-error" style="margin-top: 0.5rem;">
                            ${backup.error_message}
                        </div>
                    </div>
                ` : ''}
            </div>
        `);

        modal.show();

        // Hide footer after modal is shown
        const footer = modal.overlay?.querySelector('.modal-footer');
        if (footer) {
            footer.style.display = 'none';
        }

    } catch (error) {
        notify.error('Failed to load backup details: ' + error.message);
    }
}

async function restoreBackup(backupId) {
    try {
        // Get backup details to determine source type
        const backup = await api.getBackup(backupId);

        // Load KVM hosts for VM backups
        let kvmHosts = [];
        if (backup.source_type === 'vm') {
            kvmHosts = await api.listKVMHosts();
        }

        const modal = new Modal('Restore Backup', `
            <form id="restoreForm">
                <div class="alert alert-info" style="margin-bottom: 1rem;">
                    <div class="alert-icon">ℹ</div>
                    <div class="alert-content">
                        Restoring backup of <strong>${backup.source_name}</strong>
                    </div>
                </div>

                ${kvmHosts.length > 0 ? `
                    <div class="form-group">
                        <label class="form-label">Target Host</label>
                        <select class="form-input" name="target_host_id">
                            <option value="">Original Host (default)</option>
                            ${kvmHosts.map(host => `
                                <option value="${host.id}">${host.name} (${host.hostname})</option>
                            `).join('')}
                        </select>
                        <div class="form-help">Select a different host to restore to a different location</div>
                    </div>
                ` : ''}

                <div class="form-group">
                    <label class="form-label">Storage Type</label>
                    <select class="form-input" name="storage_type">
                        <option value="auto">Auto (detect from backup)</option>
                        <option value="file">File (/var/lib/libvirt/images)</option>
                        <option value="rbd">RBD (Ceph storage)</option>
                    </select>
                    <div class="form-help">
                        <strong>Auto:</strong> Restores to the same storage type as the original backup<br>
                        <strong>File:</strong> Force restore to file-based storage (use for hosts without Ceph)<br>
                        <strong>RBD:</strong> Force restore to Ceph RBD storage (requires Ceph cluster)
                    </div>
                </div>

                <div class="form-group">
                    <label class="form-label">New Name</label>
                    <input type="text" class="form-input" name="new_name"
                           placeholder="Leave empty to use original name">
                    <div class="form-help">Specify a new name for the restored VM/container</div>
                </div>

                <div class="form-group">
                    <label style="display: flex; align-items: center; gap: 0.5rem;">
                        <input type="checkbox" name="overwrite">
                        <span>Overwrite if exists</span>
                    </label>
                    <div class="form-help">WARNING: This will replace the existing VM/container with the same name</div>
                </div>
            </form>
        `);

        modal.setOnConfirm(async () => {
            try {
                const form = document.getElementById('restoreForm');
                const formData = getFormData(form);

                // Convert target_host_id to number or null
                const data = {
                    target_host_id: formData.target_host_id ? parseInt(formData.target_host_id) : null,
                    new_name: formData.new_name || null,
                    overwrite: formData.overwrite || false,
                    storage_type: formData.storage_type || 'auto',
                    storage_config: null
                };

                const loading = showLoading(modal.overlay);
                const result = await api.restoreBackup(backupId, data);
                hideLoading(loading);

                notify.success(`Restore queued successfully! Job ID: ${result.job_id}`);
                modal.close();

                // Optionally navigate to jobs view
                setTimeout(() => {
                    if (confirm('Restore has been queued. Would you like to view the jobs page?')) {
                        loadView('jobs');
                    }
                }, 500);

            } catch (error) {
                notify.error('Failed to restore backup: ' + error.message);
            }
        });

        modal.show();

    } catch (error) {
        notify.error('Failed to load restore dialog: ' + error.message);
    }
}

async function deleteBackupConfirm(backupId) {
    showConfirmDialog(
        'Delete Backup',
        'Are you sure you want to delete this backup? This action cannot be undone.',
        async () => {
            try {
                await api.deleteBackup(backupId);
                notify.success('Backup deleted successfully');
                renderBackups();
            } catch (error) {
                notify.error('Failed to delete backup: ' + error.message);
            }
        }
    );
}
