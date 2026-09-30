/* ============================================================================
 * pages/profile.js — technician profile.
 * ==========================================================================*/

import * as Shell from '../shell/index.js';
import { escape, dateTime } from '../core/format.js';
import { API } from '../core/api.js';

export async function init(tech) {
    const el = Shell.content();

    el.innerHTML = `
        <section class="tech-profile-page">
            <div class="tech-card-head" style="margin-bottom:1rem;">
                <div style="min-width:0;">
                    <h2 style="font-size:1.12rem; font-weight:750; letter-spacing:-0.02em;">My Profile</h2>
                    <p style="font-size:0.81rem; color:var(--t-text-muted); margin-top:0.15rem;">
                        Your technician account details.
                    </p>
                </div>
            </div>

            <section class="tech-card" style="margin-bottom:1.1rem;">
                <div class="tech-card-head">
                    <h3 class="tech-card-title"><i class="fas fa-user"></i> Identity</h3>
                    <span class="tech-pill tech-pill--${tech.idVerified ? 'ok' : 'warn'}">
                        ${tech.idVerified ? 'Verified' : 'Verification Pending'}
                    </span>
                </div>
                <div class="tech-kv">
                    <div class="tech-kv-item"><span class="tech-kv-key">Name</span><span class="tech-kv-val">${escape(tech.name)}</span></div>
                    <div class="tech-kv-item"><span class="tech-kv-key">Staff ID</span><span class="tech-kv-val">${escape(tech.staffId || tech.username || '')}</span></div>
                    <div class="tech-kv-item"><span class="tech-kv-key">Email</span><span class="tech-kv-val">${escape(tech.email || '—')}</span></div>
                    <div class="tech-kv-item"><span class="tech-kv-key">Phone</span><span class="tech-kv-val">${escape(tech.phone || '—')}</span></div>
                    <div class="tech-kv-item"><span class="tech-kv-key">Availability</span><span class="tech-kv-val">${escape(tech.availability || 'available')}</span></div>
                    <div class="tech-kv-item"><span class="tech-kv-key">Member Since</span><span class="tech-kv-val">${escape(dateTime(tech.createdAt))}</span></div>
                </div>
                <p class="tech-hint" style="margin-top:1rem;">
                    To change your name, email, or availability, contact an administrator.
                </p>
            </section>

            <section class="tech-card">
                <div class="tech-card-head">
                    <h3 class="tech-card-title"><i class="fas fa-key"></i> Change Password</h3>
                </div>
                <form id="pwForm">
                    <div class="tech-field">
                        <label class="tech-label">Current Password</label>
                        <input class="tech-input" type="password" id="curPw" />
                    </div>
                    <div class="tech-field">
                        <label class="tech-label">New Password</label>
                        <input class="tech-input" type="password" id="newPw" />
                    </div>
                    <div class="tech-field">
                        <label class="tech-label">Confirm New Password</label>
                        <input class="tech-input" type="password" id="newPw2" />
                    </div>
                    <button class="tech-btn tech-btn--primary" type="submit">
                        <i class="fas fa-key"></i> Change Password
                    </button>
                </form>
            </section>
        </section>
    `;

    document.getElementById('pwForm').addEventListener('submit', async e => {
        e.preventDefault();
        const cur = document.getElementById('curPw').value;
        const np  = document.getElementById('newPw').value;
        const np2 = document.getElementById('newPw2').value;

        if (np.length < 8) return Shell.toast('Password must be 8+ chars.', 'warn');
        if (np !== np2)    return Shell.toast('Passwords do not match.', 'warn');

        const res = await API.post('/technician/api/me/password', {
            current_password: cur,
            new_password: np,
        });

        if (res.ok) {
            Shell.toast('Password changed.', 'ok');
            e.target.reset();
        } else {
            Shell.toast(res.reason || 'Could not change password.', 'danger');
        }
    });
}