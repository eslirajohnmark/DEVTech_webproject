/* ============================================================================
 * shell/layout.js — sidebar + topbar markup.
 * ==========================================================================*/

import { escape, relative } from '../core/format.js';
import * as Notes from '../data/notifications.js';

const NAV = [
    { key: 'dashboard', label: 'Dashboard',        icon: 'fa-gauge-high',    href: '/technician/dashboard' },
    { key: 'my_jobs',   label: 'My Jobs',          icon: 'fa-briefcase',     href: '/technician/jobs' },
    { key: 'intake',    label: 'Device Intake',    icon: 'fa-box-archive',   href: '/technician/intake' },
    { key: 'messages',  label: 'Messages',         icon: 'fa-comments',      href: '/technician/messages', unread: true },
    { key: 'incidents', label: 'Incident Reports', icon: 'fa-shield-halved', href: '/technician/incidents' },
    { key: 'profile',   label: 'My Profile',       icon: 'fa-user',          href: '/technician/profile' },
];

function availabilityLabel(key) {
    return {
        available: 'Available',
        on_field: 'On Field',
        off_duty: 'Off Duty',
    }[key] || key;
}

export function sidebarMarkup(tech, active) {
    const items = NAV.map(item => {
        const isActive = item.key === active ? ' is-active' : '';
        return `<a class="tech-nav-item${isActive}" href="${item.href}">` +
            `<i class="fas ${item.icon}"></i><span>${escape(item.label)}</span>` +
            (item.unread ? '<span class="tech-nav-badge" hidden></span>' : '') +
        `</a>`;
    }).join('');

    return `<aside class="tech-sidebar" id="techSidebar">` +
        `<div class="tech-brand">` +
            `<div class="tech-brand-mark"><i class="fas fa-screwdriver-wrench"></i></div>` +
            `<div class="tech-brand-text">` +
                `<div class="tech-brand-name">DEV<span>Tech</span></div>` +
                `<div class="tech-brand-sub">Technician Portal</div>` +
            `</div>` +
            `<button class="tech-sidebar-close" id="sidebarClose" aria-label="Close menu"><i class="fas fa-xmark"></i></button>` +
        `</div>` +
        `<a class="tech-whoami" href="/technician/profile">` +
            `<div class="tech-whoami-avatar">${escape(tech.avatarInitials || 'TT')}</div>` +
            `<div class="tech-whoami-text">` +
                `<span class="tech-whoami-name">${escape(tech.name)}</span>` +
                `<span class="tech-whoami-role">` +
                    `<i class="fas fa-circle tech-dot ${escape(tech.availability || 'available')}"></i>` +
                    escape(availabilityLabel(tech.availability || 'available')) +
                `</span>` +
            `</div>` +
        `</a>` +
        `<nav class="tech-nav">${items}</nav>` +
        `<a class="tech-nav-item tech-logout" href="#" id="logoutBtn">` +
            `<i class="fas fa-arrow-right-from-bracket"></i><span>Sign out</span>` +
        `</a>` +
    `</aside>`;
}

export function topbarMarkup(meta, tech) {
    const dateLabel = new Date().toLocaleDateString('en-US', {
        weekday: 'short', month: 'short', day: 'numeric',
    });
    return `<header class="tech-topbar">` +
        `<button class="tech-menu-btn" id="sidebarOpen" aria-label="Open menu"><i class="fas fa-bars"></i></button>` +
        `<div class="tech-topbar-title">` +
            `<h1>${escape(meta.title || 'Technician Portal')}</h1>` +
            (meta.subtitle ? `<p>${escape(meta.subtitle)}</p>` : '') +
        `</div>` +
        `<div class="tech-topbar-actions">` +
            `<span class="tech-today"><i class="fas fa-calendar-day"></i> ${escape(dateLabel)}</span>` +
            `<a class="tech-icon-btn" href="/technician/messages" aria-label="Messages">` +
                `<i class="fas fa-comments"></i>` +
            `</a>` +
            `<div class="tech-bell-wrap">` +
                `<button class="tech-icon-btn" id="bellBtn" aria-label="Notifications">` +
                    `<i class="fas fa-bell"></i>` +
                `</button>` +
                `<div class="tech-bell-panel" id="bellPanel" hidden>${bellPanelMarkup(tech)}</div>` +
            `</div>` +
        `</div>` +
    `</header>`;
}

export function bellPanelMarkup(tech) {
    const notes = Notes.forTech(tech.id);
    if (!notes.length) {
        return `<div class="tech-bell-head">Notifications</div>` +
               `<div class="tech-bell-empty">Nothing new right now.</div>`;
    }
    const iconFor = {
        message: 'fa-comment-dots',
        admin: 'fa-user-shield',
        approval: 'fa-circle-question',
        schedule: 'fa-calendar-day',
        system: 'fa-circle-info',
    };
    return `<div class="tech-bell-head">Notifications</div>` +
        notes.map(n =>
            `<div class="tech-bell-item${n.read ? '' : ' is-unread'}">` +
                `<i class="fas ${iconFor[n.kind] || 'fa-bell'}"></i>` +
                `<div>` +
                    `<p>${escape(n.text)}</p>` +
                    `<span>${escape(relative(n.at))}</span>` +
                `</div>` +
            `</div>`
        ).join('');
}