/* ============================================================================
 * shell/index.js — public shell API.
 *
 * Every page controller imports `init` from here. Returns a promise
 * resolving to the technician record (or null after redirecting to
 * login).
 * ==========================================================================*/

import { escape } from '../core/format.js';
import { on as busOn } from '../core/bus.js';
import * as Session  from '../data/session.js';
import * as Config   from '../data/config.js';
import * as Jobs     from '../data/jobs.js';
import * as Threads  from '../data/threads.js';
import * as Notes    from '../data/notifications.js';
import * as Incidents from '../data/incidents.js';
import * as Technicians from '../data/technicians.js';

import { sidebarMarkup, topbarMarkup, bellPanelMarkup } from './layout.js';
import { refreshBadges } from './badges.js';
import { toast } from './toast.js';
import { modal, closeModal } from './modal.js';

export { toast, modal, closeModal, escape };

const state = {
    tech: null,
    page: null,
    contentEl: null,
    scrimEl: null,
    sidebarEl: null,
    bellOpen: false,
    activeModal: null,
};

export async function init(meta) {
    meta = meta || {};

    // Load config first so anything reading it has values.
    await Config.load();

    // Fetch everything the shell needs, in parallel.
    await Promise.all([
        Technicians.bootstrap(),
        Jobs.bootstrap(),
        Jobs.bootstrapStats(),
        Threads.bootstrap(),
        Notes.bootstrap(),
        Incidents.bootstrap(),
    ]);

    const tech = await Session.ensure();
    if (!tech) {
        location.replace('/technician/login');
        return null;
    }

    state.tech = tech;
    state.page = meta.page || 'dashboard';

    const layout = document.getElementById('techLayout');
    if (!layout) {
        console.error('[TechShell] Missing <div id="techLayout"></div>');
        return null;
    }

    layout.innerHTML =
        sidebarMarkup(tech, state.page) +
        `<div class="tech-main">` +
            topbarMarkup(meta, tech) +
            `<main class="tech-content" id="techContent"></main>` +
        `</div>` +
        `<div class="tech-scrim" id="techScrim"></div>`;

    if (meta.title) document.title = 'DEVTech · ' + meta.title;

    state.contentEl = document.getElementById('techContent');
    state.scrimEl   = document.getElementById('techScrim');
    state.sidebarEl = document.getElementById('techSidebar');

    wireShell();

    busOn(() => refreshBadges(state));

    return tech;
}

export function content() { return state.contentEl; }

function wireShell() {
    const _on = (id, handler) => {
        const el = document.getElementById(id);
        if (el) el.addEventListener('click', handler);
    };

    _on('sidebarOpen', openDrawer);
    _on('sidebarClose', closeDrawer);
    if (state.scrimEl) state.scrimEl.addEventListener('click', closeDrawer);

    _on('bellBtn', e => {
        e.stopPropagation();
        state.bellOpen ? closeBell() : openBell();
    });

    document.addEventListener('click', e => {
        if (!state.bellOpen) return;
        const panel = document.getElementById('bellPanel');
        const wrap = panel && panel.parentElement;
        if (wrap && !wrap.contains(e.target)) closeBell();
    });

    document.addEventListener('keydown', e => {
        if (e.key !== 'Escape') return;
        if (state.activeModal) closeModal();
        else if (state.bellOpen) closeBell();
        else closeDrawer();
    });

    _on('logoutBtn', e => {
        e.preventDefault();
        modal({
            title: 'Sign out',
            icon: 'fa-arrow-right-from-bracket',
            body: '<p style="font-size:0.87rem;">You will be returned to the login screen. Your session ends immediately.</p>',
            actions: [
                { label: 'Cancel', tone: 'ghost' },
                { label: 'Sign out', tone: 'danger', onClick: () => {
                    Session.logout().then(() => {
                        location.href = '/technician/login';
                    });
                }},
            ],
        });
    });

    closeDrawer();
}

function openDrawer() {
    if (state.sidebarEl) state.sidebarEl.classList.add('is-open');
    if (state.scrimEl) state.scrimEl.classList.add('is-visible');
}
function closeDrawer() {
    if (state.sidebarEl) state.sidebarEl.classList.remove('is-open');
    if (state.scrimEl) state.scrimEl.classList.remove('is-visible');
}
function openBell() {
    const panel = document.getElementById('bellPanel');
    if (!panel) return;
    panel.hidden = false;
    state.bellOpen = true;
    Notes.markAllRead();
    refreshBadges(state);
}
function closeBell() {
    const panel = document.getElementById('bellPanel');
    if (panel) panel.hidden = true;
    state.bellOpen = false;
}