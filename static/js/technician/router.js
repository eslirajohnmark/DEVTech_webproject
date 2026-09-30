/* ============================================================================
 * router.js — maps page_module meta to a page controller.
 * ==========================================================================*/

import * as Dashboard from './pages/dashboard.js';
import * as MyJobs from './pages/my_jobs.js';
import * as JobDetail from './pages/job_detail.js';
import * as Intake from './pages/intake.js';
import * as ServiceReport from './pages/service_report.js';
import * as Incidents from './pages/incidents.js';
import * as Messages from './pages/messages.js';
import * as Profile from './pages/profile.js';
import * as Login from './pages/login.js';
import * as Registration from './pages/registration.js';

const ROUTES = {
    login:          Login,
    registration:   Registration,
    dashboard:      Dashboard,
    my_jobs:        MyJobs,
    job_detail:     JobDetail,
    intake:         Intake,
    service_report: ServiceReport,
    incidents:      Incidents,
    messages:       Messages,
    profile:        Profile,
};

export function resolve(pageModule) {
    return ROUTES[pageModule] || null;
}