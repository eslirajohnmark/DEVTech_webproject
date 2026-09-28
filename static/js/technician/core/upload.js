/* ============================================================================
 * core/upload.js — file picker + upload + gallery rendering.
 * ==========================================================================*/

import { API } from './api.js';
import { escape } from './format.js';
import { toast } from '../shell/toast.js';

export function pickAndUpload({ ownerType, ownerId, jobId, caption, onDone }) {
    const input = document.createElement('input');
    input.type = 'file';
    input.accept = 'image/*,application/pdf';
    input.style.display = 'none';
    document.body.appendChild(input);

    input.addEventListener('change', async () => {
        if (!input.files.length) { input.remove(); return; }
        const file = input.files[0];

        if (file.size > 8 * 1024 * 1024) {
            toast('File is larger than 8 MB.', 'warn');
            input.remove();
            return;
        }

        const fd = new FormData();
        fd.append('file', file);
        fd.append('ownerType', ownerType);
        fd.append('ownerId', ownerId);
        if (jobId) fd.append('jobId', jobId);
        if (caption) fd.append('caption', caption);

        toast('Uploading ' + file.name + '...', undefined, 1800);
        const res = await API.form('/technician/api/uploads', fd);
        input.remove();

        if (!res.ok) { toast(res.reason, 'danger'); return; }
        toast('Uploaded.', 'ok');
        if (onDone) onDone(res.file);
    });

    input.click();
}

export function renderGallery(files) {
    if (!files || !files.length) {
        return '<p class="tech-hint" style="margin-top:0.6rem;">No files attached yet.</p>';
    }
    return `<div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(120px,1fr));gap:0.55rem;margin-top:0.7rem;">${
        files.map(f => {
            const inner = f.isImage
                ? `<img src="${escape(f.url)}" alt="" style="width:100%;height:100px;object-fit:cover;border-radius:6px;" />`
                : `<div style="height:100px;display:grid;place-items:center;background:var(--t-glass-3);border-radius:6px;"><i class="fas fa-file-pdf" style="font-size:1.6rem;color:var(--t-red);"></i></div>`;
            return `<figure style="margin:0;position:relative;">` +
                `<a href="${escape(f.url)}" target="_blank" rel="noopener">${inner}</a>` +
                `<button class="tech-btn tech-btn--ghost tech-btn--sm" style="position:absolute;top:4px;right:4px;padding:2px 6px;" data-delete-upload="${escape(f.id)}" title="Remove">&times;</button>` +
                `<figcaption style="font-size:0.7rem;color:var(--t-text-muted);margin-top:0.25rem;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${escape(f.originalName)}</figcaption>` +
            `</figure>`;
        }).join('')
    }</div>`;
}

export async function load(ownerType, ownerId, container) {
    const res = await API.get('/technician/api/uploads/' + ownerType + '/' + ownerId);
    if (res.ok) container.innerHTML = renderGallery(res.files);
}