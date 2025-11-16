/**
 * Utility functions for Lab Backup System
 */

// Date formatting
function formatDate(dateString) {
    if (!dateString) return 'N/A';
    const date = new Date(dateString);
    return date.toLocaleString('en-US', {
        year: 'numeric',
        month: 'short',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
    });
}

function formatDateRelative(dateString) {
    if (!dateString) return 'N/A';
    const date = new Date(dateString);
    const now = new Date();
    const diff = now - date;

    const seconds = Math.floor(diff / 1000);
    const minutes = Math.floor(seconds / 60);
    const hours = Math.floor(minutes / 60);
    const days = Math.floor(hours / 24);

    if (days > 7) return formatDate(dateString);
    if (days > 0) return `${days} day${days > 1 ? 's' : ''} ago`;
    if (hours > 0) return `${hours} hour${hours > 1 ? 's' : ''} ago`;
    if (minutes > 0) return `${minutes} minute${minutes > 1 ? 's' : ''} ago`;
    return 'Just now';
}

// File size formatting
function formatBytes(bytes, decimals = 2) {
    if (bytes === 0 || bytes === null || bytes === undefined) return '0 Bytes';

    const k = 1024;
    const dm = decimals < 0 ? 0 : decimals;
    const sizes = ['Bytes', 'KB', 'MB', 'GB', 'TB', 'PB'];

    const i = Math.floor(Math.log(bytes) / Math.log(k));

    return parseFloat((bytes / Math.pow(k, i)).toFixed(dm)) + ' ' + sizes[i];
}

// Status badge generation
function getStatusBadge(status) {
    const statusMap = {
        'completed': { class: 'badge-success', text: 'Completed' },
        'running': { class: 'badge-info', text: 'Running' },
        'pending': { class: 'badge-warning', text: 'Pending' },
        'failed': { class: 'badge-error', text: 'Failed' },
        'cancelled': { class: 'badge-error', text: 'Cancelled' },
    };

    const badge = statusMap[status.toLowerCase()] || { class: 'badge-primary', text: status };
    return `<span class="badge ${badge.class}">${badge.text}</span>`;
}

// Notification/Toast system
class NotificationManager {
    constructor() {
        this.container = null;
        this.init();
    }

    init() {
        if (!this.container) {
            this.container = document.createElement('div');
            this.container.id = 'notification-container';
            this.container.style.cssText = `
                position: fixed;
                top: 1rem;
                right: 1rem;
                z-index: 9999;
                display: flex;
                flex-direction: column;
                gap: 0.75rem;
                max-width: 400px;
            `;
            document.body.appendChild(this.container);
        }
    }

    show(message, type = 'info', duration = 5000) {
        const notification = document.createElement('div');
        notification.className = `alert alert-${type}`;
        notification.style.cssText = `
            animation: slideIn 0.3s ease-out;
            box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.1);
        `;

        const icons = {
            success: '✓',
            error: '✕',
            warning: '⚠',
            info: 'ℹ',
        };

        notification.innerHTML = `
            <div class="alert-icon">${icons[type] || icons.info}</div>
            <div class="alert-content">${message}</div>
        `;

        this.container.appendChild(notification);

        if (duration > 0) {
            setTimeout(() => {
                notification.style.animation = 'slideOut 0.3s ease-in';
                setTimeout(() => notification.remove(), 300);
            }, duration);
        }

        return notification;
    }

    success(message, duration) {
        return this.show(message, 'success', duration);
    }

    error(message, duration) {
        return this.show(message, 'error', duration);
    }

    warning(message, duration) {
        return this.show(message, 'warning', duration);
    }

    info(message, duration) {
        return this.show(message, 'info', duration);
    }
}

// Add animations
const style = document.createElement('style');
style.textContent = `
    @keyframes slideIn {
        from {
            transform: translateX(100%);
            opacity: 0;
        }
        to {
            transform: translateX(0);
            opacity: 1;
        }
    }

    @keyframes slideOut {
        from {
            transform: translateX(0);
            opacity: 1;
        }
        to {
            transform: translateX(100%);
            opacity: 0;
        }
    }
`;
document.head.appendChild(style);

const notify = new NotificationManager();

// Modal management
class Modal {
    constructor(title, content) {
        this.title = title;
        this.content = content;
        this.overlay = null;
        this.onConfirm = null;
        this.onCancel = null;
    }

