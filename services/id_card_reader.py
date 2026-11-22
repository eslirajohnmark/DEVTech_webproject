"""Picks a hired technician's name, birth date, ID type and ID number out of the text OCR
read from a Philippine valid ID (Technician Roster). Every value is a suggestion the admin
checks against the card before saving.

The photo never reaches the server: the admin's browser reads the printed text
(Tesseract.js, see static/js/id-scan.js) and only that text is sent here."""
import calendar
import re
from datetime import date

from services.technician_service import ID_NUMBER_RE, ID_TYPES, NAME_RE

# ID type -> words printed only on that card. Checked in order; the first hit wins.
SIGNATURES = [
    ('Passport', re.compile(r'PASAPORTE|\bPASSPORT\b|^P.PHL[A-Z<]{5}', re.M)),
    ('PhilSys National ID', re.compile(r'PHILIPPINE IDENTIFICATION|PAMBANSANG PAGKAKAKILANLAN|PHILSYS|\bPHILID\b')),
    ('UMID', re.compile(r'UNIFIED MULTI|\bUMID\b|\bCRN\b')),
    ("Driver's License", re.compile(r"DRIVER'?S LICEN[SC]E|LAND TRANSPORTATION|\bLTO\b")),
    ('PRC ID', re.compile(r'PROFESSIONAL REGULATION|\bPRC\b')),
    ('Postal ID', re.compile(r'POSTAL IDENTITY|PHILPOST|PHILIPPINE POSTAL|\bPRN\b')),
    ("Voter's ID", re.compile(r"COMMISSION ON ELECTIONS|COMELEC|VOTER'?S")),
    ('PhilHealth ID', re.compile(r'PHIL ?HEALTH|HEALTH INSURANCE')),
    ('SSS ID', re.compile(r'SOCIAL SECURITY|\bSSS\b')),
    ('TIN ID', re.compile(r'INTERNAL REVENUE|TAXPAYER|\bTIN\b')),
]

# ID type -> how its number is printed. Capture groups are joined with dashes.
NUMBER_PATTERNS = {
    'PhilSys National ID': re.compile(r'\b(\d{4})[ -]?(\d{4})[ -]?(\d{4})[ -]?(\d{4})\b'),
    "Driver's License": re.compile(r'\b([A-Z]\d{2})[ -]?(\d{2})[ -]?(\d{6})\b'),
    'UMID': re.compile(r'\b(\d{4})[ -]?(\d{7})[ -]?(\d)\b'),
    'Passport': re.compile(r'\b(P\d{7}[A-Z]|[A-Z]{2}\d{7})\b'),
    'PRC ID': re.compile(r'\b(\d{7})\b'),
    'Postal ID': re.compile(r'\b(\d{12})(?: ?([A-Z]))?\b'),
    "Voter's ID": re.compile(r'\bVIN\b[ :.]*([A-Z0-9][A-Z0-9 -]{9,30}[A-Z0-9])'),
    'SSS ID': re.compile(r'\b(\d{2})[ -]?(\d{7})[ -]?(\d)\b'),
    'PhilHealth ID': re.compile(r'\b(\d{2})[ -]?(\d{9})[ -]?(\d)\b'),
    'TIN ID': re.compile(r'\b(\d{3})[ -]?(\d{3})[ -]?(\d{3})(?:[ -]?(\d{3,5}))?\b'),
}

# Cards that print the name as "LAST, FIRST MIDDLE" / "FIRST M. LAST" without a label above it.
COMMA_NAME_TYPES = ("Driver's License", "Voter's ID", 'PhilHealth ID')
PLAIN_NAME_TYPES = ('SSS ID', 'TIN ID', 'Postal ID')

# Field labels, matched loosely: OCR often mangles small print ("APOLYIDALLASTNEME").
MIDDLE_LABEL = re.compile(r'GITNANG ?[A-Z]*|MIDD?[A-Z]{0,2}E ?(INITIAL ?)?N[A-Z]M|MIDDLE ?INITIAL')
LAST_LABEL = re.compile(r'APEL[YV]?[A-Z]?DO|L[A-Z]ST ?N[A-Z]M|SURN[A-Z]M')
GIVEN_LABEL = re.compile(r'PANGALAN|G[I1L]VEN ?N[A-Z]M|F[I1]RST ?N[A-Z]M')
BIRTH_LABEL = re.compile(r'BIRTH|KAP[A-Z]{0,2}NGANAKAN|DATE ?OF ?B|\bD\.? ?O\.? ?B\b')
MONTH = r'(JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)[A-Z]*\.?'
MONTHS = ['JAN', 'FEB', 'MAR', 'APR', 'MAY', 'JUN', 'JUL', 'AUG', 'SEP', 'OCT', 'NOV', 'DEC']

