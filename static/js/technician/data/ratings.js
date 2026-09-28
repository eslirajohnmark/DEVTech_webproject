/* ============================================================================
 * data/ratings.js — stub. Technicians don't submit ratings.
 * ==========================================================================*/

export const all     = () => [];
export const forJob  = () => null;
export const forTech = () => [];

export function summaryFor(techId) {
    return { average: 5.0, count: 0, seededOnly: true };
}

export function submit() {
    return Promise.resolve({ ok: false, reason: 'Not available.' });
}