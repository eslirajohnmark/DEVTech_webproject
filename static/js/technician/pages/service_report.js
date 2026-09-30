/* ============================================================================
 * pages/service_report.js — service report form.
 * ==========================================================================*/

import * as Shell from '../shell/index.js';
import * as Jobs from '../data/jobs.js';
import * as Reports from '../data/reports.js';
import * as Config from '../data/config.js';
import { escape } from '../core/format.js';

export async function init(tech, jobId) {
    const el = Shell.content();
    const job = Jobs.get(Number(jobId));
    if (!job) { el.innerHTML = '<p class="tech-hint">Job not found.</p>'; return; }

    const current = Reports.latestForJob(job.id) || {};
    const outcomes = Config.outcomes();

    el.innerHTML = `
        <section class="tech-report-page">
            <a href="/technician/jobs/${job.id}" class="tech-back">
                <i class="fas fa-arrow-left"></i> Back to job
            </a>

            <div class="tech-card-head" style="margin-bottom:1rem;">
                <div style="min-width:0;">
                    <h2 style="font-size:1.12rem; font-weight:750; letter-spacing:-0.02em;">Service Report</h2>
                    <p style="font-size:0.81rem; color:var(--t-text-muted); margin-top:0.15rem;">
                        ${escape(job.bookingNumber || job.id)}
                    </p>
                </div>
            </div>

            <form id="reportForm" class="tech-card">
                <div class="tech-field">
                    <label class="tech-label">Diagnosis</label>
                    <textarea class="tech-textarea" id="diagnosis" rows="4">${escape(current.diagnosis || '')}</textarea>
                </div>

                <div class="tech-field">
                    <label class="tech-label">Work Performed</label>
                    <textarea class="tech-textarea" id="workPerformed" rows="4">${escape(current.workPerformed || '')}</textarea>
                </div>

                <div class="tech-field">
                    <label class="tech-label">Outcome</label>
                    <select class="tech-select" id="outcome" style="width:100%;">
                        <option value="">Select outcome</option>
                        ${outcomes.map(o => `<option value="${escape(o.key || o)}" ${current.outcome === (o.key || o) ? 'selected' : ''}>${escape(o.label || o)}</option>`).join('')}
                    </select>
                </div>

                <div class="tech-field">
                    <label class="tech-label">Hours Spent</label>
                    <input class="tech-input" id="hoursSpent" type="number" step="0.25" min="0" value="${escape(current.hoursSpent || '')}" />
                </div>

                <div style="display:flex; gap:0.55rem; justify-content:flex-end; flex-wrap:wrap; margin-top:1rem;">
                    <button class="tech-btn tech-btn--ghost" type="button" id="saveDraftBtn">
                        <i class="fas fa-floppy-disk"></i> Save Draft
                    </button>
                    <button class="tech-btn tech-btn--primary" type="button" id="submitReportBtn">
                        <i class="fas fa-paper-plane"></i> Submit Report
                    </button>
                </div>
            </form>
        </section>
    `;

    const gather = () => ({
        diagnosis: document.getElementById('diagnosis').value,
        workPerformed: document.getElementById('workPerformed').value,
        outcome: document.getElementById('outcome').value,
        hoursSpent: parseFloat(document.getElementById('hoursSpent').value) || 0,
    });

    document.getElementById('saveDraftBtn').addEventListener('click', async () => {
        const res = await Reports.saveDraft(job.id, tech.id, gather());
        Shell.toast(res.ok ? 'Draft saved.' : (res.reason || 'Could not save draft.'), res.ok ? 'ok' : 'danger');
    });

    document.getElementById('submitReportBtn').addEventListener('click', async e => {
        e.preventDefault();
        const res = await Reports.submit(job.id, tech.id, gather());
        if (res.ok) {
            Shell.toast('Report submitted.', 'ok');
            setTimeout(() => window.location.href = '/technician/jobs/' + job.id, 600);
        } else {
            Shell.toast(res.reason || 'Could not submit report.', 'danger');
        }
    });
}