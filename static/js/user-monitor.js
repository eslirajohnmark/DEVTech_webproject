

(function () {
    'use strict';

    var bookingId = window.__MONITOR_BOOKING_ID__;
    var root = document.getElementById('monitorRoot');
    var refreshBtn = document.getElementById('refreshBtn');
    var csrfToken = (document.querySelector('meta[name="csrf-token"]') || {}).content || '';

    function esc(s) {
        return String(s == null ? '' : s)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#39;');
    }

    function statusPillTone(label) {
        var map = {
            'Requested': 'amber',
            'Assigned': 'blue',
            'Diagnosis': 'purple',
            'On Repair': 'purple',
            'Ready for Collection': 'green',
            'Released': 'green',
            'On Hold': 'red',
            'Cancelled': 'neutral'
        };

        return map[label] || 'neutral';
    }

    function stars(rating) {
        var r = Math.round(Number(rating) || 0);
        var out = '';

        for (var i = 1; i <= 5; i++) {
            out += (i <= r ? '★' : '☆');
        }

        return out;
    }

    function render(data) {
        var b = data.booking;

        var header =
            '<div class="usr-detail-head">' +
                '<div>' +
                    '<h1 class="usr-detail-title">' +
                        esc(b.service) +
                    '</h1>' +

                    '<p class="usr-detail-sub">' +
                        'Ticket ' +
                        esc(b.number) +
                        ' &middot; ' +
                        esc(b.deviceType) +
                    '</p>' +
                '</div>' +

                '<span class="usr-pill usr-pill--' +
                    statusPillTone(b.statusLabel) +
                '">' +
                    esc(b.statusLabel) +
                '</span>' +
            '</div>';

        var track =
            '<section class="usr-track-card">' +
                '<div class="usr-track">' +

                    data.stages.map(function (s, i) {

                        var cls =
                            i < data.stageIndex
                                ? 'is-done'
                                : (
                                    i === data.stageIndex
                                        ? 'is-current'
                                        : ''
                                );

                        return (
                            '<div class="usr-stage ' +
                                cls +
                            '">' +

                                '<div class="usr-stage-dot">' +

                                    '<i class="fas ' +
                                        (
                                            i < data.stageIndex
                                                ? 'fa-check'
                                                : esc(s.icon)
                                        ) +
                                    '"></i>' +

                                '</div>' +

                                '<div class="usr-stage-name">' +
                                    esc(s.label) +
                                '</div>' +

                            '</div>'
                        );
                    }).join('') +

                '</div>' +
            '</section>';

        function contactRow(icon, label, value) {
            return (
                '<div class="usr-contact-row">' +

                    '<i class="fas ' +
                        icon +
                    '"></i>' +

                    '<div class="usr-contact-row-body">' +

                        '<div class="usr-contact-row-label">' +
                            esc(label) +
                        '</div>' +

                        '<div class="usr-contact-row-value">' +
                            esc(value || '—') +
                        '</div>' +

                    '</div>' +

                '</div>'
            );
        }

        var techColumn = data.technician

            ? '<section class="usr-panel">' +

                  '<div class="usr-panel-head">' +
                      '<h3>' +
                          '<i class="fas fa-user-gear"></i> ' +
                          'Technician Assigned' +
                      '</h3>' +
                  '</div>' +

                  '<div class="usr-tech-pic">' +
                      esc(data.technician.initials) +
                  '</div>' +

                  '<div class="usr-tech-name">' +
                      esc(data.technician.name) +
                  '</div>' +

                  '<div class="usr-tech-role">' +
                      esc(data.technician.role || 'Technician') +
                  '</div>' +

                  '<div class="usr-tech-stars">' +

                      '<span class="stars">' +
                          stars(data.technician.rating) +
                      '</span>' +

                      '<span>' +
                          Number(
                              data.technician.rating || 0
                          ).toFixed(1) +

                          ' (' +
                          (data.technician.rating_count || 0) +
                          ')' +

                      '</span>' +

                  '</div>' +

                  '<div class="usr-contact-title">' +
                      'Contact' +
                  '</div>' +

                  contactRow(
                      'fa-id-badge',
                      'Verified',
                      data.technician.verified
                          ? 'Verified by DEVTech'
                          : 'Pending verification'
                  ) +

                  contactRow(
                      'fa-envelope',
                      'Email',
                      data.technician.email
                  ) +

                  contactRow(
                      'fa-phone',
                      'Phone',
                      data.technician.phone
                  ) +

                  /*
                   * MESSAGE TECHNICIAN BUTTON
                   *
                   * Opens the existing DEVTech messaging page and
                   * passes the technician's user ID as conv_id.
                   */
                  '<a class="usr-btn usr-btn--primary" ' +
                     'style="margin-top:.8rem;width:100%;" ' +
                     'href="/messages?conv_id=' +
                     esc(data.technician.id) +
                     '">' +

                     '<i class="fas fa-comments"></i> ' +
                     'Message technician' +

                  '</a>' +

              '</section>'

            : '<section class="usr-panel">' +

                  '<div class="usr-panel-head">' +
                      '<h3>' +
                          '<i class="fas fa-user-gear"></i> ' +
                          'Technician Assigned' +
                      '</h3>' +
                  '</div>' +

                  '<div class="usr-empty">' +

                      '<i class="fas fa-hourglass-half"></i>' +

                      '<h3>' +
                          'Not yet assigned' +
                      '</h3>' +

                      '<p>' +
                          'Your request is still being reviewed.' +
                      '</p>' +

                  '</div>' +

              '</section>';

        var deviceColumn =
            '<section class="usr-panel">' +

                '<div class="usr-panel-head">' +
                    '<h3>' +
                        '<i class="fas fa-laptop"></i> ' +
                        'Device Details' +
                    '</h3>' +
                '</div>' +

                devRow(
                    'fa-laptop',
                    'Device type',
                    b.deviceType
                ) +

                devRow(
                    'fa-tag',
                    'Service',
                    b.service
                ) +

                devRow(
                    'fa-store',
                    'Service mode',
                    b.isInShop
                        ? 'In-Shop'
                        : 'Home Service'
                ) +

                devRow(
                    'fa-calendar',
                    'Scheduled',
                    b.scheduledDate +
                    ' · ' +
                    b.scheduledTime
                ) +

                devRow(
                    'fa-map-location',
                    'Location',
                    b.address
                ) +

                (
                    b.description

                        ? '<div class="usr-note">' +

                              '<div class="usr-note-label">' +
                                  'Problem you reported' +
                              '</div>' +

                              '<p>' +
                                  esc(b.description) +
                              '</p>' +

                          '</div>'

                        : ''
                ) +

                (
                    data.payment

                        ? devRow(
                              'fa-money-bill-wave',
                              'Amount',
                              '₱' +
                              Number(
                                  data.payment.amount
                              ).toFixed(2)
                          ) +

                          devRow(
                              'fa-credit-card',
                              'Payment',
                              data.payment.method +
                              ' · ' +
                              data.payment.status
                          )

                        : ''
                ) +

                (
                    data.repair

                        ? '<div class="usr-note">' +

                              '<div class="usr-note-label">' +
                                  'Technician findings' +
                              '</div>' +

                              '<p>' +
                                  esc(
                                      data.repair.diagnosis
                                  ) +
                              '</p>' +

                              (
                                  data.repair.recommendations

                                      ? '<div class="usr-note-label" ' +
                                            'style="margin-top:.6rem">' +
                                            'Recommendations' +
                                        '</div>' +

                                        '<p>' +
                                            esc(
                                                data.repair.recommendations
                                            ) +
                                        '</p>'

                                      : ''
                              ) +

                          '</div>'

                        : ''
                ) +

            '</section>';

        function devRow(icon, label, value) {
            return (
                '<div class="usr-dev-row">' +

                    '<i class="fas ' +
                        icon +
                    '"></i>' +

                    '<div class="usr-dev-row-body">' +

                        '<div class="usr-dev-row-label">' +
                            esc(label) +
                        '</div>' +

                        '<div class="usr-dev-row-value">' +
                            esc(value || '—') +
                        '</div>' +

                    '</div>' +

                '</div>'
            );
        }

        var activityColumn =
            '<section class="usr-panel">' +

                '<div class="usr-panel-head">' +

                    '<h3>' +
                        '<i class="fas fa-clock-rotate-left"></i> ' +
                        'Activity Log' +
                    '</h3>' +

                    '<span class="usr-chip">' +
                        (data.timeline || []).length +
                    '</span>' +

                '</div>' +

                (
                    data.timeline &&
                    data.timeline.length

                        ? '<div class="usr-timeline">' +

                              data.timeline.map(function (e) {

                                  return (
                                      '<div class="usr-tl-item" ' +
                                          'data-action="' +
                                          esc(e.action || '') +
                                      '">' +

                                          '<p class="usr-tl-text">' +
                                              esc(e.text) +
                                          '</p>' +

                                          '<p class="usr-tl-meta">' +

                                              '<strong>' +
                                                  esc(
                                                      e.by || 'System'
                                                  ) +
                                              '</strong>' +

                                              ' &middot; ' +

                                              esc(e.at) +

                                          '</p>' +

                                      '</div>'
                                  );

                              }).join('') +

                          '</div>'

                        : '<div class="usr-empty">' +

                              '<i class="fas fa-clock-rotate-left"></i>' +

                              '<h3>' +
                                  'No activity yet' +
                              '</h3>' +

                              '<p>' +
                                  'Updates will appear here as your device is processed.' +
                              '</p>' +

                          '</div>'
                ) +

            '</section>';

        var ratingBlock = data.canRate

            ? '<section class="usr-rating-section">' +

                  '<div class="usr-rating-head">' +

                      '<h2>' +
                          'Rate Technician' +
                      '</h2>' +

                      '<p>' +
                          'How was your experience with ' +

                          esc(
                              data.technician
                                  ? data.technician.name
                                  : 'our team'
                          ) +

                          '?' +

                      '</p>' +

                  '</div>' +

                  '<form id="ratingForm" ' +
                        'class="usr-rating-form" ' +
                        'novalidate>' +

                      '<div class="usr-rating-block">' +

                          '<label class="usr-rating-block-label">' +
                              'Service' +
                          '</label>' +

                          '<div class="usr-stars-input" ' +
                               'id="starsInput">' +

                              [1, 2, 3, 4, 5].map(function (n) {

                                  return (
                                      '<button type="button" ' +
                                          'class="usr-star" ' +
                                          'data-value="' +
                                          n +
                                      '">' +

                                          '<i class="fas fa-star"></i>' +

                                      '</button>'
                                  );

                              }).join('') +

                          '</div>' +

                          '<div class="usr-rating-label" ' +
                               'id="ratingLabel">' +
                              'Select a rating' +
                          '</div>' +

                          '<p class="usr-error" id="errStars">' +
                              'Please select a rating.' +
                          '</p>' +

                      '</div>' +

                      '<div class="usr-rating-block">' +

                          '<label class="usr-rating-block-label" ' +
                                 'for="ratingExperience">' +
                              'Short description' +
                          '</label>' +

                          '<input class="usr-underline-input" ' +
                                 'id="ratingExperience" ' +
                                 'placeholder="e.g. Fast repair, friendly technician…" />' +

                          '<p class="usr-error" id="errExperience">' +
                              'Please share at least 15 characters.' +
                          '</p>' +

                      '</div>' +

                      '<div class="usr-rating-block">' +

                          '<label class="usr-rating-block-label" ' +
                                 'for="ratingImprovement">' +
                              'Suggested improvement' +
                          '</label>' +

                          '<input class="usr-underline-input" ' +
                                 'id="ratingImprovement" ' +
                                 'placeholder="Optional" />' +

                      '</div>' +

                      '<div class="usr-rating-actions">' +

                          '<button type="submit" ' +
                                  'class="usr-btn usr-btn--primary">' +

                              '<i class="fas fa-paper-plane"></i> ' +
                              'Submit' +

                          '</button>' +

                      '</div>' +

                  '</form>' +

              '</section>'

            : (
                data.rating

                    ? '<section class="usr-rating-section">' +

                          '<div class="usr-rating-head">' +

                              '<h2>' +
                                  'Your Rating' +
                              '</h2>' +

                          '</div>' +

                          '<div class="usr-rating-submitted">' +

                              '<i class="fas fa-circle-check"></i>' +

                              '<div class="usr-rating-submitted-text">' +

                                  '<div class="usr-rating-submitted-stars">' +

                                      stars(
                                          data.rating.stars
                                      ) +

                                      ' ' +

                                      data.rating.stars +

                                      '/5' +

                                  '</div>' +

                                  '<p>' +
                                      esc(
                                          data.rating.experience
                                      ) +
                                  '</p>' +

                              '</div>' +

                          '</div>' +

                      '</section>'

                    : ''
            );

        root.innerHTML =
            header +
            track +

            '<div class="usr-tri-grid">' +
                techColumn +
                deviceColumn +
                activityColumn +
            '</div>' +

            ratingBlock;

        if (data.canRate) {
            wireRating();
        }
    }

    function wireRating() {
        var form = document.getElementById('ratingForm');

        if (!form) {
            return;
        }

        var container =
            document.getElementById('starsInput');

        var label =
            document.getElementById('ratingLabel');

        var selected = 0;

        var LBL = {
            1: 'Poor',
            2: 'Fair',
            3: 'Good',
            4: 'Very good',
            5: 'Excellent'
        };

        container.addEventListener('click', function (e) {

            var btn =
                e.target.closest('.usr-star');

            if (!btn) {
                return;
            }

            selected =
                Number(btn.dataset.value);

            paint(
                container,
                selected,
                0
            );

            label.textContent =
                LBL[selected] +
                ' — ' +
                selected +
                '/5';

            document
                .getElementById('errStars')
                .classList
                .remove('is-shown');
        });

        container.addEventListener('mouseover', function (e) {

            var btn =
                e.target.closest('.usr-star');

            if (!btn) {
                return;
            }

            paint(
                container,
                selected,
                Number(btn.dataset.value)
            );
        });

        container.addEventListener('mouseleave', function () {

            paint(
                container,
                selected,
                0
            );

        });

        form.addEventListener('submit', function (e) {

            e.preventDefault();

            var exp =
                document
                    .getElementById('ratingExperience')
                    .value
                    .trim();

            var imp =
                document
                    .getElementById('ratingImprovement')
                    .value
                    .trim();

            var ok = true;

            if (!selected) {

                document
                    .getElementById('errStars')
                    .classList
                    .add('is-shown');

                ok = false;
            }

            if (exp.length < 15) {

                document
                    .getElementById('errExperience')
                    .classList
                    .add('is-shown');

                ok = false;
            }

            if (!ok) {
                return;
            }

            fetch(
                '/api/booking/' +
                bookingId +
                '/rate',
                {
                    method: 'POST',
                    credentials: 'same-origin',

                    headers: {
                        'Content-Type':
                            'application/json',

                        'X-CSRFToken':
                            csrfToken
                    },

                    body: JSON.stringify({
                        stars: selected,
                        experience: exp,
                        improvement: imp
                    })
                }
            )

            .then(function (r) {
                return r.json();
            })

            .then(function (res) {

                if (!res.ok) {

                    alert(
                        res.reason ||
                        'Could not submit rating.'
                    );

                    return;
                }

                window.location.reload();

            })

            .catch(function () {

                alert(
                    'Network error.'
                );

            });
        });
    }

    function paint(container, sel, hover) {

        Array.prototype.forEach.call(
            container.querySelectorAll('.usr-star'),
            function (s, i) {

                var n = i + 1;

                s.classList.toggle(
                    'is-filled',
                    n <= sel
                );

                s.classList.toggle(
                    'is-hover',
                    hover && n <= hover
                );
            }
        );
    }

    function load() {

        if (!bookingId) {

            root.innerHTML =
                '<div class="usr-empty">' +

                    '<i class="fas fa-circle-exclamation"></i>' +

                    '<h3>' +
                        'No booking selected' +
                    '</h3>' +

                    '<p>' +
                        'Pick a booking from My Bookings to monitor it.' +
                    '</p>' +

                '</div>';

            return;
        }

        fetch(
            '/api/booking/' +
            bookingId +
            '/monitor',
            {
                credentials: 'same-origin'
            }
        )

        .then(function (r) {
            return r.json();
        })

        .then(function (data) {

            if (!data.ok) {

                root.innerHTML =
                    '<div class="usr-empty">' +

                        '<i class="fas fa-circle-exclamation"></i>' +

                        '<h3>' +
                            'Repair not found' +
                        '</h3>' +

                        '<p>' +
                            esc(data.reason || '') +
                        '</p>' +

                    '</div>';

                return;
            }

            render(data);

        })

        .catch(function () {

            root.innerHTML =
                '<div class="usr-empty">' +

                    '<i class="fas fa-circle-exclamation"></i>' +

                    '<h3>' +
                        'Could not load' +
                    '</h3>' +

                    '<p>' +
                        'Please try again.' +
                    '</p>' +

                '</div>';
        });
    }

    if (refreshBtn) {

        refreshBtn.addEventListener(
            'click',
            function () {

                var i =
                    this.querySelector('i');

                if (i) {
                    i.classList.add('fa-spin');
                }

                load();

                setTimeout(
                    function () {

                        if (i) {
                            i.classList.remove(
                                'fa-spin'
                            );
                        }

                    },
                    800
                );
            }
        );
    }

    // Auto-refresh every 45 seconds so the repair
    // status updates without a manual page reload.
    setInterval(
        load,
        45000
    );

    load();

})();