/* DEVTech sign-in pages: while a sign-in is paused after too many wrong passwords
   (services/login_guard.py), keep the button disabled and count down to when it opens.
   Markup: <form data-lock-seconds="10"> ... <p data-lock-note hidden></p>. The server
   checks the lockout again on every attempt; this only saves a pointless try. */
(function () {
    'use strict';
    var form = document.querySelector('form[data-lock-seconds]');
    if (!form) return;
    var left = parseInt(form.getAttribute('data-lock-seconds'), 10) || 0;
    if (left <= 0) return;

    var button = form.querySelector('button[type="submit"], input[type="submit"]');
    var note = form.querySelector('[data-lock-note]');
    var label = button ? button.innerHTML : '';

    function tick() {
        if (left <= 0) {
            if (button) { button.disabled = false; button.innerHTML = label; }
            if (note) { note.textContent = 'You can try signing in again.'; note.classList.add('is-open'); }
            return;
        }
        var text = 'Sign-in is paused. Try again in ' + left + ' second' + (left === 1 ? '' : 's') + '.';
        if (button) { button.disabled = true; button.textContent = 'Try again in ' + left + 's'; }
        if (note) { note.hidden = false; note.textContent = text; }
        left -= 1;
        setTimeout(tick, 1000);
    }
    tick();
})();
