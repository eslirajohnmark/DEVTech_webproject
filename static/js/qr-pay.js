/* DEVTech QR payment dialog (QR Ph through PayMongo).

   DevtechPay.open({transactionId, title, onPaid, onClose})
     - asks the server for the QR code with the exact amount (POST /api/payments/<id>/qr);
     - checks every few seconds whether the payment has arrived (GET /api/payments/<id>/status);
     - when it expires, offers a new code; card / e-wallet stays available as a fallback.
   The server decides the amount and confirms the payment with PayMongo itself. */
(function () {
    'use strict';
    if (window.DevtechPay) return;

    const POLL_MS = 3000;
    let dialog, state = null;

    function csrf() {
        const m = document.querySelector('meta[name="csrf-token"]');
        return m ? m.content : '';
    }

    function build() {
        dialog = document.createElement('div');
        dialog.className = 'qrpay';
        dialog.hidden = true;
        dialog.innerHTML = `
          <div class="qrpay-backdrop" data-close></div>
          <section class="qrpay-card g-panel" role="dialog" aria-modal="true" aria-labelledby="qrpayTitle">
            <button type="button" class="qrpay-x" data-close aria-label="Close">&times;</button>
            <h2 id="qrpayTitle">Scan to pay</h2>
            <p class="qrpay-amount"><span>Amount</span><strong id="qrpayAmount"></strong></p>
            <div class="qrpay-code">
              <img id="qrpayImg" alt="QR Ph code for this payment" hidden>
              <div class="qrpay-loading" id="qrpayLoading"><i class="fas fa-spinner fa-spin" aria-hidden="true"></i> Creating your QR code…</div>
              <div class="qrpay-done" id="qrpayDone" hidden><i class="fas fa-circle-check" aria-hidden="true"></i><strong>Payment received</strong></div>
              <div class="qrpay-expired" id="qrpayExpired" hidden>
                <p>This code has expired.</p>
                <button type="button" class="g-btn g-btn--primary" id="qrpayRenew">Get a new code</button>
              </div>
            </div>
            <ol class="qrpay-how" id="qrpayHow">
              <li>Open GCash, Maya or your bank's app and choose <b>Scan QR</b>.</li>
              <li>Scan this code. The amount is already filled in.</li>
              <li>Confirm the payment. This window updates by itself.</li>
            </ol>
            <p class="qrpay-status" id="qrpayStatus" aria-live="polite"></p>
            <p class="qrpay-ref" id="qrpayRef"></p>
            <div class="qrpay-actions">
              <a class="qrpay-test" id="qrpayTest" target="_blank" rel="noopener" hidden>Test mode: simulate the payment</a>
              <form method="POST" id="qrpayCard"><input type="hidden" name="csrf_token">
                <button type="submit" class="g-btn g-btn--quiet"><i class="fas fa-credit-card" aria-hidden="true"></i> Pay with card or e-wallet instead</button>
              </form>
              <button type="button" class="g-btn g-btn--quiet" data-close id="qrpayLater">I'll pay later</button>
            </div>
          </section>`;
        document.body.appendChild(dialog);
        dialog.querySelectorAll('[data-close]').forEach(el => el.addEventListener('click', close));
        dialog.querySelector('#qrpayRenew').addEventListener('click', () => load(true));
        document.addEventListener('keydown', e => { if (e.key === 'Escape' && !dialog.hidden) close(); });
    }

    function $(id) { return dialog.querySelector('#' + id); }

    function show(part) {
        ['qrpayImg', 'qrpayLoading', 'qrpayDone', 'qrpayExpired'].forEach(id => { $(id).hidden = id !== part; });
        $('qrpayHow').hidden = part !== 'qrpayImg';
    }

    function expiry(value) {
        if (value === null || value === undefined || value === '') return null;
        const n = Number(value);
        return isNaN(n) ? Date.parse(value) : (n < 1e12 ? n * 1000 : n);
    }

    function tick() {
        if (!state || state.paid) return;
        if (state.expiresAt) {
            const left = Math.max(0, state.expiresAt - Date.now());
            if (!left) { show('qrpayExpired'); $('qrpayStatus').textContent = ''; return; }
            const m = Math.floor(left / 60000), s = Math.floor(left / 1000) % 60;
            $('qrpayStatus').innerHTML = `<span class="qrpay-dot" aria-hidden="true"></span>Waiting for your payment. Code expires in ${m}:${String(s).padStart(2, '0')}`;
        } else {
            $('qrpayStatus').innerHTML = '<span class="qrpay-dot" aria-hidden="true"></span>Waiting for your payment…';
        }
    }

    function poll() {
        if (!state || state.paid) return;
        fetch(`/api/payments/${state.id}/status`, {headers: {'Accept': 'application/json'}})
            .then(r => r.ok ? r.json() : null)
            .then(d => {
                if (!d || !state) return;
                if (d.status === 'paid') return paid();
                if (d.status === 'cancelled') { $('qrpayStatus').textContent = 'This payment was cancelled.'; stop(); }
            })
            .catch(() => {});
    }

    function paid() {
        state.paid = true;
        stop();
        show('qrpayDone');
        $('qrpayStatus').textContent = 'Thank you! Your payment is confirmed.';
        $('qrpayLater').textContent = 'Done';
        $('qrpayCard').hidden = $('qrpayTest').hidden = true;
        const cb = state.onPaid;
        setTimeout(() => { if (cb) cb(); }, 1400);
    }

    function stop() {
        if (state && state.timer) clearInterval(state.timer);
        if (state && state.clock) clearInterval(state.clock);
    }

    function load(fresh) {
        show('qrpayLoading');
        $('qrpayStatus').textContent = '';
        fetch(`/api/payments/${state.id}/qr`, {method: 'POST', headers: {'Accept': 'application/json'}})
            .then(r => r.json().then(d => ({ok: r.ok, d})))
            .then(({ok, d}) => {
                if (!state) return;
                if (d.status === 'paid') return paid();
                if (!ok) throw new Error(d.message || 'The QR code could not be created.');
                $('qrpayImg').src = d.qr;
                $('qrpayAmount').textContent = '₱' + d.amount;
                $('qrpayRef').textContent = 'Reference ' + d.reference;
                $('qrpayCard').action = d.card_url;
                $('qrpayTest').hidden = !d.test_url;
                if (d.test_url) $('qrpayTest').href = d.test_url;
                state.expiresAt = expiry(d.expires_at);
                show('qrpayImg');
                stop();
                tick();
                state.clock = setInterval(tick, 1000);
                state.timer = setInterval(poll, POLL_MS);
            })
            .catch(err => {
                show('qrpayExpired');
                $('qrpayExpired').querySelector('p').textContent = err.message;
                $('qrpayRenew').textContent = 'Try again';
            });
    }

    function open(opts) {
        if (!dialog) build();
        state = {id: opts.transactionId, onPaid: opts.onPaid, onClose: opts.onClose, paid: false};
        $('qrpayTitle').textContent = opts.title || 'Scan to pay';
        $('qrpayAmount').textContent = opts.amount ? '₱' + opts.amount : '';
        $('qrpayLater').textContent = "I'll pay later";
        $('qrpayCard').hidden = false;
        $('qrpayCard').querySelector('[name="csrf_token"]').value = csrf();
        $('qrpayRenew').textContent = 'Get a new code';
        $('qrpayExpired').querySelector('p').textContent = 'This code has expired.';
        dialog.hidden = false;
        document.body.style.overflow = 'hidden';
        load(false);
        setTimeout(() => $('qrpayLater').focus(), 50);
    }

    function close() {
        if (!state) return;
        const s = state;
        stop();
        state = null;
        dialog.hidden = true;
        document.body.style.overflow = '';
        if (!s.paid && s.onClose) s.onClose();
        if (s.paid && s.onPaid === undefined) location.reload();
    }

    window.DevtechPay = {open, close};
})();
