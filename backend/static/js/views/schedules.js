/**
 * Schedules View
 */

async function renderSchedules() {
    const mainContent = document.getElementById('mainContent');
    const headerActions = document.getElementById('headerActions');

    // Add action buttons to header
    headerActions.innerHTML = `
        <button class="btn btn-primary btn-sm" onclick="showCreateScheduleDialog()">
            + Create Schedule
        </button>
        <button class="btn btn-secondary btn-sm" onclick="renderSchedules()">
            🔄 Refresh
        </button>
    `;

    // Show loading
    mainContent.innerHTML = '<div class="spinner"></div>';

    try {
        const schedules = await api.listSchedules();
        renderSchedulesList(schedules);
    } catch (error) {
        console.error('Failed to load schedules:', error);
        mainContent.innerHTML = `
            <div class="alert alert-error">
                <div class="alert-icon">✕</div>
                <div class="alert-content">
                    <div class="alert-title">Failed to load schedules</div>
                    ${error.message}
                </div>
            </div>
        `;
    }
}

function renderSchedulesList(schedules) {
    const mainContent = document.getElementById('mainContent');

    if (schedules.length === 0) {
        mainContent.innerHTML = `
            <div class="card">
                <div class="card-body">
                    <div class="empty-state">
                        <div class="empty-state-icon">📅</div>
                        <div class="empty-state-title">No schedules configured</div>
                        <div class="empty-state-description">
                            Create a backup schedule to automate your backups
                        </div>
                        <button class="btn btn-primary" onclick="showCreateScheduleDialog()">
                            Create Schedule
                        </button>
                    </div>
                </div>
            </div>
        `;
        return;
    }

    const enabledCount = schedules.filter(s => s.enabled).length;
    const disabledCount = schedules.length - enabledCount;

    mainContent.innerHTML = `
        <!-- Summary -->
        <div class="stats-grid" style="margin-bottom: 1.5rem;">
            <div class="stat-card">
                <div class="stat-icon primary">📅</div>
                <div class="stat-content">
                    <div class="stat-label">Total Schedules</div>
                    <div class="stat-value">${schedules.length}</div>
                </div>
            </div>
            <div class="stat-card">
                <div class="stat-icon success">✓</div>
                <div class="stat-content">
                    <div class="stat-label">Enabled</div>
                    <div class="stat-value">${enabledCount}</div>
                </div>
            </div>
            <div class="stat-card">
                <div class="stat-icon error">⏸</div>
                <div class="stat-content">
                    <div class="stat-label">Disabled</div>
                    <div class="stat-value">${disabledCount}</div>
                </div>
            </div>
        </div>

        <!-- Schedules Table -->
        <div class="card">
            <div class="card-header">
                <h3 class="card-title">All Schedules</h3>
            </div>
            <div class="card-body">
                <div class="table-container">
                    <table class="table">
                        <thead>
                            <tr>
                                <th>Name</th>
                                <th>Source Type</th>
                                <th>Schedule Type</th>
                                <th>Cron Expression</th>
                                <th>Last Run</th>
                                <th>Next Run</th>
                                <th>Status</th>
                                <th>Actions</th>
                            </tr>
                        </thead>
                        <tbody>
                            ${schedules.map(schedule => `
                                <tr>
                                    <td><strong>${schedule.name}</strong></td>
                                    <td><span class="badge badge-primary">${schedule.source_type}</span></td>
                                    <td><span class="badge badge-info">${schedule.schedule_type}</span></td>
                                    <td>
                                        <code style="font-size: 0.8rem;">${schedule.cron_expression}</code>
                                        <div style="font-size: 0.75rem; color: var(--text-secondary);">
                                            ${formatCronExpression(schedule.cron_expression)}
                                        </div>
                                    </td>
                                    <td>${formatDateRelative(schedule.last_run)}</td>
                                    <td>${schedule.next_run ? formatDate(schedule.next_run) : 'Not scheduled'}</td>
                                    <td>
                                        <span class="badge ${schedule.enabled ? 'badge-success' : 'badge-error'}">
                                            ${schedule.enabled ? 'Enabled' : 'Disabled'}
                                        </span>
                                    </td>
                                    <td>
                                        <button class="btn btn-sm btn-secondary" onclick="viewScheduleDetails(${schedule.id})">
                                            View
                                        </button>
                                        <button class="btn btn-sm btn-primary" onclick="triggerSchedule(${schedule.id})">
                                            Run Now
                                        </button>
                                        <button class="btn btn-sm btn-secondary" onclick="editSchedule(${schedule.id})">
                                            Edit
                                        </button>
                                        <button class="btn btn-sm btn-danger" onclick="deleteScheduleConfirm(${schedule.id})">
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

async function showCreateScheduleDialog() {
    // This would need to fetch VMs, containers, and storage backends
    // For now, showing a simplified version
    const modal = new Modal('Create Backup Schedule', `
        <form id="createScheduleForm">
            <div class="form-group">
                <label class="form-label required">Name</label>
                <input type="text" class="form-input" name="name" required>
            </div>

            <div class="form-group">
                <label class="form-label required">Source Type</label>
                <select class="form-select" name="source_type" required>
                    <option value="vm">Virtual Machine (KVM)</option>
                    <option value="container">Container (Podman)</option>
                </select>
            </div>

            <div class="form-group">
                <label class="form-label required">Source ID</label>
                <input type="number" class="form-input" name="source_id" required>
                <div class="form-help">ID of the VM or container to backup</div>
            </div>

            <div class="form-group">
                <label class="form-label required">Schedule Type</label>
                <select class="form-select" name="schedule_type" required>
                    <option value="daily">Daily</option>
                    <option value="weekly">Weekly</option>
                    <option value="monthly">Monthly</option>
                    <option value="custom">Custom</option>
                </select>
            </div>

            <div class="form-group">
                <label class="form-label required">Cron Expression</label>
                <input type="text" class="form-input" name="cron_expression"
                       value="0 2 * * *" required>
                <div class="form-help">Examples: "0 2 * * *" (daily at 2 AM), "0 2 * * 0" (Sundays at 2 AM)</div>
            </div>

            <div class="form-group">
                <label class="form-label required">Storage Backend ID</label>
                <input type="number" class="form-input" name="storage_backend_id" required>
                <div class="form-help">ID of the storage backend to use</div>
            </div>

            <div class="form-group">
                <label class="form-label">Retention - Daily (days)</label>
                <input type="number" class="form-input" name="retention_daily" value="7">
            </div>

            <div class="form-group">
                <label class="form-label">Retention - Weekly (weeks)</label>
                <input type="number" class="form-input" name="retention_weekly" value="4">
            </div>

            <div class="form-group">
                <label class="form-label">Retention - Monthly (months)</label>
                <input type="number" class="form-input" name="retention_monthly" value="12">
            </div>

            <div class="form-group">
                <label style="display: flex; align-items: center; gap: 0.5rem;">
                    <input type="checkbox" name="enabled" checked>
                    <span>Enable schedule immediately</span>
                </label>
            </div>
        </form>
    `);

    modal.setOnConfirm(async () => {
        try {
            const form = document.getElementById('createScheduleForm');
            const data = getFormData(form);

            // Build retention config
            data.retention_config = {
                daily: data.retention_daily || 7,
                weekly: data.retention_weekly || 4,
                monthly: data.retention_monthly || 12,
                yearly: 5
            };
            delete data.retention_daily;
            delete data.retention_weekly;
            delete data.retention_monthly;

            const loading = showLoading(modal.overlay);
            await api.createSchedule(data);
            hideLoading(loading);

            notify.success('Schedule created successfully');
            modal.close();
            renderSchedules();

        } catch (error) {
            notify.error('Failed to create schedule: ' + error.message);
        }
    });

    modal.show();
}

async function viewScheduleDetails(scheduleId) {
    try {
        const schedule = await api.getSchedule(scheduleId);

        const modal = new Modal('Schedule Details', `
            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 1rem;">
                <div>
                    <strong>ID:</strong> ${schedule.id}
                </div>
                <div>
                    <strong>Name:</strong> ${schedule.name}
                </div>
                <div>
                    <strong>Source Type:</strong> ${schedule.source_type}
                </div>
                <div>
                    <strong>Source ID:</strong> ${schedule.source_id}
                </div>
                <div>
                    <strong>Schedule Type:</strong> ${schedule.schedule_type}
                </div>
                <div>
                    <strong>Storage Backend ID:</strong> ${schedule.storage_backend_id}
                </div>
                <div style="grid-column: 1 / -1;">
                    <strong>Cron Expression:</strong>
                    <code>${schedule.cron_expression}</code>
                    <div style="font-size: 0.875rem; color: var(--text-secondary); margin-top: 0.25rem;">
                        ${formatCronExpression(schedule.cron_expression)}
                    </div>
                </div>
                <div>
                    <strong>Last Run:</strong> ${formatDate(schedule.last_run)}
                </div>
                <div>
                    <strong>Next Run:</strong> ${schedule.next_run ? formatDate(schedule.next_run) : 'Not scheduled'}
                </div>
                <div>
                    <strong>Status:</strong>
                    <span class="badge ${schedule.enabled ? 'badge-success' : 'badge-error'}">
                        ${schedule.enabled ? 'Enabled' : 'Disabled'}
                    </span>
                </div>
                <div style="grid-column: 1 / -1;">
                    <strong>Retention Policy:</strong>
                    <div style="margin-top: 0.5rem; display: grid; grid-template-columns: repeat(4, 1fr); gap: 0.5rem;">
                        <div class="badge badge-info">Daily: ${schedule.retention_config?.daily || 0}</div>
                        <div class="badge badge-info">Weekly: ${schedule.retention_config?.weekly || 0}</div>
                        <div class="badge badge-info">Monthly: ${schedule.retention_config?.monthly || 0}</div>
                        <div class="badge badge-info">Yearly: ${schedule.retention_config?.yearly || 0}</div>
                    </div>
                </div>
            </div>
        `);

        modal.overlay.querySelector('.modal-footer').style.display = 'none';
        modal.show();

    } catch (error) {
        notify.error('Failed to load schedule details: ' + error.message);
    }
}

async function triggerSchedule(scheduleId) {
    showConfirmDialog(
        'Run Schedule Now',
        'This will trigger an immediate backup. Continue?',
        async () => {
            try {
                await api.triggerSchedule(scheduleId);
                notify.success('Backup triggered successfully');
                setTimeout(() => loadView('jobs'), 1000);
            } catch (error) {
                notify.error('Failed to trigger schedule: ' + error.message);
            }
        }
    );
}

async function editSchedule(scheduleId) {
    // Similar to create but pre-filled with existing data
    notify.info('Edit functionality coming soon');
}

async function deleteScheduleConfirm(scheduleId) {
    showConfirmDialog(
        'Delete Schedule',
        'Are you sure you want to delete this schedule? This will not delete existing backups.',
        async () => {
            try {
                await api.deleteSchedule(scheduleId);
                notify.success('Schedule deleted successfully');
                renderSchedules();
            } catch (error) {
                notify.error('Failed to delete schedule: ' + error.message);
            }
        }
    );
}
