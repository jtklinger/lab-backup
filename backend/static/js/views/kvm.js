/**
 * KVM Infrastructure View
 */

async function renderKVM() {
    const mainContent = document.getElementById('mainContent');
    const headerActions = document.getElementById('headerActions');

    headerActions.innerHTML = `
        <button class="btn btn-primary btn-sm" onclick="showAddKVMHostDialog()">
            + Add KVM Host
        </button>
        <button class="btn btn-secondary btn-sm" onclick="renderKVM()">
            🔄 Refresh
        </button>
    `;

    mainContent.innerHTML = '<div class="spinner"></div>';

    try {
        const [hosts, vms] = await Promise.all([
            api.listKVMHosts(),
            api.listVMs(),
        ]);
        renderKVMContent(hosts, vms);
    } catch (error) {
        console.error('Failed to load KVM infrastructure:', error);
        mainContent.innerHTML = `
            <div class="alert alert-error">
                <div class="alert-icon">✕</div>
                <div class="alert-content">
                    <div class="alert-title">Failed to load KVM infrastructure</div>
                    ${error.message}
                </div>
            </div>
        `;
    }
}

function renderKVMContent(hosts, vms) {
    const mainContent = document.getElementById('mainContent');

    if (hosts.length === 0) {
        mainContent.innerHTML = `
            <div class="card">
                <div class="card-body">
                    <div class="empty-state">
                        <div class="empty-state-icon">🖥️</div>
                        <div class="empty-state-title">No KVM hosts configured</div>
                        <div class="empty-state-description">
                            Add a KVM host to start backing up virtual machines
                        </div>
                        <button class="btn btn-primary" onclick="showAddKVMHostDialog()">
                            Add KVM Host
                        </button>
                    </div>
                </div>
            </div>
        `;
        return;
    }

    const totalVMs = vms.length;
    const runningVMs = vms.filter(vm => vm.state === 'running').length;

    mainContent.innerHTML = `
        <div class="stats-grid" style="margin-bottom: 1.5rem;">
            <div class="stat-card">
                <div class="stat-icon primary">🖥️</div>
                <div class="stat-content">
                    <div class="stat-label">KVM Hosts</div>
                    <div class="stat-value">${hosts.length}</div>
                </div>
            </div>
            <div class="stat-card">
                <div class="stat-icon info">💻</div>
                <div class="stat-content">
                    <div class="stat-label">Total VMs</div>
                    <div class="stat-value">${totalVMs}</div>
                </div>
            </div>
            <div class="stat-card">
                <div class="stat-icon success">▶️</div>
                <div class="stat-content">
                    <div class="stat-label">Running VMs</div>
                    <div class="stat-value">${runningVMs}</div>
                </div>
            </div>
        </div>

        <!-- KVM Hosts -->
        <div class="card" style="margin-bottom: 1.5rem;">
            <div class="card-header">
                <h3 class="card-title">KVM Hosts</h3>
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
                                        <button class="btn btn-sm btn-primary" onclick="refreshKVMHost(${host.id})">
                                            Refresh
                                        </button>
                                        <button class="btn btn-sm btn-danger" onclick="deleteKVMHost(${host.id})">
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

        <!-- Virtual Machines -->
        <div class="card">
            <div class="card-header">
                <h3 class="card-title">Virtual Machines</h3>
            </div>
            <div class="card-body">
                ${vms.length === 0 ? `
                    <div class="empty-state">
                        <div class="empty-state-icon">💻</div>
                        <div class="empty-state-title">No VMs found</div>
                        <div class="empty-state-description">Refresh your KVM hosts to discover VMs</div>
                    </div>
                ` : `
                    <div class="table-container">
                        <table class="table">
                            <thead>
                                <tr>
                                    <th>Name</th>
                                    <th>UUID</th>
                                    <th>State</th>
                                    <th>CPUs</th>
                                    <th>Memory</th>
                                    <th>Host</th>
                                    <th>Actions</th>
                                </tr>
                            </thead>
                            <tbody>
                                ${vms.map(vm => `
                                    <tr>
                                        <td><strong>${vm.name}</strong></td>
                                        <td><code style="font-size: 0.75rem;">${vm.uuid}</code></td>
                                        <td>
                                            <span class="badge ${vm.state === 'running' ? 'badge-success' : 'badge-error'}">
                                                ${vm.state}
                                            </span>
                                        </td>
                                        <td>${vm.vcpus || 'N/A'}</td>
                                        <td>${formatBytes((vm.memory || 0) * 1024)}</td>
                                        <td>${hosts.find(h => h.id === vm.kvm_host_id)?.name || 'Unknown'}</td>
                                        <td>
                                            <button class="btn btn-sm btn-primary" onclick="createVMSchedule(${vm.id})">
                                                Schedule Backup
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

function showAddKVMHostDialog() {
    const modal = new Modal('Add KVM Host', `
        <form id="addKVMHostForm">
            <div class="form-group">
                <label class="form-label required">Name</label>
                <input type="text" class="form-input" name="name" required>
            </div>
            <div class="form-group">
                <label class="form-label required">URI</label>
                <input type="text" class="form-input" name="uri"
                       placeholder="qemu+ssh://user@host/system" required>
                <div class="form-help">
                    Examples: qemu:///system (local), qemu+ssh://user@host/system (SSH)
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
            const form = document.getElementById('addKVMHostForm');
            const data = getFormData(form);

            const loading = showLoading(modal.overlay);
            await api.createKVMHost(data);
            hideLoading(loading);

            notify.success('KVM host added successfully');
            modal.close();
            renderKVM();
        } catch (error) {
            notify.error('Failed to add KVM host: ' + error.message);
        }
    });

    modal.show();
}

async function refreshKVMHost(hostId) {
    try {
        notify.info('Refreshing KVM host...');
        await api.refreshKVMHost(hostId);
        notify.success('KVM host refreshed');
        renderKVM();
    } catch (error) {
        notify.error('Failed to refresh KVM host: ' + error.message);
    }
}

async function deleteKVMHost(hostId) {
    showConfirmDialog(
        'Delete KVM Host',
        'Are you sure? This will also delete all VM records from this host.',
        async () => {
            try {
                await api.deleteKVMHost(hostId);
                notify.success('KVM host deleted');
                renderKVM();
            } catch (error) {
                notify.error('Failed to delete KVM host: ' + error.message);
            }
        }
    );
}

function createVMSchedule(vmId) {
    // Switch to schedules view with pre-filled VM ID
    loadView('schedules');
    setTimeout(() => showCreateScheduleDialog(), 500);
}
