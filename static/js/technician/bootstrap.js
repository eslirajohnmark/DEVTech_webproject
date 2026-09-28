/* ============================================================================
 * bootstrap.js — reads page metadata from <meta> tags.
 *
 * Every technician template declares:
 *   <meta name="tech-page"     content="dashboard" />
 *   <meta name="tech-title"    content="Dashboard" />
 *   <meta name="tech-subtitle" content="Your workload at a glance" />
 *   <meta name="tech-user-id"  content="42" />
 *   <meta name="tech-job-id"   content="0" />
 *
 * Page controllers read Bootstrap.page / .title / .jobId instead of
 * inline <script> blocks. That's what lets the CSP drop 'unsafe-inline'
 * on /technician/* routes.
 * ==========================================================================*/

function meta(name) {
    const el = document.querySelector('meta[name="' + name + '"]');
    return el ? el.getAttribute('content') : null;
}

export const Bootstrap = {
    page:     meta('tech-page')     || 'dashboard',
    userId:   parseInt(meta('tech-user-id') || '0', 10),
    jobId:    parseInt(meta('tech-job-id')  || '0', 10),
    title:    meta('tech-title')    || 'Technician Portal',
    subtitle: meta('tech-subtitle') || '',
};