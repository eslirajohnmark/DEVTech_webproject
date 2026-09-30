/* ============================================================================
 * pages/dashboard.js — technician workload overview.
 * ==========================================================================*/

import * as Shell from '../shell/index.js';
import * as Jobs from '../data/jobs.js';
import { escape, relative } from '../core/format.js';

function statCard(label, value, icon, tone) {
    return `<div class="tech-stat tech-stat--${tone}">
        <div class="tech-stat-icon"><i class="fas ${icon}"></i></div>
        <div class="tech-stat-body">
            <span class="tech-stat-num">${value}</span>
            <span class="tech-stat-label">${escape(label)}</span>
        </div>
    </div>`;
}

function jobRow(job) {
    return `<a class="tech-job" data-status="${escape(job.repairStatus || 'accepted')}" href="/technician/jobs/${job.id}">
        <div class="tech-job-top">
            <div style="min-width:0;">
                <span class="tech-job-id">${escape(job.bookingNumber || job.id)}</span>
                <div class="tech-job-customer">${escape(job.serviceName || '—')}</div>
                <div class="tech-job-service">${escape(job.deviceType || '')}</div>
            </div>
            <div class="tech-job-badges">
                <span class="tech-pill tech-pill--info">${escape(job.repairStatus || '')}</span>
            </div>
        </div>
        <div class="tech-job-meta">
            <span class="tech-chip"><i class="fas fa-clock"></i> ${escape(relative(job.updatedAt || job.createdAt))}</span>
        </div>
    </a>`;
}

export async function init(tech) {
    const el = Shell.content();
    const stats = Jobs.statsFor(tech.id);
    const today = new Date().toISOString().slice(0, 10);
    const todays = Jobs.scheduledFor(tech.id, today);
    const active = Jobs.activeFor(tech.id);

    el.innerHTML = `
        <section class="tech-dashboard">
            <div class="tech-card-head" style="margin-bottom:1rem;">
                <div style="min-width:0;">
                    <h2 style="font-size:1.12rem; font-weight:750; letter-spacing:-0.02em;">
                        Good to see you, ${escape(tech.name)}.
                    </h2>
                    <p style="font-size:0.81rem; color:var(--t-text-muted); margin-top:0.15rem;">
                        ${active.length} active job${active.length === 1 ? '' : 's'} today.
                    </p>
                </div>
            </div>

            <div class="tech-stats">
                ${statCard('Total Jobs', stats.total, 'fa-briefcase', 'info')}
                ${statCard('On Repair', stats.on_repair, 'fa-screwdriver-wrench', 'warn')}
                ${statCard('Ready', stats.ready, 'fa-box-open', 'ok')}
                ${statCard('Completed', stats.released || 0, 'fa-circle-check', 'neutral')}
            </div>

            <section class="tech-card" style="margin-bottom:1.1rem;">
                <div class="tech-card-head">
                    <h3 class="tech-card-title"><i class="fas fa-calendar-day"></i> Today's Schedule</h3>
                </div>
                <div class="tech-jobs">
                    ${todays.length
                        ? todays.map(jobRow).join('')
                        : '<p class="tech-hint">No jobs scheduled for today.</p>'}
                </div>
            </section>

            <section class="tech-card">
                <div class="tech-card-head">
                    <h3 class="tech-card-title"><i class="fas fa-list"></i> Recent Activity</h3>
                </div>
                <div class="tech-jobs">
                    ${active.length
                        ? active.slice(0, 5).map(jobRow).join('')
                        : '<p class="tech-hint">Nothing active right now.</p>'}
                </div>
            </section>
        </section>
    `;
}