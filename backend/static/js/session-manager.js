/**
 * Session Manager - Monitors JWT token expiration and provides warnings
 */

class SessionManager {
    constructor(apiClient, warningMinutes = 5) {
        this.api = apiClient;
        this.warningMinutes = warningMinutes;
        this.checkInterval = 60000; // Check every minute
        this.warningShown = false;
        this.intervalId = null;
        this.notificationId = null;
    }

    /**
     * Load session settings from the backend
     */
    async loadSettings() {
        try {
            const warningResponse = await this.api.request('/settings/session.warning_minutes');
            if (warningResponse && warningResponse.value !== undefined) {
                this.warningMinutes = parseInt(warningResponse.value);
                console.log(`Session warning set to ${this.warningMinutes} minutes`);
            }
        } catch (error) {
            console.warn('Failed to load session settings, using defaults:', error);
        }
    }

    /**
     * Decode JWT token and extract expiration time
     */
    decodeToken(token) {
        try {
            const base64Url = token.split('.')[1];
            const base64 = base64Url.replace(/-/g, '+').replace(/_/g, '/');
            const jsonPayload = decodeURIComponent(atob(base64).split('').map(function(c) {
                return '%' + ('00' + c.charCodeAt(0).toString(16)).slice(-2);
            }).join(''));

            return JSON.parse(jsonPayload);
        } catch (error) {
            console.error('Error decoding token:', error);
            return null;
        }
    }

    /**
     * Get time remaining until token expires (in minutes)
     */
    getTimeRemaining() {
        const token = this.api.getToken();
        if (!token) {
            return 0;
        }

        const payload = this.decodeToken(token);
        if (!payload || !payload.exp) {
            return 0;
        }

        const now = Math.floor(Date.now() / 1000);
        const expiresAt = payload.exp;
        const secondsRemaining = expiresAt - now;

        return Math.floor(secondsRemaining / 60);
    }

    /**
     * Show session expiration warning notification
     */
    showWarning(minutesRemaining) {
        // Remove any existing warning
        this.hideWarning();

        const notificationContainer = document.getElementById('notification-container');
        if (!notificationContainer) {
            console.error('Notification container not found');
            return;
        }

        const notification = document.createElement('div');
        notification.className = 'notification notification-warning session-warning';
        notification.id = 'session-warning';

        notification.innerHTML = `
            <div class="notification-content">
                <span class="notification-icon">⚠</span>
                <span class="notification-message">
                    Your session will expire in ${minutesRemaining} ${minutesRemaining === 1 ? 'minute' : 'minutes'}
                </span>
                <button class="btn btn-sm btn-primary" onclick="sessionManager.continueSession()">
                    Continue Session
                </button>
                <button class="notification-close" onclick="sessionManager.hideWarning()">×</button>
            </div>
        `;

        notificationContainer.appendChild(notification);
        this.notificationId = 'session-warning';
        this.warningShown = true;

        // Animate in
        setTimeout(() => notification.classList.add('show'), 10);
    }

    /**
     * Hide session warning notification
     */
    hideWarning() {
        const notification = document.getElementById('session-warning');
        if (notification) {
            notification.classList.remove('show');
            setTimeout(() => notification.remove(), 300);
        }
        this.warningShown = false;
        this.notificationId = null;
    }

    /**
     * Refresh the session by getting a new access token
     */
    async continueSession() {
        try {
            this.hideWarning();

            await this.api.refreshAccessToken();

            // Show success notification
            if (window.notify) {
                notify.success('Session renewed successfully');
            }

            this.warningShown = false;

        } catch (error) {
            console.error('Failed to refresh session:', error);

            if (window.notify) {
                notify.error('Failed to renew session. Please log in again.');
            }

            // Redirect to login after delay
            setTimeout(() => this.api.logout(), 2000);
        }
    }

    /**
     * Check session status and show warning if needed
     */
    checkSession() {
        const minutesRemaining = this.getTimeRemaining();

        // Token expired
        if (minutesRemaining <= 0) {
            console.log('Session expired, logging out...');
            this.stop();

            if (window.notify) {
                notify.error('Your session has expired. Please log in again.');
            }

            setTimeout(() => this.api.logout(), 2000);
            return;
        }

        // Show warning if within warning threshold and not already shown
        if (minutesRemaining <= this.warningMinutes && !this.warningShown) {
            console.log(`Session expiring in ${minutesRemaining} minutes, showing warning...`);
            this.showWarning(minutesRemaining);
        }

        // Update warning message if already shown
        if (this.warningShown) {
            const messageEl = document.querySelector('#session-warning .notification-message');
            if (messageEl) {
                messageEl.textContent = `Your session will expire in ${minutesRemaining} ${minutesRemaining === 1 ? 'minute' : 'minutes'}`;
            }
        }
    }

    /**
     * Start monitoring session
     */
    async start() {
        // Load settings from backend
        await this.loadSettings();

        // Initial check
        this.checkSession();

        // Set up periodic checks
        this.intervalId = setInterval(() => {
            this.checkSession();
        }, this.checkInterval);

        console.log('Session manager started');
    }

    /**
     * Stop monitoring session
     */
    stop() {
        if (this.intervalId) {
            clearInterval(this.intervalId);
            this.intervalId = null;
        }

        this.hideWarning();
        console.log('Session manager stopped');
    }

    /**
     * Update warning threshold
     */
    setWarningMinutes(minutes) {
        this.warningMinutes = minutes;
        this.warningShown = false; // Reset warning state
    }
}

// Global session manager instance (will be initialized in app.js)
let sessionManager = null;
