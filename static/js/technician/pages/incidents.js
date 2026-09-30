/* ============================================================================
 * pages/incidents.js — incident reports list + form.
 * ==========================================================================*/

import * as Shell from '../shell/index.js';
import * as Incidents from '../data/incidents.js';
import * as Config from '../data/config.js';
import { escape, relative } from '../core/format.js';

export async function init(tech) {
    const el = Shell.content();
    const reports = Incidents.forTech(tech.id);
    const types = Config.incidentTypes();
    const severities = Config.severities();

    el.innerHTML = `
        <section class="tech-incidents-page">
            <div class="tech-card-head" style="margin-bottom:1rem;">
                <div style="min-width:0;">
                    <h2 style="font-size:1.12rem; font-weight:750; letter-spacing:-0.02em;">Incident Reports</h2>
                    <p style="font-size:0.81rem; color:var(--t-text-muted); margin-top:0.15rem;">
                        File and review safety or security incidents.
                    </p>
                </div>
            </div>

            <section class="tech-card" style="margin-bottom:1.1rem;">
                <div class="tech-card-head">
                    <h3 class="tech-card-title"><i class="fas fa-shield-halved"></i> File a New Incident</h3>
                </div>
                <form id="incidentForm">
                    <div class="tech-field">
                        <label class="tech-label">Type</label>
                        <select class="tech-select" id="incidentType" style="width:100%;">
                            ${types.map(t => `<option value="${escape(t.key)}">${escape(t.label)}</option>`).join('')}
                        </select>
                    </div>
                    <div class="tech-field">
                        <label class="tech-label">Severity</label>
                        <select class="tech-select" id="incidentSeverity" style="width:100%;">
                            ${severities.map(s => `<option value="${escape(s.key)}">${escape(s.label)}</option>`).join('')}
                        </select>
                    </div>
                    <div class="tech-field">
                        <label class="tech-label">Location</label>
                        <input class="tech-input" id="incidentLocation" />
                    </div>
                    <div class="tech-field">
                        <label class="tech-label">Description</label>
                        <textarea class="tech-textarea" id="incidentDescription" rows="4"></textarea>
                    </div>
                    <div class="tech-field">
                        <label class="tech-label">Action Taken</label>
                        <textarea class="tech-textarea" id="incidentAction" rows="3"></textarea>
                    </div>
                    <div class="tech-field">
                        <label class="tech-check"><input type="checkbox" id="incidentAuthorities" /> <span>Authorities notified</span></label>
                    </div>
                    <button class="tech-btn tech-btn--danger" type="submit">
                        <i class="fas fa-shield-halved"></i> File Report
                    </button>
                </form>
            </section>

            <section class="tech-card">
                <div class="tech-card-head">
                    <h3 class="tech-card-title"><i class="fas fa-clock-rotate-left"></i> History</h3>
                    <span class="tech-chip">${reports.length}</span>
                </div>
                <div class="tech-jobs">
                    ${reports.length
                        ? reports.map(r => `
                            <article class="tech-job" data-status="on_hold">
                                <div class="tech-job-top">
                                    <div style="min-width:0;">
                                        <span class="tech-job-id">${escape(r.type)}</span>
                                        <div class="tech-job-customer">${escape(r.severity)}</div>
                                    </div>
                                </div>
                                <p class="tech-job-desc">${escape(r.description)}</p>
                                <div class="tech-job-meta">
                                    <span class="tech-chip"><i class="fas fa-clock"></i> ${escape(relative(r.createdAt))}</span>
                                </div>
                            </article>
                        `).join('')
                        : '<p class="tech-hint">No incidents filed.</p>'}
                </div>
            </section>
        </section>
    `;

    document.getElementById('incidentForm').addEventListener('submit', async e => {
        e.preventDefault();
        const res = await Incidents.file(tech.id, {
            type: document.getElementById('incidentType').value,
            severity: document.getElementById('incidentSeverity').value,
            location: document.getElementById('incidentLocation').value,
            description: document.getElementById('incidentDescription').value,
            actionTaken: document.getElementById('incidentAction').value,
            authoritiesNotified: document.getElementById('incidentAuthorities').checked,
        });
        if (res.ok) {
            Shell.toast('Incident filed.', 'ok');
            location.reload();
        } else {
            Shell.toast(res.reason || 'Could not file incident.', 'danger');
        }
    });
}