# Words that show a line is card furniture, not a person's name.
NOT_A_NAME = {'REPUBLIC', 'REPUBLIKA', 'PHILIPPINES', 'PILIPINAS', 'PHILIPPINE', 'SOCIAL', 'SECURITY', 'SYSTEM',
              'BUREAU', 'INTERNAL', 'REVENUE', 'POSTAL', 'IDENTITY', 'IDENTIFICATION', 'CARD', 'DEPARTMENT',
              'FINANCE', 'CORPORATION', 'PHILPOST', 'TAXPAYER', 'NUMBER', 'SIGNATURE', 'ADDRESS', 'DATE', 'BIRTH',
              'ISSUE', 'ISSUED', 'VALID', 'UNTIL', 'MEMBER', 'NATIONALITY', 'FILIPINO', 'CITY', 'BRGY', 'BARANGAY',
              'STREET', 'PROVINCE', 'SEX', 'MALE', 'FEMALE', 'NAME', 'OFFICE', 'COMMISSION', 'HEALTH', 'INSURANCE',
              'LICENSE', 'TRANSPORTATION', 'PURPOSE'}

LETTERS = 'A-ZÑÀ-ÖØ-Þ'
TWO_LETTERS = re.compile(f'[{LETTERS}]{{2}}')


def _lines(text):
    """Upper-cased lines with single spaces; blank lines stay so two readings line up."""
    text = (text or '').replace('’', "'").replace('‘', "'").replace('`', "'").upper()
    return [re.sub(r'[ \t]+', ' ', line).strip() for line in re.split(r'\r\n|\r|\n', text)]


def detect_type(text):
    text = '\n'.join(_lines(text))
    for id_type, pattern in SIGNATURES:
        if pattern.search(text):
            return id_type
    return None


def read(text, id_type=None, confident_text=None, today=None):
    """{id_type, full_name, birth_date (YYYY-MM-DD), id_number, warning}; None where nothing was found.
    confident_text: the same lines holding only the words OCR was sure of; names come from these,
    so background patterns read as letters don't end up in them."""
    today = today or date.today()
    lines = _lines(text)
    confident = lines if confident_text is None else _lines(confident_text)
    if len(confident) != len(lines):
        confident = lines
    joined = '\n'.join(lines)
    detected = detect_type(joined)
    chosen = id_type if id_type in ID_TYPES else None
    kind = chosen or detected
    mrz = _passport_mrz(joined, today) if kind == 'Passport' else {}
    full_name, middle_unread = _full_name(lines, confident, kind, mrz)

    warnings = []
    if chosen and detected and detected != chosen:
        warnings.append(f'This looks like a {detected}, not a {chosen}. Check the ID type.')
    if middle_unread:
        warnings.append("The middle name couldn't be read. Add it if the ID shows one.")
    return {
        'id_type': kind,
        'full_name': full_name,
        'birth_date': mrz.get('birth_date') or _birth_date(joined, today),
        'id_number': mrz.get('id_number') or (_id_number(joined, kind) if kind else None),
        'warning': ' '.join(warnings) or None,
    }


# ---- ID number ------------------------------------------------------------------------

def _id_number(text, kind):
    pattern = NUMBER_PATTERNS.get(kind)
    if not pattern:
        return None
    for candidate in (text, _fix_digits(text)):
        m = pattern.search(candidate)
        if m:
            number = re.sub(r'\s+', ' ', '-'.join(g for g in m.groups() if g).strip())
            return number if ID_NUMBER_RE.match(number) else None
    return None


def _fix_digits(text):
    """OCR reads 0 as O and 1 as I or L inside numbers; fix that in mostly-digit words."""
    def fix(m):
        word = m.group(0)
        digits = sum(c.isdigit() for c in word)
        return word.translate(str.maketrans('OIL|', '0111')) if digits / len(word) >= 0.6 else word
    return re.sub(r'[A-Z0-9|]{4,}', fix, text)


# ---- birth date ---------------------------------------------------------------------------

def _age(born, today):
    return today.year - born.year - ((today.month, today.day) < (born.month, born.day))


def _dates(text, today):
    """Every date in the text with its position, in reading order: [(position, date)]."""
    found = {}

    def add(at, year, month, day):
        if year < 100:
            year += 1900 if 2000 + year > today.year - 18 else 2000
        if not (1 <= month <= 12) or year <= 1900:
            return
        if not 1 <= day <= calendar.monthrange(year, month)[1]:
            return
        d = date(year, month, day)
        if d <= today:
            found[at] = (at, d)

    for m in re.finditer(rf'\b{MONTH}\s+(\d{{1,2}}),?\s+(\d{{4}})\b', text):
        add(m.start(), int(m.group(3)), MONTHS.index(m.group(1)) + 1, int(m.group(2)))
    for m in re.finditer(rf'\b(\d{{1,2}})\s+{MONTH},?\s+(\d{{4}}|\d{{2}})\b', text):
        add(m.start(), int(m.group(3)), MONTHS.index(m.group(2)) + 1, int(m.group(1)))
    for m in re.finditer(r'\b(\d{4})[/.-](\d{1,2})[/.-](\d{1,2})\b', text):
        add(m.start(), int(m.group(1)), int(m.group(2)), int(m.group(3)))
    for m in re.finditer(r'\b(\d{1,2})[/.-](\d{1,2})[/.-](\d{4})\b', text):
        a, b = int(m.group(1)), int(m.group(2))
        month, day = (b, a) if a > 12 else (a, b)
        add(m.start(), int(m.group(3)), month, day)
    return [found[k] for k in sorted(found)]


