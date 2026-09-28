/* ============================================================================
 * core/storage.js — namespaced localStorage with memory fallback.
 * ==========================================================================*/

const NS = 'devtech.tech.v1.';
const memory = {};

export const available = (() => {
    try {
        const probe = NS + 'probe';
        localStorage.setItem(probe, '1');
        localStorage.removeItem(probe);
        return true;
    } catch {
        return false;
    }
})();

export function read(key, fallback) {
    try {
        const raw = available ? localStorage.getItem(NS + key) : memory[key];
        return raw ? JSON.parse(raw) : fallback;
    } catch {
        return fallback;
    }
}

export function write(key, value) {
    const raw = JSON.stringify(value);
    try {
        if (available) localStorage.setItem(NS + key, raw);
        else memory[key] = raw;
    } catch {
        memory[key] = raw;
    }
    return value;
}

export function remove(key) {
    try {
        if (available) localStorage.removeItem(NS + key);
        else delete memory[key];
    } catch {
        delete memory[key];
    }
}

export function keys() {
    if (!available) return Object.keys(memory);
    const out = [];
    for (let i = 0; i < localStorage.length; i++) {
        const k = localStorage.key(i);
        if (k && k.startsWith(NS)) out.push(k.slice(NS.length));
    }
    return out;
}

export { NS };