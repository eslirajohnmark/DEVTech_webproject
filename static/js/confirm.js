/* DEVTech: "Are you sure?" before an action that submits, changes or removes something.

   Mark the element; this script does the rest (no inline handlers, so it works under a strict CSP):
     <form data-confirm="Send the intake record to the shop?">            asks before the form submits
     <button type="submit" data-confirm="Remove this certificate?">     asks for that one button
     <button type="button" data-confirm="..." onclick="...">              asks before the click goes through
     <a href="..." data-confirm="...">                                    asks before following the link
   Optional: data-confirm-title, data-confirm-ok (button text), data-confirm-tone="danger".
   From JavaScript: DevtechConfirm({title, message, ok, tone}).then(function (yes) { ... }).
   Styles: static/css/confirm.css (loaded by this script). */
(function () {
    'use strict';
    if (window.DevtechConfirm) {
        return;
    }

    var script = document.currentScript;
    var dialog = null;
    var resolver = null;

    function loadStyles() {
        if (!script || document.querySelector('link[data-dc-css]')) {
            return;
        }
        var link = document.createElement('link');
        link.rel = 'stylesheet';
        link.href = script.src.replace(/js\/confirm\.js.*$/, 'css/confirm.css');
        link.setAttribute('data-dc-css', '');
        document.head.appendChild(link);
    }

    function build() {
        dialog = document.createElement('dialog');
        // Dark glass in the admin and technician portals, light glass for customers.
        var tech = !!document.querySelector('.tech-layout, .tech-login-page');
        var admin = !!document.querySelector('.admin-dashboard-wrapper, body[data-user-role="admin"]');
        dialog.className = 'dc' + (tech ? ' dc--tech' : (admin ? ' dc--admin' : ''));
        dialog.setAttribute('aria-labelledby', 'dcTitle');
        dialog.setAttribute('aria-describedby', 'dcMessage');
        dialog.innerHTML =
            '<form method="dialog" class="dc-card">' +
            '  <span class="dc-icon" aria-hidden="true"><i class="fas fa-circle-question"></i></span>' +
            '  <h2 class="dc-title" id="dcTitle"></h2>' +
            '  <p class="dc-message" id="dcMessage"></p>' +
            '  <div class="dc-actions">' +
            '    <button type="submit" value="cancel" class="dc-btn dc-btn--cancel">Cancel</button>' +
            '    <button type="submit" value="ok" class="dc-btn dc-btn--ok"></button>' +
            '  </div>' +
            '</form>';
        document.body.appendChild(dialog);
        dialog.addEventListener('close', function () {
            var done = resolver;
            resolver = null;
            if (done) {
                done(dialog.returnValue === 'ok');
            }
        });
        dialog.addEventListener('click', function (event) {
            if (event.target === dialog) {          // a click on the backdrop cancels
                dialog.close('cancel');
            }
        });
    }

    /** Ask; resolves true when the person confirms. */
    function ask(options) {
        options = options || {};
        if (!window.HTMLDialogElement) {             // very old browsers: the built-in prompt
            return Promise.resolve(window.confirm(options.message || options.title || 'Are you sure?'));
        }
        if (!dialog) {
            build();
        }
        if (resolver) {
            resolver(false);
        }
        var danger = options.tone === 'danger';
        dialog.classList.toggle('dc--danger', danger);
        dialog.querySelector('.dc-icon i').className = 'fas ' + (danger ? 'fa-triangle-exclamation' : 'fa-circle-question');
        dialog.querySelector('.dc-title').textContent = options.title || 'Are you sure?';
        dialog.querySelector('.dc-message').textContent = options.message || '';
        dialog.querySelector('.dc-message').hidden = !options.message;
        dialog.querySelector('.dc-btn--ok').textContent = options.ok || 'Yes, continue';
        dialog.returnValue = '';
        return new Promise(function (resolve) {
            resolver = resolve;
            dialog.showModal();
            // A risky action starts on Cancel, so Enter does not confirm it by accident.
            dialog.querySelector(danger ? '.dc-btn--cancel' : '.dc-btn--ok').focus();
        });
    }

    function optionsFrom(el, fallback) {
        var source = el && el.hasAttribute('data-confirm') ? el : fallback;
        var read = function (name) {
            return (el && el.getAttribute(name)) || (fallback && fallback.getAttribute(name)) || '';
        };
        return {
            message: source ? source.getAttribute('data-confirm') : '',
            title: read('data-confirm-title'),
            ok: read('data-confirm-ok'),
            tone: read('data-confirm-tone')
        };
    }

    window.DevtechConfirm = ask;
    /* Shorthand for page scripts: devtechAsk('Delete this?', {message, ok, tone}) resolves true on "yes". */
    window.devtechAsk = function (title, options) {
        options = options || {};
        return ask({ title: title, message: options.message || '', ok: options.ok, tone: options.tone });
    };
    loadStyles();

    /* Forms: ask once the browser's own checks have passed, then submit with the same button. */
    document.addEventListener('submit', function (event) {
        var form = event.target;
        var submitter = event.submitter || null;
        var asking = submitter && submitter.hasAttribute('data-confirm') ? submitter
            : (form.hasAttribute && form.hasAttribute('data-confirm') ? form : null);
        if (!asking || form.dataset.dcConfirmed === '1') {
            return;
        }
        event.preventDefault();
        event.stopImmediatePropagation();
        ask(optionsFrom(asking, form)).then(function (yes) {
            if (!yes) {
                return;
            }
            form.dataset.dcConfirmed = '1';
            try {
                if (form.requestSubmit) {
                    form.requestSubmit(submitter && submitter.form === form ? submitter : undefined);
                } else {
                    form.submit();
                }
            } finally {
                setTimeout(function () { delete form.dataset.dcConfirmed; }, 0);
            }
        });
    }, true);

    /* Buttons that run JavaScript, and links. */
    document.addEventListener('click', function (event) {
        var el = event.target.closest && event.target.closest('[data-confirm]');
        if (!el || el.tagName === 'FORM' || el.dataset.dcConfirmed === '1') {
            return;
        }
        if (el.tagName === 'BUTTON' && (el.type === 'submit' || !el.getAttribute('type')) && el.form) {
            return;                                   // handled by the submit listener above
        }
        event.preventDefault();
        event.stopImmediatePropagation();
        ask(optionsFrom(el)).then(function (yes) {
            if (!yes) {
                return;
            }
            if (el.tagName === 'A' && el.href) {
                window.location.href = el.href;
                return;
            }
            el.dataset.dcConfirmed = '1';
            try {
                el.click();
            } finally {
                delete el.dataset.dcConfirmed;
            }
        });
    }, true);
})();
