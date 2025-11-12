/**
 * Storage Backends View
 */

async function renderStorage() {
    const mainContent = document.getElementById('mainContent');
    const headerActions = document.getElementById('headerActions');

    headerActions.innerHTML = `
        <button class="btn btn-primary btn-sm" onclick="showAddStorageDialog()">
            + Add Storage Backend
        </button>
        <button class="btn btn-secondary btn-sm" onclick="renderStorage()">
            🔄 Refresh
        </button>
    `;

    mainContent.innerHTML = '<div class="spinner"></div>';

    try {
        const backends = await api.listStorageBackends();
        renderStorageList(backends);
    } catch (error) {
        console.error('Failed to load storage backends:', error);
        mainContent.innerHTML = `
            <div class="alert alert-error">
                <div class="alert-icon">✕</div>
                <div class="alert-content">
                    <div class="alert-title">Failed to load storage backends</div>
                    ${error.message}
                </div>
            </div>
        `;
    }
}

function renderStorageList(backends) {
    const mainContent = document.getElementById('mainContent');

    if (backends.length === 0) {
        mainContent.innerHTML = `
            <div class="card">
                <div class="card-body">
                    <div class="empty-state">
                        <div class="empty-state-icon">💿</div>
                        <div class="empty-state-title">No storage backends configured</div>
                        <div class="empty-state-description">
                            Add a storage backend to store your backups
                        </div>
                        <button class="btn btn-primary" onclick="showAddStorageDialog()">
                            Add Storage Backend
                        </button>
                    </div>
                </div>
            </div>
        `;
        return;
    }

    const totalCapacity = backends.reduce((sum, b) => sum + (b.capacity || 0), 0);
    const totalUsed = backends.reduce((sum, b) => sum + (b.used || 0), 0);

    mainContent.innerHTML = `
        <div class="stats-grid" style="margin-bottom: 1.5rem;">
            <div class="stat-card">
                <div class="stat-icon primary">💿</div>
                <div class="stat-content">
                    <div class="stat-label">Storage Backends</div>
                    <div class="stat-value">${backends.length}</div>
                </div>
            </div>
            <div class="stat-card">
                <div class="stat-icon info">📊</div>
                <div class="stat-content">
                    <div class="stat-label">Total Capacity</div>
                    <div class="stat-value">${totalCapacity} GB</div>
                </div>
            </div>
            <div class="stat-card">
                <div class="stat-icon warning">📈</div>
                <div class="stat-content">
                    <div class="stat-label">Total Used</div>
                    <div class="stat-value">${totalUsed} GB</div>
                </div>
            </div>
            <div class="stat-card">
                <div class="stat-icon ${totalCapacity > 0 && (totalUsed / totalCapacity * 100) > 80 ? 'error' : 'success'}">
                    ${totalCapacity > 0 && (totalUsed / totalCapacity * 100) > 80 ? '⚠' : '✓'}
                </div>
                <div class="stat-content">
                    <div class="stat-label">Usage</div>
                    <div class="stat-value">${totalCapacity > 0 ? Math.round((totalUsed / totalCapacity) * 100) : 0}%</div>
                </div>
            </div>
        </div>

        <div class="card">
            <div class="card-header">
                <h3 class="card-title">Storage Backends</h3>
            </div>
            <div class="card-body">
                <div class="table-container">
                    <table class="table">
                        <thead>
                            <tr>
                                <th>Name</th>
                                <th>Type</th>
                                <th>Usage</th>
                                <th>Capacity</th>
                                <th>Threshold</th>
                                <th>Last Check</th>
                                <th>Status</th>
                                <th>Actions</th>
                            </tr>
                        </thead>
                        <tbody>
                            ${backends.map(backend => {
                                const usedGB = backend.used || 0;
                                const capacityGB = backend.capacity || 0;
                                const percentage = capacityGB > 0 ? Math.round((usedGB / capacityGB) * 100) : 0;
                                const overThreshold = percentage > backend.threshold;

                                return `
                                    <tr>
                                        <td><strong>${backend.name}</strong></td>
                                        <td><span class="badge badge-primary">${backend.type}</span></td>
                                        <td>${usedGB} GB</td>
                                        <td>${capacityGB > 0 ? capacityGB + ' GB' : 'Unknown'}</td>
                                        <td>${backend.threshold}%</td>
                                        <td>${formatDateRelative(backend.last_check)}</td>
                                        <td>
                                            <span class="badge ${backend.enabled ? 'badge-success' : 'badge-error'}">
                                                ${backend.enabled ? 'Enabled' : 'Disabled'}
                                            </span>
                                            ${overThreshold ? `
                                                <span class="badge badge-warning">
                                                    ${percentage}% full
                                                </span>
                                            ` : ''}
                                        </td>
                                        <td>
                                            <button class="btn btn-sm btn-secondary" onclick="viewStorageDetails(${backend.id})">
                                                View
                                            </button>
                                            <button class="btn btn-sm btn-primary" onclick="testStorage(${backend.id})">
                                                Test
                                            </button>
                                            <button class="btn btn-sm btn-danger" onclick="deleteStorage(${backend.id})">
                                                Delete
                                            </button>
                                        </td>
                                    </tr>
                                `;
                            }).join('')}
                        </tbody>
                    </table>
                </div>
            </div>
        </div>
    `;
}

