/* ============================================================================
 * core/dom.js — tiny DOM helpers.
 * ==========================================================================*/

export const $  = (sel, root = document) => root.querySelector(sel);
export const $$ = (sel, root = document) =>
    Array.from(root.querySelectorAll(sel));

export function on(id, event, handler) {
    const el = typeof id === 'string' ? document.getElementById(id) : id;
    if (el) el.addEventListener(event, handler);
    return el;
}

export function val(id) {
    const el = document.getElementById(id);
    return el ? el.value.trim() : '';
}

export function checked(id) {
    const el = document.getElementById(id);
    return el ? !!el.checked : false;
}

export function toggleError(id, show) {
    const el = document.getElementById(id);
    if (el) el.classList.toggle('is-shown', !!show);
    return !show;
}