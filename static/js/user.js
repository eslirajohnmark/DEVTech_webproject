// ==========================================
// DEVTech - User Panel JavaScript
// ==========================================

/**
 * Shows/hides the mobile nav drawer. The CSS contract (see user.css'
 * "MOBILE MENU TOGGLE" / "RESPONSIVE SIDEBAR" sections) already hides
 * #mobileNavMenu by default under 769px and reveals it via the .open
 * class - this was the one missing piece connecting the hamburger button
 * to that behavior; the button's onclick had nothing to call before.
 */
function toggleMobileMenu() {
    const menu = document.getElementById('mobileNavMenu');
    if (menu) menu.classList.toggle('open');
}

document.addEventListener('DOMContentLoaded', function() {
    // Close the mobile nav drawer after navigating, so it doesn't stay
    // open (covering the page) when the new page loads.
    const mobileMenu = document.getElementById('mobileNavMenu');
    if (mobileMenu) {
        mobileMenu.querySelectorAll('.user-nav-item').forEach(function(link) {
            link.addEventListener('click', function() {
                mobileMenu.classList.remove('open');
            });
        });
    }

    // ===== FLASH MESSAGES =====
    const flashMessages = document.querySelectorAll('.flash-message');
    flashMessages.forEach(msg => {
        const closeBtn = msg.querySelector('.flash-close');
        if (closeBtn) {
            closeBtn.addEventListener('click', function() {
                msg.remove();
            });
        }
        setTimeout(() => {
            if (msg) {
                msg.style.opacity = '0';
                msg.style.transform = 'translateY(-10px)';
                setTimeout(() => msg.remove(), 300);
            }
        }, 5000);
    });

    // ===== CHARACTER COUNTER =====
    const textareas = document.querySelectorAll('textarea[data-max-chars]');
    textareas.forEach(textarea => {
        const maxChars = parseInt(textarea.dataset.maxChars) || 500;
        const counter = document.getElementById(textarea.dataset.counterId);
        
        textarea.addEventListener('input', function() {
            const count = this.value.length;
            if (counter) {
                counter.textContent = count;
                counter.style.color = count > maxChars * 0.9 ? '#ef4444' : '';
            }
        });
    });

    // ===== TIME SLOT SELECTION =====
    document.querySelectorAll('.time-slot').forEach(slot => {
        slot.addEventListener('click', function() {
            if (this.classList.contains('booked')) return;
            document.querySelectorAll('.time-slot').forEach(s => s.classList.remove('selected'));
            this.classList.add('selected');
            const hiddenInput = document.getElementById('selectedTime');
            if (hiddenInput) {
                hiddenInput.value = this.dataset.time;
            }
        });
    });

    // ===== IN-SHOP TOGGLE =====
    const inShopCheck = document.getElementById('inShopCheck');
    const addressInput = document.getElementById('serviceAddress');
    if (inShopCheck && addressInput) {
        inShopCheck.addEventListener('change', function() {
            if (this.checked) {
                addressInput.value = 'DEVTech Repair Center, Tacloban City';
                addressInput.disabled = true;
            } else {
                addressInput.value = '';
                addressInput.disabled = false;
            }
        });
    }

    // ===== BOOKING FORM VALIDATION =====
    const bookingForm = document.getElementById('bookingForm');
    if (bookingForm) {
        bookingForm.addEventListener('submit', function(e) {
            const required = this.querySelectorAll('[required]');
            let valid = true;
            required.forEach(field => {
                if (!field.value.trim()) {
                    field.style.borderColor = '#ef4444';
                    valid = false;
                } else {
                    field.style.borderColor = '';
                }
            });
            
            if (!valid) {
                e.preventDefault();
                alert('Please fill in all required fields.');
            }
        });
    }

    // ===== PASSWORD STRENGTH =====
    const passwordInput = document.getElementById('password');
    const strengthBar = document.getElementById('passwordStrength');
    if (passwordInput && strengthBar) {
        passwordInput.addEventListener('input', function() {
            const strength = checkPasswordStrength(this.value);
            strengthBar.style.width = strength.percentage + '%';
            strengthBar.style.background = strength.color;
        });
    }

    // ===== BOOKING FORM FUNCTIONS =====
    initBookingForm();

    // ===== PRESENCE HEARTBEAT =====
    // Keeps this account's online/offline status (shown to admins in
    // User Management) accurate while this tab is open.
    startPresenceHeartbeat();
});

/**
 * Periodically pings the server so this session's last_active stays
 * fresh. Paused while the tab is hidden to avoid needless requests.
 */
function startPresenceHeartbeat() {
    const HEARTBEAT_MS = 25000;

    function ping() {
        fetch('/api/ping', { method: 'POST' }).catch(() => {});
    }

    ping();
    setInterval(() => {
        if (document.visibilityState === 'visible') ping();
    }, HEARTBEAT_MS);

    document.addEventListener('visibilitychange', function() {
        if (document.visibilityState === 'visible') ping();
    });
}

// ==========================================
// PASSWORD STRENGTH CHECKER
// ==========================================