function showAddStorageDialog() {
    const modal = new Modal('Add Storage Backend', `
        <form id="addStorageForm">
            <div class="form-group">
                <label class="form-label required">Name</label>
                <input type="text" class="form-input" name="name" required>
            </div>

            <div class="form-group">
                <label class="form-label required">Type</label>
                <select class="form-select" name="type" id="storageType" required onchange="updateStorageConfig()">
                    <option value="local">Local Filesystem</option>
                    <option value="s3">S3 Compatible</option>
                    <option value="smb">SMB/CIFS (Coming Soon)</option>
                    <option value="nfs">NFS (Coming Soon)</option>
                </select>
            </div>

            <div id="storageConfig">
                <!-- Dynamic config fields will be inserted here -->
            </div>

            <div class="form-group">
                <label class="form-label">Storage Threshold (%)</label>
                <input type="number" class="form-input" name="threshold" value="80" min="1" max="100">
                <div class="form-help">Alert when storage usage exceeds this percentage</div>
            </div>

            <div class="form-group">
                <label style="display: flex; align-items: center; gap: 0.5rem;">
                    <input type="checkbox" name="enabled" checked>
                    <span>Enable backend</span>
                </label>
            </div>
        </form>
    `);

    // Trigger initial config update
    setTimeout(() => updateStorageConfig(), 100);

    modal.setOnConfirm(async () => {
        try {
            const form = document.getElementById('addStorageForm');
            const formData = getFormData(form);

            // Build config object based on type
            const config = {};
            const type = formData.type;

            if (type === 'local') {
                config.path = formData.config_path;
            } else if (type === 's3') {
                config.bucket = formData.config_bucket;
                config.region = formData.config_region;
                config.endpoint = formData.config_endpoint || null;
                config.access_key = formData.config_access_key;
                config.secret_key = formData.config_secret_key;
            }

            const data = {
                name: formData.name,
                type: type,
                config: config,
                threshold: formData.threshold,
                enabled: formData.enabled,
            };

            const loading = showLoading(modal.overlay);
            await api.createStorageBackend(data);
            hideLoading(loading);

            notify.success('Storage backend added successfully');
            modal.close();
            renderStorage();
        } catch (error) {
            notify.error('Failed to add storage backend: ' + error.message);
        }
    });

    modal.show();
}

