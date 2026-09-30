/* bootstrap.js */
import * as Shell from './shell/index.js';
import * as Router from './router.js';
import * as Theme from './theme.js';

(async () => {
    Theme.init && Theme.init();

    const meta = {
        page: document.querySelector('meta[name="page_module"]')?.content || 'dashboard',
        title: document.querySelector('meta[name="meta_title"]')?.content || '',
        subtitle: document.querySelector('meta[name="meta_subtitle"]')?.content || '',
        jobId: document.querySelector('meta[name="meta_job_id"]')?.content || '',
    };

    // Login/registration render into the whole page, not the shell.
    const publicPages = ['login', 'registration'];
    if (publicPages.includes(meta.page)) {
        const mod = Router.resolve(meta.page);
        if (mod && mod.init) mod.init();
        return;
    }

    const tech = await Shell.init(meta);
    if (!tech) return;

    const mod = Router.resolve(meta.page);
    if (mod && mod.init) {
        await mod.init(tech, meta.jobId);
    } else {
        Shell.content().innerHTML = '<p class="tech-hint">Unknown page.</p>';
    }
})();