/* DEVTech: one click per action. Include once per page (defer).

   Forms: once a form really submits (after the browser's own checks and any "Are you
   sure?" dialog from confirm.js), its submit buttons are disabled and show "Please wait…"
   until the next page loads. Enter or a second click does nothing meanwhile. If the server
   sends the person back (wrong password, a field to fix), that is a new page, so the
   button works again. Coming back with the browser's Back button unlocks it too.

   Buttons that send a request without leaving the page (fetch: checkout, cancel, approve…):
   the button that was clicked stays disabled until the server answers.

   data-busy-text="Creating your account…" on a button replaces "Please wait…".
   Opt out: data-no-busy on a form or a button. The server still refuses duplicates on
   its own (one booking per slot, one checkout per cart, a payment used once). */
(function () {
    'use strict';
    if (window.DevtechBusy) return;

    var SAFETY_MS = 25000;                 // a form that never leaves the page (a file download) unlocks again
    var BACKGROUND = /\/api\/(ping|live|notifications\/unread-count|admin\/session-check)\b/;
    var script = document.currentScript;

    (function loadStyles() {
        if (!script || document.querySelector('link[data-busy-css]')) return;
        var link = document.createElement('link');
        link.rel = 'stylesheet';
        link.href = script.src.replace(/js\/busy-guard\.js.*$/, 'css/busy-guard.css');
        link.setAttribute('data-busy-css', '');
        document.head.appendChild(link);
    })();

    function lockButton(btn, label) {
        if (!btn || btn.dataset.busy === '1') return;
        btn.dataset.busy = '1';
        btn.dataset.busyWasDisabled = btn.disabled ? '1' : '';
        btn.disabled = true;
        btn.setAttribute('aria-busy', 'true');
        btn.classList.add('is-busy');
        if (label) {
            if (btn.tagName === 'INPUT') {
                btn.dataset.busyLabel = btn.value;
                btn.value = btn.getAttribute('data-busy-text') || 'Please wait…';
            } else {
                btn.dataset.busyHtml = btn.innerHTML;
                var w = btn.getBoundingClientRect().width;
                if (w) btn.style.minWidth = Math.ceil(w) + 'px';      // the button keeps its size
                btn.textContent = '';
                var icon = document.createElement('i');
                icon.className = 'fas fa-spinner fa-spin';
                icon.setAttribute('aria-hidden', 'true');
                btn.appendChild(icon);
                btn.appendChild(document.createTextNode(' ' + (btn.getAttribute('data-busy-text') || 'Please wait…')));
            }
        }
    }

    function unlockButton(btn) {
        if (!btn || btn.dataset.busy !== '1') return;
        if ('busyHtml' in btn.dataset) { btn.innerHTML = btn.dataset.busyHtml; delete btn.dataset.busyHtml; btn.style.minWidth = ''; }
        if ('busyLabel' in btn.dataset) { btn.value = btn.dataset.busyLabel; delete btn.dataset.busyLabel; }
        btn.disabled = btn.dataset.busyWasDisabled === '1';
        delete btn.dataset.busyWasDisabled;
        delete btn.dataset.busy;
        btn.removeAttribute('aria-busy');
        btn.classList.remove('is-busy');
    }

    function submitButtons(form) {
        var inside = Array.prototype.slice.call(form.querySelectorAll('button[type="submit"], button:not([type]), input[type="submit"]'));
        var outside = form.id ? Array.prototype.slice.call(document.querySelectorAll(
            'button[form="' + form.id + '"], input[type="submit"][form="' + form.id + '"]')) : [];
        return inside.concat(outside).filter(function (b) { return !b.hasAttribute('data-no-busy'); });
    }

    function lockForm(form, submitter) {
        if (form.dataset.busy === '1') return;
        form.dataset.busy = '1';
        submitButtons(form).forEach(function (b) { lockButton(b, b === submitter || !submitter); });
        form._busyTimer = setTimeout(function () { unlockForm(form); }, SAFETY_MS);
    }

    function unlockForm(form) {
        clearTimeout(form._busyTimer);
        delete form.dataset.busy;
        submitButtons(form).forEach(unlockButton);
    }

    function skip(form) {
        return !form || form.hasAttribute('data-no-busy') || (form.getAttribute('target') || '') === '_blank'
            || (form.getAttribute('method') || '').toLowerCase() === 'dialog';      // a dialog's own buttons
    }

    // A form already on its way: a second submit (Enter, double click) is stopped before
    // any other handler sees it.
    window.addEventListener('submit', function (e) {
        var form = e.target;
        if (!skip(form) && form.dataset.busy === '1') {
            e.preventDefault();
            e.stopImmediatePropagation();
        }
    }, true);

    // Lock only a submit that really goes ahead (confirm.js and fetch-based forms cancel theirs).
    document.addEventListener('submit', function (e) {
        var form = e.target, submitter = e.submitter || null;
        if (skip(form)) return;
        setTimeout(function () { if (!e.defaultPrevented) lockForm(form, submitter); }, 0);
    });

    // Back / forward from the browser's cache: nothing is on its way any more.
    window.addEventListener('pageshow', function (e) {
        if (!e.persisted) return;
        document.querySelectorAll('form[data-busy="1"]').forEach(unlockForm);
        document.querySelectorAll('[data-busy="1"]').forEach(unlockButton);
    });

    // ---- buttons that send a request without leaving the page ----
    var lastClick = null;
    document.addEventListener('click', function (e) {
        var btn = e.target.closest && e.target.closest('button, input[type="submit"], input[type="button"]');
        if (btn && (btn.dataset.busy === '1' || (btn.form && btn.form.dataset.busy === '1' && btn.type === 'submit'))) {
            e.preventDefault();                       // still waiting for the server: ignore the click
            e.stopImmediatePropagation();
            return;
        }
        if (btn && btn.closest('dialog')) return;     // "Are you sure?" OK: the button behind it is the one waiting
        if (!btn || btn.hasAttribute('data-no-busy') || btn.closest('[data-no-busy]')) { lastClick = null; return; }
        lastClick = {btn: btn, at: Date.now()};
    }, true);

    if (window.fetch) {
        var nativeFetch = window.fetch;
        window.fetch = function (input, init) {
            var method = ((init && init.method) || (input && input.method) || 'GET').toUpperCase();
            var url = typeof input === 'string' ? input : (input && input.url) || '';
            var btn = null;
            // the button clicked just before this request (within the time a confirm dialog takes)
            if (method !== 'GET' && !BACKGROUND.test(url) && lastClick && Date.now() - lastClick.at < 60000
                    && lastClick.btn.isConnected && lastClick.btn.dataset.busy !== '1') {
                btn = lastClick.btn;
                lastClick = null;
                lockButton(btn, false);
            }
            var request = nativeFetch.apply(this, arguments);
            if (btn) {
                request.then(function () { unlockButton(btn); }, function () { unlockButton(btn); });
            }
            return request;
        };
    }

    window.DevtechBusy = {lock: lockButton, unlock: unlockButton, lockForm: lockForm, unlockForm: unlockForm};
})();