def _birth_date(text, today):
    dates = _dates(text, today)
    if not dates:
        return None
    for label in BIRTH_LABEL.finditer(text):
        for at, d in dates:
            if at >= label.start() and at - label.start() <= 120:
                return d.isoformat()
    adult = sorted(d for _, d in dates if 18 <= _age(d, today) <= 100)
    return adult[0].isoformat() if adult else None


# ---- name -------------------------------------------------------------------------------

def _full_name(lines, confident, kind, mrz):
    """(name in given-middle-last order, whether a middle-name label had nothing readable under it)."""
    parts = {'given': None, 'middle': None, 'last': None}
    middle_label = False
    for i, line in enumerate(lines):
        is_middle = bool(MIDDLE_LABEL.search(line))
        has_last = bool(LAST_LABEL.search(MIDDLE_LABEL.sub('', line)))
        has_given = bool(GIVEN_LABEL.search(line))
        if has_last and has_given:
            value = _value_after(lines, confident, i)
            if value is not None:
                return _valid_name(_from_comma_name(value) if ',' in value else value), False
            continue
        middle_label = middle_label or is_middle
        key = 'middle' if is_middle else ('last' if has_last else ('given' if has_given else None))
        if key and parts[key] is None:
            parts[key] = _value_after(lines, confident, i)
    if parts['given'] and parts['last']:
        name = _valid_name(' '.join(p for p in (parts['given'], parts['middle'], parts['last']) if p))
        return name, bool(name is not None and middle_label and parts['middle'] is None)
    if mrz.get('full_name'):
        return _valid_name(mrz['full_name']), False
    for line in confident:
        if kind in COMMA_NAME_TYPES and re.fullmatch(r"[A-ZÑ][A-ZÑ .'-]+, ?[A-ZÑ][A-ZÑ .'-]+", line) \
                and _looks_like_name(line):
            return _valid_name(_from_comma_name(line)), False
        if kind in PLAIN_NAME_TYPES and re.fullmatch(r"[A-ZÑ][A-ZÑ .'-]+", line) and _looks_like_name(line):
            return _valid_name(line), False
    return None, False


def _value_after(lines, confident, i):
    """The value printed for the label on line i: after a colon on the same line, otherwise on the next few lines."""
    if ':' in confident[i]:
        same = _clean_name(confident[i][confident[i].rindex(':') + 1:])
        if TWO_LETTERS.search(same):
            return same
    for j in range(i + 1, min(i + 4, len(lines))):
        if _is_label(lines[j]):
            return None
        value = _clean_name(confident[j])
        if TWO_LETTERS.search(value):
            return value
    return None


def _is_label(line):
    return any(label.search(line) for label in (LAST_LABEL, GIVEN_LABEL, MIDDLE_LABEL, BIRTH_LABEL))


def _from_comma_name(value):
    last, rest = (part.strip() for part in value.split(',', 1))
    return f'{rest} {last}'.strip()


def _looks_like_name(line):
    words = [w for w in re.split(r'[ ,]+', line.strip()) if w]
    letters = len(re.sub(r'[ ,.]', '', line))
    return 2 <= len(words) <= 6 and letters >= 6 and not ({w.strip(".'-") for w in words} & NOT_A_NAME)


def _clean_name(value):
    value = re.sub(r"[^A-ZÀ-ÖØ-Þ .,'-]", ' ', value)
    return re.sub(r'\s+', ' ', value).strip(" ,-'")


def _valid_name(name):
    name = re.sub(r'\s+', ' ', (name or '').replace(',', ' ')).strip()
    ok = len(name.split(' ')) >= 2 and len(name) <= 100 and NAME_RE.match(name)
    return name if ok else None


# ---- passport ------------------------------------------------------------------------------

def _passport_mrz(text, today):
    """The machine-readable zone at the bottom of the photo page."""
    found = {}
    for line in text.replace(' ', '').split('\n'):
        m = re.match(r'^P.PHL([A-Z]+(?:<[A-Z]+)*)<<([A-Z<]+)$', line.rstrip('<'))
        if m:
            given = m.group(2).replace('<', ' ').strip()
            found['full_name'] = f"{given} {m.group(1).replace('<', ' ')}".strip()
            continue
        m = re.match(r'^([A-Z0-9<]{9})\dPHL(\d{2})(\d{2})(\d{2})\d[MF<]', line)
        if m:
            found['id_number'] = m.group(1).rstrip('<')
            yy, month, day = int(m.group(2)), int(m.group(3)), int(m.group(4))
            year = yy + (1900 if 2000 + yy > today.year - 18 else 2000)
            if 1 <= month <= 12 and 1 <= day <= calendar.monthrange(year, month)[1]:
                found['birth_date'] = f'{year:04d}-{month:02d}-{day:02d}'
    return found
