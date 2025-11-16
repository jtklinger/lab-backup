/**
 * Dashboard View
 */

// Auto-refresh state
let dashboardAutoRefreshInterval = null;

async function renderDashboard() {
    const mainContent = document.getElementById('mainContent');
    const headerActions = document.getElementById('headerActions');

    // Get auto-refresh settings from localStorage
    const autoRefreshEnabled = localStorage.getItem('dashboard_auto_refresh') === 'true';
    const refreshInterval = parseInt(localStorage.getItem('dashboard_refresh_interval')) || 60;

    // Add refresh controls to header
    headerActions.innerHTML = `
        <div style="display: flex; gap: 0.5rem; align-items: center;">
            <button class="btn btn-secondary btn-sm" onclick="loadDashboardData()" title="Refresh dashboard">
                🔄 Refresh
            </button>
            <label style="display: flex; align-items: center; gap: 0.5rem; margin: 0; font-size: 0.875rem;">
                <input type="checkbox" id="autoRefreshToggle" ${autoRefreshEnabled ? 'checked' : ''}
                    onchange="toggleDashboardAutoRefresh()" style="margin: 0;">
                <span>Auto-refresh</span>
            </label>
            <select id="refreshIntervalSelect" class="form-control" style="width: auto; padding: 0.25rem 0.5rem; font-size: 0.875rem;"
                onchange="updateDashboardRefreshInterval()" ${!autoRefreshEnabled ? 'disabled' : ''}>
                <option value="30" ${refreshInterval === 30 ? 'selected' : ''}>30s</option>
                <option value="60" ${refreshInterval === 60 ? 'selected' : ''}>60s</option>
                <option value="120" ${refreshInterval === 120 ? 'selected' : ''}>2m</option>
                <option value="300" ${refreshInterval === 300 ? 'selected' : ''}>5m</option>
            </select>
        </div>
    `;

    // Initialize auto-refresh if enabled
    if (autoRefreshEnabled) {
        startDashboardAutoRefresh(refreshInterval);
    }

    // Load dashboard data
    await loadDashboardData();
}

async function loadDashboardData() {
    const mainContent = document.getElementById('mainContent');

    // Show loading
    mainContent.innerHTML = '<div class="spinner"></div>';

    try {
        // Fetch dashboard data in parallel
        const [backups, schedules, jobs, storageBackends] = await Promise.all([
            api.listBackups({ limit: 10 }),
            api.listSchedules({ limit: 100 }),
            api.listJobs({ limit: 10 }),
            api.listStorageBackends(),
        ]);

        // Calculate stats
        const stats = {
            totalBackups: backups.length,
            activeSchedules: schedules.filter(s => s.enabled).length,
            runningJobs: jobs.filter(j => j.status === 'running').length,
            failedBackups: backups.filter(b => b.status === 'failed').length,
            storageUsed: calculateStorageUsed(storageBackends),
            recentBackups: backups.slice(0, 5),
            recentJobs: jobs.slice(0, 5),
        };

        renderDashboardContent(stats, schedules, storageBackends);

    } catch (error) {
        console.error('Failed to load dashboard:', error);
        mainContent.innerHTML = `
            <div class="alert alert-error">
                <div class="alert-icon">✕</div>
                <div class="alert-content">
                    <div class="alert-title">Failed to load dashboard</div>
                    ${error.message}
                </div>
            </div>
        `;
    }
}

function calculateStorageUsed(backends) {
    return backends.reduce((total, backend) => {
        return total + (backend.used || 0);
    }, 0);
}

