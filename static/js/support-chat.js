/* Customer support chat (templates/user/support.html).
   Starts a conversation, shows the thread and polls for replies every few seconds. */
(function () {
    'use strict';
    const root = document.getElementById('supChat');
    if (!root) return;
    const $ = id => document.getElementById(id);
    const POLL_MS = 4000;
    let convos = JSON.parse(root.dataset.conversations || '[]');
    let current = null, lastId = 0, timer = null, sending = false;

    // ---- conversation list (beside the chat)
    function renderList() {
        const ul = $('supConvos');
        ul.innerHTML = '';
        convos.forEach(c => {
            const li = document.createElement('li');
            const b = document.createElement('button');
            b.type = 'button';
            b.className = 'sup-convo' + (current && c.id === current ? ' is-current' : '') + (c.unread ? ' is-unread' : '');
            const title = document.createElement('strong');
            title.textContent = c.topic;
            const snip = document.createElement('span');
            snip.textContent = c.snippet;
            const meta = document.createElement('small');
            meta.textContent = (c.status === 'resolved' ? 'Resolved' : c.status === 'waiting' ? 'Replied' : 'Waiting for us') + ', ' + c.last_at;
            b.append(title, snip, meta);
            b.addEventListener('click', () => open(c.id));
            li.append(b);
            ul.append(li);
        });
        $('supHistory').hidden = !convos.length;
    }

    // ---- messages
    function bubble(m) {
        const li = document.createElement('li');
        li.className = 'sup-msg sup-msg--' + (m.role === 'customer' ? 'me' : m.role === 'system' ? 'note' : 'them');
        if (m.role === 'admin') {
            const who = document.createElement('span');
            who.className = 'sup-who';
            who.textContent = m.who + ', DEVTech Support';
            li.append(who);
        }
        const p = document.createElement('p');
        p.textContent = m.body;
        const t = document.createElement('time');
        t.textContent = m.at;
        if (m.iso) t.dateTime = m.iso;
        li.append(p, t);
        return li;
    }

    function load(initial) {
        if (!current) return;
        const id = current;
        fetch(`/api/support/conversations/${id}?after=${lastId}`, {headers: {'Accept': 'application/json'}})
            .then(r => r.ok ? r.json() : null)
            .then(d => {
                if (!d || id !== current) return;
                const list = $('supMessages');
                const nearBottom = list.scrollHeight - list.scrollTop - list.clientHeight < 80;
                // Two requests can overlap (opening + the timer): add each message once.
                d.messages.forEach(m => { if (m.id <= lastId) return; list.append(bubble(m)); lastId = m.id; });
                if (d.messages.length && (initial || nearBottom)) list.scrollTop = list.scrollHeight;
                const c = d.conversation;
                $('supTitle').textContent = c.topic;
                $('supSub').textContent = c.status === 'resolved' ? 'Resolved' :
                    c.assigned ? `${c.assigned} is helping you` : 'Waiting for a team member to reply';
                $('supResolved').hidden = c.status !== 'resolved';
                const i = convos.findIndex(x => x.id === c.id);
                if (i >= 0) { convos[i] = Object.assign(convos[i], c, {unread: false}); renderList(); }
            })
            .catch(() => {});
    }

    function open(id, quiet) {
        current = id;
        lastId = 0;
        $('supMessages').innerHTML = '';
        $('supStart').hidden = true;
        $('supThread').hidden = false;
        $('supNew').hidden = false;
        renderList();
        load(true);
        clearInterval(timer);
        timer = setInterval(() => { if (!document.hidden) load(false); }, POLL_MS);
        if (!quiet) $('supInput').focus();
    }

    function startScreen(quiet) {
        current = null;
        clearInterval(timer);
        $('supStart').hidden = false;
        $('supThread').hidden = true;
        $('supNew').hidden = !convos.length;
        $('supTitle').textContent = 'DEVTech Support';
        $('supSub').textContent = 'Real people from our shop, not a bot.';
        renderList();
        if (!quiet) $('supFirst').focus();
    }

    // The FAQ chatbot (faq-bot.js) hands a question it can't answer to the team.
    window.DevtechSupport = {
        askTeam(text) {
            if (current) {                                   // a conversation is open: write in it
                const box = $('supInput');
                if (text && !box.value.trim()) box.value = text;
                box.focus();
            } else {
                startScreen(true);
                if (text && !$('supFirst').value.trim()) $('supFirst').value = text;
                $('supFirst').focus();
            }
            root.scrollIntoView({behavior: 'smooth', block: 'start'});
        }
    };

    // ---- start
    $('supStartBtn').addEventListener('click', () => {
        const body = $('supFirst').value.trim();
        const err = $('supStartError');
        if (body.length < 5) { err.textContent = 'Tell us a little more so we can help.'; err.hidden = false; return; }
        const topic = (root.querySelector('input[name=topic]:checked') || {}).value || 'general';
        const btn = $('supStartBtn');
        btn.disabled = true;
        fetch('/api/support/conversations', {method: 'POST', headers: {'Content-Type': 'application/json'},
                                             body: JSON.stringify({topic, body})})
            .then(r => r.json().then(d => ({ok: r.ok, d})))
            .then(({ok, d}) => {
                if (!ok) throw new Error(d.message || 'Your message could not be sent.');
                convos.unshift({id: d.id, topic: root.querySelector('input[name=topic]:checked').parentElement.textContent.trim(),
                                snippet: body.slice(0, 90), status: 'open', last_at: 'just now', unread: false});
                $('supFirst').value = '';
                err.hidden = true;
                open(d.id);
            })
            .catch(e => { err.textContent = e.message; err.hidden = false; })
            .finally(() => { btn.disabled = false; });
    });
    $('supNew').addEventListener('click', () => startScreen(false));

    // ---- reply
    const input = $('supInput');
    function grow() { input.style.height = 'auto'; input.style.height = Math.min(input.scrollHeight, 160) + 'px'; }
    input.addEventListener('input', grow);
    input.addEventListener('keydown', e => {
        if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); $('supComposer').requestSubmit(); }
    });
    $('supComposer').addEventListener('submit', e => {
        e.preventDefault();
        const body = input.value.trim();
        if (!body || sending || !current) return;
        sending = true;
        fetch(`/api/support/conversations/${current}/messages`, {method: 'POST', headers: {'Content-Type': 'application/json'},
                                                               body: JSON.stringify({body})})
            .then(r => r.json())
            .then(d => {
                if (!d.success) throw new Error(d.message);
                input.value = '';
                grow();
                load(true);
            })
            .catch(() => { input.classList.add('is-error'); setTimeout(() => input.classList.remove('is-error'), 1500); })
            .finally(() => { sending = false; });
    });

    // Open the latest conversation that is still going, if there is one.
    const active = convos.find(c => c.status !== 'resolved');
    if (active) open(active.id, true); else startScreen(true);
})();
