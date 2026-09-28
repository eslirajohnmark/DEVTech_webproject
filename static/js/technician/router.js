/* ============================================================================
 * router.js — client-side URL map.
 *
 * Mirrors Flask's url_for('technician.*') so page controllers don't
 * hardcode paths. If a route ever changes on the server side, change
 * it here and every caller picks up the new path.
 * ==========================================================================*/

const BASE = '/technician';
const enc = v => encodeURIComponent(v);

export const Router = {
    base: BASE,

    // ---- page routes ----
    login:     () => BASE + '/login',
    register:  () => BASE + '/register',
    logout:    () => BASE + '/logout',
    dashboard: () => BASE + '/dashboard',
    profile:   () => BASE + '/profile',
    myJobs:    () => BASE + '/jobs',
    jobDetail: id => BASE + '/jobs/' + enc(id),
    intake:    id => id ? BASE + '/intake/' + enc(id) : BASE + '/intake',
    reports:   () => BASE + '/reports',
    reportNew: id => BASE + '/reports/new/' + enc(id),
    incidents: () => BASE + '/incidents',
    messages:  id => id ? BASE + '/messages/' + enc(id) : BASE + '/messages',

    // ---- JSON API routes ----
    api: {
        me:     BASE + '/api/me',
        login:  BASE + '/api/login',
        logout: BASE + '/api/logout',
        config: BASE + '/api/config',

        jobs:       BASE + '/api/jobs',
        jobStats:   BASE + '/api/jobs/stats',
        job:        id => BASE + '/api/jobs/' + enc(id),
        jobAdvance: id => BASE + '/api/jobs/' + enc(id) + '/advance',
        jobNotes:   id => BASE + '/api/jobs/' + enc(id) + '/notes',
        jobLogs:    id => BASE + '/api/jobs/' + enc(id) + '/logs',
        jobIntake:  id => BASE + '/api/jobs/' + enc(id) + '/intake',
        jobReport:  id => BASE + '/api/jobs/' + enc(id) + '/report',

        incidents: BASE + '/api/incidents',
        uploads:   BASE + '/api/uploads',
        upload:    id => BASE + '/api/uploads/' + enc(id),

        notifications:     BASE + '/api/notifications',
        notificationsRead: BASE + '/api/notifications/read',
    },
};