function checkPasswordStrength(password) {
    let score = 0;
    if (password.length >= 8) score++;
    if (password.match(/[a-z]/)) score++;
    if (password.match(/[A-Z]/)) score++;
    if (password.match(/[0-9]/)) score++;
    if (password.match(/[^a-zA-Z0-9]/)) score++;
    
    const percentages = [0, 20, 40, 60, 80, 100];
    const colors = ['#ef4444', '#ef4444', '#f59e0b', '#f59e0b', '#22c55e', '#22c55e'];
    
    return {
        percentage: percentages[score],
        color: colors[score],
        score: score
    };
}

// ==========================================
// TOAST NOTIFICATION
// ==========================================

function showUserToast(message, type = 'info') {
    let toast = document.getElementById('userToast');
    
    if (!toast) {
        toast = document.createElement('div');
        toast.id = 'userToast';
        toast.className = 'user-toast';
        document.body.appendChild(toast);
    }
    
    let icon = 'fa-info-circle';
    if (type === 'success') icon = 'fa-check-circle';
    else if (type === 'error') icon = 'fa-exclamation-circle';
    else if (type === 'warning') icon = 'fa-exclamation-triangle';
    
    toast.innerHTML = `<i class="fas ${icon}"></i> ${message}`;
    toast.className = 'user-toast show';
    
    clearTimeout(toast._timeout);
    toast._timeout = setTimeout(() => {
        toast.classList.remove('show');
    }, 3000);
}

// ==========================================
// AJAX REQUEST HELPER
// ==========================================

function userAjax(url, method = 'GET', data = null) {
    return fetch(url, {
        method: method,
        headers: {
            'Content-Type': 'application/json',
            'X-Requested-With': 'XMLHttpRequest'
        },
        body: data ? JSON.stringify(data) : null
    })
    .then(response => response.json())
    .catch(error => {
        showUserToast('An error occurred: ' + error.message, 'error');
        throw error;
    });
}

// ==========================================
// BOOKING FORM FUNCTIONS
// ==========================================

