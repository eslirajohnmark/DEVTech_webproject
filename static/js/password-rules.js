/* Live password checklist for the registration forms (customer and technician).
   Markup: <div data-password-rules="password"> with <li data-rule="length|upper|lower|digit|special">.
   The same rules are checked on the server (services/password_rules.py).
   window.passwordProblem(value) returns what is missing, or '' when the password is fine. */
(function () {
    'use strict';
    var RULES = {
        length: function (p) { return p.length >= 8; },
        upper: function (p) { return /[A-Z]/.test(p); },
        lower: function (p) { return /[a-z]/.test(p); },
        digit: function (p) { return /\d/.test(p); },
        special: function (p) { return /[^A-Za-z0-9\s]/.test(p); }
    };
    var LABELS = {
        length: 'at least 8 characters', upper: 'a capital letter', lower: 'a small letter',
        digit: 'a number', special: 'a special character such as ! @ # $ %'
    };

    window.passwordProblem = function (value) {
        var missing = Object.keys(RULES).filter(function (k) { return !RULES[k](value || ''); })
            .map(function (k) { return LABELS[k]; });
        if (!missing.length) return '';
        return 'Your password needs ' + (missing.length > 1
            ? missing.slice(0, -1).join(', ') + ' and ' + missing[missing.length - 1] : missing[0]) + '.';
    };

    document.querySelectorAll('[data-password-rules]').forEach(function (box) {
        var input = document.getElementById(box.getAttribute('data-password-rules'));
        if (!input) return;
        function update() {
            var value = input.value;
            box.querySelectorAll('[data-rule]').forEach(function (li) {
                var ok = RULES[li.getAttribute('data-rule')](value);
                li.classList.toggle('is-met', ok);
                li.setAttribute('aria-label', li.textContent.trim() + (ok ? ': done' : ': still needed'));
            });
            box.classList.toggle('is-complete', !window.passwordProblem(value));
        }
        input.addEventListener('input', update);
        update();
    });
})();
