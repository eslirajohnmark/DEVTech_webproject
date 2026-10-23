/* DEVTech — show/hide password button for every password field.
   Include once per page:  <script src=".../js/password-toggle.js" defer></script>
   It loads its own small stylesheet, enhances every input[type=password] (also
   ones added later, e.g. inside modals) and skips fields that already have a
   portal-specific toggle next to them. Add data-pw-toggle="off" to opt a field out. */
(function () {
    'use strict';

    var EXISTING = '.pw-toggle, .admin-password-toggle, .tech-password-toggle';
    var script = document.currentScript;

    function loadStyles() {
        if (document.querySelector('link[data-pw-toggle-css]') || !script) return;
        var link = document.createElement('link');
        link.rel = 'stylesheet';
        link.href = script.src.replace(/js\/password-toggle\.js.*$/, 'css/password-toggle.css');
        link.setAttribute('data-pw-toggle-css', '');
        document.head.appendChild(link);
    }

    function setState(input, btn, show) {
        input.type = show ? 'text' : 'password';
        btn.setAttribute('aria-pressed', show ? 'true' : 'false');
        btn.setAttribute('aria-label', show ? 'Hide password' : 'Show password');
        btn.title = show ? 'Hide password' : 'Show password';
        btn.firstChild.className = show ? 'fas fa-eye-slash' : 'fas fa-eye';
    }

    function enhance(input) {
        if (input.dataset.pwToggle) return;                 // done already, or opted out
        input.dataset.pwToggle = 'on';
        var parent = input.parentElement;
        if (!parent || parent.querySelector(EXISTING)) return;   // portal has its own

        // Inputs inside an ".input-box" (icon + field) already have a positioned box;
        // anything else gets a thin wrapper so the button can sit inside the field.
        var host = parent;
        if (!parent.classList.contains('input-box')) {
            host = document.createElement('span');
            host.className = 'pw-wrap';
            parent.insertBefore(host, input);
            host.appendChild(input);
        }
        host.classList.add('pw-host');
        input.classList.add('pw-has-toggle');

        var btn = document.createElement('button');
        btn.type = 'button';
        btn.className = 'pw-toggle';
        btn.appendChild(document.createElement('i'));
        btn.firstChild.setAttribute('aria-hidden', 'true');
        if (input.id) btn.setAttribute('aria-controls', input.id);
        setState(input, btn, false);
        btn.disabled = input.disabled;

        btn.addEventListener('mousedown', function (e) { e.preventDefault(); });   // keep focus in the field
        btn.addEventListener('click', function () {
            var show = input.type === 'password';
            setState(input, btn, show);
            input.focus({ preventScroll: true });
            try {
                var end = input.value.length;
                input.setSelectionRange(end, end);
            } catch (err) { /* some types don't support selection */ }
        });
        host.appendChild(btn);

        // Follow the field's disabled state (e.g. profile forms with an Edit switch).
        new MutationObserver(function () { btn.disabled = input.disabled; })
            .observe(input, { attributes: true, attributeFilter: ['disabled'] });

        // Never submit while showing the password in plain text (password managers
        // and the browser's autofill expect type=password on submit).
        if (input.form) {
            input.form.addEventListener('submit', function () { setState(input, btn, false); });
        }
    }

    function scan(root) {
        (root || document).querySelectorAll('input[type="password"]').forEach(enhance);
    }

    function start() {
        loadStyles();
        scan();
        new MutationObserver(function (records) {
            records.forEach(function (r) {
                r.addedNodes.forEach(function (n) {
                    if (n.nodeType !== 1) return;
                    if (n.matches && n.matches('input[type="password"]')) enhance(n);
                    else if (n.querySelectorAll) scan(n);
                });
            });
        }).observe(document.body, { childList: true, subtree: true });
    }

    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start);
    else start();
    window.DevtechPasswordToggle = { scan: scan };
})();