function initBookingForm() {
    // request_service.html ships its own complete, self-contained booking
    // script (geofencing, its own toggleAddress/updateSummary/initMap).
    // If that's already loaded, running this generic version too would
    // double-bind every event listener on the same elements AND call
    // L.map('locationMap', ...) a second time on the same container -
    // Leaflet throws "Map container is already initialized" when that
    // happens, which is exactly what was breaking the booking page's map.
    if (typeof window.toggleAddress === 'function') return;

    // DOM Elements
    const deviceRadios = document.querySelectorAll('input[name="category"]');
    const serviceSelect = document.getElementById('service_id');
    const problemDesc = document.getElementById('problemDesc');
    const bookingDate = document.getElementById('bookingDate');
    const serviceAddress = document.getElementById('serviceAddress');
    const inShopCheck = document.getElementById('inShopCheck');
    const charCount = document.getElementById('charCount');
    const timeSlots = document.querySelectorAll('.user-time-slot');
    const bookingTime = document.getElementById('bookingTime');

    // Summary Elements
    const summaryDevice = document.getElementById('summaryDevice');
    const summaryService = document.getElementById('summaryService');
    const summaryIssue = document.getElementById('summaryIssue');
    const summarySchedule = document.getElementById('summarySchedule');
    const summaryAddress = document.getElementById('summaryAddress');
    const summaryPrice = document.getElementById('summaryPrice');
    const summaryHours = document.getElementById('summaryHours');

    if (!serviceSelect) return; // Not on booking page

    // ===== SET DEFAULTS =====
    const tomorrow = new Date();
    tomorrow.setDate(tomorrow.getDate() + 1);
    bookingDate.value = tomorrow.toISOString().split('T')[0];

    const today = new Date().toISOString().split('T')[0];
    bookingDate.setAttribute('min', today);

    inShopCheck.checked = true;
    serviceAddress.value = 'DEVTech Repair Center, Tacloban City';
    serviceAddress.disabled = true;

    document.getElementById('device-desktop').checked = true;

    // ===== UPDATE SUMMARY =====
    function updateSummary() {
        const selectedRadio = document.querySelector('input[name="category"]:checked');
        summaryDevice.textContent = selectedRadio ? selectedRadio.value : 'Desktop';

        const selectedOption = serviceSelect.options[serviceSelect.selectedIndex];
        if (selectedOption && selectedOption.value) {
            const serviceName = selectedOption.text.split(' - ')[0] || 'Not selected';
            summaryService.textContent = serviceName;
            const price = selectedOption.dataset.price;
            summaryPrice.textContent = price ? '₱' + parseFloat(price).toFixed(2) : '₱0.00';
            const hours = selectedOption.dataset.hours;
            summaryHours.textContent = hours ? hours + ' hour(s)' : '1-2 hours';
        } else {
            summaryService.textContent = 'Not selected';
            summaryPrice.textContent = '₱0.00';
            summaryHours.textContent = '1-2 hours';
        }

        const issueText = problemDesc.value.trim();
        summaryIssue.textContent = issueText || 'Not described yet';
        summaryIssue.className = issueText ? '' : 'user-summary-placeholder';

        if (!inShopCheck.checked) {
            const addrText = serviceAddress.value.trim();
            summaryAddress.textContent = addrText || 'Not set';
            summaryAddress.className = addrText ? '' : 'user-summary-placeholder';
        } else {
            summaryAddress.textContent = 'In-shop repair';
            summaryAddress.className = '';
        }

        const date = bookingDate.value;
        const selectedSlot = document.querySelector('.user-time-slot.selected');
        const timeText = selectedSlot ? selectedSlot.querySelector('span:first-child').textContent : '';
        
        if (date && timeText) {
            const formattedDate = new Date(date + 'T00:00:00').toLocaleDateString('en-US', {
                month: 'short',
                day: 'numeric',
                year: 'numeric'
            });
            summarySchedule.textContent = `${formattedDate} · ${timeText}`;
            summarySchedule.className = '';
        } else if (date) {
            const formattedDate = new Date(date + 'T00:00:00').toLocaleDateString('en-US', {
                month: 'short',
                day: 'numeric',
                year: 'numeric'
            });
            summarySchedule.textContent = `${formattedDate} (time not set)`;
            summarySchedule.className = 'user-summary-placeholder';
        } else {
            summarySchedule.textContent = 'Not set';
            summarySchedule.className = 'user-summary-placeholder';
        }
    }

    // ===== EVENT LISTENERS =====
    problemDesc.addEventListener('input', function() {
        const count = this.value.length;
        charCount.textContent = count;
        charCount.style.color = count > 450 ? '#ef4444' : '';
        updateSummary();
    });

    deviceRadios.forEach(radio => {
        radio.addEventListener('change', updateSummary);
    });

    serviceSelect.addEventListener('change', updateSummary);

    inShopCheck.addEventListener('change', function() {
        if (this.checked) {
            serviceAddress.value = 'DEVTech Repair Center, Tacloban City';
            serviceAddress.disabled = true;
            summaryAddress.textContent = 'In-shop repair';
            summaryAddress.className = '';
            const mapSection = document.querySelector('.map-section');
            if (mapSection) mapSection.style.display = 'none';
        } else {
            serviceAddress.value = '';
            serviceAddress.disabled = false;
            summaryAddress.textContent = 'Not set';
            summaryAddress.className = 'user-summary-placeholder';
            const mapSection = document.querySelector('.map-section');
            if (mapSection) {
                mapSection.style.display = 'block';
                if (typeof initBookingMap === 'function') {
                    initBookingMap();
                }
            }
        }
        updateSummary();
    });

    serviceAddress.addEventListener('input', function() {
        if (!inShopCheck.checked) {
            summaryAddress.textContent = this.value || 'Not set';
            summaryAddress.className = this.value ? '' : 'user-summary-placeholder';
        }
    });

    timeSlots.forEach(slot => {
        slot.addEventListener('click', function() {
            if (this.classList.contains('booked') || this.classList.contains('lunch')) {
                showUserToast('This time slot is not available');
                return;
            }
            
            timeSlots.forEach(s => s.classList.remove('selected'));
            this.classList.add('selected');
            bookingTime.value = this.dataset.time;
            updateSummary();
        });
    });

    bookingDate.addEventListener('change', updateSummary);

    // ===== RESET FORM =====
    window.resetForm = function() {
        if (confirm('Clear all form fields?')) {
            document.getElementById('device-desktop').checked = true;
            serviceSelect.value = '';
            problemDesc.value = '';
            charCount.textContent = '0';
            inShopCheck.checked = true;
            serviceAddress.value = 'DEVTech Repair Center, Tacloban City';
            serviceAddress.disabled = true;
            timeSlots.forEach(s => s.classList.remove('selected'));
            bookingTime.value = '';
            const tomorrow = new Date();
            tomorrow.setDate(tomorrow.getDate() + 1);
            bookingDate.value = tomorrow.toISOString().split('T')[0];
            
            if (typeof resetMap === 'function') {
                resetMap();
            }
            
            updateSummary();
            showUserToast('Form has been cleared');
        }
    };

    // ===== SUBMIT BOOKING =====
    window.submitBooking = function() {
        const service = serviceSelect.value;
        const description = problemDesc.value.trim();
        const date = bookingDate.value;
        const time = bookingTime.value;
        const isInShop = inShopCheck.checked;
        const isValidLoc = document.getElementById('isValidLocation')?.value;
        const address = serviceAddress.value.trim();
        
        if (!service) {
            showUserToast('Please select a service');
            serviceSelect.focus();
            return;
        }
        
        if (!description) {
            showUserToast('Please describe your issue');
            problemDesc.focus();
            return;
        }
        
        if (!date) {
            showUserToast('Please select a date');
            bookingDate.focus();
            return;
        }
        
        if (!time) {
            showUserToast('Please select a time slot');
            return;
        }
        
        if (!isInShop) {
            if (!address) {
                showUserToast('Please enter your address');
                serviceAddress.focus();
                return;
            }
            if (isValidLoc !== '1') {
                showUserToast('Please pin your location on the map (Tacloban City only)');
                return;
            }
        }
        
        document.getElementById('bookingForm').submit();
    };

    // ===== KEYBOARD SHORTCUTS =====
    document.addEventListener('keydown', function(e) {
        if (e.ctrlKey && e.key === 'Enter') {
            e.preventDefault();
            submitBooking();
        }
        if (e.key === 'Enter' && document.activeElement.id === 'mapSearchInput') {
            e.preventDefault();
            if (typeof searchLocation === 'function') {
                searchLocation();
            }
        }
    });

    // ===== INITIAL SUMMARY =====
    updateSummary();
    
    // ===== INITIALIZE MAP =====
    const mapSection = document.querySelector('.map-section');
    if (mapSection) mapSection.style.display = 'none';
    
    console.log('✅ Booking form initialized with defaults');
}

