/* ============================================================================
 * data/intake.js — device intake record cache.
 * ==========================================================================*/

import { API } from '../core/api.js';
import { emit } from '../core/bus.js';

const _byJob = {};

export const all     = () => Object.keys(_byJob).map(k => _byJob[k]);
export const forTech = tid => all().filter(r => r && r.technicianId === tid);

export function forJob(jobId) {
    if (_byJob[jobId] !== undefined) return _byJob[jobId];
    API.get('/technician/api/jobs/' + jobId + '/intake').then(res => {
        if (res.ok) { _byJob[jobId] = res.record; emit('intake'); }
    });
    return null;
}

export async function save(jobId, data) {
    const res = await API.post('/technician/api/jobs/' + jobId + '/intake', data);
    if (res.ok) { _byJob[jobId] = res.record; emit('intake'); }
    return res;
}