function renderDashboardContent(stats, schedules, storageBackends) {
    const mainContent = document.getElementById('mainContent');

    mainContent.innerHTML = `
        <!-- Stats Grid -->
        <div class="stats-grid">
            <div class="stat-card">
                <div class="stat-icon primary">💾</div>
                <div class="stat-content">
                    <div class="stat-label">Total Backups</div>
                    <div class="stat-value">${stats.totalBackups}</div>
                </div>
            </div>

            <div class="stat-card">
                <div class="stat-icon success">📅</div>
                <div class="stat-content">
                    <div class="stat-label">Active Schedules</div>
                    <div class="stat-value">${stats.activeSchedules}</div>
                </div>
            </div>

            <div class="stat-card">
                <div class="stat-icon ${stats.runningJobs > 0 ? 'info' : 'primary'}">⚙️</div>
                <div class="stat-content">
                    <div class="stat-label">Running Jobs</div>
                    <div class="stat-value">${stats.runningJobs}</div>
                </div>
            </div>

            <div class="stat-card">
                <div class="stat-icon ${stats.failedBackups > 0 ? 'error' : 'success'}">
                    ${stats.failedBackups > 0 ? '⚠' : '✓'}
                </div>
                <div class="stat-content">
                    <div class="stat-label">Failed Backups</div>
                    <div class="stat-value">${stats.failedBackups}</div>
                </div>
            </div>
        </div>

        <!-- Recent Activity -->
        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 1.5rem; margin-bottom: 1.5rem;">
            <!-- Recent Backups -->
            <div class="card">
                <div class="card-header">
                    <h3 class="card-title">Recent Backups</h3>
                    <a href="#backups" class="btn btn-sm btn-secondary">View All</a>
                </div>
                <div class="card-body">
                    ${stats.recentBackups.length === 0 ? `
                        <div class="empty-state">
                            <div class="empty-state-icon">💾</div>
                            <div class="empty-state-title">No backups yet</div>
                            <div class="empty-state-description">Create a backup schedule to get started</div>
                        </div>
                    ` : `
                        <div class="table-container">
                            <table class="table">
                                <thead>
                                    <tr>
                                        <th>Source</th>
                                        <th>Type</th>
                                        <th>Status</th>
                                        <th>Date</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    ${stats.recentBackups.map(backup => `
                                        <tr>
                                            <td>${backup.source_name}</td>
                                            <td><span class="badge badge-primary">${backup.backup_type}</span></td>
                                            <td>${getStatusBadge(backup.status)}</td>
                                            <td>${formatDateRelative(backup.created_at)}</td>
                                        </tr>
                                    `).join('')}
                                </tbody>
                            </table>
                        </div>
                    `}
                </div>
            </div>

            <!-- Recent Jobs -->
            <div class="card">
                <div class="card-header">
                    <h3 class="card-title">Recent Jobs</h3>
                    <a href="#jobs" class="btn btn-sm btn-secondary">View All</a>
                </div>
                <div class="card-body">
                    ${stats.recentJobs.length === 0 ? `
                        <div class="empty-state">
                            <div class="empty-state-icon">⚙️</div>
                            <div class="empty-state-title">No jobs yet</div>
                            <div class="empty-state-description">Jobs will appear here when backups run</div>
                        </div>
                    ` : `
                        <div class="table-container">
                            <table class="table">
                                <thead>
                                    <tr>
                                        <th>Type</th>
                                        <th>Status</th>
                                        <th>Started</th>
                                        <th>Duration</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    ${stats.recentJobs.map(job => `
                                        <tr>
                                            <td><span class="badge badge-primary">${job.type}</span></td>
                                            <td>${getStatusBadge(job.status)}</td>
                                            <td>${formatDateRelative(job.started_at)}</td>
                                            <td>${calculateDuration(job.started_at, job.completed_at)}</td>
                                        </tr>
                                    `).join('')}
                                </tbody>
                            </table>
                        </div>
                    `}
                </div>
            </div>
        </div>

        <!-- Schedules Overview -->
        <div class="card">
            <div class="card-header">
                <h3 class="card-title">Backup Schedules</h3>
                <a href="#schedules" class="btn btn-sm btn-primary">Manage Schedules</a>
            </div>
            <div class="card-body">
                ${schedules.length === 0 ? `
                    <div class="empty-state">
                        <div class="empty-state-icon">📅</div>
                        <div class="empty-state-title">No schedules configured</div>
                        <div class="empty-state-description">Create a backup schedule to automate your backups</div>
                        <a href="#schedules" class="btn btn-primary">Create Schedule</a>
                    </div>
                ` : `
                    <div class="table-container">
                        <table class="table">
                            <thead>
                                <tr>
                                    <th>Name</th>
                                    <th>Type</th>
                                    <th>Schedule</th>
                                    <th>Last Run</th>
                                    <th>Next Run</th>
                                    <th>Status</th>
                                </tr>
                            </thead>
                            <tbody>
                                ${schedules.slice(0, 10).map(schedule => `
                                    <tr>
                                        <td>${schedule.name}</td>
                                        <td><span class="badge badge-primary">${schedule.source_type}</span></td>
                                        <td>${formatCronExpression(schedule.cron_expression)}</td>
                                        <td>${formatDateRelative(schedule.last_run)}</td>
                                        <td>${formatDate(schedule.next_run)}</td>
                                        <td>
                                            <span class="badge ${schedule.enabled ? 'badge-success' : 'badge-error'}">
                                                ${schedule.enabled ? 'Enabled' : 'Disabled'}
                                            </span>
                                        </td>
                                    </tr>
                                `).join('')}
                            </tbody>
                        </table>
                    </div>
                `}
            </div>
        </div>

        <!-- Storage Overview -->
        <div class="card">
            <div class="card-header">
                <h3 class="card-title">Storage Backends</h3>
                <a href="#storage" class="btn btn-sm btn-secondary">Manage Storage</a>
            </div>
            <div class="card-body">
                ${storageBackends.length === 0 ? `
                    <div class="empty-state">
                        <div class="empty-state-icon">💿</div>
                        <div class="empty-state-title">No storage backends configured</div>
                        <div class="empty-state-description">Add a storage backend to store your backups</div>
                        <a href="#storage" class="btn btn-primary">Add Storage Backend</a>
                    </div>
                ` : `
                    <div class="table-container">
                        <table class="table">
                            <thead>
                                <tr>
                                    <th>Name</th>
                                    <th>Type</th>
                                    <th>Usage</th>
                                    <th>Capacity</th>
                                    <th>Status</th>
                                </tr>
                            </thead>
                            <tbody>
                                ${storageBackends.map(backend => {
                                    const usedGB = backend.used || 0;
                                    const capacityGB = backend.capacity || 0;
                                    const percentage = capacityGB > 0 ? Math.round((usedGB / capacityGB) * 100) : 0;

                                    return `
                                        <tr>
                                            <td>${backend.name}</td>
                                            <td><span class="badge badge-primary">${backend.type}</span></td>
                                            <td>${usedGB} GB</td>
                                            <td>${capacityGB > 0 ? capacityGB + ' GB' : 'Unknown'}</td>
                                            <td>
                                                <span class="badge ${backend.enabled ? 'badge-success' : 'badge-error'}">
                                                    ${backend.enabled ? 'Enabled' : 'Disabled'}
                                                </span>
                                                ${percentage > backend.threshold ? `
                                                    <span class="badge badge-warning">
                                                        ${percentage}% full
                                                    </span>
                                                ` : ''}
                                            </td>
                                        </tr>
                                    `;
                                }).join('')}
                            </tbody>
                        </table>
                    </div>
                `}
            </div>
        </div>
    `;
}