// ==========================================
// MAP FUNCTIONS - Tacloban Geofencing (Updated)
// ==========================================

// ==========================================
// TACLOBAN CITY BOUNDARY (real barangay-level data)
// Sourced from an official GADM-style administrative boundary dataset
// (138 barangays, 141 polygon parts) rather than the old ~30-point
// hand-drawn approximation. Loaded once, eagerly, as soon as this script
// parses - by the time a user actually interacts with a map (which
// requires the page to finish loading first), the fetch has long since
// completed, so isInsideTacloban() below can stay a plain synchronous
// function everywhere it's already called.
// ==========================================

const TACLOBAN_CENTER = [11.2444, 125.0039];
const TACLOBAN_BOUNDARY_URL = '/static/data/tacloban_boundary.geojson';

let TACLOBAN_BOUNDARY_GEOJSON = null;  // raw GeoJSON, kept for drawing on the map
let TACLOBAN_POLYGONS = null;          // parsed [ [ [lat,lng], ... ], ... ] rings per polygon, for point-in-polygon tests
let taclobanBoundaryLoadPromise = null;

function loadTaclobanBoundary() {
    if (TACLOBAN_POLYGONS) return Promise.resolve(TACLOBAN_POLYGONS);
    if (taclobanBoundaryLoadPromise) return taclobanBoundaryLoadPromise;

    taclobanBoundaryLoadPromise = fetch(TACLOBAN_BOUNDARY_URL)
        .then(function(response) {
            if (!response.ok) throw new Error('HTTP ' + response.status);
            return response.json();
        })
        .then(function(geojson) {
            TACLOBAN_BOUNDARY_GEOJSON = geojson;
            // GeoJSON coordinates are [lon, lat]; every other lat/lng pair
            // in this app (Leaflet, TACLOBAN_CENTER, etc.) is [lat, lng] -
            // converting once here means nothing downstream has to care.
            TACLOBAN_POLYGONS = geojson.features.map(function(feature) {
                return feature.geometry.coordinates.map(function(ring) {
                    return ring.map(function(pt) { return [pt[1], pt[0]]; });
                });
            });
            return TACLOBAN_POLYGONS;
        })
        .catch(function(err) {
            console.error('Failed to load Tacloban boundary data:', err);
            TACLOBAN_POLYGONS = [];
            return TACLOBAN_POLYGONS;
        });

    return taclobanBoundaryLoadPromise;
}

// Kick the fetch off immediately - don't wait for DOMContentLoaded, since
// the sooner this starts the more certain it's already finished by the
// time any map on the page is actually opened.
loadTaclobanBoundary();

function pointInRing(lat, lng, ring) {
    let inside = false;
    for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
        const yi = ring[i][0], xi = ring[i][1];
        const yj = ring[j][0], xj = ring[j][1];
        const intersect = ((yi > lat) !== (yj > lat)) &&
            (lng < (xj - xi) * (lat - yi) / (yj - yi) + xi);
        if (intersect) inside = !inside;
    }
    return inside;
}

/**
 * Check if a point falls inside any of Tacloban City's 138 barangays.
 * A polygon's first ring is its outer boundary; any further rings are
 * holes cut out of it (standard GeoJSON convention) - a point only
 * counts as inside that polygon if it's within the outer ring and NOT
 * within any hole.
 */
function isInsideTacloban(lat, lng) {
    if (!TACLOBAN_POLYGONS) {
        // Extremely unlikely in practice (see loadTaclobanBoundary above),
        // but fail open rather than wrongly rejecting a legitimate pin
        // during the brief window before the fetch resolves.
        console.warn('Tacloban boundary not loaded yet - allowing pin as a precaution.');
        return true;
    }
    return TACLOBAN_POLYGONS.some(function(rings) {
        const outer = rings[0];
        const holes = rings.slice(1);
        if (!pointInRing(lat, lng, outer)) return false;
        return !holes.some(function(hole) { return pointInRing(lat, lng, hole); });
    });
}

let mapInstance = null;
let mapMarker = null;
let isMapInitialized = false;
let tempMarker = null;
let isPinning = false;

/**
 * Initialize the map
 */
