/* DEVTech read-only location map.

   <div class="map-view" data-map-lat="11.24" data-map-lng="125.00" data-map-label="Customer's pin"></div>
   becomes a small map with the pin and links to directions. Call
   DevtechMapView.render(root) after adding such elements to the page later
   (e.g. inside a details window). Needs Leaflet (static/vendor/leaflet). */
(function () {
    'use strict';
    if (window.DevtechMapView) return;

    function pinIcon() {
        return L.divIcon({
            className: 'devtech-pin',
            html: '<svg viewBox="0 0 32 44" width="32" height="44" aria-hidden="true"><path d="M16 1C7.7 1 1 7.6 1 15.8 1 27 16 43 16 43s15-16 15-27.2C31 7.6 24.3 1 16 1z" fill="#2563EB" stroke="#fff" stroke-width="2"/><circle cx="16" cy="16" r="5.5" fill="#fff"/></svg>',
            iconSize: [32, 44], iconAnchor: [16, 43]
        });
    }

    function render(root) {
        if (typeof L === 'undefined') return;
        (root || document).querySelectorAll('[data-map-lat][data-map-lng]:not([data-map-ready])').forEach(el => {
            const lat = parseFloat(el.dataset.mapLat), lng = parseFloat(el.dataset.mapLng);
            if (isNaN(lat) || isNaN(lng)) return;
            if (!el.getClientRects().length) return;      // hidden (e.g. closed panel): drawn when shown
            el.dataset.mapReady = '1';
            const box = document.createElement('div');
            box.className = 'map-view-canvas';
            el.appendChild(box);
            const map = L.map(box, {scrollWheelZoom: false, zoomControl: true}).setView([lat, lng], 16);
            L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
                attribution: '© OpenStreetMap contributors', maxZoom: 19
            }).addTo(map);
            L.marker([lat, lng], {icon: pinIcon(), title: el.dataset.mapLabel || 'Pinned location'}).addTo(map);
            const links = document.createElement('p');
            links.className = 'map-view-links';
            const dir = document.createElement('a');
            dir.href = `https://www.google.com/maps/dir/?api=1&destination=${lat},${lng}`;
            dir.target = '_blank'; dir.rel = 'noopener';
            dir.innerHTML = '<i class="fas fa-route" aria-hidden="true"></i> Directions';
            const open = document.createElement('a');
            open.href = `https://www.openstreetmap.org/?mlat=${lat}&mlon=${lng}#map=17/${lat}/${lng}`;
            open.target = '_blank'; open.rel = 'noopener';
            open.innerHTML = '<i class="fas fa-up-right-from-square" aria-hidden="true"></i> Open map';
            const coords = document.createElement('span');
            coords.textContent = `${lat.toFixed(5)}, ${lng.toFixed(5)}`;
            links.append(dir, open, coords);
            el.appendChild(links);
            // The container may have been hidden or still growing when the map was made.
            setTimeout(() => map.invalidateSize(), 150);
        });
    }

    window.DevtechMapView = {render, pinIcon};
    document.addEventListener('DOMContentLoaded', () => render(document));
})();
