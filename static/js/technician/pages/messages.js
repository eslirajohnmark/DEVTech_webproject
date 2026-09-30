/* ============================================================================
 * pages/messages.js — thread list + chat pane.
 * ==========================================================================*/

import * as Shell from '../shell/index.js';
import * as Threads from '../data/threads.js';
import { escape, relative } from '../core/format.js';

export async function init(tech, threadId) {
    const el = Shell.content();
    const threads = Threads.forTech(tech.id);
    const active = threadId ? Threads.get(Number(threadId)) : threads[0];

    el.innerHTML = `
        <section class="tech-msg-layout">
            <aside class="tech-msg-list">
                <div class="tech-card-head" style="padding:0.9rem 1rem 0.6rem;">
                    <h3 class="tech-card-title"><i class="fas fa-comments"></i> Conversations</h3>
                </div>
                ${threads.length
                    ? threads.map(t => `
                        <button class="tech-thread ${active && active.id === t.id ? 'is-active' : ''}" data-thread="${escape(t.id)}">
                            <div class="tech-thread-avatar">${escape((t.participantName || '?').charAt(0).toUpperCase())}</div>
                            <div class="tech-thread-body">
                                <div class="tech-thread-name">
                                    <span style="overflow:hidden; text-overflow:ellipsis; white-space:nowrap;">${escape(t.participantName || 'Conversation')}</span>
                                    ${t.unread ? `<span class="tech-thread-unread">${t.unread}</span>` : ''}
                                </div>
                                <div class="tech-thread-preview">${escape((t.lastMessage || '').slice(0, 44))}</div>
                            </div>
                            <div class="tech-thread-time">${escape(relative(t.updatedAt))}</div>
                        </button>
                    `).join('')
                    : '<p class="tech-hint" style="padding:1rem;">No conversations yet.</p>'}
            </aside>

            <main class="tech-msg-pane">
                ${active ? `
                    <div class="tech-msg-head">
                        <h3 style="font-size:0.94rem; font-weight:700;">${escape(active.participantName || 'Conversation')}</h3>
                    </div>
                    <div class="tech-msg-body" id="chatMessages">
                        ${(active.messages || []).map(m => `
                            <div class="tech-bubble from-${m.from === 'technician' ? 'tech' : 'customer'}">
                                ${escape(m.text)}
                                <span class="tech-bubble-time">${escape(relative(m.at))}</span>
                            </div>
                        `).join('')}
                    </div>
                    <form class="tech-msg-compose" id="chatForm">
                        <textarea class="tech-textarea" id="chatText" placeholder="Type a message..." rows="1"></textarea>
                        <button class="tech-btn tech-btn--primary" type="submit">
                            <i class="fas fa-paper-plane"></i>
                        </button>
                    </form>
                ` : '<div class="tech-hint" style="padding:1rem;">Select a conversation.</div>'}
            </main>
        </section>
    `;

    document.querySelectorAll('[data-thread]').forEach(row => {
        row.addEventListener('click', () => {
            window.location.href = '/technician/messages/' + encodeURIComponent(row.dataset.thread);
        });
    });

    if (active) {
        Threads.markRead(active.id);
        const chatEl = document.getElementById('chatMessages');
        if (chatEl) chatEl.scrollTop = chatEl.scrollHeight;

        const form = document.getElementById('chatForm');
        if (form) {
            form.addEventListener('submit', async e => {
                e.preventDefault();
                const input = document.getElementById('chatText');
                const text = input.value.trim();
                if (!text) return;
                const res = await Threads.append(active.id, 'technician', text);
                if (res.ok) {
                    input.value = '';
                    location.reload();
                } else {
                    Shell.toast(res.reason || 'Could not send.', 'danger');
                }
            });
        }
    }
}