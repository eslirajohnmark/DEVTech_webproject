/* DEVTech — "Profile look" editor (templates/partials/profile_studio.html).
   Live preview of avatar / colour / frame / banner, photo picking with drag and
   drop, character counters and a "Surprise me" button. No inline handlers, so it
   runs under the technician portal's nonce-only CSP too. */
(function () {
    'use strict';

    var MAX_BYTES = 3 * 1024 * 1024;
    var TYPES = ['image/jpeg', 'image/png', 'image/webp', 'image/gif'];

    function initialsOf(name) {
        var parts = (name || '').trim().split(/\s+/).filter(Boolean);
        return (parts.slice(0, 2).map(function (p) { return p[0]; }).join('') || '?').toUpperCase();
    }

    function setup(root) {
        var form = root.querySelector('form');
        var q = function (sel) { return root.querySelector(sel); };
        var checked = function (name) {
            var el = form.querySelector('input[name="' + name + '"]:checked');
            return el ? el.value : '';
        };
        var fullName = root.dataset.fullName || '';
        var nameInput = q('#pfDisplayName');
        var headlineInput = q('#pfHeadline');
        var fileInput = q('[data-pf-file]');
        var fileLabel = q('[data-pf-file-label]');
        var fileLabelDefault = fileLabel ? fileLabel.textContent : '';
        var previewAvatarHost = q('[data-pf-preview-avatar]');
        var savedImg = previewAvatarHost.querySelector('img');
        var savedPhoto = savedImg ? savedImg.getAttribute('src') : '';
        var pickedPhoto = '';

        function shownName() {
            return (nameInput && nameInput.value.trim()) || fullName;
        }

        function renderAvatar() {
            var mode = checked('avatar_mode');
            var color = checked('avatar_color');
            var frame = checked('avatar_frame');
            var span = document.createElement('span');
            span.className = 'pf-avatar pf-avatar--xl pf-c-' + color + ' pf-frame--' + frame;
            span.setAttribute('role', 'img');
            span.setAttribute('aria-label', shownName());
            var photo = pickedPhoto || savedPhoto;
            if (mode === 'photo' && photo) {
                var img = document.createElement('img');
                img.src = photo;
                img.alt = '';
                span.appendChild(img);
            } else if (mode === 'icon') {
                var i = document.createElement('i');
                i.className = 'fas fa-' + (checked('avatar_icon') || 'user');
                i.setAttribute('aria-hidden', 'true');
                span.appendChild(i);
            } else {
                var t = document.createElement('span');
                t.className = 'pf-avatar-initials';
                t.textContent = initialsOf(shownName());
                span.appendChild(t);
            }
            previewAvatarHost.replaceChildren(span);

            root.querySelectorAll('[data-pf-frame-sample]').forEach(function (s) {
                s.className = s.className.replace(/pf-c-\S+/, 'pf-c-' + color);
            });
            var sample = q('[data-pf-initials-sample]');
            if (sample) sample.textContent = initialsOf(shownName());
        }

        function renderPanels() {
            var mode = checked('avatar_mode');
            root.querySelectorAll('[data-pf-panel]').forEach(function (p) {
                p.classList.toggle('is-open', p.dataset.pfPanel === mode);
            });
        }

        function renderText() {
            q('[data-pf-preview-name]').textContent = shownName();
            q('[data-pf-preview-headline]').textContent = headlineInput ? headlineInput.value.trim() : '';
            root.querySelectorAll('[data-pf-count-for]').forEach(function (c) {
                var input = document.getElementById(c.dataset.pfCountFor);
                if (input) c.textContent = input.value.length + ' / ' + input.maxLength;
            });
        }

        function renderBanner() {
            var b = q('[data-pf-preview-banner]');
            b.className = 'pf-banner pf-banner--' + checked('banner');
        }

        function renderAll() {
            renderPanels();
            renderText();
            renderAvatar();
            renderBanner();
        }

        function selectMode(mode) {
            var r = form.querySelector('input[name="avatar_mode"][value="' + mode + '"]');
            if (r) r.checked = true;
        }

        function usePhoto(file) {
            if (!file) return;
            if (TYPES.indexOf(file.type) === -1) {
                alert('Please choose a JPG, PNG, WEBP or GIF image.');
                fileInput.value = '';
                return;
            }
            if (file.size > MAX_BYTES) {
                alert('That photo is larger than 3 MB. Please choose a smaller one.');
                fileInput.value = '';
                return;
            }
            var reader = new FileReader();
            reader.onload = function () {
                pickedPhoto = reader.result;
                if (fileLabel) fileLabel.textContent = file.name;
                selectMode('photo');
                renderAll();
            };
            reader.readAsDataURL(file);
        }

        form.addEventListener('change', function (e) {
            if (e.target === fileInput) {
                usePhoto(fileInput.files[0]);
                return;
            }
            renderAll();
        });
        form.addEventListener('input', function (e) {
            if (e.target === nameInput || e.target === headlineInput) {
                renderText();
                renderAvatar();
            }
        });

        // Drag and drop onto the upload area.
        var drop = q('[data-pf-drop]');
        if (drop && fileInput) {
            ['dragenter', 'dragover'].forEach(function (ev) {
                drop.addEventListener(ev, function (e) { e.preventDefault(); drop.classList.add('is-over'); });
            });
            ['dragleave', 'drop'].forEach(function (ev) {
                drop.addEventListener(ev, function (e) { e.preventDefault(); drop.classList.remove('is-over'); });
            });
            drop.addEventListener('drop', function (e) {
                var files = e.dataTransfer && e.dataTransfer.files;
                if (!files || !files.length) return;
                try { fileInput.files = files; } catch (err) { /* older browsers: preview only */ }
                usePhoto(files[0]);
            });
        }

        form.addEventListener('submit', function (e) {
            if (checked('avatar_mode') === 'photo' && !savedPhoto && !(fileInput.files && fileInput.files.length)) {
                e.preventDefault();
                alert('Choose a photo to upload, or pick an icon or your initials instead.');
            }
        });

        form.addEventListener('reset', function () {
            pickedPhoto = '';
            if (fileLabel) fileLabel.textContent = fileLabelDefault;
            setTimeout(renderAll, 0);         // after the browser restores the fields
        });

        var dice = q('[data-pf-surprise]');
        if (dice) {
            dice.addEventListener('click', function () {
                ['avatar_color', 'avatar_frame', 'banner', 'avatar_icon'].forEach(function (name) {
                    var opts = form.querySelectorAll('input[name="' + name + '"]');
                    if (opts.length) opts[Math.floor(Math.random() * opts.length)].checked = true;
                });
                if (checked('avatar_mode') !== 'photo') selectMode(Math.random() < 0.6 ? 'icon' : 'initials');
                renderAll();
                dice.querySelector('i').animate(
                    [{ transform: 'rotate(0)' }, { transform: 'rotate(360deg)' }],
                    { duration: 450, easing: 'ease-out' });
            });
        }

        renderAll();
        if (location.hash === '#look') root.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }

    function start() {
        document.querySelectorAll('[data-pf-studio]').forEach(setup);
    }
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start);
    else start();
})();
