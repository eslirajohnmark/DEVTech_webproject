/* ============================================================================
 * shell/badges.js — refreshes unread counters on nav and bell.
 * ==========================================================================*/

import * as Threads from '../data/threads.js';
import * as Notes   from '../data/notifications.js';

export function refreshBadges(state) {
    if (!state.tech) return;
    const unreadMessages = Threads.unreadCount();
    const unreadNotes = Notes.unreadCount();

    document.querySelectorAll('.tech-nav-item').forEach(item => {
        const href = item.getAttribute('href') || '';
        if (!href.includes('/messages')) return;
        const badge = item.querySelector('.tech-nav-badge');
        if (unreadMessages) {
            if (badge) badge.textContent = unreadMessages;
            else {
                const span = document.createElement('span');
                span.className = 'tech-nav-badge';
                span.textContent = unreadMessages;
                item.appendChild(span);
            }
        } else if (badge) badge.remove();
    });

    const msgIcon = document.querySelector(
        '.tech-topbar-actions a[href*="/messages"]');
    if (msgIcon) {
        const mb = msgIcon.querySelector('.tech-icon-badge');
        if (unreadMessages) {
            if (mb) mb.textContent = unreadMessages;
            else {
                const s = document.createElement('span');
                s.className = 'tech-icon-badge';
                s.textContent = unreadMessages;
                msgIcon.appendChild(s);
            }
        } else if (mb) mb.remove();
    }

    const bellBtn = document.getElementById('bellBtn');
    if (bellBtn) {
        const bb = bellBtn.querySelector('.tech-icon-badge');
        if (unreadNotes) {
            if (bb) bb.textContent = unreadNotes;
            else {
                const s = document.createElement('span');
                s.className = 'tech-icon-badge';
                s.textContent = unreadNotes;
                bellBtn.appendChild(s);
            }
        } else if (bb) bb.remove();
    }
}