/* ============================================================================
 * data/incidents.js — incident report cache.
 * ==========================================================================*/

import { API } from '../core/api.js';
import { emit } from '../core/bus.js';

let _reports = [];

export const all     = () => _reports.slice();
export const forTech = () => _reports.slice();
export const forJob  = jid => _reports.filter(r => r.jobId === jid);

export async function file(techId, data) {
    const res = await API.post('/technician/api/incidents', data);
    if (res.ok) await refresh();
    return res;
}

export async function bootstrap() {
    const res = await API.get('/technician/api/incidents');
    if (res.ok) _reports = res.incidents;
    return _reports;
}

export async function refresh() {
    await bootstrap();
    emit('incidents');
}