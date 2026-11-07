/* ==========================================================================
   DEVTech — Messenger-style chat for the admin and technician inboxes
   (templates/admin/messages.html, templates/technician/messages.html; the
   customer page has the same behaviour in its own template).

   - groups bubbles from the same person, time dividers in local time,
     the other person's avatar on their last bubble, Sent / Seen
   - sends in the background (no page reload); the message shows at once
     and is marked "Not sent" if the server refuses it
   - Enter sends, Shift+Enter adds a line, the box grows with the text
   - redoes all of that after live.js swaps the list / thread in
   No inline handlers: the technician pages run a strict CSP.
   ========================================================================== */
(function () {
    'use strict';

    var root = document.querySelector('.mx');
    if (!root) return;

    var GROUP_GAP = 5 * 60 * 1000;      // same person, closer than this: one group
    var DIVIDER_GAP = 20 * 60 * 1000;   // a time divider after a longer pause
    var MAX_FILE = 5 * 1024 * 1024;

    function $(sel, el) { return (el || document).querySelector(sel); }
    function $$(sel, el) { return Array.prototype.slice.call((el || document).querySelectorAll(sel)); }
    function thread() { return $('.mx-thread', root); }

    function sameDay(a, b) { return a.toDateString() === b.toDateString(); }

    function dividerLabel(d) {
        var now = new Date(), t = d.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' });
        if (sameDay(d, now)) return t;
        if (now - d < 6 * 864e5) return d.toLocaleDateString([], { weekday: 'short' }) + ' ' + t;
        return d.toLocaleDateString([], { month: 'short', day: 'numeric',
            year: d.getFullYear() === now.getFullYear() ? undefined : 'numeric' }) + ', ' + t;
    }

    function listLabel(d) {
        var now = new Date();
        if (sameDay(d, now)) return d.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' });
        if (now - d < 6 * 864e5) return d.toLocaleDateString([], { weekday: 'short' });
        return d.toLocaleDateString([], { month: 'short', day: 'numeric' });
    }

    function scrollToBottom(smooth) {
        var box = thread();
        if (box) box.scrollTo({ top: box.scrollHeight, behavior: smooth ? 'smooth' : 'auto' });
    }

    function localizeList() {
        $$('.mx-conv-time[data-ts]', root).forEach(function (el) {
            var d = new Date(el.dataset.ts);
            if (!isNaN(d)) el.textContent = listLabel(d);
        });
    }

    function decorate() {
        var box = thread();
        if (!box) return;
        $$('.mx-divider, .mx-receipt', box).forEach(function (el) { el.remove(); });
        var items = $$('.mx-msg', box);
        items.forEach(function (el, i) {
            var prev = items[i - 1], next = items[i + 1];
            var t = new Date(el.dataset.ts), mine = el.classList.contains('sent');
            var joinsPrev = prev && prev.classList.contains('sent') === mine && t - new Date(prev.dataset.ts) < GROUP_GAP;
            var joinsNext = next && next.classList.contains('sent') === mine && new Date(next.dataset.ts) - t < GROUP_GAP;
            el.classList.toggle('is-first', !joinsPrev);
            el.classList.toggle('is-last', !joinsNext);
            if (isNaN(t)) return;
            $('.mx-bubble', el).title = t.toLocaleString([], { dateStyle: 'medium', timeStyle: 'short' });
            if (!prev || t - new Date(prev.dataset.ts) > DIVIDER_GAP) {
                var div = document.createElement('div');
                div.className = 'mx-divider';
                div.textContent = dividerLabel(t);
                el.parentNode.insertBefore(div, el);
            }
        });
        var mine = items.filter(function (el) { return el.classList.contains('sent'); });
        var last = mine[mine.length - 1];
        if (last) {
            var r = document.createElement('div');
            r.className = 'mx-receipt';
            if (last.classList.contains('is-failed')) {
                r.classList.add('is-failed');
                r.textContent = 'Not sent' + (last.dataset.error ? ' · ' + last.dataset.error : '');
            } else if (last.classList.contains('is-pending')) {
                r.textContent = 'Sending…';
            } else {
                r.textContent = last.dataset.read === '1' ? 'Seen' : 'Sent';
            }
            last.parentNode.insertBefore(r, last.nextSibling);
        }
        box.classList.add('mx-ready');
    }

    // ---- search the conversation list ----
    var search = $('.mx-search-input', root);
    function applySearch() {
        if (!search) return;
        var q = search.value.toLowerCase().trim();
        $$('.mx-conv', root).forEach(function (c) {
            c.hidden = !!q && (c.dataset.search || '').toLowerCase().indexOf(q) === -1;
        });
    }
    if (search) search.addEventListener('input', applySearch);

    // ---- composer ----
    var form = $('.mx-composer', root);
    var input = form && $('.mx-input', form);
    var picker = form && $('input[type=file]', form);
    var chip = $('.mx-chip', root);

    function autosize() {
        input.style.height = 'auto';
        input.style.height = Math.min(input.scrollHeight, 132) + 'px';
    }
    function clearFile() {
        if (picker) picker.value = '';
        if (chip) chip.hidden = true;
    }

    if (form && input) {
        input.addEventListener('input', autosize);
        input.addEventListener('keydown', function (e) {
            if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) {
                e.preventDefault();
                form.requestSubmit ? form.requestSubmit() : form.dispatchEvent(new Event('submit', { cancelable: true }));
            }
        });
        if (picker && chip) {
            picker.addEventListener('change', function () {
                var f = picker.files[0];
                if (!f) { chip.hidden = true; return; }
                if (f.size > MAX_FILE) {
                    clearFile();
                    window.alert('That file is larger than 5 MB.');
                    return;
                }
                $('.mx-chip-name', chip).textContent = f.name;
                chip.hidden = false;
                input.focus();
            });
            $('.mx-chip-remove', chip).addEventListener('click', clearFile);
        }

        form.addEventListener('submit', function (e) {
            e.preventDefault();
            var text = input.value.trim(), file = picker && picker.files[0];
            if (!text && !file) { input.focus(); return; }
            var body = new FormData(form);         // csrf token, recipient, text and file

            var box = thread();
            var empty = $('.mx-empty-thread', box);
            if (empty) empty.remove();
            var msg = document.createElement('div');
            msg.className = 'mx-msg sent is-pending';
            msg.dataset.ts = new Date().toISOString();
            msg.dataset.read = '0';
            msg.innerHTML = '<div class="mx-bubble"><p></p><span class="mx-time"></span></div>';
            var bubble = $('.mx-bubble', msg), p = $('p', bubble);
            if (text) { p.textContent = text; } else { p.textContent = 'Sending ' + file.name + '…'; p.className = 'mx-file-note'; }
            box.appendChild(msg);
            decorate();
            scrollToBottom(true);
            input.value = '';
            autosize();
            clearFile();
            input.focus();

            fetch(form.action, { method: 'POST', body: body, credentials: 'same-origin',
                                 headers: { 'X-Requested-With': 'XMLHttpRequest' } })
                .then(function (r) {
                    return r.json().catch(function () { return {}; }).then(function (d) { return { ok: r.ok, d: d }; });
                })
                .then(function (res) {
                    if (!msg.isConnected) return;         // a live update already shows the saved copy
                    msg.classList.remove('is-pending');
                    if (res.ok && res.d.success) {
                        if (res.d.sent_at) msg.dataset.ts = res.d.sent_at;
                        if (!text) p.remove();
                        (res.d.attachments || []).forEach(function (a) {
                            var link = document.createElement('a');
                            link.href = a.url;
                            link.className = 'msg-attachment' + (a.is_image ? '' : ' msg-attachment-file');
                            if (a.is_image) {
                                link.target = '_blank';
                                link.rel = 'noopener';
                                var img = document.createElement('img');
                                img.src = a.url;
                                img.alt = a.name;
                                img.addEventListener('load', function () { scrollToBottom(false); });
                                link.appendChild(img);
                            } else {
                                link.textContent = ' ' + a.name;
                                var icon = document.createElement('i');
                                icon.className = 'fas fa-file-pdf';
                                link.insertBefore(icon, link.firstChild);
                            }
                            bubble.insertBefore(link, $('.mx-time', bubble));
                        });
                        if (window.DevtechLive) window.DevtechLive.poll();
                    } else {
                        msg.classList.add('is-failed');
                        msg.dataset.error = res.d.message || 'try again';
                        if (text && !input.value) input.value = text;
                    }
                    decorate();
                    scrollToBottom(false);
                })
                .catch(function () {
                    msg.classList.remove('is-pending');
                    msg.classList.add('is-failed');
                    msg.dataset.error = 'no connection';
                    if (text && !input.value) input.value = text;
                    decorate();
                });
        });
    }

    // ---- after live.js swaps the list / thread in ----
    document.addEventListener('devtech:live-updated', function () {
        localizeList();
        applySearch();
        var box = thread();
        var nearBottom = box && box.scrollHeight - box.scrollTop - box.clientHeight < 60;
        decorate();
        if (nearBottom) scrollToBottom(false);
    });

    localizeList();
    decorate();
    scrollToBottom(false);
    var active = $('.mx-conv.is-active', root);
    if (active) active.scrollIntoView({ block: 'nearest' });
    // Phones: the portal's menu bar sits above the page; bring the open chat into view.
    if (root.classList.contains('has-thread') && window.innerWidth <= 768) root.scrollIntoView({ block: 'start' });
})();