function calculateDuration(startedAt, completedAt) {
    if (!startedAt) return 'N/A';
    if (!completedAt) return 'In progress';

    const start = new Date(startedAt);
    const end = new Date(completedAt);
    const diff = end - start;

    const seconds = Math.floor(diff / 1000);
    const minutes = Math.floor(seconds / 60);
    const hours = Math.floor(minutes / 60);

    if (hours > 0) return `${hours}h ${minutes % 60}m`;
    if (minutes > 0) return `${minutes}m ${seconds % 60}s`;
    return `${seconds}s`;
}

// Auto-refresh control functions
function toggleDashboardAutoRefresh() {
    const toggle = document.getElementById('autoRefreshToggle');
    const intervalSelect = document.getElementById('refreshIntervalSelect');
    const enabled = toggle.checked;

    // Save to localStorage
    localStorage.setItem('dashboard_auto_refresh', enabled);

    // Enable/disable interval selector
    intervalSelect.disabled = !enabled;

    if (enabled) {
        const interval = parseInt(intervalSelect.value);
        startDashboardAutoRefresh(interval);
        notify.success(`Auto-refresh enabled (every ${formatInterval(interval)})`);
    } else {
        stopDashboardAutoRefresh();
        notify.info('Auto-refresh disabled');
    }
}

function updateDashboardRefreshInterval() {
    const intervalSelect = document.getElementById('refreshIntervalSelect');
    const interval = parseInt(intervalSelect.value);

    // Save to localStorage
    localStorage.setItem('dashboard_refresh_interval', interval);

    // Restart auto-refresh with new interval
    const toggle = document.getElementById('autoRefreshToggle');
    if (toggle.checked) {
        startDashboardAutoRefresh(interval);
        notify.success(`Refresh interval updated to ${formatInterval(interval)}`);
    }
}

function startDashboardAutoRefresh(intervalSeconds) {
    // Clear existing interval
    stopDashboardAutoRefresh();

    // Set new interval
    dashboardAutoRefreshInterval = setInterval(() => {
        console.log('Auto-refreshing dashboard...');
        loadDashboardData();
    }, intervalSeconds * 1000);
}

function stopDashboardAutoRefresh() {
    if (dashboardAutoRefreshInterval) {
        clearInterval(dashboardAutoRefreshInterval);
        dashboardAutoRefreshInterval = null;
    }
}

function formatInterval(seconds) {
    if (seconds < 60) return `${seconds}s`;
    const minutes = Math.floor(seconds / 60);
    return `${minutes}m`;
}

// Clean up auto-refresh when navigating away from dashboard
window.addEventListener('hashchange', () => {
    if (!window.location.hash.includes('dashboard')) {
        stopDashboardAutoRefresh();
    }
});
