/* ============================================================================
 * core/bus.js — tiny pub/sub for cross-module change notification.
 * ==========================================================================*/

const listeners = [];

export function on(fn) {
    listeners.push(fn);
    return fn;
}

export function off(fn) {
    const i = listeners.indexOf(fn);
    if (i !== -1) listeners.splice(i, 1);
}

export function emit(key) {
    for (const fn of listeners) {
        try { fn(key); } catch { /* isolate */ }
    }
}