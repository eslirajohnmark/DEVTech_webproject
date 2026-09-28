/* ============================================================================
 * core/api.js — fetch wrapper. Single choke point for HTTP.
 *
 * Attaches X-CSRFToken from <meta name="csrf-token"> on state-changing
 * requests. Normalises every response to { ok, reason?, ...data }.
 * ==========================================================================*/

function csrfToken() {
    const meta = document.querySelector('meta[name="csrf-token"]');
    return meta ? meta.getAttribute('content') : '';
}

async function request(method, url, body) {
    const headers = { 'Accept': 'application/json' };
    const token = csrfToken();
    if (token) headers['X-CSRFToken'] = token;

    const opts = { method, credentials: 'same-origin', headers };

    if (body instanceof FormData) {
        opts.body = body;
    } else if (body !== undefined && body !== null) {
        headers['Content-Type'] = 'application/json';
        opts.body = JSON.stringify(body);
    }

    try {
        const res = await fetch(url, opts);
        let data;
        try { data = await res.json(); }
        catch { data = { ok: false, reason: 'HTTP ' + res.status }; }

        if (res.status === 401 && !location.pathname.includes('/login')) {
            location.replace('/technician/login');
            return { ok: false, reason: 'Not signed in.' };
        }
        if (res.ok && data.ok !== false) return data;
        return { ok: false, reason: data.reason || ('HTTP ' + res.status) };
    } catch (err) {
        return { ok: false, reason: err.message || 'Network error' };
    }
}

export const API = {
    get:   url       => request('GET', url),
    post:  (url, b)  => request('POST', url, b),
    patch: (url, b)  => request('PATCH', url, b),
    del:   url       => request('DELETE', url),
    form:  (url, fd) => request('POST', url, fd),
};