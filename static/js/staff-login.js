/* DEVTech staff sign-in (admin + technician): show/hide password, close a message. */
(function () {
    'use strict';
    document.querySelectorAll('.sl-eye').forEach(function (btn) {
        btn.addEventListener('click', function () {
            var input = document.getElementById(btn.getAttribute('data-target'));
            if (!input) return;
            var show = input.type === 'password';
            input.type = show ? 'text' : 'password';
            btn.setAttribute('aria-label', show ? 'Hide password' : 'Show password');
            btn.setAttribute('aria-pressed', show ? 'true' : 'false');
            btn.querySelector('i').className = show ? 'fas fa-eye-slash' : 'fas fa-eye';
        });
    });
    document.querySelectorAll('.sl-flash-close').forEach(function (btn) {
        btn.addEventListener('click', function () { btn.parentElement.remove(); });
    });
})();
