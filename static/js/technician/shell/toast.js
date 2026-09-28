/* ============================================================================
 * shell/toast.js — transient notification.
 * ==========================================================================*/

import { escape } from '../core/format.js';

let _timer = null;

export function toast(message, tone, duration) {
    const existing = document.querySelector('.tech-toast');
    if (existing) existing.remove();
    if (_timer) clearTimeout(_timer);

    const icon = {
        ok:     'fa-circle-check',
        warn:   'fa-triangle-exclamation',
        danger: 'fa-circle-exclamation',
    }[tone] || 'fa-circle-info';

    const el = document.createElement('div');
    el.className = 'tech-toast' + (tone ? ' tech-toast--' + tone : '');
    el.innerHTML = `<i class="fas ${icon}"></i><span>${escape(message)}</span>`;
    document.body.appendChild(el);

    void el.offsetWidth;
    el.classList.add('is-visible');

    _timer = setTimeout(() => {
        el.classList.remove('is-visible');
        setTimeout(() => el.remove(), 260);
    }, duration || 3200);
}