function initLocationMap() {
    if (isMapInitialized || !document.getElementById('locationMap')) return;
    
    if (typeof L === 'undefined') {
        console.error('Leaflet not loaded');
        return;
    }

    mapInstance = L.map('locationMap', {
        center: TACLOBAN_CENTER,
        zoom: 14,
        zoomControl: true,
        maxBounds: [
            [11.1000, 124.9000],
            [11.3600, 125.1200]
        ],
        maxBoundsViscosity: 0.8
    });

    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        attribution: '© OpenStreetMap contributors',
        maxZoom: 19
    }).addTo(mapInstance);

    // Draw the real barangay boundaries (transparent fill so users can see
    // through to the map tiles underneath). Falls back gracefully if the
    // fetch is still in flight - draws in as soon as it resolves.
    loadTaclobanBoundary().then(function() {
        if (TACLOBAN_BOUNDARY_GEOJSON && mapInstance) {
            L.geoJSON(TACLOBAN_BOUNDARY_GEOJSON, {
                style: {
                    color: '#2563eb',
                    weight: 1.5,
                    opacity: 0.7,
                    fillColor: '#2563eb',
                    fillOpacity: 0.04,
                    smoothFactor: 1
                }
            }).addTo(mapInstance);
        }
    });

    L.marker(TACLOBAN_CENTER, {
        icon: L.divIcon({
            className: 'boundary-label',
            html: '📍 Tacloban City',
            iconSize: [100, 20],
            iconAnchor: [50, 10]
        })
    }).addTo(mapInstance);

    // Click on map to pin (allow clicks anywhere, validate after)
    mapInstance.on('click', function(e) {
        const lat = e.latlng.lat;
        const lng = e.latlng.lng;
        
        // Always pin the location, then validate
        pinLocation(lat, lng);
    });

    isMapInitialized = true;
    setTimeout(() => {
        if (mapInstance) {
            mapInstance.invalidateSize();
        }
    }, 500);

    console.log('✅ Map initialized successfully');
}

/**
 * Pin a location on the map
 */
function pinLocation(lat, lng) {
    // Remove existing marker
    if (mapMarker) {
        mapInstance.removeLayer(mapMarker);
        mapMarker = null;
    }

    // Remove any temporary marker
    if (tempMarker) {
        mapInstance.removeLayer(tempMarker);
        tempMarker = null;
    }

    const valid = isInsideTacloban(lat, lng);
    const markerColor = valid ? '#2563eb' : '#ef4444';

    // Create marker icon
    const markerIcon = L.divIcon({
        className: 'custom-marker',
        html: `<div style="background:${markerColor};width:24px;height:24px;border-radius:50%;border:3px solid white;box-shadow:0 2px 10px rgba(37,99,235,0.5);"></div>`,
        iconSize: [24, 24],
        iconAnchor: [12, 12]
    });

    mapMarker = L.marker([lat, lng], {
        draggable: true,
        icon: markerIcon
    }).addTo(mapInstance);

    // Add popup with validation status
    const statusText = valid ? '✅ Within Tacloban City' : '❌ Outside Tacloban City';
    mapMarker.bindPopup(`
        <div style="padding: 4px 8px;">
            <strong>📍 Pinned Location</strong><br>
            ${statusText}
            ${valid ? '<br>Location accepted!' : '<br>Please pin inside Tacloban City'}
        </div>
    `).openPopup();

    // Drag handler
    mapMarker.on('dragend', function() {
        const pos = mapMarker.getLatLng();
        const isValid = isInsideTacloban(pos.lat, pos.lng);
        if (!isValid) {
            showUserToast('⚠️ Location outside Tacloban City. Please drag inside the boundary.', 'warning');
            // Flash the marker red
            const icon = L.divIcon({
                className: 'custom-marker invalid pulse',
                html: `<div style="background:#ef4444;width:24px;height:24px;border-radius:50%;border:3px solid white;box-shadow:0 2px 10px rgba(239,68,68,0.5);"></div>`,
                iconSize: [24, 24],
                iconAnchor: [12, 12]
            });
            mapMarker.setIcon(icon);
            setTimeout(() => {
                const resetIcon = L.divIcon({
                    className: 'custom-marker invalid',
                    html: `<div style="background:#ef4444;width:24px;height:24px;border-radius:50%;border:3px solid white;box-shadow:0 2px 10px rgba(239,68,68,0.5);"></div>`,
                    iconSize: [24, 24],
                    iconAnchor: [12, 12]
                });
                mapMarker.setIcon(resetIcon);
            }, 1000);
        }
        pinLocation(pos.lat, pos.lng);
    });

    // Update hidden inputs and UI
    document.getElementById('pinnedLat').value = lat;
    document.getElementById('pinnedLng').value = lng;
    document.getElementById('isValidLocation').value = valid ? '1' : '0';

    // Update UI
    updatePinResult(lat, lng, valid);
    mapInstance.setView([lat, lng], 15);

    // Show toast notification
    if (valid) {
        showUserToast('📍 Location pinned successfully within Tacloban City!', 'success');
    } else {
        showUserToast('⚠️ Location is outside Tacloban City. Please pin inside the boundary.', 'warning');
    }
}

/**
 * Update pin result display
 */
