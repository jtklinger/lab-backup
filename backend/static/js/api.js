/**
 * API Client for Lab Backup System
 */

const API_BASE = '/api/v1';

class APIClient {
    constructor() {
        this.token = localStorage.getItem('auth_token');
        this.refreshToken = localStorage.getItem('refresh_token');
    }

    setToken(token, refreshToken = null) {
        this.token = token;
        if (token) {
            localStorage.setItem('auth_token', token);
        } else {
            localStorage.removeItem('auth_token');
        }

        if (refreshToken !== null) {
            this.refreshToken = refreshToken;
            if (refreshToken) {
                localStorage.setItem('refresh_token', refreshToken);
            } else {
                localStorage.removeItem('refresh_token');
            }
        }
    }

    getToken() {
        return this.token;
    }

    getRefreshToken() {
        return this.refreshToken;
    }

    async request(endpoint, options = {}) {
        const headers = {
            'Content-Type': 'application/json',
            ...options.headers,
        };

        if (this.token) {
            headers['Authorization'] = `Bearer ${this.token}`;
        }

        const config = {
            ...options,
            headers,
        };

        if (options.body && typeof options.body === 'object') {
            config.body = JSON.stringify(options.body);
        }

        try {
            const response = await fetch(`${API_BASE}${endpoint}`, config);

            if (response.status === 401) {
                // Unauthorized - redirect to login
                this.setToken(null);
                window.location.href = '/static/login.html';
                throw new Error('Unauthorized');
            }

            const data = await response.json().catch(() => null);

            if (!response.ok) {
                throw new Error(data?.detail || `HTTP ${response.status}`);
            }

            return data;
        } catch (error) {
            console.error('API Error:', error);
            throw error;
        }
    }

