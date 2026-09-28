/* ============================================================================
 * theme.js — dark/light toggle, applied before paint.
 *
 * Runs as soon as the module loads (imported by technician_base.html's
 * <head>, nonce-protected). Reads the saved theme from localStorage
 * and writes it to <html data-theme="..."> before the first paint so
 * there's no flash of the wrong theme.
 *
 * Also injects a toggle button into the topbar after the shell renders.
 * ==========================================================================*/

const STORAGE_KEY = 'devtech.tech.v1.theme';
const VALID = ['dark', 'light'];
const listeners = [];

const readStored = () => {
    try {
        const v = localStorage.getItem(STORAGE_KEY);
        return VALID.includes(v) ? v : null;
    } catch { return null; }
};

const writeStored = v => {
    try { localStorage.setItem(STORAGE_KEY, v); } catch { /* ignore */ }
};

const detectPreferred = () => {
    if (window.matchMedia &&
        window.matchMedia('(prefers-color-scheme: light)').matches) {
        return 'light';
    }
    return 'dark';
};

const apply = theme => {
    if (!VALID.includes(theme)) theme = 'dark';
    document.documentElement.setAttribute('data-theme', theme);
    document.documentElement.style.colorScheme = theme;
    return theme;
};

// Apply before paint
apply(readStored() || detectPreferred());

const current = () =>
    document.documentElement.getAttribute('data-theme') || 'dark';

const notify = theme => {
    for (const fn of listeners) {
        try { fn(theme); } catch { /* isolate */ }
    }
};

const updateButtons = () => {
    const isLight = current() === 'light';
    document.querySelectorAll('.tech-theme-toggle').forEach(b => {
        b.setAttribute('aria-pressed', isLight ? 'true' : 'false');
        b.title = isLight ? 'Switch to dark mode' : 'Switch to light mode';
    });
};

const set = theme => {
    const applied = apply(theme);
    writeStored(applied);
    updateButtons();
    notify(applied);
    return applied;
};

const toggle = () => set(current() === 'dark' ? 'light' : 'dark');
const onChange = fn => { listeners.push(fn); return fn; };

const buildButton = () => {
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'tech-icon-btn tech-theme-toggle';
    btn.setAttribute('aria-label', 'Toggle theme');
    btn.innerHTML =
        '<i class="fas fa-moon tech-theme-icon-dark" aria-hidden="true"></i>' +
        '<i class="fas fa-sun tech-theme-icon-light" aria-hidden="true"></i>';
    btn.addEventListener('click', toggle);
    return btn;
};

const inject = () => {
    let slot = document.querySelector('.tech-topbar-actions');
    if (!slot) {
        const bell = document.getElementById('bellBtn');
        if (bell && bell.parentElement) slot = bell.parentElement;
    }
    if (!slot) return;
    if (slot.querySelector('.tech-theme-toggle')) return;

    const btn = buildButton();
    const bellWrap = slot.querySelector('.tech-bell-wrap');
    if (bellWrap) slot.insertBefore(btn, bellWrap);
    else slot.appendChild(btn);
    updateButtons();
};

// Inject on DOM ready and again whenever the shell re-renders
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', inject);
} else {
    inject();
}

window.addEventListener('storage', e => {
    if (e.key === STORAGE_KEY && e.newValue && e.newValue !== current()) {
        apply(e.newValue);
        updateButtons();
        notify(e.newValue);
    }
});

export const Theme = { get: current, set, toggle, onChange, inject };