/* ============================================================================
 * pages/registration.js — technician sign-up controller.
 * ==========================================================================*/

import { API } from '../core/api.js';

function showError(msg) {
    const box = document.getElementById('formError');
    const txt = document.getElementById('formErrorText');
    if (box && txt) { txt.textContent = msg; box.classList.add('is-shown'); }
}
function hideError() {
    const box = document.getElementById('formError');
    if (box) box.classList.remove('is-shown');
}
function showSuccess(msg) {
    const box = document.getElementById('formSuccess');
    const txt = document.getElementById('formSuccessText');
    if (box && txt) { txt.textContent = msg; box.classList.add('is-shown'); }
}

function strength(pw) {
    let s = 0;
    if (pw.length >= 8) s++;
    if (/[A-Z]/.test(pw)) s++;
    if (/[0-9]/.test(pw)) s++;
    if (/[^A-Za-z0-9]/.test(pw)) s++;
    return s <= 1 ? 'weak' : s === 2 || s === 3 ? 'medium' : 'strong';
}

export function init() {
    const form = document.getElementById('registerForm');
    if (!form) return;

    const pwInput = document.getElementById('regPassword');
    const meter   = document.getElementById('pwMeter');
    const label   = document.getElementById('pwLabel');

    if (pwInput && meter && label) {
        pwInput.addEventListener('input', () => {
            const pw = pwInput.value;
            if (!pw) { meter.removeAttribute('data-strength'); label.textContent = 'Enter a password'; return; }
            const s = strength(pw);
            meter.setAttribute('data-strength', s);
            label.textContent = s === 'weak' ? 'Weak password' : s === 'medium' ? 'Medium strength' : 'Strong password';
        });
    }

    form.addEventListener('submit', async e => {
        e.preventDefault();
        hideError();

        const fullName = (document.getElementById('regFullname')  || {}).value?.trim() || '';
        const email    = (document.getElementById('regEmail')     || {}).value?.trim() || '';
        const staffId  = (document.getElementById('regStaffId')   || {}).value?.trim().toUpperCase() || '';
        const gender   = (document.getElementById('regGender')    || {}).value || '';
        const dob      = (document.getElementById('regDob')       || {}).value || '';
        const password = (document.getElementById('regPassword')  || {}).value || '';
        const confirm  = (document.getElementById('regPassword2') || {}).value || '';
        const terms    = !!(document.getElementById('regTerms')   || {}).checked;

        if (fullName.length < 3)                return showError('Enter your complete name.');
        if (!/^\S+@\S+\.\S+$/.test(email))       return showError('Enter a valid email address.');
        if (!/^TECH-\d{4}$/.test(staffId))      return showError('Tech ID must look like TECH-0001.');
        if (!gender)                            return showError('Select a gender.');
        if (!dob)                               return showError('Enter your date of birth.');

        const age = Math.floor((Date.now() - new Date(dob).getTime()) / 31557600000);
        if (age < 18) return showError('You must be at least 18 years old.');

        if (password.length < 8 || !/[A-Za-z]/.test(password) || !/[0-9]/.test(password))
            return showError('Password must be 8+ chars with a letter and a number.');
        if (password !== confirm) return showError('Passwords do not match.');
        if (!terms)               return showError('Please confirm the information above is correct.');

        const btn = document.getElementById('createBtn');
        if (btn) { btn.disabled = true; btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Creating account…'; }

        const res = await API.post('/technician/api/register', {
            full_name: fullName,
            email,
            staff_id: staffId,
            gender,
            date_of_birth: dob,
            password,
        });

        if (btn) { btn.disabled = false; btn.innerHTML = '<i class="fas fa-user-plus"></i> Create Account'; }

        if (res.ok) {
            showSuccess('Account created! Redirecting…');
            setTimeout(() => { window.location.href = res.redirect || '/technician/login'; }, 800);
        } else {
            showError(res.reason || 'Registration failed.');
        }
    });
}