    show() {
        this.overlay = document.createElement('div');
        this.overlay.className = 'modal-overlay';
        this.overlay.innerHTML = `
            <div class="modal">
                <div class="modal-header">
                    <h3 class="modal-title">${this.title}</h3>
                    <button class="modal-close" onclick="this.closest('.modal-overlay').remove()">×</button>
                </div>
                <div class="modal-body">
                    ${this.content}
                </div>
                <div class="modal-footer">
                    <button class="btn btn-secondary" data-action="cancel">Cancel</button>
                    <button class="btn btn-primary" data-action="confirm">Confirm</button>
                </div>
            </div>
        `;

        document.body.appendChild(this.overlay);

        this.overlay.querySelector('[data-action="cancel"]').addEventListener('click', () => {
            if (this.onCancel) this.onCancel();
            this.close();
        });

        this.overlay.querySelector('[data-action="confirm"]').addEventListener('click', () => {
            if (this.onConfirm) this.onConfirm();
            this.close();
        });

        this.overlay.addEventListener('click', (e) => {
            if (e.target === this.overlay) {
                this.close();
            }
        });

        return this;
    }

    close() {
        if (this.overlay) {
            this.overlay.remove();
            this.overlay = null;
        }
    }

    setOnConfirm(callback) {
        this.onConfirm = callback;
        return this;
    }

    setOnCancel(callback) {
        this.onCancel = callback;
        return this;
    }
}

function showConfirmDialog(title, message, onConfirm) {
    return new Modal(title, `<p>${message}</p>`)
        .setOnConfirm(onConfirm)
        .show();
}

// Loading overlay
function showLoading(container) {
    const loading = document.createElement('div');
    loading.className = 'loading-overlay';
    loading.innerHTML = '<div class="spinner"></div>';
    container.style.position = 'relative';
    container.appendChild(loading);
    return loading;
}

function hideLoading(loading) {
    if (loading && loading.parentNode) {
        loading.remove();
    }
}

// Form helpers
function getFormData(formElement) {
    const formData = new FormData(formElement);
    const data = {};
    for (const [key, value] of formData.entries()) {
        // Handle checkboxes
        if (formElement.elements[key].type === 'checkbox') {
            data[key] = formElement.elements[key].checked;
        }
        // Handle numbers
        else if (formElement.elements[key].type === 'number') {
            data[key] = value ? parseFloat(value) : null;
        }
        // Handle regular inputs
        else {
            data[key] = value;
        }
    }
    return data;
}

function setFormData(formElement, data) {
    Object.keys(data).forEach(key => {
        const element = formElement.elements[key];
        if (element) {
            if (element.type === 'checkbox') {
                element.checked = data[key];
            } else {
                element.value = data[key] || '';
            }
        }
    });
}

// Debounce function
function debounce(func, wait) {
    let timeout;
    return function executedFunction(...args) {
        const later = () => {
            clearTimeout(timeout);
            func(...args);
        };
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
    };
}

// Copy to clipboard
function copyToClipboard(text) {
    if (navigator.clipboard) {
        navigator.clipboard.writeText(text).then(() => {
            notify.success('Copied to clipboard');
        });
    } else {
        // Fallback
        const textArea = document.createElement('textarea');
        textArea.value = text;
        document.body.appendChild(textArea);
        textArea.select();
        document.execCommand('copy');
        document.body.removeChild(textArea);
        notify.success('Copied to clipboard');
    }
}

// Check if user is authenticated
function checkAuth() {
    const token = localStorage.getItem('auth_token');
    if (!token && !window.location.pathname.includes('login.html') && !window.location.pathname.includes('setup')) {
        window.location.href = '/static/login.html';
        return false;
    }
    return true;
}

// Get user info from token (simple JWT decode)
function getUserFromToken() {
    const token = localStorage.getItem('auth_token');
    if (!token) return null;

    try {
        const base64Url = token.split('.')[1];
        const base64 = base64Url.replace(/-/g, '+').replace(/_/g, '/');
        const jsonPayload = decodeURIComponent(atob(base64).split('').map(c => {
            return '%' + ('00' + c.charCodeAt(0).toString(16)).slice(-2);
        }).join(''));

        return JSON.parse(jsonPayload);
    } catch (e) {
        return null;
    }
}

// Format cron expression to readable text
function formatCronExpression(expression) {
    // This is a simple formatter - for complex expressions you might want a library
    const parts = expression.split(' ');
    if (parts.length < 5) return expression;

    const [minute, hour, dayOfMonth, month, dayOfWeek] = parts;

    if (minute === '0' && hour === '0' && dayOfMonth === '*') {
        return 'Daily at midnight';
    }
    if (minute === '0' && hour !== '*' && dayOfMonth === '*') {
        return `Daily at ${hour}:00`;
    }
    if (dayOfWeek !== '*' && dayOfMonth === '*') {
        const days = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'];
        return `Weekly on ${days[dayOfWeek]} at ${hour}:${minute}`;
    }

    return expression;
}
