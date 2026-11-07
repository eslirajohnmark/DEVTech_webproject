/* ==========================================================================
   DEVTech — notification feed (templates/partials/notification_feed.html)
   Local times ("5 min ago"), Today / Yesterday group headers, filter chips,
   and the "Delete all" confirmation dialog. No inline handlers, so it also
   runs on the technician pages' strict CSP.
   ========================================================================== */
(function () {
    'use strict';

    var DAY = 24 * 3600 * 1000;

    function sameDay(a, b) { return a.toDateString() === b.toDateString(); }

    function timeLabel(d, now) {
        var mins = Math.round((now - d) / 60000);
        if (sameDay(d, now)) {
            if (mins < 1) return 'Just now';
            if (mins < 60) return mins + ' min ago';
            return Math.floor(mins / 60) + ' h ago';
        }
        return d.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' });
    }

    function dayLabel(d, now) {
        if (sameDay(d, now)) return 'Today';
        if (sameDay(d, new Date(now - DAY))) return 'Yesterday';
        if (now - d < 6 * DAY) return d.toLocaleDateString([], { weekday: 'long' });
        return d.toLocaleDateString([], { month: 'long', day: 'numeric',
            year: d.getFullYear() === now.getFullYear() ? undefined : 'numeric' });
    }

    function decorate(list) {
        var now = new Date(), last = null;
        Array.prototype.forEach.call(list.querySelectorAll('.nf-item'), function (item) {
            var d = new Date(item.dataset.ts);
            if (isNaN(d)) return;
            var t = item.querySelector('.nf-time');
            t.textContent = timeLabel(d, now);
            t.setAttribute('datetime', d.toISOString());
            t.title = d.toLocaleString([], { dateStyle: 'medium', timeStyle: 'short' });
            var label = dayLabel(d, now);
            if (label !== last) {
                var head = document.createElement('li');
                head.className = 'nf-day';
                head.setAttribute('role', 'presentation');
                head.textContent = label;
                item.parentNode.insertBefore(head, item);
                last = label;
            }
        });
    }

    function applyFilter(feed, filter) {
        var list = feed.querySelector('.nf-list');
        if (!list) return;
        var shown = 0, header = null, headerHasItems = false;
        var finish = function () { if (header) header.hidden = !headerHasItems; };
        Array.prototype.forEach.call(list.children, function (el) {
            if (el.classList.contains('nf-day')) {
                finish();
                header = el;
                headerHasItems = false;
                return;
            }
            var match = filter === 'all' || (filter === 'new' ? el.dataset.new === '1' : el.dataset.type === filter);
            el.hidden = !match;
            if (match) { shown++; headerHasItems = true; }
        });
        finish();
        var empty = feed.querySelector('.nf-filter-empty');
        if (empty) empty.hidden = shown > 0;
    }

    Array.prototype.forEach.call(document.querySelectorAll('.nf'), function (feed) {
        var list = feed.querySelector('.nf-list');
        if (list) decorate(list);
        Array.prototype.forEach.call(feed.querySelectorAll('.nf-chip'), function (chip) {
            chip.addEventListener('click', function () {
                Array.prototype.forEach.call(feed.querySelectorAll('.nf-chip'), function (c) {
                    c.classList.toggle('is-active', c === chip);
                    c.setAttribute('aria-pressed', c === chip ? 'true' : 'false');
                });
                applyFilter(feed, chip.dataset.filter);
            });
        });
    });

    // Confirmation dialogs: [data-nf-open="<dialog id>"] opens, [data-nf-close] or a backdrop click closes.
    document.addEventListener('click', function (e) {
        var opener = e.target.closest('[data-nf-open]');
        if (opener) {
            var dialog = document.getElementById(opener.getAttribute('data-nf-open'));
            if (dialog && dialog.showModal) dialog.showModal();
            else if (dialog && window.confirm('Delete all notifications? This cannot be undone.')) {
                dialog.querySelector('form').submit();      // very old browsers without <dialog>
            }
            return;
        }
        if (e.target.closest('[data-nf-close]')) {
            e.target.closest('dialog').close();
            return;
        }
        if (e.target.tagName === 'DIALOG' && e.target.classList.contains('nf-dialog')) {
            e.target.close();                                // click on the dimmed backdrop
        }
    });
})();
