/* Admin support desk (templates/admin/support.html): conversation list, the
   chat with quick replies, and the customer's details. Polls for new messages. */
(function () {
    'use strict';
    const desk = document.getElementById('deskChat');
    if (!desk) return;
    const $ = id => document.getElementById(id);
    const quick = JSON.parse(desk.dataset.quick || '[]');
    let view = 'open', current = null, lastId = 0, convo = null, sending = false, searchTimer = null;

    function post(url, body) {
        return fetch(url, {method: 'POST', headers: {'Content-Type': 'application/json',
            'X-CSRFToken': (document.querySelector('meta[name="csrf-token"]') || {}).content || ''},
            body: JSON.stringify(body)}).then(r => r.json().then(d => ({ok: r.ok, d})));
    }

    // ---- tabs: chats / inquiries
    document.querySelectorAll('.desk-tab').forEach(t => t.addEventListener('click', () => {
        document.querySelectorAll('.desk-tab').forEach(x => { x.classList.toggle('is-active', x === t); x.setAttribute('aria-selected', x === t); });
        desk.hidden = t.dataset.tab !== 'chat';
        $('deskInquiries').hidden = t.dataset.tab !== 'inquiries';
    }));
    if (location.hash === '#inquiries') document.querySelector('[data-tab="inquiries"]').click();

    // ---- list
    function item(c) {
        const li = document.createElement('li');
        const b = document.createElement('button');
        b.type = 'button';
        b.className = 'desk-item' + (c.id === current ? ' is-current' : '') + (c.unread ? ' is-unread' : '');
        const top = document.createElement('span');
        top.className = 'desk-item-top';
        const name = document.createElement('strong');
        name.textContent = c.customer;
        const when = document.createElement('time');
        when.textContent = c.last_at;
        top.append(name, when);
        const topic = document.createElement('span');
        topic.className = 'desk-item-topic';
        topic.textContent = c.topic + (c.assigned ? ` (${c.assigned})` : '');
        const snip = document.createElement('span');
        snip.className = 'desk-item-snip';
        snip.textContent = c.snippet;
        b.append(top, topic, snip);
        b.addEventListener('click', () => open(c.id));
        li.append(b);
        return li;
    }

    function loadList() {
        const q = encodeURIComponent($('deskSearch').value.trim());
        fetch(`/api/admin/support/conversations?view=${view}&q=${q}`, {headers: {'Accept': 'application/json'}})
            .then(r => r.ok ? r.json() : null)
            .then(d => {
                if (!d) return;
                const ul = $('deskItems');
                ul.innerHTML = '';
                d.items.forEach(c => ul.append(item(c)));
                if (!d.items.length) {
                    const li = document.createElement('li');
                    li.className = 'desk-none';
                    li.textContent = view === 'open' ? 'Nobody is waiting for a reply.' : 'No conversations here.';
                    ul.append(li);
                }
                desk.querySelectorAll('[data-count]').forEach(el => { el.textContent = d.counts[el.dataset.count]; });
                $('deskOpenCount').textContent = d.counts.open;
            })
            .catch(() => {});
    }
    desk.querySelectorAll('.desk-view').forEach(v => v.addEventListener('click', () => {
        desk.querySelectorAll('.desk-view').forEach(x => x.classList.toggle('is-active', x === v));
        view = v.dataset.view;
        loadList();
    }));
    $('deskSearch').addEventListener('input', () => { clearTimeout(searchTimer); searchTimer = setTimeout(loadList, 250); });

    // ---- thread
    function bubble(m) {
        const li = document.createElement('li');
        li.className = 'desk-msg desk-msg--' + (m.role === 'admin' ? 'us' : m.role === 'system' ? 'note' : 'them');
        if (m.role !== 'system') {
            const who = document.createElement('span');
            who.className = 'desk-who';
            who.textContent = m.who;
            li.append(who);
        }
        const p = document.createElement('p');
        p.textContent = m.body;
        const t = document.createElement('time');
        t.textContent = m.at;
        li.append(p, t);
        return li;
    }

    function setHeader(c) {
        convo = c;
        $('deskTopic').textContent = c.topic;
        $('deskStatus').textContent = {open: 'Needs a reply', waiting: 'Waiting on customer', resolved: 'Resolved'}[c.status];
        $('deskStatus').dataset.status = c.status;
        $('deskResolve').innerHTML = c.status === 'resolved' ? '<i class="fas fa-rotate-left"></i> Reopen' : '<i class="fas fa-check"></i> Resolve';
        $('deskWaiting').hidden = c.status !== 'open';
        $('deskAssign').textContent = c.assigned ? `Assigned: ${c.assigned}` : 'Assign to me';
    }

    function loadThread(initial) {
        if (!current) return;
        const id = current;
        fetch(`/api/admin/support/conversations/${id}?after=${lastId}`, {headers: {'Accept': 'application/json'}})
            .then(r => r.ok ? r.json() : null)
            .then(d => {
                if (!d || id !== current) return;
                const list = $('deskMessages');
                const nearBottom = list.scrollHeight - list.scrollTop - list.clientHeight < 80;
                // Two requests can overlap (opening + the timer): add each message once.
                d.messages.forEach(m => { if (m.id <= lastId) return; list.append(bubble(m)); lastId = m.id; });
                if (d.messages.length && (initial || nearBottom)) list.scrollTop = list.scrollHeight;
                setHeader(d.conversation);
                if (d.customer) showCustomer(d.customer);
            })
            .catch(() => {});
    }

    function showCustomer(c) {
        $('deskName').textContent = c.name;
        const dl = $('deskCustomer');
        dl.innerHTML = '';
        [['Email', c.email], ['Phone', c.phone || 'Not given'], ['City', c.city || 'Not given'],
         ['Customer since', c.joined], ['Conversations', String(c.conversations)]].forEach(([k, v]) => {
            const dt = document.createElement('dt'); dt.textContent = k;
            const dd = document.createElement('dd'); dd.textContent = v;
            dl.append(dt, dd);
        });
        const fill = (ul, rows, text) => {
            ul.innerHTML = '';
            if (!rows.length) { const li = document.createElement('li'); li.className = 'desk-none'; li.textContent = 'None yet'; ul.append(li); }
            rows.forEach(r => { const li = document.createElement('li'); li.textContent = text(r); ul.append(li); });
        };
        fill($('deskBookings'), c.bookings, b => `${b.number}: ${b.service} (${b.status})`);
        fill($('deskOrders'), c.orders, o => `${o.number}: ₱${o.total} (${o.status})`);
        $('deskContext').hidden = false;
    }

    function open(id) {
        current = id;
        lastId = 0;
        $('deskMessages').innerHTML = '';
        $('deskEmpty').hidden = true;
        $('deskConvo').hidden = false;
        desk.querySelectorAll('.desk-item').forEach(b => b.classList.remove('is-current'));
        loadThread(true);
        setTimeout(loadList, 400);              // its unread dot goes away
        $('deskInput').focus();
    }

    // ---- replying
    const input = $('deskInput');
    function send(resolve) {
        const body = input.value.trim();
        if (!body || sending || !current) return;
        sending = true;
        post(`/api/admin/support/conversations/${current}/messages`, {body, resolve})
            .then(({ok}) => { if (ok) { input.value = ''; loadThread(true); loadList(); } })
            .finally(() => { sending = false; input.focus(); });
    }
    $('deskComposer').addEventListener('submit', e => { e.preventDefault(); send(false); });
    $('deskSendResolve').addEventListener('click', () => send(true));
    input.addEventListener('keydown', e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(false); } });
    quick.forEach(text => {
        const b = document.createElement('button');
        b.type = 'button';
        b.className = 'desk-chip';
        b.textContent = text;
        b.addEventListener('click', () => { input.value = input.value ? input.value.trimEnd() + ' ' + text : text; input.focus(); });
        $('deskQuick').append(b);
    });

    function status(body) {
        if (!current) return;
        post(`/api/admin/support/conversations/${current}/status`, body).then(() => { loadThread(false); loadList(); });
    }
    $('deskResolve').addEventListener('click', () => status({status: convo && convo.status === 'resolved' ? 'open' : 'resolved'}));
    $('deskWaiting').addEventListener('click', () => status({status: 'waiting'}));
    $('deskAssign').addEventListener('click', () => status({assign: convo && convo.assigned ? 'none' : 'me'}));

    loadList();
    setInterval(() => { if (!document.hidden) { loadThread(false); } }, 4000);
    setInterval(() => { if (!document.hidden) loadList(); }, 15000);
})();
