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
                                        <button class="btn btn-sm btn-secondary" onclick="showSSHKeyDialog(${host.id}, '${host.name}')">
                                            🔑 SSH Keys
                                        </button>
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
                                            <button class="btn btn-sm btn-success" onclick="showBackupNowDialog('vm', ${vm.id}, '${vm.name}')">
                                                ⚡ Backup Now
                                            </button>
                                            <button class="btn btn-sm btn-primary" onclick="createVMSchedule(${vm.id})">
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
                    Examples: qemu:///system (local), qemu+ssh://user@host/system (SSH), qemu+tcp://user@host/system (SASL/TCP with password)
                </div>
            </div>
            <div class="form-group">
                <label style="display: flex; align-items: center; gap: 0.5rem;">
                    <input type="checkbox" name="enabled" checked>
                    <span>Enable host</span>
                </label>
            </div>

            <!-- Authentication Method Selection -->
            <div style="border-top: 1px solid var(--border-color); margin-top: 1.5rem; padding-top: 1.5rem;">
                <h4 style="margin-bottom: 0.75rem;">Authentication Method</h4>
                <div class="form-group">
                    <label style="display: flex; align-items: center; gap: 0.5rem;">
                        <input type="radio" name="auth_method" value="ssh" checked onchange="toggleAuthMethodFields()">
                        <span>SSH Key Authentication</span>
                    </label>
                    <label style="display: flex; align-items: center; gap: 0.5rem; margin-top: 0.5rem;">
                        <input type="radio" name="auth_method" value="password" onchange="toggleAuthMethodFields()">
                        <span>Password Authentication (SASL/TCP)</span>
                    </label>
                </div>
            </div>

            <!-- Password Authentication Fields -->
            <div id="passwordAuthFields" style="display: none; margin-top: 1rem;">
                <div class="form-group">
                    <label class="form-label required">Username</label>
                    <input type="text" class="form-input" name="password_username" placeholder="username">
                    <div class="form-help">
                        Username for SASL authentication
                    </div>
                </div>
                <div class="form-group">
                    <label class="form-label required">Password</label>
                    <input type="password" class="form-input" name="password_field" placeholder="Enter password">
                    <div class="form-help">
                        Password will be encrypted before storage
                    </div>
                </div>
            </div>

            <!-- SSH Key Configuration -->
            <div id="sshKeyConfig" style="border-top: 1px solid var(--border-color); margin-top: 1.5rem; padding-top: 1.5rem;">
                <h4 style="margin-bottom: 0.75rem;">SSH Key Options (Optional)</h4>
                <div class="form-group">
                    <label style="display: flex; align-items: center; gap: 0.5rem;">
                        <input type="radio" name="ssh_key_option" value="default" checked onchange="toggleSSHKeyFields()">
                        <span>Use default SSH keys from ~/.ssh</span>
                    </label>
                    <label style="display: flex; align-items: center; gap: 0.5rem; margin-top: 0.5rem;">
                        <input type="radio" name="ssh_key_option" value="upload" onchange="toggleSSHKeyFields()">
                        <span>Upload existing SSH key</span>
                    </label>
                    <label style="display: flex; align-items: center; gap: 0.5rem; margin-top: 0.5rem;">
                        <input type="radio" name="ssh_key_option" value="generate" onchange="toggleSSHKeyFields()">
                        <span>Generate new SSH key</span>
                    </label>
                </div>

                <!-- Upload SSH Key Fields -->
                <div id="uploadSSHKeyFields" style="display: none; margin-top: 1rem;">
                    <div class="form-group">
                        <label class="form-label">Key Type</label>
                        <select class="form-input" name="upload_key_type">
                            <option value="ed25519">ed25519</option>
                            <option value="rsa">RSA</option>
                            <option value="ecdsa">ECDSA</option>
                        </select>
                    </div>
                    <div class="form-group">
                        <label class="form-label">Private Key</label>
                        <textarea class="form-input" name="upload_private_key" rows="6"
                                  placeholder="-----BEGIN OPENSSH PRIVATE KEY-----"></textarea>
                    </div>
                    <div class="form-group">
                        <label class="form-label">Public Key</label>
                        <textarea class="form-input" name="upload_public_key" rows="2"
                                  placeholder="ssh-ed25519 AAAA..."></textarea>
                    </div>
                </div>

                <!-- Generate SSH Key Fields -->
                <div id="generateSSHKeyFields" style="display: none; margin-top: 1rem;">
                    <div class="form-group">
                        <label class="form-label">Key Type</label>
                        <select class="form-input" name="generate_key_type" id="generateKeyTypeSelect" onchange="toggleGenerateKeySize()">
                            <option value="ed25519">ed25519 (Recommended)</option>
                            <option value="rsa">RSA</option>
                        </select>
                    </div>
                    <div class="form-group" id="generateKeySizeGroup" style="display: none;">
                        <label class="form-label">RSA Key Size</label>
                        <select class="form-input" name="generate_key_size">
                            <option value="2048">2048 bits</option>
                            <option value="4096" selected>4096 bits</option>
                        </select>
                    </div>
                </div>
            </div>
        </form>
    `);

    modal.setOnConfirm(async () => {
        try {
            const form = document.getElementById('addKVMHostForm');
            const formData = getFormData(form);

            const loading = showLoading(modal.overlay);

            // Determine authentication method
            const authMethod = formData.auth_method || 'ssh';
            const sshKeyOption = formData.ssh_key_option || 'default';

            // Prepare KVM host data
            const hostData = {
                name: formData.name,
                uri: formData.uri,
                enabled: formData.enabled,
                auth_type: authMethod
            };

            // Add password if using password auth
            if (authMethod === 'password') {
                if (!formData.password_username || !formData.password_field) {
                    notify.error('Username and password are required for password authentication');
                    hideLoading(loading);
                    return;
                }
                hostData.username = formData.password_username;
                hostData.password = formData.password_field;
            }

            // Skip connection test if we're going to generate an SSH key
            const skipTest = authMethod === 'ssh' && sshKeyOption === 'generate';
            hostData.skip_connection_test = skipTest;

            // Create the KVM host
            const newHost = await api.createKVMHost(hostData);

            // Handle SSH key creation if needed (only for SSH auth)
            if (authMethod === 'ssh') {
                if (sshKeyOption === 'upload' && formData.upload_private_key && formData.upload_public_key) {
                    // Upload the SSH key
                    await api.uploadSSHKey(newHost.id, {
                        key_type: formData.upload_key_type,
                        private_key: formData.upload_private_key,
                        public_key: formData.upload_public_key
                    });
                    notify.success('KVM host and SSH key added successfully');
                } else if (sshKeyOption === 'generate') {
                    // Generate new SSH key
                    const keyParams = {
                        key_type: formData.generate_key_type
                    };
                    if (formData.generate_key_type === 'rsa') {
                        keyParams.key_size = parseInt(formData.generate_key_size);
                    }
                    const newKey = await api.generateSSHKey(newHost.id, keyParams);

                    hideLoading(loading);
                    notify.success('KVM host added and SSH key generated');
                    modal.close();

                    // Show the public key to the user
                    await showPublicKey(newHost.id, newKey.id);
                    renderKVM();
                    return;
                } else {
                    notify.success('KVM host added successfully');
                }
            } else {
                // Password auth
                notify.success('KVM host added successfully with password authentication');
            }

            hideLoading(loading);
            modal.close();
            renderKVM();
        } catch (error) {
            notify.error('Failed to add KVM host: ' + error.message);
        }
    });

    modal.show();
}

// Helper functions for Add KVM Host dialog
function toggleAuthMethodFields() {
    const method = document.querySelector('input[name="auth_method"]:checked').value;
    const passwordFields = document.getElementById('passwordAuthFields');
    const sshKeyConfig = document.getElementById('sshKeyConfig');

    if (method === 'password') {
        passwordFields.style.display = 'block';
        sshKeyConfig.style.display = 'none';
    } else {
        passwordFields.style.display = 'none';
        sshKeyConfig.style.display = 'block';
    }
}

function toggleSSHKeyFields() {
    const option = document.querySelector('input[name="ssh_key_option"]:checked').value;
    document.getElementById('uploadSSHKeyFields').style.display = option === 'upload' ? 'block' : 'none';
    document.getElementById('generateSSHKeyFields').style.display = option === 'generate' ? 'block' : 'none';
}

function toggleGenerateKeySize() {
    const keyType = document.getElementById('generateKeyTypeSelect').value;
    document.getElementById('generateKeySizeGroup').style.display = keyType === 'rsa' ? 'block' : 'none';
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

// SSH Key Management

async function showSSHKeyDialog(hostId, hostName) {
    try {
        const keys = await api.listSSHKeys(hostId);

        const modal = new Modal(`SSH Keys - ${hostName}`, `
            <div style="margin-bottom: 1.5rem;">
                <h4 style="margin-bottom: 0.75rem;">Existing SSH Keys</h4>
                ${keys.length === 0 ? `
                    <div class="alert alert-info">
                        <div class="alert-icon">ℹ</div>
                        <div class="alert-content">
                            No SSH keys configured. Using default keys from ~/.ssh
                        </div>
                    </div>
                ` : `
                    <div class="table-container">
                        <table class="table">
                            <thead>
                                <tr>
                                    <th>Type</th>
                                    <th>Created</th>
                                    <th>Last Used</th>
                                    <th>Actions</th>
                                </tr>
                            </thead>
                            <tbody>
                                ${keys.map(key => `
                                    <tr>
                                        <td><span class="badge badge-info">${key.key_type}</span></td>
                                        <td>${formatDate(key.created_at)}</td>
                                        <td>${key.last_used ? formatDateRelative(key.last_used) : 'Never'}</td>
                                        <td>
                                            <button class="btn btn-sm btn-secondary" onclick="showPublicKey(${hostId}, ${key.id})">
                                                📋 Public Key
                                            </button>
                                            <button class="btn btn-sm btn-danger" onclick="deleteSSHKey(${hostId}, ${key.id}, '${hostName}')">
                                                Delete
                                            </button>
                                        </td>
                                    </tr>
                                `).join('')}
                            </tbody>
                        </table>
                    </div>
                `}
            </div>

            <div style="border-top: 1px solid var(--border-color); padding-top: 1.5rem;">
                <h4 style="margin-bottom: 0.75rem;">Add New SSH Key</h4>
                <div style="display: flex; gap: 0.75rem;">
                    <button class="btn btn-primary" onclick="showUploadSSHKeyDialog(${hostId}, '${hostName}')">
                        📤 Upload Existing Key
                    </button>
                    <button class="btn btn-success" onclick="showGenerateSSHKeyDialog(${hostId}, '${hostName}')">
                        ✨ Generate New Key
                    </button>
                </div>
            </div>
        `, {
            showCancel: false,
            confirmText: 'Close'
        });

        modal.setOnConfirm(() => {
            modal.close();
        });

        modal.show();
    } catch (error) {
        // Provide more specific error message
        if (error.message.includes('not found') || error.message.includes('404')) {
            notify.error(`KVM host "${hostName}" not found. Please refresh the page.`);
        } else {
            notify.error('Failed to load SSH keys: ' + error.message);
        }
    }
}

function showUploadSSHKeyDialog(hostId, hostName) {
    const modal = new Modal(`Upload SSH Key - ${hostName}`, `
        <form id="uploadSSHKeyForm">
            <div class="form-group">
                <label class="form-label required">Key Type</label>
                <select class="form-input" name="key_type" required>
                    <option value="ed25519">ed25519 (Recommended)</option>
                    <option value="rsa">RSA</option>
                    <option value="ecdsa">ECDSA</option>
                </select>
            </div>
            <div class="form-group">
                <label class="form-label required">Private Key</label>
                <textarea class="form-input" name="private_key" rows="10"
                          placeholder="-----BEGIN OPENSSH PRIVATE KEY-----&#10;...&#10;-----END OPENSSH PRIVATE KEY-----" required></textarea>
                <div class="form-help">
                    Paste your SSH private key here. It will be encrypted before storage.
                </div>
            </div>
            <div class="form-group">
                <label class="form-label required">Public Key</label>
                <textarea class="form-input" name="public_key" rows="3"
                          placeholder="ssh-ed25519 AAAA... user@host" required></textarea>
                <div class="form-help">
                    Paste the corresponding public key here.
                </div>
            </div>
        </form>
    `);

    modal.setOnConfirm(async () => {
        try {
            const form = document.getElementById('uploadSSHKeyForm');
            const data = getFormData(form);

            const loading = showLoading(modal.overlay);
            await api.uploadSSHKey(hostId, data);
            hideLoading(loading);

            notify.success('SSH key uploaded successfully');
            modal.close();
            showSSHKeyDialog(hostId, hostName);
        } catch (error) {
            notify.error('Failed to upload SSH key: ' + error.message);
        }
    });

    modal.show();
}

function showGenerateSSHKeyDialog(hostId, hostName) {
    const modal = new Modal(`Generate SSH Key - ${hostName}`, `
        <form id="generateSSHKeyForm">
            <div class="form-group">
                <label class="form-label required">Key Type</label>
                <select class="form-input" name="key_type" id="keyTypeSelect" required onchange="toggleKeySize()">
                    <option value="ed25519">ed25519 (Recommended - Faster, More Secure)</option>
                    <option value="rsa">RSA</option>
                </select>
            </div>
            <div class="form-group" id="keySizeGroup" style="display: none;">
                <label class="form-label">RSA Key Size</label>
                <select class="form-input" name="key_size">
                    <option value="2048">2048 bits</option>
                    <option value="4096" selected>4096 bits (Recommended)</option>
                </select>
            </div>
            <div class="alert alert-info">
                <div class="alert-icon">ℹ</div>
                <div class="alert-content">
                    <div class="alert-title">What happens next?</div>
                    1. A new SSH key pair will be generated<br>
                    2. The private key will be encrypted and stored in the database<br>
                    3. You'll need to add the public key to the target host's ~/.ssh/authorized_keys
                </div>
            </div>
        </form>
    `);

    modal.setOnConfirm(async () => {
        try {
            const form = document.getElementById('generateSSHKeyForm');
            const data = getFormData(form);

            // Remove key_size if not RSA
            if (data.key_type !== 'rsa') {
                delete data.key_size;
            }

            const loading = showLoading(modal.overlay);
            const newKey = await api.generateSSHKey(hostId, data);
            hideLoading(loading);

            notify.success('SSH key generated successfully');
            modal.close();

            // Show the public key to the user
            await showPublicKey(hostId, newKey.id);

            // Refresh the SSH key dialog
            setTimeout(() => showSSHKeyDialog(hostId, hostName), 100);
        } catch (error) {
            notify.error('Failed to generate SSH key: ' + error.message);
        }
    });

    modal.show();
}

function toggleKeySize() {
    const keyType = document.getElementById('keyTypeSelect').value;
    const keySizeGroup = document.getElementById('keySizeGroup');
    keySizeGroup.style.display = keyType === 'rsa' ? 'block' : 'none';
}

async function showPublicKey(hostId, keyId) {
    try {
        const response = await api.getPublicKey(hostId, keyId);

        const modal = new Modal('Public Key', `
            <div class="alert alert-success">
                <div class="alert-icon">✓</div>
                <div class="alert-content">
                    <div class="alert-title">Copy this public key</div>
                    ${response.instructions}
                </div>
            </div>

            <div class="form-group">
                <label class="form-label">Public Key (${response.key_type})</label>
                <textarea class="form-input" rows="4" readonly id="publicKeyText">${response.public_key}</textarea>
            </div>

            <div style="margin-top: 1rem;">
                <button class="btn btn-primary" onclick="copyPublicKey()">
                    📋 Copy to Clipboard
                </button>
            </div>
        `, {
            showCancel: false,
            confirmText: 'Close'
        });

        modal.setOnConfirm(() => {
            modal.close();
        });

        modal.show();
    } catch (error) {
        notify.error('Failed to get public key: ' + error.message);
    }
}

function copyPublicKey() {
    const textArea = document.getElementById('publicKeyText');
    textArea.select();
    document.execCommand('copy');
    notify.success('Public key copied to clipboard');
}

async function deleteSSHKey(hostId, keyId, hostName) {
    showConfirmDialog(
        'Delete SSH Key',
        'Are you sure you want to delete this SSH key? The host will fall back to using default SSH keys.',
        async () => {
            try {
                await api.deleteSSHKey(hostId, keyId);
                notify.success('SSH key deleted');
                showSSHKeyDialog(hostId, hostName);
            } catch (error) {
                notify.error('Failed to delete SSH key: ' + error.message);
            }
        }
    );
}
