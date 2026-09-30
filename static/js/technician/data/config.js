/* ============================================================================
 * data/config.js — server-driven lookup tables. Loaded once per session.
 * ==========================================================================*/

import { API } from '../core/api.js';
import { emit } from '../core/bus.js';
import * as Const from '../core/constants.js';

let _cfg = null;

export async function load() {
    if (_cfg) return _cfg;
    const res = await API.get('/technician/api/config');
    if (res.ok) {
        _cfg = res.config;
        emit('config');
    }
    return _cfg || {};
}

export function get() { return _cfg || {}; }

export const deviceTypes = () =>
    (_cfg && _cfg.deviceTypes) || Const.DEVICE_TYPES.map(l => ({ label: l }));

export const accessories = () =>
    (_cfg && _cfg.accessories) || Const.ACCESSORY_OPTIONS.map(l => ({ label: l }));

export const serviceTypes = () => (_cfg && _cfg.serviceTypes) || [];

export const incidentTypes = () =>
    (_cfg && _cfg.incidentTypes) ||
    Object.keys(Const.INCIDENT_TYPES).map(k => ({
        key: k,
        label: Const.INCIDENT_TYPES[k].label,
        icon: Const.INCIDENT_TYPES[k].icon,
    }));

export const severities = () =>
    (_cfg && _cfg.incidentSeverities) ||
    Object.keys(Const.INCIDENT_SEVERITY).map(k => ({
        key: k,
        label: Const.INCIDENT_SEVERITY[k].label,
        tone: Const.INCIDENT_SEVERITY[k].tone,
    }));

export const outcomes = () => (_cfg && _cfg.outcomes) || [];
export const conditions = () => (_cfg && _cfg.conditions) || [];

export const serviceModes = () =>
    (_cfg && _cfg.serviceModes) ||
    Object.keys(Const.SERVICE_MODES).map(k => ({
        key: k,
        label: Const.SERVICE_MODES[k].label,
        icon: Const.SERVICE_MODES[k].icon,
    }));

export const statusMeta = () =>
    (_cfg && _cfg.statusMeta) || Const.STATUS_META;

export const track = () =>
    (_cfg && _cfg.track) || Const.TRACK;

export const onHoldKey = () =>
    (_cfg && _cfg.onHoldKey) || Const.ON_HOLD;