/* ============================================================================
 * pages/job_detail.js — single job view with actions.
 * ==========================================================================*/

import * as Shell from '../shell/index.js';
import * as Jobs from '../data/jobs.js';
import * as Intake from '../data/intake.js';
import * as Reports from '../data/reports.js';
import { escape, dateTime, money } from '../core/format.js';
import { STATUS_META } from '../core/constants.js';

export async function init(tech, jobId) {
    const el = Shell.content();
    const job = Jobs.get(Number(jobId));

    if (!job) {
        el.innerHTML = '<p class="tech-hint">Job not found.</p>';
        return;
    }

    const meta = STATUS_META[job.repairStatus] || { label: job.repairStatus, tone: 'info' };
    const intake = Intake.forJob(job.id);
    const report = Reports.latestForJob(job.id);

    el.innerHTML = `
        <section class="tech-job-detail">
            <a href="/technician/jobs" class="tech-back">
                <i class="fas fa-arrow-left"></i> Back to jobs
            </a>

            <div class="tech-card-head" style="margin-bottom:1rem;">
                <div style="min-width:0;">
                    <h2 style="font-size:1.12rem; font-weight:750; letter-spacing:-0.02em;">
                        ${escape(job.bookingNumber || job.id)}
                    </h2>
                    <p style="font-size:0.81rem; color:var(--t-text-muted); margin-top:0.15rem;">
                        ${escape(job.serviceName || '')}
                    </p>
                </div>
                <span class="tech-pill tech-pill--${escape(meta.tone)}">${escape(meta.label)}</span>
            </div>

            <div class="tech-grid-2">
                <section class="tech-card">
                    <div class="tech-card-head">
                        <h3 class="tech-card-title"><i class="fas fa-laptop"></i> Device</h3>
                    </div>
                    <div class="tech-kv">
                        <div class="tech-kv-item"><span class="tech-kv-key">Type</span><span class="tech-kv-val">${escape(job.deviceType || '—')}</span></div>
                        <div class="tech-kv-item"><span class="tech-kv-key">Model</span><span class="tech-kv-val">${escape(job.deviceModel || '—')}</span></div>
                        <div class="tech-kv-item"><span class="tech-kv-key">Service</span><span class="tech-kv-val">${escape(job.serviceName || '—')}</span></div>
                        <div class="tech-kv-item"><span class="tech-kv-key">Schedule</span><span class="tech-kv-val">${escape(dateTime(job.scheduledDate + ' ' + (job.scheduledTime || '')))}</span></div>
                        <div class="tech-kv-item"><span class="tech-kv-key">Mode</span><span class="tech-kv-val">${job.serviceMode === 'home_service' ? 'Home Service' : 'In-Shop'}</span></div>
                        <div class="tech-kv-item"><span class="tech-kv-key">Fee</span><span class="tech-kv-val">${escape(money(job.price || 0))}</span></div>
                    </div>
                </section>

                <section class="tech-card">
                    <div class="tech-card-head">
                        <h3 class="tech-card-title"><i class="fas fa-bolt"></i> Actions</h3>
                    </div>
                    <div style="display:flex; flex-direction:column; gap:0.5rem;">
                        <a class="tech-btn tech-btn--ghost tech-btn--wide" href="/technician/intake/${job.id}" style="justify-content:flex-start;">
                            <i class="fas fa-box-archive"></i> ${intake ? 'Edit Intake' : 'Record Intake'}
                        </a>
                        <a class="tech-btn tech-btn--ghost tech-btn--wide" href="/technician/report/${job.id}" style="justify-content:flex-start;">
                            <i class="fas fa-file-lines"></i> ${report ? 'Edit Service Report' : 'Write Service Report'}
                        </a>
                        <button class="tech-btn tech-btn--ok tech-btn--wide" id="advanceBtn" data-id="${job.id}" style="justify-content:flex-start;">
                            <i class="fas fa-forward"></i> Advance Status
                        </button>
                    </div>
                </section>
            </div>

            <section class="tech-card" style="margin-top:1.1rem;">
                <div class="tech-card-head">
                    <h3 class="tech-card-title"><i class="fas fa-clipboard-list"></i> Description</h3>
                </div>
                <p style="font-size:0.85rem; line-height:1.6;">${escape(job.description || 'No description recorded.')}</p>
            </section>
        </section>
    `;

    const advanceBtn = document.getElementById('advanceBtn');
    if (advanceBtn) {
        advanceBtn.addEventListener('click', async () => {
            advanceBtn.disabled = true;
            const res = await Jobs.advance(job.id);
            advanceBtn.disabled = false;
            if (res.ok) {
                Shell.toast('Status advanced.', 'ok');
                setTimeout(() => window.location.reload(), 500);
            } else {
                Shell.toast(res.reason || 'Could not advance job.', 'danger');
            }
        });
    }
}
// Add this after the advanceBtn listener
const diagnosisForm = document.getElementById('diagnosisForm');
if (diagnosisForm) {
    diagnosisForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        const textarea = diagnosisForm.querySelector('textarea');
        const btn = diagnosisForm.querySelector('button[type="submit"]');
        const diagnosis = textarea.value.trim();

        if (diagnosis.length < 10) {
            Shell.toast('Please write a diagnosis (at least 10 characters).', 'danger');
            return;
        }

        btn.disabled = true;
        btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Saving...';

        const res = await fetch(`/technician/api/jobs/${jobId}/diagnosis`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': document.querySelector('input[name="csrf_token"]').value
            },
            body: JSON.stringify({ diagnosis })
        });
        const data = await res.json();

        btn.disabled = false;
        btn.innerHTML = '<i class="fas fa-save"></i> Save Diagnosis';

        if (data.ok) {
            Shell.toast('Diagnosis saved.', 'ok');
            setTimeout(() => window.location.reload(), 500);
        } else {
            Shell.toast(data.reason || 'Could not save diagnosis.', 'danger');
        }
    });
}