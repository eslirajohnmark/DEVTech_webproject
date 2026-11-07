/* ==========================================================================
   DEVTech — fill the technician registration form from the QR code on a
   Philippine National ID (PhilID card or ePhilID).

   Everything happens in the browser: the photo is read here and nothing is
   sent anywhere until the technician submits the form. The server checks
   every field again, and an admin still compares the details with the ID.

   Two QR formats exist (the same ones PSA's verify.philsys.gov.ph reads):
     - PhilID card (older): JSON
         {"DateIssued", "Issuer", "subject": {"fName", "mName", "lName", "Suffix",
          "sex", "DOB": "January 01, 1990", "POB", "PCN", ...}, "alg", "signature"}
     - ePhilID (newer): 4-character prefix (e.g. "PH1:") + Base45 text of a
       COSE_Sign1 CBOR array [header, header, payload, signature]; the payload
       is a CBOR map with issuer "PH" at key 1 and the details at key 169:
         {"sb": {"fn", "mn", "ln", "sf", "s", "DOB": "1990-01-15", "POB", "PCN"}, "img", ...}
       The photo in "img" is ignored.

   Needs static/js/vendor/jsQR.js (Chrome on Windows has no built-in QR reader).
   ========================================================================== */
(function () {
    'use strict';

    // ---------- Base45 (RFC 9285) ----------
    var B45 = '0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ $%*+-./:';

    function base45Decode(text) {
        var out = [];
        for (var i = 0; i < text.length; i += 3) {
            var chunk = text.slice(i, i + 3), n = 0;
            for (var j = chunk.length - 1; j >= 0; j--) {
                var v = B45.indexOf(chunk[j]);
                if (v < 0) throw new Error('not base45');
                n = n * 45 + v;
            }
            if (chunk.length === 3) {
                if (n > 0xffff) throw new Error('not base45');
                out.push(n >> 8, n & 0xff);
            } else if (chunk.length === 2) {
                if (n > 0xff) throw new Error('not base45');
                out.push(n);
            } else {
                throw new Error('not base45');
            }
        }
        return new Uint8Array(out);
    }

    // ---------- minimal CBOR decoder (RFC 8949): what the ePhilID payload uses ----------
    function cborDecode(bytes) {
        var pos = 0;
        var view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);

        function length(info) {
            if (info < 24) return info;
            if (info === 24) return bytes[pos++];
            if (info === 25) { pos += 2; return view.getUint16(pos - 2); }
            if (info === 26) { pos += 4; return view.getUint32(pos - 4); }
            if (info === 27) { pos += 8; return view.getUint32(pos - 8) * 4294967296 + view.getUint32(pos - 4); }
            if (info === 31) return -1;                       // indefinite length
            throw new Error('bad cbor length');
        }
        function chunks(major, info, join) {
            var n = length(info);
            if (n >= 0) { var part = bytes.subarray(pos, pos + n); pos += n; return join([part]); }
            var parts = [];
            while (bytes[pos] !== 0xff) { var head = bytes[pos++]; parts.push(chunks(major, head & 31, function (p) { return p[0]; })); }
            pos++;
            return join(parts);
        }
        function item() {
            if (pos >= bytes.length) throw new Error('cbor ended early');
            var head = bytes[pos++], major = head >> 5, info = head & 31, n, i, result;
            switch (major) {
                case 0: return length(info);
                case 1: return -1 - length(info);
                case 2: return chunks(major, info, function (p) {
                    var size = p.reduce(function (s, x) { return s + x.length; }, 0), all = new Uint8Array(size), at = 0;
                    p.forEach(function (x) { all.set(x, at); at += x.length; });
                    return all;
                });
                case 3: return chunks(major, info, function (p) {
                    return p.map(function (x) { return new TextDecoder().decode(x); }).join('');
                });
                case 4:
                    n = length(info); result = [];
                    if (n < 0) { while (bytes[pos] !== 0xff) result.push(item()); pos++; }
                    else for (i = 0; i < n; i++) result.push(item());
                    return result;
                case 5:
                    n = length(info); result = {};
                    var pair = function () { var k = item(); result[String(k)] = item(); };
                    if (n < 0) { while (bytes[pos] !== 0xff) pair(); pos++; }
                    else for (i = 0; i < n; i++) pair();
                    return result;
                case 6: length(info); return item();                 // tag: keep the tagged value
                case 7:
                    if (info === 20) return false;
                    if (info === 21) return true;
                    if (info === 22 || info === 23) return null;
                    if (info === 25) { pos += 2; return view.getUint16(pos - 2); }   // half floats: not used here
                    if (info === 26) { pos += 4; return view.getFloat32(pos - 4); }
                    if (info === 27) { pos += 8; return view.getFloat64(pos - 8); }
                    return null;
            }
            throw new Error('bad cbor');
        }
        return item();
    }

    // ---------- turning QR text into form values ----------
    function titleCase(s) {
        return String(s || '').trim().toLowerCase().replace(/(^|[\s\-'.])(\S)/g, function (m, sep, ch) {
            return sep + ch.toUpperCase();
        });
    }

    function isoDate(value) {
        var s = String(value || '').trim();
        if (/^\d{4}-\d{2}-\d{2}$/.test(s)) return s;
        var d = new Date(s);                       // "January 01, 1990" on PhilID cards
        if (isNaN(d)) return '';
        return d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') + '-' + String(d.getDate()).padStart(2, '0');
    }

    function pcn(value) {
        var digits = String(value || '').replace(/\D/g, '');
        return digits.length === 16 ? digits.match(/.{4}/g).join('-') : String(value || '').trim();
    }

    function sex(value) {
        var s = String(value || '').trim().charAt(0).toUpperCase();
        return s === 'M' ? 'Male' : s === 'F' ? 'Female' : '';
    }

    function details(subject, keys) {
        var name = [keys.first, keys.middle, keys.last, keys.suffix]
            .map(function (k) { return titleCase(subject[k]); })
            .filter(Boolean).join(' ');
        return { fullname: name, dob: isoDate(subject[keys.dob]), gender: sex(subject[keys.sex]),
                 id_type: 'PhilSys National ID', id_number: pcn(subject.PCN) };
    }

    /** QR text -> {fullname, dob, gender, id_type, id_number}, or null if it isn't a PhilSys QR. */
    function parsePhilSys(text) {
        text = String(text || '').trim();
        if (text.charAt(0) === '{') {
            var legacy;
            try { legacy = JSON.parse(text); } catch (e) { return null; }
            var subject = legacy && legacy.subject;
            if (!subject || !subject.PCN) return null;
            return details(subject, { first: 'fName', middle: 'mName', last: 'lName', suffix: 'Suffix', dob: 'DOB', sex: 'sex' });
        }
        try {
            var cose = cborDecode(base45Decode(text.slice(4)));
            var claim = cborDecode(cose[2]);
            var sb = claim && claim['1'] === 'PH' && claim['169'] && claim['169'].sb;
            if (!sb || !sb.PCN) return null;
            return details(sb, { first: 'fn', middle: 'mn', last: 'ln', suffix: 'sf', dob: 'DOB', sex: 's' });
        } catch (e) {
            return null;
        }
    }

    // ---------- finding the QR code in a photo ----------
    function loadImage(file) {
        return new Promise(function (resolve, reject) {
            var reader = new FileReader();
            reader.onload = function () {
                var img = new Image();
                img.onload = function () { resolve(img); };
                img.onerror = reject;
                img.src = reader.result;            // data: URL (allowed by the page's CSP)
            };
            reader.onerror = reject;
            reader.readAsDataURL(file);
        });
    }

    /** Try a few sizes: dense ID codes read best near full size, blurry photos when smaller. */
    function findQr(img) {
        var canvas = document.createElement('canvas');
        var ctx = canvas.getContext('2d', { willReadFrequently: true });
        var longest = Math.max(img.naturalWidth, img.naturalHeight);
        var sizes = [2000, 1400, 1000, 700].filter(function (s, i) { return i === 0 || s < longest; });
        for (var i = 0; i < sizes.length; i++) {
            var scale = Math.min(1, sizes[i] / longest);
            canvas.width = Math.round(img.naturalWidth * scale);
            canvas.height = Math.round(img.naturalHeight * scale);
            ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
            var data = ctx.getImageData(0, 0, canvas.width, canvas.height);
            var code = window.jsQR(data.data, data.width, data.height,
                                   { inversionAttempts: i === sizes.length - 1 ? 'attemptBoth' : 'dontInvert' });
            if (code && code.data) return code.data;
        }
        return null;
    }

    window.DevtechIdAutofill = {
        parse: parsePhilSys,
        /** Resolves to {status: 'filled'|'not-philsys'|'no-qr'|'unsupported', values?} */
        read: function (file) {
            if (!file || !/^image\/(jpeg|png|webp)$/.test(file.type) || typeof window.jsQR !== 'function') {
                return Promise.resolve({ status: 'unsupported' });
            }
            return loadImage(file).then(function (img) {
                var text = findQr(img);
                if (!text) return { status: 'no-qr' };
                var values = parsePhilSys(text);
                return values ? { status: 'filled', values: values } : { status: 'not-philsys' };
            }, function () { return { status: 'no-qr' }; });
        }
    };
})();
