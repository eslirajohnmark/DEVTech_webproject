// static/js/admin.js - Admin Panel JavaScript

// ============================================
// CSRF PROTECTION FOR ALL fetch() CALLS
// Wraps window.fetch once so every existing and future fetch() call in
// the admin panel automatically carries the X-CSRFToken header that
// Flask-WTF's CSRFProtect requires for POST/PUT/PATCH/DELETE.
//
// Reads the token from <meta name="csrf-token"> in admin_base.html.
// ============================================
(function () {
    const csrfMeta = document.querySelector('meta[name="csrf-token"]');
    const csrfToken = csrfMeta ? csrfMeta.getAttribute('content') : null;
    const originalFetch = window.fetch;

    window.fetch = function (input, init) {
        init = init || {};
        const method = (init.method || 'GET').toUpperCase();
        const isStateChanging = ['POST', 'PUT', 'PATCH', 'DELETE'].includes(method);

        let isSameOrigin = true;
        try {
            const url = new URL(
                typeof input === 'string' ? input : input.url,
                window.location.href
            );
            isSameOrigin = url.origin === window.location.origin;
        } catch (e) {
            isSameOrigin = true;
        }

        if (isStateChanging && isSameOrigin && csrfToken) {
            init.headers = Object.assign({}, init.headers, {
                'X-CSRFToken': csrfToken,
            });
        }

        return originalFetch(input, init);
    };
})();


// ============================================
// MOBILE MENU TOGGLE
// Shows/hides the mobile nav drawer. Matches the CSS contract in
// admin.css's "MOBILE MENU TOGGLE" section.
// ============================================
function toggleMobileMenu() {
    const menu = document.getElementById('adminMobileNavMenu');
    if (menu) menu.classList.toggle('open');
}


// ============================================
// SESSION WATCH
// Every 45s, quietly confirm this tab still has an active admin
// session. If not, show a banner but do NOT reload the page — the
// admin may be halfway through typing something, and a silent reload
// would throw that away. Reloading is opt-in via the banner's button.
// ============================================
function startSessionWatch() {
    setInterval(function () {
        if (document.visibilityState !== 'visible') return;
        fetch('/api/admin/session-check', { credentials: 'same-origin' })
            .then(function (r) {
                if (!r.ok) showSessionEndedBanner();
            })
            .catch(function () { /* transient network hiccup — skip */ });
    }, 45000);
}

function showSessionEndedBanner() {
    if (document.getElementById('adminSessionEndedBanner')) return;

    var banner = document.createElement('div');
    banner.id = 'adminSessionEndedBanner';
    banner.style.cssText =
        'position:fixed;top:0;left:0;right:0;z-index:99999;' +
        'background:#ef4444;color:#fff;padding:0.9rem 1.2rem;' +
        'display:flex;align-items:center;justify-content:center;gap:0.8rem;' +
        'font-family:inherit;font-size:0.92rem;font-weight:600;' +
        'box-shadow:0 2px 12px rgba(0,0,0,0.25);';
    banner.innerHTML =
        '<i class="fas fa-exclamation-triangle"></i>' +
        '<span>Your admin session ended. Sign in again to continue.</span>' +
        '<a href="/admin/login" style="color:#fff;text-decoration:underline;' +
        'margin-left:0.4rem;">Log in</a>';
    document.body.prepend(banner);
}


// ============================================
// PRESENCE HEARTBEAT
// Pings the server periodically so this admin's last_active stays
// fresh. Paused while the tab is hidden.
// ============================================
function startPresenceHeartbeat() {
    const HEARTBEAT_MS = 25000;

    function ping() {
        fetch('/api/ping', { method: 'POST' }).catch(function () {});
    }

    ping();
    setInterval(function () {
        if (document.visibilityState === 'visible') ping();
    }, HEARTBEAT_MS);

    document.addEventListener('visibilitychange', function () {
        if (document.visibilityState === 'visible') ping();
    });
}


// ============================================
// KEYBOARD SHORTCUTS
//   Ctrl+Shift+L → Admin login
//   Ctrl+Shift+T → Technician login
//   Ctrl+Shift+R → Technician registration
// Each is a no-op if you're already on that page, and never fires
// while a text field has focus.
// ============================================
(function () {
    document.addEventListener('keydown', function (e) {
        if (!(e.ctrlKey && e.shiftKey)) return;

        var t = e.target;
        if (t && (t.tagName === 'INPUT' || t.tagName === 'TEXTAREA'
                  || t.isContentEditable)) return;

        var k = (e.key || '').toLowerCase();

        if (k === 'l') {
            e.preventDefault();
            if (location.pathname !== '/admin/login') location.href = '/admin/login';
        } else if (k === 't') {
            e.preventDefault();
            if (location.pathname !== '/technician/login') location.href = '/technician/login';
        } else if (k === 'r') {
            e.preventDefault();
            if (location.pathname !== '/technician/register') location.href = '/technician/register';
        }
    });
})();


