/* ============================================================================
 * data/notifications.js — notifications cache.
 * ==========================================================================*/

import { API } from '../core/api.js';
import { emit } from '../core/bus.js';

let _notes = [];

export const all         = () => _notes.slice();
export const forTech     = () => _notes.slice();
export const unreadCount = () => _notes.filter(n => !n.read).length;

export async function markAllRead() {
    await API.post('/technician/api/notifications/read');
    _notes.forEach(n => { n.read = true; });
    emit('notifications');
}

export async function bootstrap() {
    const res = await API.get('/technician/api/notifications');
    if (res.ok) _notes = res.notifications;
    return _notes;
}