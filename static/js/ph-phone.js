/* Philippine mobile number field (customer registration).
   Markup: <div class="phone-field" data-ph-phone> <input id="phone"> ... </div>
           <small id="phoneHint" class="phone-status"> (the message line, aria-live)
   Accepts 09171234567 or +639171234567 (spaces and dashes allowed) and says, while
   typing, what is wrong or that the number is fine. The server repeats every check
   (services/ph_phone.py) and also checks the network prefix, so this only helps the
   person typing; it never decides on its own.
   window.phPhoneProblem(value) returns the message, or '' when the format is right. */
(function () {
    'use strict';
    var LOCAL = '09171234567', INTL = '+639171234567';

    // { error: message } | { partial: message } | { ok: '+639...' }
    function check(raw, finished) {
        var typed = (raw || '').trim();
        if (!typed) return finished ? { error: 'Enter your mobile number, e.g. ' + LOCAL + '.' } : { empty: true };
        if (/[A-Za-z]/.test(typed)) return { error: 'The mobile number can only contain numbers, not letters.' };
        var compact = typed.replace(/[\s-]/g, '');
        if (/[^\d+]/.test(compact) || compact.indexOf('+', 1) !== -1) {
            return { error: 'Use numbers only. Spaces, dashes and a + at the start are the only other characters allowed.' };
        }
        var digits, need, start, example;
        if (compact.charAt(0) === '+') {
            start = '+639'; need = 12; digits = compact.length - 1; example = INTL;
            if (compact.slice(0, start.length) !== start.slice(0, compact.length)) {
                return { error: 'An international number must start with +639, e.g. ' + INTL + '.' };
            }
        } else {
            start = '09'; need = 11; digits = compact.length; example = LOCAL;
            if (compact.slice(0, 2) !== start.slice(0, compact.length)) {
                return { error: 'Incorrect prefix: a mobile number starts with 09 (' + LOCAL + ') or +639 (' + INTL + ').' };
            }
        }
        var unit = start === '09' ? 'a mobile number has 11 digits' : '+63 numbers have 12 digits after the +';
        if (digits > need) return { error: 'Too long: ' + unit + ' (you typed ' + digits + '), e.g. ' + example + '.' };
        if (digits < need) {
            return finished ? { error: 'Too short: ' + unit + ' (you typed ' + digits + '), e.g. ' + example + '.' }
                            : { partial: digits + ' of ' + need + ' digits' };
        }
        return { ok: start === '09' ? '+63' + compact.slice(1) : compact };
    }

    window.phPhoneProblem = function (value) {
        var r = check(value, true);
        return r.error || '';
    };

    document.querySelectorAll('[data-ph-phone]').forEach(function (box) {
        var input = box.querySelector('input');
        var status = document.getElementById(input.getAttribute('aria-describedby'));
        var icon = box.querySelector('.phone-icon');
        var hint = status ? status.textContent : '';

        function show(state, text) {
            box.setAttribute('data-state', state);
            if (status) {
                status.textContent = text;
                status.setAttribute('data-state', state);
            }
            if (icon) icon.className = 'phone-icon fas ' + (state === 'ok' ? 'fa-circle-check' : state === 'error' ? 'fa-circle-exclamation' : '');
            input.setAttribute('aria-invalid', state === 'error' ? 'true' : 'false');
        }

        function update(finished) {
            var r = check(input.value, finished);
            if (r.error) { show('error', r.error); input.setCustomValidity(r.error); return; }
            input.setCustomValidity('');
            if (r.ok) show('ok', 'Valid Philippine mobile number. It will be saved as ' + r.ok + '.');
            else if (r.partial) show('', 'Keep typing: ' + r.partial + '.');
            else show('', hint);
        }

        input.addEventListener('input', function () { update(false); });
        input.addEventListener('blur', function () { if (input.value) update(true); });
        if (input.value) update(true);              // a number sent back after a failed registration

        // Never submit a number that is not in a valid format.
        var form = input.form;
        if (form) {
            form.addEventListener('submit', function (e) {
                update(true);
                if (!input.checkValidity()) {
                    e.preventDefault();
                    e.stopImmediatePropagation();       // other submit handlers (and the busy lock) wait for a fix
                    input.focus();
                }
            }, true);
        }
    });
})();