// ============================================
// DOM READY
// Wires up everything that needs the DOM to exist.
// ============================================
document.addEventListener('DOMContentLoaded', function () {
    // Close the mobile nav drawer after navigating.
    const mobileMenu = document.getElementById('adminMobileNavMenu');
    if (mobileMenu) {
        mobileMenu.querySelectorAll('.admin-nav-item').forEach(function (link) {
            link.addEventListener('click', function () {
                mobileMenu.classList.remove('open');
            });
        });
    }

    // ---- flash messages: dismiss button + auto-hide ----
    document.querySelectorAll('.flash-message').forEach(function (msg) {
        const closeBtn = msg.querySelector('.flash-close');
        if (closeBtn) {
            closeBtn.addEventListener('click', function () {
                msg.remove();
            });
        }
        setTimeout(function () {
            if (msg) {
                msg.style.opacity = '0';
                msg.style.transform = 'translateY(-10px)';
                setTimeout(function () { msg.remove(); }, 300);
            }
        }, 5000);
    });

    // ---- table rows clickable via data-href ----
    document.querySelectorAll('.admin-table tbody tr').forEach(function (row) {
        row.addEventListener('click', function (e) {
            if (e.target.tagName === 'BUTTON' || e.target.tagName === 'A') return;
            const link = this.dataset.href;
            if (link) {
                window.location.href = link;
            }
        });
    });

    // ---- confirm delete actions ----
    document.querySelectorAll('.admin-btn-danger[data-confirm]').forEach(function (btn) {
        btn.addEventListener('click', function (e) {
            if (!confirm(this.dataset.confirm ||
                         'Are you sure you want to perform this action?')) {
                e.preventDefault();
            }
        });
    });

    // ---- search filter ----
    const searchInput = document.getElementById('searchInput');
    if (searchInput) {
        searchInput.addEventListener('input', function () {
            const filter = this.value.toLowerCase();
            document.querySelectorAll('.admin-table tbody tr').forEach(function (row) {
                const text = row.textContent.toLowerCase();
                row.style.display = text.includes(filter) ? '' : 'none';
            });
        });
    }

    // ---- modal backdrop click + Escape closes ----
    document.querySelectorAll('.admin-modal').forEach(function (modal) {
        modal.addEventListener('click', function (e) {
            if (e.target === this) {
                this.classList.remove('active');
                document.body.style.overflow = '';
            }
        });
    });
    document.addEventListener('keydown', function (e) {
        if (e.key === 'Escape') {
            document.querySelectorAll('.admin-modal.active').forEach(function (modal) {
                modal.classList.remove('active');
                document.body.style.overflow = '';
            });
        }
    });

    // ---- background tasks ----
    startPresenceHeartbeat();

    // Pages that fetch their own data live (User Management) set
    // data-live-refresh and manage their own polling.
    if (!document.body.dataset.liveRefresh) {
        startSessionWatch();
    }
});


// ============================================
// ADMIN TOAST
// ============================================
function showAdminToast(message, type) {
    type = type || 'info';

    var toast = document.getElementById('adminToast');
    if (!toast) {
        toast = document.createElement('div');
        toast.id = 'adminToast';
        toast.className = 'admin-toast';
        toast.innerHTML =
            '<i class="fas fa-info-circle"></i>' +
            '<span id="toastMessage"></span>';
        document.body.appendChild(toast);
    }

    var msg = toast.querySelector('#toastMessage');
    if (msg) msg.textContent = message;

    toast.classList.remove('show');
    void toast.offsetWidth;   // force reflow so the animation retriggers
    toast.classList.add('show');

    setTimeout(function () {
        toast.classList.remove('show');
    }, 3000);
}


// ============================================
// MODAL HELPERS
// ============================================
function openAdminModal(modalId) {
    var modal = document.getElementById(modalId);
    if (modal) {
        modal.classList.add('active');
        document.body.style.overflow = 'hidden';
    }
}

function closeAdminModal(modalId) {
    var modal = document.getElementById(modalId);
    if (modal) {
        modal.classList.remove('active');
        document.body.style.overflow = '';
    }
}


// ============================================
// AJAX HELPER
// ============================================
function adminAjax(url, method, data) {
    method = method || 'GET';
    return fetch(url, {
        method: method,
        headers: {
            'Content-Type': 'application/json',
            'X-Requested-With': 'XMLHttpRequest'
        },
        body: data ? JSON.stringify(data) : null
    })
    .then(function (response) { return response.json(); })
    .catch(function (error) {
        showAdminToast('An error occurred: ' + error.message, 'error');
        throw error;
    });
}