function updatePinResult(lat, lng, valid) {
    const pinResult = document.getElementById('mapPinResult');
    const pinResultText = document.getElementById('pinResultText');
    const boundaryWarning = document.getElementById('boundaryWarning');

    if (!pinResult) return;

    if (!valid) {
        pinResult.className = 'map-pin-result show invalid';
        pinResultText.textContent = '❌ Outside Tacloban City - Not Allowed';
        boundaryWarning.classList.add('show');
        document.getElementById('isValidLocation').value = '0';
        return;
    }

    boundaryWarning.classList.remove('show');
    pinResult.className = 'map-pin-result show valid';
    
    // Reverse geocode to get address
    fetch(`https://nominatim.openstreetmap.org/reverse?format=json&lat=${lat}&lon=${lng}&zoom=18&addressdetails=1`)
        .then(response => response.json())
        .then(data => {
            let address = data.display_name || `${lat.toFixed(6)}, ${lng.toFixed(6)}`;
            const parts = address.split(',');
            let shortAddress = parts.slice(0, 3).join(', ');
            if (shortAddress.length > 60) {
                shortAddress = shortAddress.substring(0, 60) + '...';
            }
            pinResultText.textContent = `📍 ${shortAddress}`;
            
            // Auto-fill address field if empty and not in-shop
            const addressField = document.getElementById('serviceAddress');
            const inShopCheck = document.getElementById('inShopCheck');
            if (addressField && !addressField.value.trim() && !inShopCheck?.checked) {
                addressField.value = shortAddress;
            }
        })
        .catch(() => {
            pinResultText.textContent = `📍 ${lat.toFixed(6)}, ${lng.toFixed(6)}`;
        });
}

/**
 * Get user's current location
 */
function getUserLocation() {
    if (!navigator.geolocation) {
        showUserToast('Geolocation is not supported by your browser.');
        return;
    }

    const btn = document.getElementById('getLocationBtn');
    if (!btn) return;
    
    btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Detecting...';
    btn.disabled = true;

    // Show a temporary pulsing dot while detecting
    const center = mapInstance.getCenter();
    const tempIcon = L.divIcon({
        className: 'custom-marker pulse',
        html: `<div style="background:#f59e0b;width:20px;height:20px;border-radius:50%;border:3px solid white;box-shadow:0 2px 10px rgba(245,158,11,0.5);"></div>`,
        iconSize: [20, 20],
        iconAnchor: [10, 10]
    });
    tempMarker = L.marker([center.lat, center.lng], {
        icon: tempIcon
    }).addTo(mapInstance);

    navigator.geolocation.getCurrentPosition(
        function(position) {
            const lat = position.coords.latitude;
            const lng = position.coords.longitude;
            
            // Remove temp marker
            if (tempMarker) {
                mapInstance.removeLayer(tempMarker);
                tempMarker = null;
            }
            
            // Always pin the location, validate after
            pinLocation(lat, lng);
            
            btn.innerHTML = '<i class="fas fa-crosshairs"></i> Use My Location';
            btn.disabled = false;
        },
        function(error) {
            let message = 'Unable to get your location. ';
            switch(error.code) {
                case error.PERMISSION_DENIED:
                    message += 'Please allow location access.';
                    break;
                case error.POSITION_UNAVAILABLE:
                    message += 'Location information is unavailable.';
                    break;
                case error.TIMEOUT:
                    message += 'Location request timed out.';
                    break;
                default:
                    message += 'Please click on the map to pin your location.';
            }
            showUserToast(message);
            btn.innerHTML = '<i class="fas fa-crosshairs"></i> Use My Location';
            btn.disabled = false;
            
            // Remove temp marker
            if (tempMarker) {
                mapInstance.removeLayer(tempMarker);
                tempMarker = null;
            }
        },
        { enableHighAccuracy: true, timeout: 10000, maximumAge: 60000 }
    );
}

/**
 * Reset the map
 */
function resetMap() {
    if (mapMarker) {
        mapInstance.removeLayer(mapMarker);
        mapMarker = null;
    }
    if (tempMarker) {
        mapInstance.removeLayer(tempMarker);
        tempMarker = null;
    }
    
    document.getElementById('pinnedLat').value = '';
    document.getElementById('pinnedLng').value = '';
    document.getElementById('isValidLocation').value = '0';
    
    const pinResult = document.getElementById('mapPinResult');
    if (pinResult) pinResult.className = 'map-pin-result';
    
    const boundaryWarning = document.getElementById('boundaryWarning');
    if (boundaryWarning) boundaryWarning.classList.remove('show');
    
    const searchInput = document.getElementById('mapSearchInput');
    if (searchInput) searchInput.value = '';
    
    mapInstance.setView(TACLOBAN_CENTER, 14);
    showUserToast('🗺️ Map has been reset');
}

/**
 * Search for a location
 */
function searchLocation() {
    const query = document.getElementById('mapSearchInput').value.trim();
    if (!query) {
        showUserToast('Please enter a location to search');
        return;
    }

    const btn = document.querySelector('.map-search-btn');
    if (btn) {
        btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i>';
        btn.disabled = true;
    }

    fetch(`https://nominatim.openstreetmap.org/search?format=json&q=${encodeURIComponent(query)}&limit=5&countrycodes=PH&bounded=1&viewbox=124.90,11.10,125.12,11.36`)
        .then(response => response.json())
        .then(data => {
            if (btn) {
                btn.innerHTML = '<i class="fas fa-arrow-right"></i>';
                btn.disabled = false;
            }

            if (data && data.length > 0) {
                let found = false;
                for (const result of data) {
                    const lat = parseFloat(result.lat);
                    const lng = parseFloat(result.lon);
                    if (isInsideTacloban(lat, lng)) {
                        pinLocation(lat, lng);
                        const addressField = document.getElementById('serviceAddress');
                        const parts = result.display_name.split(',');
                        let shortAddress = parts.slice(0, 3).join(', ');
                        if (addressField && !document.getElementById('inShopCheck')?.checked) {
                            addressField.value = shortAddress;
                        }
                        showUserToast('📍 Location found and pinned!', 'success');
                        found = true;
                        break;
                    }
                }
                if (!found) {
                    showUserToast('❌ No location found within Tacloban City. Please try a different search.', 'error');
                }
            } else {
                showUserToast('❌ Location not found. Please try a different search term.', 'error');
            }
        })
        .catch(() => {
            if (btn) {
                btn.innerHTML = '<i class="fas fa-arrow-right"></i>';
                btn.disabled = false;
            }
            showUserToast('❌ Error searching for location. Please try again.', 'error');
        });
}

