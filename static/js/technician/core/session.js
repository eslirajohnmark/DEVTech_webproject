/* ============================================================================
 * data/session.js — server-backed session cache.
 * ==========================================================================*/

import { API } from '../core/api.js';

let _cache = null;
let _pending = null;

export function current() { return _cache; }

export async function ensure() {
    if (_cache) return _cache;
    if (_pending) return _pending;
    _pending = API.get('/technician/api/me').then(res => {
        _cache = res.ok ? res.technician : null;
        _pending = null;
        return _cache;
    });
    return _pending;
}

export async function login(techId, password) {
    const res = await API.post('/technician/api/login', {
        technician_id: techId,
        password,
    });
    if (res.ok) { _cache = res.technician; return res.technician; }
    return null;
}

export async function logout() {
    await API.post('/technician/api/logout');
    _cache = null;
}

export function isLoggedIn() { return !!_cache; }
export function _setCache(t) { _cache = t; }