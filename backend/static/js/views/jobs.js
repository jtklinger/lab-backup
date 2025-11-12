/**
 * Jobs View
 */

async function renderJobs() {
    const mainContent = document.getElementById('mainContent');
    const headerActions = document.getElementById('headerActions');

    headerActions.innerHTML = `
        <button class="btn btn-secondary btn-sm" onclick="renderJobs()">
            🔄 Refresh
        </button>
    `;

    mainContent.innerHTML = '<div class="spinner"></div>';

    try {
        const jobs = await api.listJobs({ limit: 100 });
        renderJobsList(jobs);
    } catch (error) {
        console.error('Failed to load jobs:', error);
        mainContent.innerHTML = `
            <div class="alert alert-error">
                <div class="alert-icon">✕</div>
                <div class="alert-content">
                    <div class="alert-title">Failed to load jobs</div>
                    ${error.message}
                </div>
            </div>
        `;
    }
}

function renderJobsList(jobs) {
    const mainContent = document.getElementById('mainContent');

    if (jobs.length === 0) {
        mainContent.innerHTML = `
            <div class="card">
                <div class="card-body">
                    <div class="empty-state">
                        <div class="empty-state-icon">⚙️</div>
                        <div class="empty-state-title">No jobs found</div>
                        <div class="empty-state-description">
                            Jobs will appear here when backups are running
                        </div>
                    </div>
                </div>
            </div>
        `;
        return;
    }

    const statusCounts = {
        running: jobs.filter(j => j.status === 'running').length,
        completed: jobs.filter(j => j.status === 'completed').length,
        failed: jobs.filter(j => j.status === 'failed').length,
        pending: jobs.filter(j => j.status === 'pending').length,
    };

    mainContent.innerHTML = `
        <div class="stats-grid" style="margin-bottom: 1.5rem;">
            <div class="stat-card">
                <div class="stat-icon primary">⏳</div>
                <div class="stat-content">
                    <div class="stat-label">Running</div>
                    <div class="stat-value">${statusCounts.running}</div>
                </div>
            </div>
            <div class="stat-card">
                <div class="stat-icon success">✓</div>
                <div class="stat-content">
                    <div class="stat-label">Completed</div>
                    <div class="stat-value">${statusCounts.completed}</div>
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

        <div class="card">
            <div class="card-header">
                <h3 class="card-title">All Jobs</h3>
            </div>
            <div class="card-body">
                <div class="table-container">
                    <table class="table">
                        <thead>
                            <tr>
                                <th>ID</th>
                                <th>Type</th>
                                <th>Status</th>
                                <th>Started</th>
                                <th>Completed</th>
                                <th>Duration</th>
                                <th>Actions</th>
                            </tr>
                        </thead>
                        <tbody>
                            ${jobs.map(job => `
                                <tr>
                                    <td>${job.id}</td>
                                    <td><span class="badge badge-primary">${job.type}</span></td>
                                    <td>${getStatusBadge(job.status)}</td>
                                    <td>${formatDate(job.started_at)}</td>
                                    <td>${job.completed_at ? formatDate(job.completed_at) : '-'}</td>
                                    <td>${calculateDuration(job.started_at, job.completed_at)}</td>
                                    <td>
                                        <button class="btn btn-sm btn-secondary" onclick="viewJobLogs(${job.id})">
                                            View Logs
                                        </button>
                                        ${job.status === 'running' ? `
                                            <button class="btn btn-sm btn-danger" onclick="cancelJob(${job.id})">
                                                Cancel
                                            </button>
                                        ` : ''}
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

async function viewJobLogs(jobId) {
    try {
        const logs = await api.getJobLogs(jobId);

        const modal = new Modal('Job Logs', `
            <div style="background: #1e1e1e; color: #d4d4d4; padding: 1rem; border-radius: 0.375rem; font-family: monospace; font-size: 0.875rem; max-height: 400px; overflow-y: auto;">
                ${logs.length === 0 ? '<div>No logs available</div>' : logs.map(log => `
                    <div style="margin-bottom: 0.5rem;">
                        <span style="color: #888;">[${formatDate(log.timestamp)}]</span>
                        <span style="color: ${log.level === 'ERROR' ? '#f44' : log.level === 'WARNING' ? '#fa0' : '#4f4'};">${log.level}</span>
                        <span>${log.message}</span>
                    </div>
                `).join('')}
            </div>
        `);

        modal.overlay.querySelector('.modal-footer').style.display = 'none';
        modal.show();

    } catch (error) {
        notify.error('Failed to load job logs: ' + error.message);
    }
}

async function cancelJob(jobId) {
    showConfirmDialog(
        'Cancel Job',
        'Are you sure you want to cancel this job?',
        async () => {
            try {
                await api.cancelJob(jobId);
                notify.success('Job cancelled');
                renderJobs();
            } catch (error) {
                notify.error('Failed to cancel job: ' + error.message);
            }
        }
    );
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