/**
 * Initialize booking map (called from booking form)
 */
function initBookingMap() {
    const mapSection = document.querySelector('.map-section');
    if (mapSection) {
        mapSection.style.display = 'block';
    }
    
    if (typeof L === 'undefined') {
        const script = document.createElement('script');
        script.src = 'https://unpkg.com/leaflet@1.9.4/dist/leaflet.js';
        script.onload = function() {
            initLocationMap();
        };
        document.head.appendChild(script);
    } else {
        initLocationMap();
    }
}

// ==========================================
// SHOP CHECKOUT ADDRESS MAP (Leaflet)
// Backs the delivery-address pin picker in shop.html's checkout flow.
// shop.html calls initAddressMap(lat, lng) and locateMeOnMap() (and
// reads/writes the pickedLat/pickedLng globals it declares) but never
// defined either function itself - the comment there literally says
// "defined in user.js", so this is that promised implementation.
// ==========================================

let addressMapInstance = null;
let addressMapMarker = null;

function initAddressMap(lat, lng) {
    const container = document.getElementById('addressMap');
    if (!container) return; // not on a page with the checkout address map

    if (typeof L === 'undefined') {
        console.error('Leaflet not loaded - cannot show the address map.');
        return;
    }

    const hasPin = typeof lat === 'number' && typeof lng === 'number';
    const center = hasPin ? [lat, lng] : TACLOBAN_CENTER;

    // Calling L.map() twice on the same container throws "Map container
    // is already initialized" - re-center the existing instance instead
    // of creating a second one when the address form is reopened.
    if (addressMapInstance) {
        addressMapInstance.setView(center, 15);
        placeAddressMarker(center[0], center[1]);
        // The container is display:none until the address form is opened,
        // so Leaflet may have measured it as 0x0 at creation time - this
        // corrects the tile layout now that it's actually visible.
        setTimeout(function() { addressMapInstance.invalidateSize(); }, 100);
        return;
    }

    addressMapInstance = L.map('addressMap', {
        center: center,
        zoom: 15,
        zoomControl: true
    });

    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        attribution: '© OpenStreetMap contributors',
        maxZoom: 19
    }).addTo(addressMapInstance);

    // Visual reference only, same as the booking map - the shop's delivery
    // address picker doesn't reject pins outside the city (customers may
    // legitimately want delivery elsewhere), so this shows the boundary
    // without blocking anything.
    loadTaclobanBoundary().then(function() {
        if (TACLOBAN_BOUNDARY_GEOJSON && addressMapInstance) {
            L.geoJSON(TACLOBAN_BOUNDARY_GEOJSON, {
                style: {
                    color: '#2563eb',
                    weight: 1.5,
                    opacity: 0.6,
                    fillColor: '#2563eb',
                    fillOpacity: 0.03,
                    smoothFactor: 1
                }
            }).addTo(addressMapInstance);
        }
    });

    placeAddressMarker(center[0], center[1]);

    addressMapInstance.on('click', function(e) {
        placeAddressMarker(e.latlng.lat, e.latlng.lng);
    });

    setTimeout(function() { addressMapInstance.invalidateSize(); }, 100);
}

function placeAddressMarker(lat, lng) {
    pickedLat = lat;
    pickedLng = lng;

    const coordsEl = document.getElementById('addressCoords');
    if (coordsEl) {
        coordsEl.innerHTML = '<i class="fas fa-map-pin"></i> <span>Pinned: ' + lat.toFixed(6) + ', ' + lng.toFixed(6) + '</span>';
    }

    if (addressMapMarker) {
        addressMapMarker.setLatLng([lat, lng]);
    } else {
        addressMapMarker = L.marker([lat, lng], { draggable: true }).addTo(addressMapInstance);
        addressMapMarker.on('dragend', function() {
            const pos = addressMapMarker.getLatLng();
            placeAddressMarker(pos.lat, pos.lng);
        });
    }
}

function locateMeOnMap() {
    const btn = document.getElementById('locateMeBtn');
    if (!navigator.geolocation) {
        if (typeof showUserToast === 'function') {
            showUserToast('Your browser does not support geolocation.', 'error');
        }
        return;
    }

    if (btn) {
        btn.disabled = true;
        btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Locating...';
    }

    navigator.geolocation.getCurrentPosition(
        function(position) {
            const lat = position.coords.latitude;
            const lng = position.coords.longitude;
            if (addressMapInstance) {
                addressMapInstance.setView([lat, lng], 16);
            }
            placeAddressMarker(lat, lng);
            if (btn) {
                btn.disabled = false;
                btn.innerHTML = '<i class="fas fa-crosshairs"></i> Use My Location';
            }
            if (typeof showUserToast === 'function') {
                showUserToast('Location found - drag the pin to fine-tune it.', 'success');
            }
        },
        function() {
            if (btn) {
                btn.disabled = false;
                btn.innerHTML = '<i class="fas fa-crosshairs"></i> Use My Location';
            }
            if (typeof showUserToast === 'function') {
                showUserToast('Could not get your location. Please pin it manually on the map.', 'error');
            }
        }
    );
}

