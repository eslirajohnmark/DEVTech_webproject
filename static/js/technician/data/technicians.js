/* ============================================================================
 * data/technicians.js — single-technician session, no listing needed.
 * ==========================================================================*/

import * as Session from './session.js';

export function all() { return []; }

export async function bootstrap() { return []; }

export function get(id) {
    const me = Session.current();
    return me && me.id === id ? me : null;
}

export async function update(id, changes) {
    return { ok: false, reason: 'Contact an administrator to change your details.' };
}

export async function setAvailability(id, availability) {
    return { ok: false, reason: 'Contact an administrator to change your availability.' };
}