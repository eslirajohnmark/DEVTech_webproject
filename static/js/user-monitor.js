/* ============================================================================
 * user-monitor.js — live repair status page.
 *
 * Loads /api/booking/<id>/monitor, renders the rail, technician card,
 * timeline, and rating form. Polls every 20 seconds while the tab is
 * visible.
 * ==========================================================================*/
(function () {
    'use strict';

    var BOOKING_ID = window.__MONITOR_BOOKING_ID__;
    if (!BOOKING_ID) return;

    var root = document.getElementById('monitorRoot');
    var POLL_MS = 20000;
    var pollTimer = null;

    // ---- data ----
    function load(showSpinner) {
        if (showSpinner && root) {
            root.innerHTML =
                '<div class="user-monitor-loading">' +
                '<i class="fas fa-spinner fa-spin"></i>' +
                '<p>Loading repair status…</p></div>';
        }
        return fetch('/api/booking/' + BOOKING_ID + '/monitor', {
            credentials: 'same-origin',
        })
        .then(function (r) { return r.json(); })
        .then(function (data) {
            if (!data.ok) { renderError(data.reason || 'Could not load.'); return; }
            render(data);
        })
        .catch(function () { renderError('Network error. Retrying…'); });
    }

    function renderError(message) {
        if (!root) return;
        root.innerHTML =
            '<div class="user-monitor-empty">' +
            '<i class="fas fa-circle-exclamation"></i>' +
            '<h3>Something went wrong</h3>' +
            '<p>' + escape(message) + '</p>' +
            '<button class="user-btn-primary" onclick="location.reload()">Reload</button>' +
            '</div>';
    }

    // ---- render ----
    function render(data) {
        if (!root) return;
        root.innerHTML =
            heroCard(data) +
            trackCard(data) +
            '<div class="user-monitor-cols">' +
                leftColumn(data) +
                deviceColumn(data) +
                techColumn(data) +
            '</div>' +
            (data.canRate ? ratingSection() :
                (data.rating ? ratingSubmittedCard(data.rating) : '')) +
            timelineCard(data.timeline);
        if (data.canRate) wireRating();
    }

    function heroCard(data) {
        var b = data.booking;
        var pill = pillTone(b.status);
        return '<section class="user-monitor-hero">' +
            '<div class="user-monitor-hero-text">' +
                '<span class="user-monitor-hero-label">Booking ' + escape(b.number) + '</span>' +
                '<h2>' + escape(b.service) + '</h2>' +
                '<p>' + escape(b.description) + '</p>' +
                '<div class="user-monitor-hero-meta">' +
                    '<span class="user-pill user-pill--' + pill + '">' +
                        '<i class="fas fa-circle"></i> ' + escape(b.statusLabel) +
                    '</span>' +
                    '<span class="user-chip"><i class="fas fa-laptop"></i> ' + escape(b.deviceType) + '</span>' +
                    '<span class="user-chip"><i class="fas fa-calendar"></i> ' + escape(b.scheduledDate) + '</span>' +
                    '<span class="user-chip"><i class="fas fa-clock"></i> ' + escape(b.scheduledTime) + '</span>' +
                '</div>' +
            '</div>' +
            '<div class="user-monitor-hero-art"><i class="fas fa-laptop-medical"></i></div>' +
        '</section>';
    }

    function trackCard(data) {
        var stages = data.stages || [];
        var current = data.stageIndex;
        var cancelled = data.booking.status === 'cancelled';
        var stagesHtml = stages.map(function (s, i) {
            var state = '';
            if (cancelled) state = 'is-cancelled';
            else if (i < current) state = 'is-done';
            else if (i === current) state = 'is-current';
            var dotIcon = (i < current || (i === current && current === stages.length - 1))
                ? 'fa-check'
                : s.icon;
            return '<div class="user-monitor-stage ' + state + '">' +
                '<div class="user-monitor-stage-dot"><i class="fas ' + dotIcon + '"></i></div>' +
                '<div class="user-monitor-stage-name">' + escape(s.label) + '</div>' +
            '</div>';
        }).join('');

        var hold = '';
        if (data.booking.status === 'on_hold') {
            hold = '<div class="user-monitor-hold">' +
                '<i class="fas fa-pause-circle"></i>' +
                '<span>Waiting on parts or customer approval — this stage will resume shortly.</span>' +
            '</div>';
        }
        if (cancelled) {
            hold = '<div class="user-monitor-hold is-cancelled">' +
                '<i class="fas fa-circle-xmark"></i>' +
                '<span>This booking was cancelled.</span>' +
            '</div>';
        }
        return '<section class="user-monitor-track-card">' +
            '<div class="user-monitor-track">' + stagesHtml + '</div>' + hold +
        '</section>';
    }

    function leftColumn(data) {
        var b = data.booking;
        return '<section class="user-panel user-monitor-col">' +
            '<div class="user-panel-head"><h3><i class="fas fa-circle-info"></i> Service Details</h3></div>' +
            row('Booking', b.number) +
            row('Service', b.service) +
            row('Scheduled', b.scheduledDate + ' · ' + b.scheduledTime) +
            row('Location', b.isInShop ? 'In-shop repair' : (b.address || 'Home service')) +
            (data.payment ? row('Payment', data.payment.method + ' · ' + data.payment.status) : '') +
            (data.payment && data.payment.amount ? row('Amount', '₱' + data.payment.amount.toFixed(2)) : '') +
        '</section>';
    }

    function deviceColumn(data) {
        var b = data.booking;
        return '<section class="user-panel user-monitor-col">' +
            '<div class="user-panel-head"><h3><i class="fas fa-laptop"></i> Device</h3></div>' +
            row('Type', b.deviceType) +
            row('Reported issue', b.description) +
            row('Booked on', b.createdAt) +
            row('Last update', b.updatedAt) +
        '</section>';
    }

    function techColumn(data) {
        if (!data.technician) {
            return '<section class="user-panel user-monitor-col">' +
                '<div class="user-panel-head"><h3><i class="fas fa-user-gear"></i> Technician</h3></div>' +
                '<div class="user-monitor-empty-inline">' +
                    '<i class="fas fa-hourglass-half"></i>' +
                    '<p>A technician will be assigned shortly.</p>' +
                '</div>' +
            '</section>';
        }
        var t = data.technician;
        return '<section class="user-panel user-monitor-col">' +
            '<div class="user-panel-head"><h3><i class="fas fa-user-gear"></i> Assigned Technician</h3></div>' +
            '<div class="user-monitor-tech">' +
                '<div class="user-monitor-tech-avatar">' + escape(t.initials) + '</div>' +
                '<div class="user-monitor-tech-name">' + escape(t.name) +
                    (t.verified ? ' <i class="fas fa-circle-check" title="Verified"></i>' : '') +
                '</div>' +
                '<div class="user-monitor-tech-role">' + escape(t.role) + '</div>' +
                '<div class="user-monitor-tech-rating">' + renderStars(t.rating) +
                    ' <span>' + t.rating + ' (' + t.rating_count + ')</span></div>' +
            '</div>' +
            (t.phone ? row('Phone', t.phone) : '') +
            (t.email ? row('Email', t.email) : '') +
        '</section>';
    }

    function ratingSection() {
        var stars = [1,2,3,4,5].map(function (n) {
            return '<button type="button" class="user-monitor-star" ' +
                'data-value="' + n + '" aria-label="' + n + ' stars">' +
                '<i class="fas fa-star"></i></button>';
        }).join('');
        return '<section class="user-monitor-rating">' +
            '<div class="user-monitor-rating-head">' +
                '<h2>Rate this repair</h2>' +
                '<p>Your feedback helps us and future customers.</p>' +
            '</div>' +
            '<div class="user-monitor-rating-block">' +
                '<span class="user-monitor-rating-label">Your rating</span>' +
                '<div class="user-monitor-stars" id="ratingStars" data-value="0">' + stars + '</div>' +
                '<div class="user-monitor-rating-caption" id="ratingCaption">Tap a star to rate</div>' +
                '<p class="user-error" id="ratingError">Please choose a star rating.</p>' +
            '</div>' +
            '<div class="user-monitor-rating-block">' +
                '<label class="user-monitor-rating-label" for="ratingExperience">' +
                    'How was your experience? <span class="user-required-star">*</span></label>' +
                '<textarea class="user-monitor-rating-input" id="ratingExperience" rows="3" ' +
                    'placeholder="Tell us what went well — or what could be better."></textarea>' +
                '<p class="user-error" id="experienceError">Please share at least a short description.</p>' +
            '</div>' +
            '<div class="user-monitor-rating-block">' +
                '<label class="user-monitor-rating-label" for="ratingImprovement">' +
                    'Anything to improve? (optional)</label>' +
                '<textarea class="user-monitor-rating-input" id="ratingImprovement" rows="2" ' +
                    'placeholder="Ideas, suggestions, or anything we missed."></textarea>' +
            '</div>' +
            '<div class="user-monitor-rating-actions">' +
                '<button type="button" class="user-btn-primary" id="submitRating">' +
                    '<i class="fas fa-paper-plane"></i> Submit Rating</button>' +
            '</div>' +
        '</section>';
    }

    function ratingSubmittedCard(r) {
        return '<section class="user-monitor-rating-submitted">' +
            '<i class="fas fa-circle-check"></i>' +
            '<div>' +
                '<div class="user-monitor-stars-display">' + renderStars(r.stars) + '</div>' +
                '<strong>Thanks for rating this repair.</strong>' +
                '<p>' + escape(r.experience || '') + '</p>' +
                (r.improvement
                    ? '<p style="opacity:0.72;">Suggestion: ' + escape(r.improvement) + '</p>'
                    : '') +
                '<small>Submitted ' + escape(r.submittedAt) + '</small>' +
            '</div>' +
        '</section>';
    }

    function timelineCard(entries) {
        if (!entries || !entries.length) return '';
        return '<section class="user-panel user-monitor-timeline-card">' +
            '<div class="user-panel-head"><h3><i class="fas fa-clock-rotate-left"></i> Activity</h3></div>' +
            '<div class="user-monitor-timeline">' + entries.map(function (e) {
                return '<div class="user-monitor-tl-item" data-action="' + escape(e.action || '') + '">' +
                    '<p class="user-monitor-tl-text">' + escape(e.text || '') + '</p>' +
                    '<p class="user-monitor-tl-meta">' + escape(e.by || 'System') +
                        ' · ' + escape(e.at) + '</p>' +
                '</div>';
            }).join('') + '</div>' +
        '</section>';
    }

    // ---- helpers ----
    function row(label, value) {
        return '<div class="user-monitor-row">' +
            '<span class="user-monitor-row-label">' + escape(label) + '</span>' +
            '<span class="user-monitor-row-value">' + escape(value || '—') + '</span>' +
        '</div>';
    }

    function pillTone(status) {
        return ({
            pending:     'amber',
            confirmed:   'blue',
            in_progress: 'purple',
            on_hold:     'red',
            completed:   'green',
            cancelled:   'neutral',
        })[status] || 'neutral';
    }

    function renderStars(value) {
        var v = Math.round(Number(value) || 0);
        var out = '';
        for (var i = 1; i <= 5; i++) {
            out += '<i class="fas fa-star' + (i <= v ? '' : '-o') + '"></i>';
        }
        return out;
    }

    function escape(text) {
        return String(text === null || text === undefined ? '' : text)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#39;');
    }

    // ---- rating ----
    function wireRating() {
        var container = document.getElementById('ratingStars');
        var caption = document.getElementById('ratingCaption');
        if (!container) return;
        var stars = container.querySelectorAll('.user-monitor-star');
        var captions = ['Tap a star to rate', 'Poor', 'Fair', 'Good', 'Very Good', 'Excellent'];

        function paint(value) {
            stars.forEach(function (btn, i) {
                btn.classList.toggle('is-filled', i < value);
            });
            caption.textContent = captions[value] || captions[0];
        }
        stars.forEach(function (btn, i) {
            btn.addEventListener('mouseenter', function () { paint(i + 1); });
            btn.addEventListener('mouseleave', function () {
                paint(Number(container.dataset.value) || 0);
            });
            btn.addEventListener('click', function () {
                container.dataset.value = String(i + 1);
                paint(i + 1);
                document.getElementById('ratingError').classList.remove('is-shown');
            });
        });

        var btnSubmit = document.getElementById('submitRating');
        if (btnSubmit) btnSubmit.addEventListener('click', submitRating);
    }

    function submitRating() {
        var stars = Number(document.getElementById('ratingStars').dataset.value) || 0;
        var experience = document.getElementById('ratingExperience').value.trim();
        var improvement = document.getElementById('ratingImprovement').value.trim();

        var ok = true;
        if (!stars) { document.getElementById('ratingError').classList.add('is-shown'); ok = false; }
        if (experience.length < 15) {
            document.getElementById('experienceError').classList.add('is-shown');
            ok = false;
        }
        if (!ok) return;

        var btn = document.getElementById('submitRating');
        btn.disabled = true;
        btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Submitting…';

        fetch('/api/booking/' + BOOKING_ID + '/rate', {
            method: 'POST',
            credentials: 'same-origin',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': (document.querySelector('meta[name="csrf-token"]') || {}).content || '',
            },
            body: JSON.stringify({ stars: stars, experience: experience, improvement: improvement }),
        })
        .then(function (r) { return r.json(); })
        .then(function (data) {
            if (!data.ok) {
                btn.disabled = false;
                btn.innerHTML = '<i class="fas fa-paper-plane"></i> Submit Rating';
                alert(data.reason || 'Could not submit rating.');
                return;
            }
            load(true);
        })
        .catch(function () {
            btn.disabled = false;
            btn.innerHTML = '<i class="fas fa-paper-plane"></i> Submit Rating';
            alert('Network error. Please try again.');
        });
    }

    // ---- polling ----
    function startPolling() {
        stopPolling();
        pollTimer = setInterval(function () {
            if (document.visibilityState === 'visible') load(false);
        }, POLL_MS);
    }
    function stopPolling() {
        if (pollTimer) clearInterval(pollTimer);
        pollTimer = null;
    }

    var refreshBtn = document.getElementById('refreshBtn');
    if (refreshBtn) refreshBtn.addEventListener('click', function () { load(true); });

    load(true).then(startPolling);
})();