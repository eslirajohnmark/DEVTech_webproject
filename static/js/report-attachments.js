/* Service report photos: choose files, take a photo (phones), drop them, or paste
   a screenshot. Each upload goes straight to /technician/api/uploads and shows up
   with a note field (saved with the report) and a remove button. */
(function () {
    'use strict';
    const drop = document.getElementById('rpDrop');
    const list = document.getElementById('rpFiles-list');
    if (!drop || !list) return;

    const input = document.getElementById('rpFiles');
    const status = document.getElementById('rpStatus');
    const job = drop.dataset.job;
    const max = parseInt(drop.dataset.max, 10) || 12;
    const csrf = (document.querySelector('meta[name="csrf-token"]') || {}).content || '';
    const TYPES = ['image/jpeg', 'image/png', 'image/webp', 'image/gif'];
    let busy = 0;

    function say(text, isError) {
        status.textContent = text || '';
        status.classList.toggle('is-error', !!isError);
    }

    // Big phone photos are resized to at most 2000 px and saved as JPEG.
    async function shrink(file) {
        if (file.type === 'image/gif' || file.size < 1.5 * 1024 * 1024 || !window.createImageBitmap) return file;
        try {
            const bmp = await createImageBitmap(file);
            const scale = Math.min(1, 2000 / Math.max(bmp.width, bmp.height));
            const canvas = document.createElement('canvas');
            canvas.width = Math.round(bmp.width * scale);
            canvas.height = Math.round(bmp.height * scale);
            canvas.getContext('2d').drawImage(bmp, 0, 0, canvas.width, canvas.height);
            const blob = await new Promise(res => canvas.toBlob(res, 'image/jpeg', 0.85));
            if (!blob) return file;
            const name = (file.name || 'photo').replace(/\.[^.]+$/, '') + '.jpg';
            return new File([blob], name, {type: 'image/jpeg'});
        } catch (e) {
            return file;
        }
    }

    function item(f) {
        const li = document.createElement('li');
        li.className = 'rp-file';
        li.dataset.id = f.id;
        const a = document.createElement('a');
        a.className = 'rp-thumb';
        a.href = f.url;
        a.target = '_blank';
        a.rel = 'noopener';
        const img = document.createElement('img');
        img.src = f.url;
        img.alt = f.originalName;
        a.append(img);
        const body = document.createElement('div');
        body.className = 'rp-file-body';
        const cap = document.createElement('input');
        cap.className = 'tech-input rp-caption';
        cap.name = 'caption_' + f.id;
        cap.setAttribute('form', 'reportForm');
        cap.maxLength = 255;
        cap.placeholder = 'What does this show? e.g. Before: cracked panel';
        cap.setAttribute('aria-label', 'Note for ' + f.originalName);
        const small = document.createElement('small');
        small.textContent = f.originalName;
        body.append(cap, small);
        const rm = document.createElement('button');
        rm.type = 'button';
        rm.className = 'tech-btn tech-btn--ghost rp-remove';
        rm.dataset.remove = f.id;
        rm.setAttribute('aria-label', 'Remove ' + f.originalName);
        rm.innerHTML = '<i class="fas fa-trash-can"></i>';
        li.append(a, body, rm);
        return li;
    }

    async function upload(files) {
        const images = [...files].filter(f => TYPES.includes(f.type));
        if (!images.length) {
            say('Only JPG, PNG, WEBP or GIF images can be attached.', true);
            return;
        }
        const room = max - list.children.length - busy;
        if (room <= 0) {
            say(`A report can have up to ${max} photos. Remove one to add another.`, true);
            return;
        }
        const batch = images.slice(0, room);
        busy += batch.length;
        say(`Uploading ${batch.length} photo${batch.length === 1 ? '' : 's'}...`);
        let done = 0, failed = '';
        for (const original of batch) {
            const file = await shrink(original);
            const form = new FormData();
            form.append('file', file, file.name || 'screenshot.png');
            form.append('ownerType', 'report');
            form.append('ownerId', '');
            form.append('jobId', job);
            try {
                const res = await fetch(drop.dataset.upload, {method: 'POST', body: form,
                    headers: {'X-CSRFToken': csrf}, credentials: 'same-origin'});
                const data = await res.json().catch(() => ({}));
                if (!res.ok || !data.ok) throw new Error(data.reason || 'Upload failed.');
                list.append(item(data.file));
                done += 1;
            } catch (e) {
                failed = e.message;
            }
            busy -= 1;
        }
        if (images.length > batch.length) failed = `Only ${max} photos fit in one report.`;
        say(failed ? `${done} added. ${failed}` : `${done} photo${done === 1 ? '' : 's'} added. Add a note to each, then save.`, !!failed);
        const first = list.lastElementChild && list.lastElementChild.querySelector('.rp-caption');
        if (done && first) first.focus();
    }

    input.addEventListener('change', () => { upload(input.files); input.value = ''; });

    ['dragenter', 'dragover'].forEach(t => drop.addEventListener(t, e => {
        e.preventDefault();
        drop.classList.add('is-over');
    }));
    ['dragleave', 'drop'].forEach(t => drop.addEventListener(t, () => drop.classList.remove('is-over')));
    drop.addEventListener('drop', e => {
        e.preventDefault();
        upload(e.dataTransfer.files);
    });

    // A screenshot pasted anywhere on the page (text pastes are left alone).
    document.addEventListener('paste', e => {
        const files = [...(e.clipboardData ? e.clipboardData.files : [])].filter(f => f.type.startsWith('image/'));
        if (!files.length) return;
        e.preventDefault();
        upload(files.map((f, i) => f.name && f.name !== 'image.png' ? f
            : new File([f], `screenshot-${new Date().toISOString().slice(0, 19).replace(/[:T]/g, '-')}${i ? '-' + i : ''}.png`, {type: f.type})));
    });

    list.addEventListener('click', async e => {
        const btn = e.target.closest('[data-remove]');
        if (!btn) return;
        btn.disabled = true;
        try {
            const res = await fetch('/technician/api/uploads/' + encodeURIComponent(btn.dataset.remove), {
                method: 'DELETE', headers: {'X-CSRFToken': csrf}, credentials: 'same-origin'});
            const data = await res.json().catch(() => ({}));
            if (!res.ok || !data.ok) throw new Error(data.reason || 'Could not remove the photo.');
            btn.closest('li').remove();
            say('Photo removed.');
        } catch (err) {
            btn.disabled = false;
            say(err.message, true);
        }
    });
})();
