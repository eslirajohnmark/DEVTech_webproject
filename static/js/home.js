/* DEVTech home page: device picker, repair readout chip, mobile menu and contact form. */
(function () {
    'use strict';

    var reduceMotion = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    var peso = function (n) {
        return n > 0 ? '₱' + Math.round(n).toLocaleString('en-PH') : 'After diagnosis';
    };

    /* ---------- Mobile menu ---------- */
    var toggle = document.getElementById('menuToggle');
    var links = document.getElementById('navLinks');
    if (toggle && links) {
        toggle.addEventListener('click', function () {
            var open = links.classList.toggle('is-open');
            toggle.setAttribute('aria-expanded', open ? 'true' : 'false');
        });
        links.addEventListener('click', function (e) {
            if (e.target.closest('a[href^="#"]')) {
                links.classList.remove('is-open');
                toggle.setAttribute('aria-expanded', 'false');
            }
        });
    }

    /* ---------- Readout chip: walks through the real repair stages ---------- */
    var readout = document.getElementById('readout');
    var stages = readout ? readout.querySelectorAll('#readStages li') : [];
    var stageIndex = 0;
    var stageTimer = null;
    var readoutVisible = true;

    function showStage(i) {
        stageIndex = i;
        stages.forEach(function (li, n) {
            li.classList.toggle('is-done', n < i);
            li.classList.toggle('is-current', n === i);
            li.classList.toggle('is-last', n === i && i === stages.length - 1);
            if (n === i) { li.setAttribute('aria-current', 'step'); } else { li.removeAttribute('aria-current'); }
        });
    }
    function scheduleStage() {
        clearTimeout(stageTimer);
        if (reduceMotion || !readoutVisible || document.hidden || !stages.length) { return; }
        stageTimer = setTimeout(function () {
            showStage((stageIndex + 1) % stages.length);
            scheduleStage();
        }, stageIndex === stages.length - 1 ? 3200 : 1700);
    }
    if (readout && 'IntersectionObserver' in window) {
        new IntersectionObserver(function (entries) {
            readoutVisible = entries[0].isIntersecting;
            scheduleStage();
        }, { threshold: 0.2 }).observe(readout);
    }
    document.addEventListener('visibilitychange', scheduleStage);
    if (stages.length) {
        showStage(reduceMotion ? stages.length - 2 : 0);
        scheduleStage();
    }

    /* ---------- Device + problem picker ---------- */
    var data = {};
    try {
        var dataTag = document.getElementById('pickerData');
        data = dataTag ? JSON.parse(dataTag.textContent) || {} : {};
    } catch (err) { data = {}; }
    var problemsList = document.getElementById('problems');
    var deviceButtons = document.querySelectorAll('.dt-device');
    var current = { device: deviceButtons.length ? deviceButtons[0].getAttribute('data-device') : null, problem: 0 };

    function fillReadout() {
        var device = data[current.device];
        if (!readout || !device) { return; }
        var p = device.problems[current.problem];
        document.getElementById('readDevice').textContent = device.label;
        document.getElementById('readProblem').textContent = p.problem;
        document.getElementById('readService').textContent = p.service;
        document.getElementById('readPrice').textContent = peso(p.price);
        var fee = document.getElementById('readFee');
        if (fee) {
            fee.textContent = '+ ' + peso(p.fee || 0) + ' service fee';
            fee.hidden = !(p.fee > 0);
        }
        document.getElementById('readBook').setAttribute('href', p.url);

        // Send a signal pulse into the chip and restart the stage walk so the change is visible.
        readout.classList.remove('is-pulsed');
        void readout.offsetWidth;
        readout.classList.add('is-pulsed');
        showStage(0);
        scheduleStage();
    }

    function renderProblems() {
        var device = data[current.device];
        if (!problemsList || !device) { return; }
        problemsList.innerHTML = '';
        device.problems.forEach(function (p, i) {
            var li = document.createElement('li');
            var btn = document.createElement('button');
            btn.type = 'button';
            btn.className = 'dt-problem';
            btn.setAttribute('data-index', String(i));
            btn.setAttribute('aria-pressed', i === current.problem ? 'true' : 'false');
            var name = document.createElement('span');
            name.textContent = p.problem;
            var price = document.createElement('span');
            price.className = 'dt-problem-price';
            price.textContent = 'from ' + peso(p.price);
            btn.appendChild(name);
            btn.appendChild(price);
            li.appendChild(btn);
            problemsList.appendChild(li);
        });
    }

    deviceButtons.forEach(function (btn) {
        btn.addEventListener('click', function () {
            current.device = btn.getAttribute('data-device');
            current.problem = 0;
            deviceButtons.forEach(function (b) { b.setAttribute('aria-pressed', b === btn ? 'true' : 'false'); });
            renderProblems();
            fillReadout();
        });
    });

    if (problemsList) {
        problemsList.addEventListener('click', function (e) {
            var btn = e.target.closest('.dt-problem');
            if (!btn) { return; }
            current.problem = parseInt(btn.getAttribute('data-index'), 10) || 0;
            problemsList.querySelectorAll('.dt-problem').forEach(function (b) {
                b.setAttribute('aria-pressed', b === btn ? 'true' : 'false');
            });
            fillReadout();
        });
    }

    /* ---------- Live numbers count up once, when first seen ---------- */
    var counters = document.querySelectorAll('.dt-numbers [data-count]');
    if (counters.length && !reduceMotion && 'IntersectionObserver' in window) {
        var seen = new IntersectionObserver(function (entries) {
            entries.forEach(function (entry) {
                if (!entry.isIntersecting) { return; }
                seen.unobserve(entry.target);
                var el = entry.target;
                var target = parseInt(el.getAttribute('data-count'), 10) || 0;
                var start = null;
                (function frame(t) {
                    if (start === null) { start = t; }
                    var k = Math.min(1, (t - start) / 900);
                    el.textContent = Math.round(target * (1 - Math.pow(1 - k, 3))).toLocaleString('en-PH');
                    if (k < 1) { requestAnimationFrame(frame); }
                })(performance.now());
            });
        }, { threshold: 0.6 });
        counters.forEach(function (el) { seen.observe(el); });
    }

    /* ---------- Contact form ---------- */
    var form = document.getElementById('contactForm');
    if (form) {
        var status = document.getElementById('contactStatus');
        var say = function (msg, ok) {
            status.textContent = msg;
            status.className = 'dt-form-status ' + (ok ? 'is-ok' : 'is-error');
        };
        form.addEventListener('submit', function (e) {
            e.preventDefault();
            var fields = {
                name: document.getElementById('contactName'),
                email: document.getElementById('contactEmail'),
                subject: document.getElementById('contactSubject'),
                message: document.getElementById('contactMessage')
            };
            var firstEmpty = null;
            Object.keys(fields).forEach(function (k) {
                var empty = !fields[k].value.trim();
                fields[k].setAttribute('aria-invalid', empty ? 'true' : 'false');
                if (empty && !firstEmpty) { firstEmpty = fields[k]; }
            });
            if (firstEmpty) {
                say('Fill in every field so the shop can reply.', false);
                firstEmpty.focus();
                return;
            }
            if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(fields.email.value.trim())) {
                fields.email.setAttribute('aria-invalid', 'true');
                say('Enter an email address like name@example.com.', false);
                fields.email.focus();
                return;
            }

            var submit = form.querySelector('button[type="submit"]');
            submit.disabled = true;
            say('Sending…', true);
            fetch(form.getAttribute('data-action'), {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Accept': 'application/json',
                    'X-CSRFToken': document.getElementById('contactCsrf').value
                },
                body: JSON.stringify({
                    name: fields.name.value.trim(),
                    email: fields.email.value.trim(),
                    subject: fields.subject.value.trim(),
                    message: fields.message.value.trim()
                })
            })
                .then(function (res) {
                    return res.json().catch(function () {
                        return { success: false, message: res.status === 429
                            ? 'Too many messages from this connection. Try again in an hour.'
                            : 'The message didn’t send. Try again.' };
                    });
                })
                .then(function (d) {
                    say(d.message || (d.success ? 'Question sent.' : 'The message didn’t send. Try again.'), !!d.success);
                    if (d.success) { form.reset(); }
                })
                .catch(function () { say('Can’t reach the shop right now. Check your connection and try again.', false); })
                .finally(function () { submit.disabled = false; });
        });
    }
})();
