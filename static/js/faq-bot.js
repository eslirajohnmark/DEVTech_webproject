/* FAQ chatbot on the Support page: tap a common question or type one, and the
   answer comes from /api/support/bot. Anything it can't answer goes to the team chat. */
(function () {
    'use strict';
    const log = document.getElementById('botLog');
    const form = document.getElementById('botForm');
    if (!log || !form) return;
    const input = document.getElementById('botInput');
    const chipsBox = document.getElementById('botChips');
    let asking = false;

    function bubble(mine, text) {
        const li = document.createElement('li');
        li.className = 'sup-msg ' + (mine ? 'sup-msg--me' : 'sup-msg--them sup-msg--bot');
        const p = document.createElement('p');
        p.textContent = text;
        li.append(p);
        log.append(li);
        log.scrollTop = log.scrollHeight;
        return li;
    }

    function chips(list) {
        chipsBox.innerHTML = '';
        (list || []).forEach(q => {
            const b = document.createElement('button');
            b.type = 'button';
            b.className = 'sup-chip';
            b.dataset.ask = q;
            b.textContent = q;
            chipsBox.append(b);
        });
    }

    function ask(question) {
        question = (question || '').trim();
        if (!question || asking) return;
        asking = true;
        bubble(true, question);
        const wait = bubble(false, 'Typing...');
        wait.classList.add('is-typing');
        fetch('/api/support/bot', {method: 'POST', headers: {'Content-Type': 'application/json'},
                                   body: JSON.stringify({message: question})})
            .then(r => r.json())
            .then(d => {
                wait.remove();
                const li = bubble(false, d.answer || 'Sorry, I could not answer that. Please try again.');
                const extras = document.createElement('div');
                extras.className = 'sup-bot-links';
                (d.links || []).forEach(l => {
                    const a = document.createElement('a');
                    a.href = l.url;
                    a.textContent = l.label;
                    extras.append(a);
                });
                if ((d.human || d.confident === false) && window.DevtechSupport) {
                    const b = document.createElement('button');
                    b.type = 'button';
                    b.className = 'sup-linkbtn';
                    b.textContent = 'Message our team';
                    b.addEventListener('click', () => window.DevtechSupport.askTeam(question));
                    extras.append(b);
                }
                if (extras.children.length) li.append(extras);
                chips(d.suggestions);
                log.scrollTop = log.scrollHeight;
            })
            .catch(() => { wait.remove(); bubble(false, 'I could not answer just now. Please try again.'); })
            .finally(() => { asking = false; });
    }

    form.addEventListener('submit', e => {
        e.preventDefault();
        const q = input.value;
        input.value = '';
        ask(q);
    });
    chipsBox.addEventListener('click', e => {
        const b = e.target.closest('[data-ask]');
        if (b) ask(b.dataset.ask);
    });
})();
