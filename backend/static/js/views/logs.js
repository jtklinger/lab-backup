/**
 * Logs View
 */

let logsRefreshInterval = null;

async function renderLogs() {
    const mainContent = document.getElementById('mainContent');
    const headerActions = document.getElementById('headerActions');

    headerActions.innerHTML = `
        <button class="btn btn-secondary btn-sm" onclick="toggleAutoRefresh()">
            <span id="autoRefreshIcon">⏸</span> Auto-Refresh
        </button>
        <button class="btn btn-secondary btn-sm" onclick="renderLogs()">
            🔄 Refresh
        </button>
        <button class="btn btn-danger btn-sm" onclick="clearLogsConfirm()">
            🗑️ Clear Logs
        </button>
    `;

    mainContent.innerHTML = '<div class="spinner"></div>';

    try {
        const [logsData, stats] = await Promise.all([
            api.getLogs({ limit: 200 }),
            api.getLogStats(),
        ]);

        renderLogsContent(logsData, stats);
    } catch (error) {
        console.error('Failed to load logs:', error);
        mainContent.innerHTML = `
            <div class="alert alert-error">
                <div class="alert-icon">✕</div>
                <div class="alert-content">
                    <div class="alert-title">Failed to load logs</div>
                    ${error.message}
                </div>
            </div>
        `;
    }
}

function renderLogsContent(logsData, stats) {
    const mainContent = document.getElementById('mainContent');

    mainContent.innerHTML = `
        <!-- Stats -->
        <div class="stats-grid" style="margin-bottom: 1.5rem;">
            <div class="stat-card">
                <div class="stat-icon primary">📝</div>
                <div class="stat-content">
                    <div class="stat-label">Total Logs</div>
                    <div class="stat-value">${stats.total}</div>
                </div>
            </div>
            <div class="stat-card">
                <div class="stat-icon error">✕</div>
                <div class="stat-content">
                    <div class="stat-label">Errors</div>
                    <div class="stat-value">${stats.by_level.ERROR + stats.by_level.CRITICAL}</div>
                </div>
            </div>
            <div class="stat-card">
                <div class="stat-icon warning">⚠</div>
                <div class="stat-content">
                    <div class="stat-label">Warnings</div>
                    <div class="stat-value">${stats.by_level.WARNING}</div>
                </div>
            </div>
            <div class="stat-card">
                <div class="stat-icon info">ℹ</div>
                <div class="stat-content">
                    <div class="stat-label">Info</div>
                    <div class="stat-value">${stats.by_level.INFO}</div>
                </div>
            </div>
        </div>

        <!-- Filters -->
        <div class="card" style="margin-bottom: 1.5rem;">
            <div class="card-body">
                <div style="display: grid; grid-template-columns: 1fr 1fr 2fr; gap: 1rem; align-items: end;">
                    <div class="form-group" style="margin-bottom: 0;">
                        <label class="form-label">Filter by Level:</label>
                        <select id="levelFilter" class="form-select" onchange="filterLogs()">
                            <option value="">All Levels</option>
                            <option value="DEBUG">Debug</option>
                            <option value="INFO">Info</option>
                            <option value="WARNING">Warning</option>
                            <option value="ERROR">Error</option>
                            <option value="CRITICAL">Critical</option>
                        </select>
                    </div>
                    <div class="form-group" style="margin-bottom: 0;">
                        <label class="form-label">Filter by Logger:</label>
                        <input type="text" id="loggerFilter" class="form-input"
                               placeholder="e.g., backend.services.storage" oninput="filterLogs()">
                    </div>
                    <div class="form-group" style="margin-bottom: 0;">
                        <label class="form-label">Search Messages:</label>
                        <input type="text" id="searchFilter" class="form-input"
                               placeholder="Search in log messages..." oninput="filterLogs()">
                    </div>
                </div>
            </div>
        </div>

        <!-- Logs Display -->
        <div class="card">
            <div class="card-header">
                <h3 class="card-title">Application Logs (${logsData.total} entries)</h3>
            </div>
            <div class="card-body" style="padding: 0;">
                <div id="logsContainer" style="background: #1e1e1e; color: #d4d4d4; font-family: 'Consolas', 'Monaco', monospace; font-size: 0.875rem; max-height: 600px; overflow-y: auto; padding: 1rem;">
                    ${renderLogEntries(logsData.logs)}
                </div>
            </div>
        </div>
    `;
}

