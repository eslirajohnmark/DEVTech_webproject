/* ============================================================================
 * core/dynamic.js — build form controls from config.
 * ==========================================================================*/

import { escape } from './format.js';

export function select(id, options, current, attrs = '') {
    return `<select class="tech-select" id="${id}" ${attrs}>${
        options.map(o => {
            const val = typeof o === 'string' ? o : o.key;
            const label = typeof o === 'string' ? o : o.label;
            return `<option value="${escape(val)}"${
                current === val ? ' selected' : ''
            }>${escape(label)}</option>`;
        }).join('')
    }</select>`;
}

export function radioGroup(name, options, current, renderEach) {
    return options.map(o =>
        `<label class="tech-check">` +
            `<input type="radio" name="${name}" value="${escape(o.key)}"${
                current === o.key ? ' checked' : ''
            } />` +
            `<span>${renderEach(o)}</span>` +
        `</label>`
    ).join('');
}

export function checkboxGrid(name, options, selected = [], attrKey = 'label') {
    return `<div class="tech-check-grid">${
        options.map(o => {
            const val = o[attrKey] || o.key || o;
            return `<label class="tech-check">` +
                `<input type="checkbox" class="${name}" value="${escape(val)}"${
                    selected.includes(val) ? ' checked' : ''
                } />` +
                `<span>${escape(val)}</span>` +
            `</label>`;
        }).join('')
    }</div>`;
}