function updateStorageConfig() {
    const typeSelect = document.getElementById('storageType');
    const configDiv = document.getElementById('storageConfig');

    if (!typeSelect || !configDiv) return;

    const type = typeSelect.value;

    let configHTML = '';

    if (type === 'local') {
        configHTML = `
            <div class="form-group">
                <label class="form-label required">Path</label>
                <input type="text" class="form-input" name="config_path" placeholder="/backups" required>
                <div class="form-help">Local filesystem path to store backups</div>
            </div>
        `;
    } else if (type === 's3') {
        configHTML = `
            <div class="form-group">
                <label class="form-label required">Bucket Name</label>
                <input type="text" class="form-input" name="config_bucket" required>
            </div>
            <div class="form-group">
                <label class="form-label required">Region</label>
                <input type="text" class="form-input" name="config_region" placeholder="us-east-1" required>
            </div>
            <div class="form-group">
                <label class="form-label">Endpoint (Optional)</label>
                <input type="text" class="form-input" name="config_endpoint" placeholder="https://s3.amazonaws.com">
                <div class="form-help">Leave empty for AWS S3, or specify for S3-compatible services</div>
            </div>
            <div class="form-group">
                <label class="form-label required">Access Key</label>
                <input type="text" class="form-input" name="config_access_key" required>
            </div>
            <div class="form-group">
                <label class="form-label required">Secret Key</label>
                <input type="password" class="form-input" name="config_secret_key" required>
            </div>
        `;
    } else if (type === 'smb' || type === 'nfs') {
        configHTML = `
            <div class="alert alert-warning">
                <div class="alert-icon">⚠</div>
                <div class="alert-content">
                    <div class="alert-title">Coming Soon</div>
                    ${type.toUpperCase()} storage backend is not yet implemented.
                </div>
            </div>
        `;
    }

    configDiv.innerHTML = configHTML;
}

async function viewStorageDetails(backendId) {
    try {
        const backend = await api.getStorageBackend(backendId);

        const modal = new Modal('Storage Backend Details', `
            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 1rem;">
                <div>
                    <strong>ID:</strong> ${backend.id}
                </div>
                <div>
                    <strong>Name:</strong> ${backend.name}
                </div>
                <div>
                    <strong>Type:</strong> ${backend.type}
                </div>
                <div>
                    <strong>Status:</strong>
                    <span class="badge ${backend.enabled ? 'badge-success' : 'badge-error'}">
                        ${backend.enabled ? 'Enabled' : 'Disabled'}
                    </span>
                </div>
                <div>
                    <strong>Used:</strong> ${backend.used || 0} GB
                </div>
                <div>
                    <strong>Capacity:</strong> ${backend.capacity || 'Unknown'} GB
                </div>
                <div>
                    <strong>Threshold:</strong> ${backend.threshold}%
                </div>
                <div>
                    <strong>Last Check:</strong> ${formatDate(backend.last_check)}
                </div>
                <div style="grid-column: 1 / -1;">
                    <strong>Configuration:</strong>
                    <pre style="background: #f5f5f5; padding: 0.75rem; border-radius: 0.375rem; margin-top: 0.5rem; font-size: 0.8rem; overflow-x: auto;">${JSON.stringify(backend.config, null, 2)}</pre>
                </div>
            </div>
        `);

        modal.overlay.querySelector('.modal-footer').style.display = 'none';
        modal.show();

    } catch (error) {
        notify.error('Failed to load storage details: ' + error.message);
    }
}

async function testStorage(backendId) {
    try {
        notify.info('Testing storage connection...');
        await api.testStorageBackend(backendId);
        notify.success('Storage connection test successful');
    } catch (error) {
        notify.error('Storage test failed: ' + error.message);
    }
}

async function deleteStorage(backendId) {
    showConfirmDialog(
        'Delete Storage Backend',
        'Are you sure? Schedules using this backend will fail.',
        async () => {
            try {
                await api.deleteStorageBackend(backendId);
                notify.success('Storage backend deleted');
                renderStorage();
            } catch (error) {
                notify.error('Failed to delete storage backend: ' + error.message);
            }
        }
    );
}