function renderLogEntries(logs) {
    if (logs.length === 0) {
        return '<div style="text-align: center; padding: 2rem; color: #888;">No logs to display</div>';
    }

    return logs.map(log => {
        const levelColors = {
            'DEBUG': '#888',
            'INFO': '#4a9eff',
            'WARNING': '#f59e0b',
            'ERROR': '#ef4444',
            'CRITICAL': '#dc2626',
        };

        const levelColor = levelColors[log.level] || '#888';
        const timestamp = new Date(log.timestamp).toLocaleString();

        return `
            <div class="log-entry" data-level="${log.level}" data-logger="${log.logger}" data-message="${log.message.toLowerCase()}" style="margin-bottom: 0.5rem; border-left: 3px solid ${levelColor}; padding-left: 0.75rem;">
                <div style="display: flex; gap: 1rem; flex-wrap: wrap;">
                    <span style="color: #888; min-width: 180px;">${timestamp}</span>
                    <span style="color: ${levelColor}; font-weight: 600; min-width: 80px;">${log.level}</span>
                    <span style="color: #888; min-width: 200px; overflow: hidden; text-overflow: ellipsis;" title="${log.logger}">${log.logger}</span>
                    <span style="flex: 1; color: #d4d4d4;">${escapeHtml(log.message)}</span>
                </div>
                ${log.exception ? `
                    <div style="margin-top: 0.5rem; padding: 0.5rem; background: rgba(255, 0, 0, 0.1); border-radius: 0.25rem; color: #ff6b6b; font-size: 0.8rem; white-space: pre-wrap;">
                        ${escapeHtml(log.exception)}
                    </div>
                ` : ''}
            </div>
        `;
    }).join('');
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

async function filterLogs() {
    const level = document.getElementById('levelFilter').value;
    const logger = document.getElementById('loggerFilter').value;
    const search = document.getElementById('searchFilter').value;

    try {
        const params = { limit: 200 };
        if (level) params.level = level;
        if (logger) params.logger = logger;
        if (search) params.search = search;

        const logsData = await api.getLogs(params);

        // Update log container
        const logsContainer = document.getElementById('logsContainer');
        if (logsContainer) {
            logsContainer.innerHTML = renderLogEntries(logsData.logs);
        }
    } catch (error) {
        notify.error('Failed to filter logs: ' + error.message);
    }
}

function toggleAutoRefresh() {
    const icon = document.getElementById('autoRefreshIcon');

    if (logsRefreshInterval) {
        // Stop auto-refresh
        clearInterval(logsRefreshInterval);
        logsRefreshInterval = null;
        icon.textContent = '⏸';
        notify.info('Auto-refresh stopped');
    } else {
        // Start auto-refresh
        logsRefreshInterval = setInterval(() => {
            filterLogs();
        }, 3000); // Refresh every 3 seconds
        icon.textContent = '▶️';
        notify.info('Auto-refresh started (every 3s)');
    }
}

async function clearLogsConfirm() {
    showConfirmDialog(
        'Clear All Logs',
        'Are you sure you want to clear all stored logs? This action cannot be undone.',
        async () => {
            try {
                await api.clearLogs();
                notify.success('Logs cleared successfully');
                renderLogs();
            } catch (error) {
                notify.error('Failed to clear logs: ' + error.message);
            }
        }
    );
}

// Clean up interval when leaving the view
window.addEventListener('hashchange', () => {
    if (logsRefreshInterval && !window.location.hash.includes('logs')) {
        clearInterval(logsRefreshInterval);
        logsRefreshInterval = null;
    }
});
