/* ============================================================================
 * data/jobs.js — jobs cache + write actions.
 * ==========================================================================*/

import { API } from '../core/api.js';
import { emit } from '../core/bus.js';
import { now } from '../core/format.js';

let _jobs = [];
let _logs = {};
let _stats = null;

export const all       = () => _jobs.slice();
export const get       = id => _jobs.find(j => j.id === id) || null;
export const forTech   = tid => _jobs.filter(j => j.assignedTo === tid);
export const activeFor = tid => forTech(tid).filter(j => j.repairStatus !== 'completed');

export function scheduledFor(tid, isoDate) {
    const day = isoDate || now().slice(0, 10);
    return forTech(tid)
        .filter(j => j.scheduledDate === day && j.repairStatus !== 'completed')
        .sort((a, b) => toMinutes(a.scheduledTime) - toMinutes(b.scheduledTime));
}

export function statsFor(tid) {
    if (_stats) return _stats;
    const list = forTech(tid);
    const s = {
        total: list.length,
        accepted: 0, on_repair: 0, ready: 0,
        released: 0, on_hold: 0, homeService: 0, inShop: 0,
        highPriority: 0, active: 0,
    };
    for (const j of list) {
        if (s[j.repairStatus] !== undefined) s[j.repairStatus]++;
        if (j.repairStatus !== 'completed') s.active++;
        if (j.serviceMode === 'home_service') s.homeService++;
        else s.inShop++;
    }
    return s;
}

async function _post(url, body) {
    const res = await API.post(url, body || {});
    if (res.ok) { await refresh(); return res; }
    return res;
}

export const advance   = id => _post('/technician/api/jobs/' + id + '/advance');
export const saveNotes = (id, fields) => _post('/technician/api/jobs/' + id + '/notes', fields);

export function logFor(jobId) {
    if (_logs[jobId]) return _logs[jobId];
    API.get('/technician/api/jobs/' + jobId + '/logs').then(res => {
        if (res.ok) { _logs[jobId] = res.logs; emit('logs'); }
    });
    return _logs[jobId] || [];
}

export async function bootstrap() {
    const res = await API.get('/technician/api/jobs?scope=all');
    if (res.ok) _jobs = res.jobs;
    return _jobs;
}

export async function bootstrapStats() {
    const res = await API.get('/technician/api/jobs/stats');
    if (res.ok) _stats = res.stats;
    return _stats;
}

export async function refresh() {
    await bootstrap();
    emit('jobs');
    return { ok: true };
}

function toMinutes(t) {
    if (!t) return 0;
    const m = String(t).trim().match(/^(\d{1,2}):(\d{2})\s*(AM|PM)?$/i);
    if (!m) return 0;
    let h = parseInt(m[1], 10) % 12;
    const min = parseInt(m[2], 10);
    if (m[3] && m[3].toUpperCase() === 'PM') h += 12;
    return h * 60 + min;
}