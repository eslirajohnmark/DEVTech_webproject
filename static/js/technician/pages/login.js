/* ============================================================================
 * pages/login.js — sign-in page controller.
 * ==========================================================================*/

import * as Session from '../data/session.js';
import { $ } from '../core/dom.js';
import { API } from '../core/api.js';

function showError(msg) {
    const box = document.getElementById('loginError');
    const txt = document.getElementById('loginErrorText');
    if (box && txt) { txt.textContent = msg; box.classList.add('is-shown'); }
}

function hideError() {
    const box = document.getElementById('loginError');
    if (box) box.classList.remove('is-shown');
}

export function init() {
    const form = document.getElementById('loginForm');
    if (!form) return;

    const idInput = document.getElementById('loginId');
    const pwInput = document.getElementById('loginPassword');
    const btn     = document.getElementById('signInBtn');

    if (idInput) {
        idInput.addEventListener('input', () => {
            const p = idInput.selectionStart;
            idInput.value = idInput.value.toUpperCase();
            idInput.setSelectionRange(p, p);
        });
    }

    form.addEventListener('submit', async e => {
        e.preventDefault();
        hideError();

        const techId   = (idInput ? idInput.value : '').trim();
        const password = pwInput ? pwInput.value : '';

        if (!/^TECH-\d{4}$/.test(techId)) {
            showError('Enter your Tech ID in the format TECH-0001.');
            return;
        }
        if (!password) {
            showError('Enter your password.');
            return;
        }

        if (btn) { btn.disabled = true; btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Signing in…'; }

        const res = await API.post('/technician/api/login', {
            technician_id: techId,
            password,
        });

        if (btn) { btn.disabled = false; btn.innerHTML = '<i class="fas fa-arrow-right-to-bracket"></i> Sign In'; }

        if (res.ok) {
            Session._setCache(res.technician);
            window.location.href = res.redirect || '/technician/dashboard';
        } else {
            showError(res.reason || 'Invalid Tech ID or password.');
        }
    });
}