// Make functions globally accessible
window.isInsideTacloban = isInsideTacloban;
window.pinLocation = pinLocation;
window.getUserLocation = getUserLocation;
window.resetMap = resetMap;
window.searchLocation = searchLocation;
window.initBookingMap = initBookingMap;
window.initLocationMap = initLocationMap;

console.log('✅ Map functions loaded successfully');

// ==========================================
// ADMIN SHORTCUT - Ctrl + Shift + L (Hidden)
// ==========================================

/**
 * Setup admin shortcut for user pages
 * No visual indicator shown anywhere
 */
function setupAdminShortcut() {
    document.addEventListener('keydown', function(e) {
        // Check for Ctrl + Shift + L
        if (e.ctrlKey && e.shiftKey && (e.key === 'l' || e.key === 'L')) {
            e.preventDefault();
            
            // Check if we're already on the admin login page
            const currentPath = window.location.pathname;
            if (currentPath === '/admin/login' || currentPath === '/admin/login/') {
                return;
            }
            
            // Check if user is already logged in as admin
            const isAdmin = document.body.dataset.userRole === 'admin';
            if (isAdmin) {
                window.location.href = '/admin/dashboard';
                return;
            }
            
            // Redirect silently - no toast, no visual indicator
            window.location.href = '/admin/login';
        }
    });
}

// Initialize admin shortcut when DOM is ready
document.addEventListener('DOMContentLoaded', function() {
    setupAdminShortcut();
});

// ==========================================
// TIME SLOT BOOKING FUNCTIONS
// ==========================================

// Store booked slots (in a real app, this would come from the server)
let bookedSlots = {};

/**
 * Fetch booked slots from the server
 */
function fetchBookedSlots() {
    // This would be an API call in a real app
    // For demo, we'll use simulated data
    const today = new Date().toISOString().split('T')[0];
    const tomorrow = new Date();
    tomorrow.setDate(tomorrow.getDate() + 1);
    const tomorrowStr = tomorrow.toISOString().split('T')[0];
    const dayAfter = new Date();
    dayAfter.setDate(dayAfter.getDate() + 2);
    const dayAfterStr = dayAfter.toISOString().split('T')[0];
    
    bookedSlots = {
        [today]: ['09:00', '12:00', '15:00'],
        [tomorrowStr]: ['10:00', '14:00'],
        [dayAfterStr]: ['08:00', '13:00', '17:00']
    };
    
    return bookedSlots;
}

/**
 * Check if a time slot is booked for a given date
 */
function isSlotBooked(date, time) {
    if (!date || !time) return false;
    
    // Fetch booked slots if not already fetched
    if (Object.keys(bookedSlots).length === 0) {
        fetchBookedSlots();
    }
    
    // Check if the date exists in bookedSlots
    if (bookedSlots[date]) {
        return bookedSlots[date].includes(time);
    }
    return false;
}

/**
 * Update time slot availability based on selected date
 */
function updateTimeSlots() {
    const selectedDate = document.getElementById('bookingDate')?.value;
    if (!selectedDate) return;
    
    const timeSlots = document.querySelectorAll('.user-time-slot');
    let hasAvailableSlot = false;

    timeSlots.forEach(slot => {
        // Skip lunch break slots
        if (slot.classList.contains('lunch')) {
            return;
        }

        const time = slot.dataset.time;
        const isBooked = isSlotBooked(selectedDate, time);

        // Reset classes
        slot.classList.remove('booked', 'available');

        if (isBooked) {
            slot.classList.add('booked');
            slot.innerHTML = `
                <span>${slot.querySelector('span:first-child')?.textContent || time}</span>
                <span class="user-slot-badge booked-badge">Booked</span>
            `;
        } else {
            slot.classList.add('available');
            slot.innerHTML = `
                <span>${slot.querySelector('span:first-child')?.textContent || time}</span>
                <span class="user-slot-badge available-badge">Available</span>
            `;
            hasAvailableSlot = true;
        }

        // Remove selection if slot becomes booked
        if (slot.classList.contains('selected') && isBooked) {
            slot.classList.remove('selected');
            document.getElementById('bookingTime').value = '';
        }
    });

    // Update UI to show if any slots are available
    const availabilityText = document.querySelector('.user-availability-text');
    if (availabilityText) {
        if (hasAvailableSlot) {
            availabilityText.innerHTML = `<i class="fas fa-check-circle" style="color:var(--success);"></i> Available slots found for this date`;
            availabilityText.style.color = 'var(--success)';
        } else {
            availabilityText.innerHTML = `<i class="fas fa-exclamation-circle" style="color:var(--danger);"></i> No available slots for this date. Please select another date.`;
            availabilityText.style.color = 'var(--danger)';
        }
    }
}