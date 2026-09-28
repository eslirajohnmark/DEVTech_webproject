/* ============================================================================
 * data/approvals.js — customer approval request cache.
 * ==========================================================================*/

import { API } from '../core/api.js';
import { emit } from '../core/bus.js';

const _byJob = {};

export const all = () => Object.keys(_byJob).map(k => _byJob[k]);

export function pendingFor(jobId) {
    if (_byJob[jobId] !== undefined) return _byJob[jobId];
    API.get('/technician/api/jobs/' + jobId + '/approval').then(res => {
        if (res.ok) { _byJob[jobId] = res.approval; emit('approvals'); }
    });
    return null;
}

export async function request(jobId, data) {
    return API.post('/technician/api/jobs/' + jobId + '/approval', data);
}

export async function respond(approvalId, decision, note) {
    return API.post('/technician/api/approvals/' + approvalId + '/respond',
                    { decision, note: note || '' });
}