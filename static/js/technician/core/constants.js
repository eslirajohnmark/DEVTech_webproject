/* ============================================================================
 * core/constants.js — enum-shaped defaults.
 *
 * Server config (/technician/api/config) overrides these at runtime.
 * These fallbacks keep the shell renderable if that call fails.
 * ==========================================================================*/

export const TRACK = ['confirmed', 'in_progress', 'completed'];
export const ON_HOLD = 'on_hold';

export const STATUS_META = {
    pending:     { label: 'Accepted',  tone: 'info',    icon: 'fa-clipboard-check' },
    confirmed:   { label: 'Confirmed', tone: 'info',    icon: 'fa-clipboard-check' },
    in_progress: { label: 'On Repair', tone: 'warn',    icon: 'fa-screwdriver-wrench' },
    completed:   { label: 'Ready',     tone: 'ok',      icon: 'fa-box-open' },
    cancelled:   { label: 'Cancelled', tone: 'danger',  icon: 'fa-circle-xmark' },
    on_hold:     { label: 'On Hold',   tone: 'danger',  icon: 'fa-pause' },
};

export const SERVICE_MODES = {
    in_shop:      { label: 'In-Shop',      icon: 'fa-store' },
    home_service: { label: 'Home Service', icon: 'fa-house-chimney' },
};

export const DEVICE_TYPES = ['Laptop', 'Desktop', 'Tablet', 'Printer', 'Other'];

export const ACCESSORY_OPTIONS = [
    'Charger / Adapter', 'Power Cable', 'Battery', 'Carrying Bag',
    'Mouse', 'Keyboard', 'External Drive', 'Manual / Box',
];

export const INCIDENT_TYPES = {
    safety:     { label: 'Safety Concern',    icon: 'fa-shield-halved' },
    electrical: { label: 'Electrical Hazard', icon: 'fa-bolt' },
    animal:     { label: 'Aggressive Animal', icon: 'fa-dog' },
    access:     { label: 'Cannot Access',     icon: 'fa-door-closed' },
    customer:   { label: 'Customer Dispute',  icon: 'fa-user-xmark' },
    other:      { label: 'Other',             icon: 'fa-circle-question' },
};

export const INCIDENT_SEVERITY = {
    low:      { label: 'Low',      tone: 'ok' },
    medium:   { label: 'Medium',   tone: 'warn' },
    high:     { label: 'High',     tone: 'danger' },
    critical: { label: 'Critical', tone: 'danger' },
};

export const TACLOBAN_CENTER = [11.2444, 125.0039];