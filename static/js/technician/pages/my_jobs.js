/* ============================================================================
 * pages/my_jobs.js — job list with status filters.
 * ==========================================================================*/

import * as Shell from '../shell/index.js';
import * as Jobs from '../data/jobs.js';
import { escape, date } from '../core/format.js';
import { STATUS_META } from '../core/constants.js';

let _filter = 'all';

function jobCard(j) {
    const meta = STATUS_META[j.repairStatus] || { label: j.repairStatus, tone: 'info' };
    return `<a class="tech-job" data-status="${escape(j.repairStatus)}" href="/technician/jobs/${j.id}">
        <div class="tech-job-top">
            <div style="min-width:0;">
                <span class="tech-job-id">${escape(j.bookingNumber || j.id)}</span>
                <div class="tech-job-customer">${escape(j.serviceName || 'Service')}</div>
                <div class="tech-job-service"><i class="fas fa-laptop"></i> ${escape(j.deviceType || '')}</div>
            </div>
            <div class="tech-job-badges">
                <span class="tech-pill tech-pill--${escape(meta.tone)}">${escape(meta.label)}</span>
            </div>
        </div>
        <div class="tech-job-meta">
            <span class="tech-chip"><i class="fas fa-calendar"></i> ${escape(date(j.scheduledDate))}</span>
            <span class="tech-chip"><i class="fas fa-clock"></i> ${escape(j.scheduledTime || '')}</span>
        </div>
    </a>`;
}

export async function init(tech) {
    const el = Shell.content();
    const all = Jobs.forTech(tech.id);

    el.innerHTML = `
        <section class="tech-jobs-page">
            <div class="tech-card-head" style="margin-bottom:1rem;">
                <div style="min-width:0;">
                    <h2 style="font-size:1.12rem; font-weight:750; letter-spacing:-0.02em;">My Jobs</h2>
                    <p style="font-size:0.81rem; color:var(--t-text-muted); margin-top:0.15rem;">
                        ${all.length} assigned to you.
                    </p>
                </div>
            </div>

            <div class="tech-toolbar" id="jobFilters">
                <button class="tech-btn tech-btn--ghost tech-btn--sm is-active" data-filter="all">All</button>
                <button class="tech-btn tech-btn--ghost tech-btn--sm" data-filter="accepted">Accepted</button>
                <button class="tech-btn tech-btn--ghost tech-btn--sm" data-filter="on_repair">On Repair</button>
                <button class="tech-btn tech-btn--ghost tech-btn--sm" data-filter="ready">Ready</button>
                <button class="tech-btn tech-btn--ghost tech-btn--sm" data-filter="released">Released</button>
            </div>

            <div class="tech-jobs" id="jobGrid"></div>
        </section>
    `;

    const grid = document.getElementById('jobGrid');
    const render = () => {
        const filtered = _filter === 'all'
            ? all
            : all.filter(j => j.repairStatus === _filter);
        grid.innerHTML = filtered.length
            ? filtered.map(jobCard).join('')
            : '<p class="tech-hint">No jobs match this filter.</p>';
    };

    document.querySelectorAll('#jobFilters [data-filter]').forEach(pill => {
        pill.addEventListener('click', () => {
            document.querySelectorAll('#jobFilters [data-filter]').forEach(p => p.classList.remove('is-active'));
            pill.classList.add('is-active');
            _filter = pill.getAttribute('data-filter');
            render();
        });
    });

    render();
}