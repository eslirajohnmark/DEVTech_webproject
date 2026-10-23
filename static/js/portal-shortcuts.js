/* DEVTech — jump between the three portals from anywhere on the site.
     Ctrl+Shift+L  →  Admin side       (from the customer and technician sides)
     Ctrl+Shift+Y  →  Technician side  (from the customer and admin sides)
     Ctrl+Shift+U  →  Customer side    (from the admin and technician sides)
   Each goes to /go/<side>, which opens that portal's dashboard if you're already
   signed in there, or its sign-in page if not. Pressing the key for the side
   you're on does nothing. This is the only place these shortcuts are handled. */
(function () {
    'use strict';
    if (window.__devtechShortcuts) return;          // included twice on a page: bind once
    window.__devtechShortcuts = true;

    var KEYS = { l: 'admin', y: 'technician', u: 'user' };

    function currentSide() {
        var p = location.pathname;
        if (p === '/admin' || p.indexOf('/admin/') === 0) return 'admin';
        if (p === '/technician' || p.indexOf('/technician/') === 0) return 'technician';
        return 'user';
    }

    document.addEventListener('keydown', function (e) {
        if (!e.ctrlKey || !e.shiftKey || e.altKey || e.metaKey || e.repeat) return;
        var side = KEYS[(e.key || '').toLowerCase()];
        if (!side) return;
        e.preventDefault();
        e.stopPropagation();
        if (side === currentSide()) return;
        location.href = '/go/' + side;
    }, true);
})();
