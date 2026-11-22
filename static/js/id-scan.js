/*
 * Technician Roster: fill "Add a hired technician" from their valid ID, the same way technician
 * registration does. The photo is previewed and the QR code on a PhilSys National ID is read on this
 * device (static/js/id-autofill.js + vendor/jsQR.js). Nothing the admin typed is overwritten.
 *
 * For other IDs there is an optional fallback: read the printed text with Tesseract.js (also on this
 * device) and let DEVTech pick out the details (services/id_card_reader.py). Only that text is sent
 * to the server, never the photo.
 */
(function () {
    'use strict';

    var box = document.getElementById('trIdRead');
    var form = document.querySelector('.tr-form');
    if (!box || !form) {
        return;
    }

    var TESSERACT_URL = 'https://cdn.jsdelivr.net/npm/tesseract.js@5.1.1/dist/tesseract.min.js';
    var MIN_CONFIDENCE = 65;
    var IMAGE_TYPES = /^image\/(jpeg|png|webp)$/;
    var maxBytes = Number(box.getAttribute('data-max-bytes')) || 10 * 1024 * 1024;

    /* id-autofill.js names => this form's fields */
    var FIELDS = [
        ['fullname', 'full_name', 'full name'],
        ['dob', 'birth_date', 'date of birth'],
        ['id_type', 'id_type', 'ID type'],
        ['id_number', 'id_number', 'ID number']
    ];

    var fileInput = document.getElementById('trIdScan');
    var thumb = document.getElementById('trIdThumb');
    var docName = document.getElementById('trIdScanName');
    var note = document.getElementById('trIdScanNote');
    var ocrButton = document.getElementById('trIdOcr');
    var workerPromise = null;

    function say(kind, text) {
        note.className = 'tr-scan-note' + (kind ? ' is-' + kind : '');
        note.textContent = text || '';
        note.hidden = !text;
    }

    function resetThumb() {
        thumb.textContent = '';
        var icon = document.createElement('i');
        icon.className = 'fas fa-id-card';
        thumb.appendChild(icon);
    }

    /*
     * Put values into the form. Like registration: a value the admin typed themselves is kept;
     * an empty field, an earlier autofill or a matching value is replaced.
     * values: {full_name, birth_date, id_type, id_number}
     */
    function apply(values) {
        var filled = [];
        var kept = [];
        FIELDS.forEach(function (field) {
            var element = form.elements[field[1]];
            var value = values[field[1]];
            if (!element || element.disabled || !value) {
                return;
            }
            if (element.tagName === 'SELECT'
                && !Array.prototype.some.call(element.options, function (o) { return o.value === value; })) {
                return;
            }
            var typed = (element.value || '').trim();
            if (typed && !element.dataset.autofilled && typed.toUpperCase() !== String(value).toUpperCase()) {
                kept.push(field[2]);
                return;
            }
            element.value = value;
            element.dataset.autofilled = '1';
            element.classList.add('is-autofilled');
            filled.push(field[2]);
        });
        return { filled: filled, kept: kept };
    }

    function keptText(kept) {
        return kept.length ? ' Kept what you typed for: ' + kept.join(', ') + '.' : '';
    }

    // ---- QR code (PhilSys National ID), exactly as registration reads it ----------------

    function readQr(file) {
        ocrButton.hidden = true;
        if (!window.DevtechIdAutofill) {
            say('', '');
            ocrButton.hidden = false;
            return;
        }
        say('busy', 'Reading the QR code on the ID…');
        window.DevtechIdAutofill.read(file).then(function (result) {
            if (fileInput.files[0] !== file) {
                return;                                     // another file was picked meanwhile
            }
            if (result.status === 'filled') {
                var v = result.values;
                var outcome = apply({ full_name: v.fullname, birth_date: v.dob, id_type: v.id_type, id_number: v.id_number });
                say('ok', (outcome.filled.length
                    ? "Filled in from the ID's QR code: " + outcome.filled.join(', ') + '. Compare them with the ID before adding.'
                    : "The details already match the ID's QR code.") + keptText(outcome.kept));
            } else if (result.status === 'not-philsys') {
                say('', "This QR code isn't from a PhilSys National ID. Type the details, or read the printed text instead.");
                ocrButton.hidden = false;
            } else if (result.status === 'no-qr') {
                say('', 'No PhilSys QR code found. Read the printed text instead, type the details, or try a sharper, '
                    + 'straight-on photo.');
                ocrButton.hidden = false;
            } else {
                say('', '');
                ocrButton.hidden = false;
            }
        });
    }

    // ---- Optional fallback for other IDs: OCR of the printed text ------------------------

    function loadTesseract() {
        if (window.Tesseract) {
            return Promise.resolve();
        }
        return new Promise(function (resolve, reject) {
            var script = document.createElement('script');
            script.src = TESSERACT_URL;
            script.crossOrigin = 'anonymous';
            script.onload = resolve;
            script.onerror = reject;
            document.head.appendChild(script);
        });
    }

    function getWorker(onProgress) {
        if (!workerPromise) {
            workerPromise = loadTesseract().then(function () {
                return window.Tesseract.createWorker('eng', 1, {
                    logger: function (m) { if (workerPromise && workerPromise.onProgress) { workerPromise.onProgress(m); } }
                });
            });
            workerPromise.catch(function () { workerPromise = null; });
        }
        workerPromise.onProgress = onProgress;
        return workerPromise;
    }

    /* A grey, contrast-stretched copy, 1600 to 2400px on its long side: the size OCR reads best. */
    function prepare(file) {
        return createImageBitmap(file).then(function (bitmap) {
            var longSide = Math.max(bitmap.width, bitmap.height);
            var scale = longSide < 1600 ? 1600 / longSide : (longSide > 2400 ? 2400 / longSide : 1);
            var canvas = document.createElement('canvas');
            canvas.width = Math.round(bitmap.width * scale);
            canvas.height = Math.round(bitmap.height * scale);
            var ctx = canvas.getContext('2d');
            ctx.drawImage(bitmap, 0, 0, canvas.width, canvas.height);
            var image = ctx.getImageData(0, 0, canvas.width, canvas.height);
            var px = image.data;
            var histogram = new Uint32Array(256);
            var i;
            for (i = 0; i < px.length; i += 4) {
                px[i] = 0.299 * px[i] + 0.587 * px[i + 1] + 0.114 * px[i + 2];
                histogram[px[i]]++;
            }
            var total = px.length / 4, low = 0, high = 255, seen = 0;
            for (i = 0; i < 256; i++) {
                seen += histogram[i];
                if (seen < total * 0.01) { low = i; }
                if (seen <= total * 0.99) { high = i; }
            }
            var range = Math.max(high - low, 1);
            for (i = 0; i < px.length; i += 4) {
                px[i] = px[i + 1] = px[i + 2] = (px[i] - low) * 255 / range;
            }
            ctx.putImageData(image, 0, 0);
            return canvas;
        });
    }

    /* Every line OCR read, and the same lines holding only the words it was sure of. */
    function linesOf(data) {
        var lines = data.lines || [];
        if (!lines.length) {
            return { text: data.text || '', confident: '' };
        }
        return {
            text: lines.map(function (l) { return l.text.replace(/\s+/g, ' ').trim(); }).join('\n'),
            confident: lines.map(function (l) {
                return (l.words || []).filter(function (w) { return w.confidence >= MIN_CONFIDENCE; })
                    .map(function (w) { return w.text; }).join(' ');
            }).join('\n')
        };
    }

    function chosenType() {
        var select = form.elements.id_type;
        return select && !select.dataset.autofilled ? select.value : '';
    }

    function readPrintedText() {
        var file = fileInput.files[0];
        if (!file) {
            return;
        }
        ocrButton.disabled = true;
        say('busy', window.Tesseract ? 'Reading the printed text…'
            : 'Loading the text reader. The first time takes a few seconds…');
        var worker = getWorker(function (m) {
            if (m.status === 'recognizing text') {
                say('busy', 'Reading the printed text… ' + Math.round(m.progress * 100) + '%');
            }
        });
        Promise.all([worker, prepare(file)]).then(function (ready) {
            return ready[0].recognize(ready[1]);
        }).then(function (output) {
            var reading = linesOf(output.data);
            if (!reading.text.trim()) {
                throw new Error('No text was found on this photo.');
            }
            var csrf = form.querySelector('input[name="csrf_token"]');
            return fetch(box.getAttribute('data-action'), {
                method: 'POST',
                credentials: 'same-origin',
                headers: { 'Content-Type': 'application/json', 'Accept': 'application/json',
                           'X-CSRFToken': csrf ? csrf.value : '' },
                body: JSON.stringify({ text: reading.text, confident_text: reading.confident, id_type: chosenType() })
            }).then(function (response) {
                return response.json().catch(function () { return {}; }).then(function (body) {
                    if (!response.ok || !body.success) {
                        throw new Error(body.message || "The details couldn't be checked. Try again.");
                    }
                    return body.fields;
                });
            });
        }).then(function (fields) {
            if (fileInput.files[0] !== file) {
                return;
            }
            var outcome = apply(fields);
            if (!outcome.filled.length && !outcome.kept.length) {
                say('error', "Couldn't find the details in the printed text. Type them in, "
                    + 'or try a sharper, straight-on photo in good light.');
                return;
            }
            say('ok', (outcome.filled.length
                ? 'Filled in from the printed text: ' + outcome.filled.join(', ')
                    + '. Printed text is read less reliably than a QR code, so check each one against the ID.'
                : 'The details already match the printed text.')
                + keptText(outcome.kept) + (fields.warning ? ' ' + fields.warning : ''));
        }).catch(function (error) {
            say('error', error && error.message && !/^(Failed|Network|Load)/i.test(error.message)
                ? error.message : "The text reader couldn't load. Check the internet connection and try again.");
        }).then(function () {
            ocrButton.disabled = false;
        });
    }

    // ---- Picking a file: preview, size check, then read the QR code ------------------------

    fileInput.addEventListener('change', function () {
        var file = fileInput.files[0];
        resetThumb();
        ocrButton.hidden = true;
        docName.textContent = file ? file.name : 'Choose a photo of their ID';
        if (!file) {
            say('', '');
            return;
        }
        if (!IMAGE_TYPES.test(file.type)) {
            say('error', 'Use a JPG, PNG or WEBP photo of the ID.');
            return;
        }
        if (file.size > maxBytes) {
            say('error', 'This file is larger than ' + Math.round(maxBytes / 1048576) + ' MB.');
            return;
        }
        readQr(file);
        var reader = new FileReader();          // preview as a data: URL
        reader.onload = function () {
            if (fileInput.files[0] !== file) {
                return;
            }
            var img = document.createElement('img');
            img.src = reader.result;
            img.alt = '';
            thumb.textContent = '';
            thumb.appendChild(img);
        };
        reader.readAsDataURL(file);
    });

    ocrButton.addEventListener('click', readPrintedText);

    /* Editing an autofilled field makes it the admin's own value. */
    ['input', 'change'].forEach(function (type) {
        form.addEventListener(type, function (event) {
            var el = event.target;
            if (el === fileInput) {
                return;
            }
            if (el.dataset && el.dataset.autofilled) {
                delete el.dataset.autofilled;
                el.classList.remove('is-autofilled');
            }
        });
    });
})();
