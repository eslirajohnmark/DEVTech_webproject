/* ============================================================================
 * data/reports.js — service report cache.
 * ==========================================================================*/

import { API } from '../core/api.js';
import { emit } from '../core/bus.js';

const _byJob = {};

export const all     = () => Object.keys(_byJob).map(k => _byJob[k]);
export const forTech = () => all();
export const forJob  = jid => (_byJob[jid] ? [_byJob[jid]] : []);

export function latestForJob(jobId) {
    if (_byJob[jobId] !== undefined) return _byJob[jobId];
    API.get('/technician/api/jobs/' + jobId + '/report').then(res => {
        if (res.ok) { _byJob[jobId] = res.report; emit('reports'); }
    });
    return null;
}

async function _save(jobId, data, action) {
    const payload = { ...data, action };
    const res = await API.post(
        '/technician/api/jobs/' + jobId + '/report', payload);
    if (res.ok) { _byJob[jobId] = res.report; emit('reports'); }
    return res;
}

export const saveDraft = (jobId, _techId, data) => _save(jobId, data, 'draft');
export const submit    = (jobId, _techId, data) => _save(jobId, data, 'submit');

export function archiveCurrent(jobId) {
    _byJob[jobId] = null;
    return { ok: true };
}