/* ============================================================================
 * data/threads.js — message thread cache.
 * ==========================================================================*/

import { API } from '../core/api.js';
import { emit } from '../core/bus.js';

let _threads = [];

export const all     = () => _threads.slice();
export const get     = id => _threads.find(t => t.id === id) || null;
export const forTech = () => _threads.slice();

export function findByJob(jobId, techId) {
    return _threads.find(t =>
        t.jobId === jobId && t.technicianId === techId) || null;
}

export const unreadCount = () =>
    _threads.reduce((s, t) => s + (t.unread || 0), 0);

export async function append(threadId, from, text) {
    const res = await API.post(
        '/technician/api/threads/' + threadId + '/messages', { text });
    if (res.ok) await refresh();
    return res;
}

export async function markRead(threadId) {
    const res = await API.post('/technician/api/threads/' + threadId + '/read');
    const t = get(threadId);
    if (t) t.unread = 0;
    emit('threads');
    return res;
}

export async function create(techId, participantType, participantName, jobId) {
    const res = await API.post('/technician/api/threads/find-or-create', {
        participantType, participantName, jobId,
    });
    if (res.ok) location.href = '/technician/messages/' + res.thread.id;
}

export async function bootstrap() {
    const res = await API.get('/technician/api/threads');
    if (res.ok) _threads = res.threads;
    return _threads;
}

export async function refresh() {
    await bootstrap();
    emit('threads');
}