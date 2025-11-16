/**
 * Settings View
 */

async function renderSettings() {
    const mainContent = document.getElementById('mainContent');
    const headerActions = document.getElementById('headerActions');

    headerActions.innerHTML = `
        <button class="btn btn-primary btn-sm" onclick="saveAllSettings()">
            💾 Save All Changes
        </button>
    `;

    mainContent.innerHTML = '<div class="spinner"></div>';

    try {
        const categories = await api.getSettingCategories();
        const settingsByCategory = {};

        // Fetch settings for each category
        for (const category of categories) {
            settingsByCategory[category] = await api.getSettingsByCategory(category);
        }

        renderSettingsContent(settingsByCategory);
    } catch (error) {
        console.error('Failed to load settings:', error);
        mainContent.innerHTML = `
            <div class="alert alert-error">
                <div class="alert-icon">✕</div>
                <div class="alert-content">
                    <div class="alert-title">Failed to load settings</div>
                    ${error.message}
                </div>
            </div>
        `;
    }
}

function renderSettingsContent(settingsByCategory) {
    const mainContent = document.getElementById('mainContent');

    const categories = Object.keys(settingsByCategory);

    if (categories.length === 0) {
        mainContent.innerHTML = `
            <div class="card">
                <div class="card-body">
                    <div class="empty-state">
                        <div class="empty-state-icon">⚙️</div>
                        <div class="empty-state-title">No settings found</div>
                        <div class="empty-state-description">
                            Settings will be available after initial setup
                        </div>
                    </div>
                </div>
            </div>
        `;
        return;
    }

    mainContent.innerHTML = `
        <div class="alert alert-info">
            <div class="alert-icon">ℹ</div>
            <div class="alert-content">
                Make changes to the settings below and click "Save All Changes" to apply them.
            </div>
        </div>

        ${categories.map(category => `
            <div class="card" style="margin-bottom: 1.5rem;">
                <div class="card-header">
                    <h3 class="card-title" style="text-transform: capitalize;">${category} Settings</h3>
                </div>
                <div class="card-body">
                    <form id="settings-form-${category}">
                        ${settingsByCategory[category].map(setting => renderSettingField(setting)).join('')}
                    </form>
                </div>
            </div>
        `).join('')}
    `;
}

function renderSettingField(setting) {
    const inputId = `setting-${setting.key.replace(/\./g, '-')}`;
    const isSecret = setting.is_secret;
    const value = setting.value || '';

    let inputField = '';

    if (setting.value_type === 'boolean') {
        inputField = `
            <label style="display: flex; align-items: center; gap: 0.5rem;">
                <input type="checkbox" id="${inputId}" name="${setting.key}"
                       ${value === 'true' || value === true ? 'checked' : ''}>
                <span>${setting.description || setting.key}</span>
            </label>
        `;
    } else if (setting.value_type === 'integer') {
        // Add validation constraints for specific settings
        let constraints = '';
        if (setting.key === 'session.timeout_minutes') {
            constraints = 'min="1" max="60"';
        } else if (setting.key === 'session.warning_minutes') {
            constraints = 'min="1" max="30"';
        } else if (setting.key === 'logging.retention_days') {
            constraints = 'min="1" max="365"';
        } else if (setting.key === 'logging.error_retention_days') {
            constraints = 'min="1" max="365"';
        } else if (setting.key === 'logging.file_max_size_mb') {
            constraints = 'min="1" max="1000"';
        } else if (setting.key === 'logging.file_backup_count') {
            constraints = 'min="1" max="50"';
        }

        inputField = `
            <label class="form-label">${setting.description || setting.key}</label>
            <input type="number" class="form-input" id="${inputId}" name="${setting.key}"
                   value="${value}" ${isSecret ? 'readonly' : ''} ${constraints}>
        `;
    } else {
        // string type
        // Special handling for log level
        if (setting.key === 'logging.level') {
            inputField = `
                <label class="form-label">${setting.description || setting.key}</label>
                <select class="form-input" id="${inputId}" name="${setting.key}">
                    <option value="DEBUG" ${value === 'DEBUG' ? 'selected' : ''}>DEBUG</option>
                    <option value="INFO" ${value === 'INFO' ? 'selected' : ''}>INFO</option>
                    <option value="WARNING" ${value === 'WARNING' ? 'selected' : ''}>WARNING</option>
                    <option value="ERROR" ${value === 'ERROR' ? 'selected' : ''}>ERROR</option>
                    <option value="CRITICAL" ${value === 'CRITICAL' ? 'selected' : ''}>CRITICAL</option>
                </select>
            `;
        } else {
            inputField = `
                <label class="form-label">${setting.description || setting.key}</label>
                <input type="${isSecret ? 'password' : 'text'}" class="form-input"
                       id="${inputId}" name="${setting.key}"
                       value="${isSecret && value ? '********' : value}"
                       ${isSecret && value ? 'placeholder="Leave blank to keep current value"' : ''}>
            `;
        }
    }

    return `
        <div class="form-group">
            ${inputField}
            ${setting.description && setting.value_type === 'boolean' ? '' : `
                <div class="form-help">
                    Key: <code>${setting.key}</code>
                    ${isSecret ? ' (Secret - masked for security)' : ''}
                </div>
            `}
        </div>
    `;
}

async function saveAllSettings() {
    try {
        const allSettings = {};

        // Gather all settings from all forms
        const forms = document.querySelectorAll('[id^="settings-form-"]');

        forms.forEach(form => {
            const formData = new FormData(form);

            for (const [key, value] of formData.entries()) {
                const input = form.elements[key];

                if (input.type === 'checkbox') {
                    allSettings[key] = input.checked;
                } else if (input.type === 'number') {
                    allSettings[key] = value ? parseInt(value) : 0;
                } else {
                    // Skip empty password fields (secret fields)
                    if (input.type === 'password' && !value) {
                        continue;
                    }
                    allSettings[key] = value;
                }
            }
        });

        notify.info('Saving settings...');
        await api.bulkUpdateSettings(allSettings);
        notify.success('Settings saved successfully');
        renderSettings();

    } catch (error) {
        notify.error('Failed to save settings: ' + error.message);
    }
}
