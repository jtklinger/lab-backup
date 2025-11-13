/**
 * Podman Infrastructure View
 */

async function renderPodman() {
    const mainContent = document.getElementById('mainContent');
    const headerActions = document.getElementById('headerActions');

    headerActions.innerHTML = `
        <button class="btn btn-primary btn-sm" onclick="showAddPodmanHostDialog()">
            + Add Podman Host
        </button>
        <button class="btn btn-secondary btn-sm" onclick="renderPodman()">
            🔄 Refresh
        </button>
    `;

    mainContent.innerHTML = '<div class="spinner"></div>';

    try {
        const [hosts, containers] = await Promise.all([
            api.listPodmanHosts(),
            api.listContainers(),
        ]);
        renderPodmanContent(hosts, containers);
    } catch (error) {
        console.error('Failed to load Podman infrastructure:', error);
        mainContent.innerHTML = `
            <div class="alert alert-error">
                <div class="alert-icon">✕</div>
                <div class="alert-content">
                    <div class="alert-title">Failed to load Podman infrastructure</div>
                    ${error.message}
                </div>
            </div>
        `;
    }
}

function renderPodmanContent(hosts, containers) {
    const mainContent = document.getElementById('mainContent');

    if (hosts.length === 0) {
        mainContent.innerHTML = `
            <div class="card">
                <div class="card-body">
                    <div class="empty-state">
                        <div class="empty-state-icon">📦</div>
                        <div class="empty-state-title">No Podman hosts configured</div>
                        <div class="empty-state-description">
                            Add a Podman host to start backing up containers
                        </div>
                        <button class="btn btn-primary" onclick="showAddPodmanHostDialog()">
                            Add Podman Host
                        </button>
                    </div>
                </div>
            </div>
        `;
        return;
    }

    const totalContainers = containers.length;
    const runningContainers = containers.filter(c => c.state === 'running').length;

    mainContent.innerHTML = `
        <div class="stats-grid" style="margin-bottom: 1.5rem;">
            <div class="stat-card">
                <div class="stat-icon primary">📦</div>
                <div class="stat-content">
                    <div class="stat-label">Podman Hosts</div>
                    <div class="stat-value">${hosts.length}</div>
                </div>
            </div>
            <div class="stat-card">
                <div class="stat-icon info">🐋</div>
                <div class="stat-content">
                    <div class="stat-label">Total Containers</div>
                    <div class="stat-value">${totalContainers}</div>
                </div>
            </div>
            <div class="stat-card">
                <div class="stat-icon success">▶️</div>
                <div class="stat-content">
                    <div class="stat-label">Running</div>
                    <div class="stat-value">${runningContainers}</div>
                </div>
            </div>
        </div>

        <!-- Podman Hosts -->
        <div class="card" style="margin-bottom: 1.5rem;">
            <div class="card-header">
                <h3 class="card-title">Podman Hosts</h3>
            </div>
            <div class="card-body">
                <div class="table-container">
                    <table class="table">
                        <thead>
                            <tr>
                                <th>Name</th>
                                <th>URI</th>
                                <th>Status</th>
                                <th>Last Checked</th>
                                <th>Actions</th>
                            </tr>
                        </thead>
                        <tbody>
                            ${hosts.map(host => `
                                <tr>
                                    <td><strong>${host.name}</strong></td>
                                    <td><code style="font-size: 0.8rem;">${host.uri}</code></td>
                                    <td>
                                        <span class="badge ${host.enabled ? 'badge-success' : 'badge-error'}">
                                            ${host.enabled ? 'Active' : 'Disabled'}
                                        </span>
                                    </td>
                                    <td>${formatDateRelative(host.last_check)}</td>
                                    <td>
                                        <button class="btn btn-sm btn-primary" onclick="refreshPodmanHost(${host.id})">
                                            Refresh
                                        </button>
                                        <button class="btn btn-sm btn-danger" onclick="deletePodmanHost(${host.id})">
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

        <!-- Containers -->
        <div class="card">
            <div class="card-header">
                <h3 class="card-title">Containers</h3>
            </div>
            <div class="card-body">
                ${containers.length === 0 ? `
                    <div class="empty-state">
                        <div class="empty-state-icon">🐋</div>
                        <div class="empty-state-title">No containers found</div>
                        <div class="empty-state-description">Refresh your Podman hosts to discover containers</div>
                    </div>
                ` : `
                    <div class="table-container">
                        <table class="table">
                            <thead>
                                <tr>
                                    <th>Name</th>
                                    <th>Container ID</th>
                                    <th>Image</th>
                                    <th>State</th>
                                    <th>Host</th>
                                    <th>Actions</th>
                                </tr>
                            </thead>
                            <tbody>
                                ${containers.map(container => `
                                    <tr>
                                        <td><strong>${container.name}</strong></td>
                                        <td><code style="font-size: 0.75rem;">${container.container_id.substring(0, 12)}</code></td>
                                        <td>${container.image || 'N/A'}</td>
                                        <td>
                                            <span class="badge ${container.state === 'running' ? 'badge-success' : 'badge-error'}">
                                                ${container.state}
                                            </span>
                                        </td>
                                        <td>${hosts.find(h => h.id === container.podman_host_id)?.name || 'Unknown'}</td>
                                        <td>
                                            <button class="btn btn-sm btn-success" onclick="showBackupNowDialog('container', ${container.id}, '${container.name}')">
                                                ⚡ Backup Now
                                            </button>
                                            <button class="btn btn-sm btn-primary" onclick="createContainerSchedule(${container.id})">
                                                📅 Schedule
                                            </button>
                                        </td>
                                    </tr>
                                `).join('')}
                            </tbody>
                        </table>
                    </div>
                `}
            </div>
        </div>
    `;
}

function showAddPodmanHostDialog() {
    const modal = new Modal('Add Podman Host', `
        <form id="addPodmanHostForm">
            <div class="form-group">
                <label class="form-label required">Name</label>
                <input type="text" class="form-input" name="name" required>
            </div>
            <div class="form-group">
                <label class="form-label required">URI</label>
                <input type="text" class="form-input" name="uri"
                       placeholder="unix:///run/podman/podman.sock" required>
                <div class="form-help">
                    Examples: unix:///run/podman/podman.sock (local), ssh://user@host/run/podman/podman.sock (SSH)
                </div>
            </div>
            <div class="form-group">
                <label style="display: flex; align-items: center; gap: 0.5rem;">
                    <input type="checkbox" name="enabled" checked>
                    <span>Enable host</span>
                </label>
            </div>
        </form>
    `);

    modal.setOnConfirm(async () => {
        try {
            const form = document.getElementById('addPodmanHostForm');
            const data = getFormData(form);

            const loading = showLoading(modal.overlay);
            await api.createPodmanHost(data);
            hideLoading(loading);

            notify.success('Podman host added successfully');
            modal.close();
            renderPodman();
        } catch (error) {
            notify.error('Failed to add Podman host: ' + error.message);
        }
    });

    modal.show();
}

async function refreshPodmanHost(hostId) {
    try {
        notify.info('Refreshing Podman host...');
        await api.refreshPodmanHost(hostId);
        notify.success('Podman host refreshed');
        renderPodman();
    } catch (error) {
        notify.error('Failed to refresh Podman host: ' + error.message);
    }
}

async function deletePodmanHost(hostId) {
    showConfirmDialog(
        'Delete Podman Host',
        'Are you sure? This will also delete all container records from this host.',
        async () => {
            try {
                await api.deletePodmanHost(hostId);
                notify.success('Podman host deleted');
                renderPodman();
            } catch (error) {
                notify.error('Failed to delete Podman host: ' + error.message);
            }
        }
    );
}

function createContainerSchedule(containerId) {
    loadView('schedules');
    setTimeout(() => showCreateScheduleDialog(), 500);
}