    // Auth endpoints
    async login(username, password) {
        const formData = new URLSearchParams();
        formData.append('username', username);
        formData.append('password', password);

        const response = await fetch(`${API_BASE}/auth/token`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/x-www-form-urlencoded',
            },
            body: formData,
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || 'Login failed');
        }

        const data = await response.json();
        this.setToken(data.access_token, data.refresh_token);
        return data;
    }

    async refreshAccessToken() {
        if (!this.refreshToken) {
            throw new Error('No refresh token available');
        }

        const response = await fetch(`${API_BASE}/auth/refresh`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                refresh_token: this.refreshToken
            }),
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || 'Token refresh failed');
        }

        const data = await response.json();
        this.setToken(data.access_token, data.refresh_token);
        return data;
    }

    async getCurrentUser() {
        return this.request('/auth/me');
    }

    logout() {
        this.setToken(null, null);
        window.location.href = '/static/login.html';
    }

    // Dashboard endpoints
    async getDashboardStats() {
        return this.request('/settings/dashboard/stats');
    }

    // Backup endpoints
    async listBackups(params = {}) {
        const query = new URLSearchParams(params).toString();
        return this.request(`/backups${query ? '?' + query : ''}`);
    }

    async getBackup(id) {
        return this.request(`/backups/${id}`);
    }

    async deleteBackup(id) {
        return this.request(`/backups/${id}`, { method: 'DELETE' });
    }

    async triggerBackup(data) {
        return this.request('/backups/trigger', {
            method: 'POST',
            body: data
        });
    }

    async restoreBackup(backupId, data) {
        return this.request(`/backups/${backupId}/restore`, {
            method: 'POST',
            body: data
        });
    }

    // Schedule endpoints
    async listSchedules(params = {}) {
        const query = new URLSearchParams(params).toString();
        return this.request(`/schedules${query ? '?' + query : ''}`);
    }

    async getSchedule(id) {
        return this.request(`/schedules/${id}`);
    }

    async createSchedule(data) {
        return this.request('/schedules', {
            method: 'POST',
            body: data,
        });
    }

    async updateSchedule(id, data) {
        return this.request(`/schedules/${id}`, {
            method: 'PUT',
            body: data,
        });
    }

    async deleteSchedule(id) {
        return this.request(`/schedules/${id}`, { method: 'DELETE' });
    }

    async triggerSchedule(id) {
        return this.request(`/schedules/${id}/trigger`, { method: 'POST' });
    }

    // Job endpoints
    async listJobs(params = {}) {
        const query = new URLSearchParams(params).toString();
        return this.request(`/jobs${query ? '?' + query : ''}`);
    }

    async getJob(id) {
        return this.request(`/jobs/${id}`);
    }

    async getJobLogs(id) {
        return this.request(`/jobs/${id}/logs`);
    }

    async cancelJob(id) {
        return this.request(`/jobs/${id}/cancel`, { method: 'POST' });
    }

    // Storage endpoints
    async listStorageBackends() {
        return this.request('/storage');
    }

    async getStorageBackend(id) {
        return this.request(`/storage/${id}`);
    }

    async createStorageBackend(data) {
        return this.request('/storage', {
            method: 'POST',
            body: data,
        });
    }

    async updateStorageBackend(id, data) {
        return this.request(`/storage/${id}`, {
            method: 'PUT',
            body: data,
        });
    }

    async deleteStorageBackend(id) {
        return this.request(`/storage/${id}`, { method: 'DELETE' });
    }

    async testStorageBackend(id) {
        return this.request(`/storage/${id}/test`, { method: 'POST' });
    }

    // KVM endpoints
    async listKVMHosts() {
        return this.request('/kvm/hosts');
    }

    async getKVMHost(id) {
        return this.request(`/kvm/hosts/${id}`);
    }

    async createKVMHost(data) {
        return this.request('/kvm/hosts', {
            method: 'POST',
            body: data,
        });
    }

    async updateKVMHost(id, data) {
        return this.request(`/kvm/hosts/${id}`, {
            method: 'PUT',
            body: data,
        });
    }

    async deleteKVMHost(id) {
        return this.request(`/kvm/hosts/${id}`, { method: 'DELETE' });
    }

    async refreshKVMHost(id) {
        return this.request(`/kvm/hosts/${id}/refresh`, { method: 'POST' });
    }

    async listVMs(hostId = null) {
        const query = hostId ? `?host_id=${hostId}` : '';
        return this.request(`/kvm/vms${query}`);
    }

    async getVM(id) {
        return this.request(`/kvm/vms/${id}`);
    }

    // SSH Key endpoints
    async listSSHKeys(hostId) {
        return this.request(`/kvm/hosts/${hostId}/ssh-keys`);
    }

    async uploadSSHKey(hostId, data) {
        return this.request(`/kvm/hosts/${hostId}/ssh-keys`, {
            method: 'POST',
            body: data,
        });
    }

    async generateSSHKey(hostId, params) {
        return this.request(`/kvm/hosts/${hostId}/ssh-keys/generate`, {
            method: 'POST',
            body: params,
        });
    }

    async getPublicKey(hostId, keyId) {
        return this.request(`/kvm/hosts/${hostId}/ssh-keys/${keyId}/public`);
    }

    async deleteSSHKey(hostId, keyId) {
        return this.request(`/kvm/hosts/${hostId}/ssh-keys/${keyId}`, {
            method: 'DELETE',
        });
    }

    // Podman endpoints
    async listPodmanHosts() {
        return this.request('/podman/hosts');
    }

    async getPodmanHost(id) {
        return this.request(`/podman/hosts/${id}`);
    }

    async createPodmanHost(data) {
        return this.request('/podman/hosts', {
            method: 'POST',
            body: data,
        });
    }

    async updatePodmanHost(id, data) {
        return this.request(`/podman/hosts/${id}`, {
            method: 'PUT',
            body: data,
        });
    }

    async deletePodmanHost(id) {
        return this.request(`/podman/hosts/${id}`, { method: 'DELETE' });
    }

    async refreshPodmanHost(id) {
        return this.request(`/podman/hosts/${id}/refresh`, { method: 'POST' });
    }

    async listContainers(hostId = null) {
        const query = hostId ? `?host_id=${hostId}` : '';
        return this.request(`/podman/containers${query}`);
    }

    async getContainer(id) {
        return this.request(`/podman/containers/${id}`);
    }

    // Settings endpoints
    async getSettingCategories() {
        return this.request('/settings/categories');
    }

    async getSettingsByCategory(category) {
        return this.request(`/settings/category/${category}`);
    }

    async getSetting(key) {
        return this.request(`/settings/${key}`);
    }

    async updateSetting(key, value) {
        return this.request(`/settings/${key}`, {
            method: 'PUT',
            body: { value },
        });
    }

    async bulkUpdateSettings(settings) {
        return this.request('/settings/bulk', {
            method: 'PUT',
            body: { settings },
        });
    }

    // Logs endpoints
    async getLogs(params = {}) {
        const query = new URLSearchParams(params).toString();
        return this.request(`/logs${query ? '?' + query : ''}`);
    }

    async getLogStats() {
        return this.request('/logs/stats');
    }

    async clearLogs() {
        return this.request('/logs/clear', { method: 'POST' });
    }

    // Application logs (database)
    async getApplicationLogs(params = {}) {
        const query = new URLSearchParams(params).toString();
        return this.request(`/logs/application${query ? '?' + query : ''}`);
    }

    async getApplicationLogStats() {
        return this.request('/logs/application/stats');
    }

    async clearApplicationLogs() {
        return this.request('/logs/application', { method: 'DELETE' });
    }
}

// Create global API instance
const api = new APIClient();
