/* ============================================================================
 * core/format.js — money, dates, relative time, escaping.
 * ==========================================================================*/

export function money(amount) {
    return 'P' + Number(amount || 0).toLocaleString('en-PH', {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2,
    });
}

export function date(iso) {
    if (!iso) return '-';
    const d = new Date(String(iso).slice(0, 10) + 'T00:00:00');
    if (isNaN(d.getTime())) return iso;
    return d.toLocaleDateString('en-US', {
        month: 'short', day: '2-digit', year: 'numeric',
    });
}

export function dateTime(stamp) {
    if (!stamp) return '-';
    const d = new Date(String(stamp).replace(' ', 'T'));
    if (isNaN(d.getTime())) return stamp;
    return d.toLocaleDateString('en-US', {
        month: 'short', day: '2-digit', year: 'numeric',
    }) + ' - ' + d.toLocaleTimeString('en-US', {
        hour: 'numeric', minute: '2-digit',
    });
}

export function relative(stamp) {
    const then = new Date(String(stamp).replace(' ', 'T'));
    if (isNaN(then.getTime())) return stamp;
    const diff = Math.floor((Date.now() - then.getTime()) / 1000);
    if (diff < 60)     return 'Just now';
    if (diff < 3600)   return Math.floor(diff / 60) + 'm ago';
    if (diff < 86400)  return Math.floor(diff / 3600) + 'h ago';
    if (diff < 604800) return Math.floor(diff / 86400) + 'd ago';
    return date(String(stamp).slice(0, 10));
}

export function escape(text) {
    return String(text === null || text === undefined ? '' : text)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
}

export function now() {
    const d = new Date();
    const p = n => String(n).padStart(2, '0');
    return d.getFullYear() + '-' + p(d.getMonth() + 1) + '-' + p(d.getDate())
         + ' ' + p(d.getHours()) + ':' + p(d.getMinutes()) + ':' + p(d.getSeconds());
}

export function capitalize(text) {
    const s = String(text || '');
    return s.charAt(0).toUpperCase() + s.slice(1);
}