/* ============================================================================
 * pages/intake.js — device intake form.
 * ==========================================================================*/

import * as Shell from '../shell/index.js';
import * as Jobs from '../data/jobs.js';
import * as Intake from '../data/intake.js';
import * as Config from '../data/config.js';
import { checkboxGrid, select } from '../core/dynamic.js';
import { escape } from '../core/format.js';

export async function init(tech, jobId) {
    const el = Shell.content();
    const job = Jobs.get(Number(jobId));
    if (!job) { el.innerHTML = '<p class="tech-hint">Job not found.</p>'; return; }

    const current = Intake.forJob(job.id) || {};
    const deviceTypes = Config.deviceTypes();
    const conditions = Config.conditions();
    const accessories = Config.accessories();

    el.innerHTML = `
        <section class="tech-intake-page">
            <a href="/technician/jobs/${job.id}" class="tech-back">
                <i class="fas fa-arrow-left"></i> Back to job
            </a>

            <div class="tech-card-head" style="margin-bottom:1rem;">
                <div style="min-width:0;">
                    <h2 style="font-size:1.12rem; font-weight:750; letter-spacing:-0.02em;">Device Intake</h2>
                    <p style="font-size:0.81rem; color:var(--t-text-muted); margin-top:0.15rem;">
                        ${escape(job.bookingNumber || job.id)}
                    </p>
                </div>
            </div>

            <form id="intakeForm" class="tech-card">
                <div class="tech-field">
                    <label class="tech-label">Device Type</label>
                    ${select('deviceType', deviceTypes, current.deviceType || job.deviceType || '')}
                </div>

                <div class="tech-field">
                    <label class="tech-label">Device Model</label>
                    <input class="tech-input" id="deviceModel" value="${escape(current.deviceModel || '')}" />
                </div>

                <div class="tech-field">
                    <label class="tech-label">Condition</label>
                    ${select('condition', conditions, current.condition || '')}
                </div>

                <div class="tech-field">
                    <label class="tech-label">Condition Notes</label>
                    <textarea class="tech-textarea" id="conditionNotes" rows="3">${escape(current.conditionNotes || '')}</textarea>
                </div>

                <div class="tech-field">
                    <label class="tech-label">Accessories Received</label>
                    ${checkboxGrid('accessory', accessories, current.accessories || [], 'label')}
                </div>

                <div class="tech-field">
                    <label class="tech-check"><input type="checkbox" id="powersOn" ${current.powersOn ? 'checked' : ''} /> <span>Powers on</span></label>
                    <label class="tech-check"><input type="checkbox" id="hasPassword" ${current.hasPassword ? 'checked' : ''} /> <span>Has password</span></label>
                    <label class="tech-check"><input type="checkbox" id="dataBackupConsent" ${current.dataBackupConsent ? 'checked' : ''} /> <span>Data backup consent</span></label>
                    <label class="tech-check"><input type="checkbox" id="customerPresent" ${current.customerPresent ? 'checked' : ''} /> <span>Customer present</span></label>
                </div>

                <div class="tech-field">
                    <label class="tech-label">Photos Note</label>
                    <input class="tech-input" id="photosNote" value="${escape(current.photosNote || '')}" />
                </div>

                <button class="tech-btn tech-btn--primary" type="submit" id="saveIntakeBtn">
                    <i class="fas fa-check"></i> Save Intake
                </button>
            </form>
        </section>
    `;

    document.getElementById('intakeForm').addEventListener('submit', async e => {
        e.preventDefault();
        const accessories = Array.from(document.querySelectorAll('.accessory:checked')).map(cb => cb.value);

        const btn = document.getElementById('saveIntakeBtn');
        btn.disabled = true;

        const res = await Intake.save(job.id, {
            deviceType: document.getElementById('deviceType').value,
            deviceModel: document.getElementById('deviceModel').value,
            condition: document.getElementById('condition').value,
            conditionNotes: document.getElementById('conditionNotes').value,
            accessories,
            powersOn: document.getElementById('powersOn').checked,
            hasPassword: document.getElementById('hasPassword').checked,
            dataBackupConsent: document.getElementById('dataBackupConsent').checked,
            customerPresent: document.getElementById('customerPresent').checked,
            photosNote: document.getElementById('photosNote').value,
        });

        btn.disabled = false;
        if (res.ok) {
            Shell.toast('Intake saved.', 'ok');
        } else {
            Shell.toast(res.reason || 'Could not save intake.', 'danger');
        }
    });
}