/**
 * Main application controller
 */

// Check authentication on load
checkAuth();

// Current view
let currentView = 'dashboard';

// View registry
const views = {
    dashboard: renderDashboard,
    backups: renderBackups,
    schedules: renderSchedules,
    jobs: renderJobs,
    kvm: renderKVM,
    podman: renderPodman,
    storage: renderStorage,
    settings: renderSettings,
};

// Initialize app
async function initApp() {
    try {
        // Load user info
        const user = await api.getCurrentUser();
        displayUserInfo(user);

        // Setup navigation
        setupNavigation();

        // Load initial view
        const hash = window.location.hash.slice(1) || 'dashboard';
        loadView(hash);

    } catch (error) {
        console.error('Failed to initialize app:', error);
        notify.error('Failed to load application');
        api.logout();
    }
}

// Display user info in sidebar
function displayUserInfo(user) {
    const userAvatar = document.getElementById('userAvatar');
    const userName = document.getElementById('userName');
    const userRole = document.getElementById('userRole');

    userAvatar.textContent = user.username.charAt(0).toUpperCase();
    userName.textContent = user.username;
    userRole.textContent = user.role.charAt(0).toUpperCase() + user.role.slice(1);
}

// Setup navigation
function setupNavigation() {
    const navItems = document.querySelectorAll('.nav-item');

    navItems.forEach(item => {
        item.addEventListener('click', (e) => {
            e.preventDefault();
            const view = item.getAttribute('data-view');
            loadView(view);
        });
    });

    // Handle browser back/forward
    window.addEventListener('hashchange', () => {
        const hash = window.location.hash.slice(1) || 'dashboard';
        loadView(hash, false);
    });
}

// Load a view
function loadView(viewName, updateHash = true) {
    if (!views[viewName]) {
        console.error('View not found:', viewName);
        return;
    }

    // Update active navigation
    document.querySelectorAll('.nav-item').forEach(item => {
        item.classList.remove('active');
        if (item.getAttribute('data-view') === viewName) {
            item.classList.add('active');
        }
    });

    // Update hash
    if (updateHash) {
        window.location.hash = viewName;
    }

    // Update page title
    const titles = {
        dashboard: 'Dashboard',
        backups: 'Backup History',
        schedules: 'Backup Schedules',
        jobs: 'Job Monitor',
        kvm: 'KVM Infrastructure',
        podman: 'Podman Infrastructure',
        storage: 'Storage Backends',
        settings: 'System Settings',
    };
    document.getElementById('pageTitle').textContent = titles[viewName] || viewName;

    // Render view
    currentView = viewName;
    views[viewName]();
}

// Logout handler
function handleLogout() {
    showConfirmDialog(
        'Confirm Logout',
        'Are you sure you want to logout?',
        () => {
            api.logout();
        }
    );
}

// Initialize on page load
document.addEventListener('DOMContentLoaded', initApp);
