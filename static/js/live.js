/* DEVTech — live updates without refreshing (customer, technician and admin portals).

   Keeps one request waiting on /api/live while the tab is visible; the server
   answers the moment something changes (hidden tabs check every 30 s) and:
     • updates unread badges ([data-live-count="messages|notifications"]) and the tab title;
     • pops up new notifications and messages;
     • when the data on this page changed:
         - pages with [data-live-region] elements (message inboxes) swap just those
           parts in place, so a half-written reply is never lost;
         - other pages refresh themselves once you're idle (not typing, no dialog
           open, no unsaved form), keeping your scroll position; if you're busy an
           "Updates available" button appears instead.
   A page can opt out of refreshing with {% block live_mode %}self{% endblock %}.
   Works under the technician portal's strict CSP (no inline handlers). */
(function () {
    'use strict';
    if (window.__devtechLive) return;
    window.__devtechLive = true;

    var FAST = 4000, SLOW = 30000;
    var SCROLL_KEY = 'devtech-live-scroll';
    var SCROLLERS = 'main, .user-main-content, .tech-content, .admin-main-content, [data-live-scroll]';

    var state, mode, timer = null, inflight = false, stopped = false;
    var dirty = false, pending = false, chip = null, toastBox = null, baseTitle;

    function $all(sel, root) { return Array.prototype.slice.call((root || document).querySelectorAll(sel)); }

    // ---------- scroll position survives a live refresh ----------
    function saveScroll() {
        try {
            sessionStorage.setItem(SCROLL_KEY, JSON.stringify({
                url: location.href, win: window.scrollY,
                els: $all(SCROLLERS).map(function (el) { return el.scrollTop; })
            }));
        } catch (e) { /* storage unavailable: just reload */ }
    }
    function restoreScroll() {
        var saved;
        try { saved = JSON.parse(sessionStorage.getItem(SCROLL_KEY) || 'null'); } catch (e) { saved = null; }
        if (!saved || saved.url !== location.href) return;
        var apply = function () {
            $all(SCROLLERS).forEach(function (el, i) { if (saved.els[i]) el.scrollTop = saved.els[i]; });
            if (saved.win) window.scrollTo(0, saved.win);
        };
        apply();
        window.addEventListener('load', function () {
            apply();
            try { sessionStorage.removeItem(SCROLL_KEY); } catch (e) { /* ignore */ }
        });
    }

    // ---------- counts ----------
    function setCounts(s) {
        $all('[data-live-count]').forEach(function (el) {
            var v = el.getAttribute('data-live-count') === 'messages' ? s.mu : s.nu;
            el.textContent = v > 99 ? '99+' : String(v || 0);
            el.hidden = !v;
            if (el.style.display === 'none' && v) el.style.display = '';
        });
        var total = (s.mu || 0) + (s.nu || 0);
        document.title = (total ? '(' + (total > 99 ? '99+' : total) + ') ' : '') + baseTitle;
    }

    // ---------- pop-ups ----------
    function portalRoot() {
        return document.querySelector('.user-dashboard-wrapper, .admin-dashboard-wrapper, .tech-layout') || document.body;
    }
    function links() {
        var p = location.pathname;
        if (p.indexOf('/admin') === 0) return { n: '/admin/notifications', m: '/admin/messages?conv=' };
        if (p.indexOf('/technician') === 0) return { n: '/technician/notifications', m: '/technician/messages?thread=' };
        return { n: '/notifications', m: '/messages?conv=' };
    }
    // Pop-ups survive a live refresh: they are remembered for a few seconds and
    // shown again on the refreshed page.
    var TOAST_KEY = 'devtech-live-toasts', TOAST_MS = 7000;
    function rememberToast(t) {
        try {
            var list = JSON.parse(sessionStorage.getItem(TOAST_KEY) || '[]')
                .filter(function (x) { return Date.now() - x.at < TOAST_MS; });
            list.push(t);
            sessionStorage.setItem(TOAST_KEY, JSON.stringify(list.slice(-3)));
        } catch (e) { /* storage unavailable: pop-up just won't survive a refresh */ }
    }
    function replayToasts() {
        var list;
        try {
            list = JSON.parse(sessionStorage.getItem(TOAST_KEY) || '[]');
            sessionStorage.removeItem(TOAST_KEY);
        } catch (e) { return; }
        list.filter(function (x) { return Date.now() - x.at < TOAST_MS; }).forEach(function (x) {
            toast(x.kind, x.icon, x.title, x.body, x.href, true);
        });
    }
    function toast(kind, icon, title, body, href, replayed) {
        if (!replayed) rememberToast({ kind: kind, icon: icon, title: title, body: body, href: href, at: Date.now() });
        if (!toastBox) {
            toastBox = document.createElement('div');
            toastBox.className = 'live-toasts';
            toastBox.setAttribute('aria-live', 'polite');
            portalRoot().appendChild(toastBox);
        }
        var a = document.createElement('a');
        a.className = 'live-toast live-toast--' + kind;
        a.href = href;
        var i = document.createElement('i');
        i.className = 'fas fa-' + icon + ' live-toast-icon';
        i.setAttribute('aria-hidden', 'true');
        var text = document.createElement('span');
        text.className = 'live-toast-text';
        var strong = document.createElement('strong');
        strong.textContent = title;
        var small = document.createElement('small');
        small.textContent = body || '';
        text.appendChild(strong);
        text.appendChild(small);
        var close = document.createElement('button');
        close.type = 'button';
        close.className = 'live-toast-close';
        close.setAttribute('aria-label', 'Dismiss');
        close.textContent = '×';
        close.addEventListener('click', function (e) {
            e.preventDefault();
            e.stopPropagation();
            a.remove();
            try { sessionStorage.removeItem(TOAST_KEY); } catch (err) { /* ignore */ }
        });
        a.appendChild(i);
        a.appendChild(text);
        a.appendChild(close);
        toastBox.appendChild(a);
        while (toastBox.children.length > 3) toastBox.firstChild.remove();
        setTimeout(function () { a.classList.add('is-leaving'); }, 6500);
        setTimeout(function () { a.remove(); }, 7000);
    }
    function viewing(key) {
        var q = new URLSearchParams(location.search);
        return /messages/.test(location.pathname) && (q.get('conv') === key || q.get('thread') === key);
    }

    // ---------- refreshing the page's data ----------
    function openDialog() {
        return $all('[class*="modal"], [role="dialog"], dialog[open]').some(function (el) {
            if (el.closest('.live-toasts')) return false;
            var cs = getComputedStyle(el);
            return (cs.position === 'fixed' || el.tagName === 'DIALOG') && cs.display !== 'none' &&
                cs.visibility !== 'hidden' && parseFloat(cs.opacity) > 0.05 && el.offsetWidth > 0;
        });
    }
    function busy() {
        var a = document.activeElement;
        if (a && a !== document.body && a.matches(
            'textarea, select, [contenteditable=""], [contenteditable="true"], ' +
            'input:not([type=button]):not([type=submit]):not([type=reset]):not([type=checkbox]):not([type=radio])')) return true;
        if (dirty || openDialog()) return true;
        // An expanded panel (e.g. "Issue refund", "Mark as refunded") means the user is mid-task.
        if (document.querySelector('main details[open]:not([data-live-ignore])')) return true;
        var sel = window.getSelection && String(window.getSelection());
        return !!(sel && sel.trim());
    }
    function showChip() {
        if (chip) return;
        chip = document.createElement('button');
        chip.type = 'button';
        chip.className = 'live-chip';
        var i = document.createElement('i');
        i.className = 'fas fa-rotate';
        i.setAttribute('aria-hidden', 'true');
        chip.appendChild(i);
        chip.appendChild(document.createTextNode(' Updates available · Refresh'));
        chip.addEventListener('click', function () { saveScroll(); location.reload(); });
        portalRoot().appendChild(chip);
    }
    function softReload() {
        if (busy()) { pending = true; showChip(); return; }
        saveScroll();
        location.reload();
    }
    function refreshRegions() {
        fetch(location.href, { credentials: 'same-origin', headers: { 'X-Requested-With': 'devtech-live' } })
            .then(function (r) { return r.ok && !r.redirected ? r.text() : null; })
            .then(function (html) {
                if (!html) return;
                var doc = new DOMParser().parseFromString(html, 'text/html');
                $all('[data-live-region]').forEach(function (el) {
                    var fresh = el.id && doc.getElementById(el.id);
                    if (!fresh) return;
                    var a = document.activeElement;
                    if (a && a !== el && el.contains(a) && a.matches('input, textarea, select')) return;
                    if (el.innerHTML === fresh.innerHTML) return;
                    var atBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 48;
                    var top = el.scrollTop;
                    el.innerHTML = fresh.innerHTML;
                    el.className = fresh.className;
                    el.scrollTop = (el.getAttribute('data-live-region') === 'chat' && atBottom) ? el.scrollHeight : top;
                });
                document.dispatchEvent(new CustomEvent('devtech:live-updated'));
            })
            .catch(function () { /* next poll tries again */ });
    }
    function refresh() {
        if (mode === 'self') return;
        if (mode === 'regions') refreshRegions();
        else softReload();
    }

    // ---------- polling ----------
    function handle(next) {
        var p = location.pathname;
        var newN = next.n > state.n, newM = next.m !== state.m, newS = next.s !== state.s;
        var l = links();
        (next.new_notifications || []).slice().reverse().forEach(function (n) {
            var icon = { success: 'circle-check', error: 'circle-exclamation', warning: 'triangle-exclamation' }[n.type] || 'bell';
            toast(n.type || 'info', icon, n.title, n.message, l.n);
        });
        (next.new_messages || []).slice().reverse().forEach(function (m) {
            if (!viewing(m.key)) toast('message', 'comment-dots', 'New message from ' + m.from, m.preview, l.m + encodeURIComponent(m.key));
        });
        setCounts(next);
        var onMessages = /messages/.test(p), onNotifications = /notification/.test(p), onDashboard = /dashboard/.test(p);
        var changed = newS || (newM && (onMessages || onDashboard)) || (newN && (onNotifications || onDashboard));
        state = { n: next.n, nu: next.nu, m: next.m, mu: next.mu, s: next.s };
        if (changed) refresh();
        else if (pending && !busy()) { saveScroll(); location.reload(); }
    }
    function schedule(delay) {
        clearTimeout(timer);
        if (stopped) return;
        timer = setTimeout(poll, delay != null ? delay : (document.visibilityState === 'visible' ? FAST : SLOW));
    }
    // While the tab is visible the request waits on the server until something
    // changes (answered at once), then is re-armed right away. Hidden tabs just
    // check every SLOW ms so they don't hold connections open.
    var failures = 0;
    function poll() {
        if (stopped || inflight) return;
        inflight = true;
        var wait = document.visibilityState === 'visible';
        var url = '/api/live?n=' + state.n + '&m=' + state.m;
        if (wait) {
            url += '&wait=1&nu=' + state.nu + '&mu=' + state.mu + '&s=' + encodeURIComponent(state.s);
        }
        var ctl = window.AbortController ? new AbortController() : null;
        var giveUp = ctl ? setTimeout(function () { ctl.abort(); }, 40000) : null;
        var waited = false;
        fetch(url, {
            credentials: 'same-origin', cache: 'no-store', headers: { 'Accept': 'application/json' },
            signal: ctl ? ctl.signal : undefined
        })
            .then(function (r) {
                if (r.status === 401 || r.redirected) { stopped = true; return null; }
                return r.ok ? r.json() : null;
            })
            .then(function (next) {
                if (next && next.ok) {
                    failures = 0;
                    waited = !!next.waited;
                    handle(next);
                } else if (!stopped) {
                    failures++;
                }
            })
            .catch(function () { failures++; /* offline for a moment: keep trying */ })
            .then(function () {
                clearTimeout(giveUp);
                inflight = false;
                if (!wait) schedule();
                else if (failures) schedule(Math.min(FAST * failures, SLOW));
                else schedule(waited ? 50 : FAST);       // no free waiting slot: normal pace
            });
    }

    function start() {
        var boot = document.getElementById('devtechLiveBoot');
        try { state = boot && JSON.parse(boot.textContent); } catch (e) { state = null; }
        if (!state) return;                                   // signed out
        var meta = document.querySelector('meta[name="devtech-live-mode"]');
        mode = (meta && meta.content) || 'auto';
        if (mode === 'auto' && document.querySelector('[data-live-region]')) mode = 'regions';
        baseTitle = document.title.replace(/^\(\d+\+?\)\s*/, '');
        setCounts(state);
        restoreScroll();
        replayToasts();

        document.addEventListener('input', function (e) {
            var t = e.target;
            if (t && t.matches && t.matches('input, textarea, select') && !t.closest('[data-live-ignore]')) dirty = true;
        }, true);
        document.addEventListener('submit', function () { dirty = false; pending = false; }, true);
        document.addEventListener('visibilitychange', function () {
            if (document.visibilityState === 'visible') schedule(0);
        });
        window.addEventListener('focus', function () { schedule(0); });
        window.DevtechLive = { poll: function () { schedule(0); } };
        schedule(document.visibilityState === 'visible' ? 0 : SLOW);   // arm the waiting request right away
    }

    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start);
    else start();
})();
