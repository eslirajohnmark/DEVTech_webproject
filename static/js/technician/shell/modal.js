/* ============================================================================
 * shell/modal.js — modal dialogs.
 * ==========================================================================*/

import { escape } from '../core/format.js';

let _active = null;

export function modal(options) {
    closeModal();

    const wrap = document.createElement('div');
    wrap.className = 'tech-modal';

    const actions = (options.actions || []).map((a, i) =>
        `<button class="tech-btn tech-btn--${a.tone || 'ghost'}" data-action="${i}">${escape(a.label)}</button>`
    ).join('');

    wrap.innerHTML =
        `<div class="tech-modal-card" role="dialog" aria-modal="true">` +
            `<div class="tech-modal-head">` +
                `<h2>${options.icon ? `<i class="fas ${options.icon}"></i> ` : ''}${escape(options.title || '')}</h2>` +
                `<button class="tech-modal-x" id="modalClose" aria-label="Close"><i class="fas fa-xmark"></i></button>` +
            `</div>` +
            `<div class="tech-modal-body">${options.body || ''}</div>` +
            (actions ? `<div class="tech-modal-foot">${actions}</div>` : '') +
        `</div>`;

    document.body.appendChild(wrap);
    void wrap.offsetWidth;
    wrap.classList.add('is-open');
    _active = wrap;

    wrap.querySelector('#modalClose').addEventListener('click', closeModal);
    wrap.querySelectorAll('[data-action]').forEach(btn => {
        btn.addEventListener('click', () => {
            const action = (options.actions || [])[Number(btn.dataset.action)];
            if (!action) return;
            if (action.onClick && action.onClick() === false) return;
            closeModal();
        });
    });
    wrap.addEventListener('click', e => { if (e.target === wrap) closeModal(); });

    const focusTarget = wrap.querySelector('input, textarea, select')
        || wrap.querySelector('.tech-modal-foot .tech-btn');
    if (focusTarget) focusTarget.focus();

    return wrap;
}

export function closeModal() {
    if (!_active) return;
    const wrap = _active;
    wrap.classList.remove('is-open');
    _active = null;
    setTimeout(() => wrap.remove(), 240);
}