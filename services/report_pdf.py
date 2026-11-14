"""A technician's service report as a PDF for the admin: the job, the findings,
the work done, the outcome, approved extra work and the attached photos.

Built with fpdf2's core Helvetica font, so text is reduced to Latin-1 (the peso
sign is written as PHP)."""
import io
from datetime import datetime

from fpdf import FPDF
from PIL import Image

INK = (15, 30, 61)
MUTED = (106, 119, 146)
BLUE = (37, 99, 235)
LINE = (221, 228, 241)
WASH = (238, 243, 252)

OUTCOMES = {'fixed': 'Fixed', 'partial': 'Partially fixed', 'not_repairable': 'Not repairable',
            'for_parts': 'Awaiting parts', 'customer_declined': 'Customer declined'}

_SWAP = {'₱': 'PHP ', '‘': "'", '’': "'", '“': '"', '”': '"', '–': '-',
         '—': '-', '…': '...', '•': '-', ' ': ' ', '→': '->'}


def clean(text):
    """Text the core PDF font can draw."""
    text = str(text or '')
    for a, b in _SWAP.items():
        text = text.replace(a, b)
    return text.encode('latin-1', 'replace').decode('latin-1')


class _Doc(FPDF):
    shop = 'DEVTech Computer Services'
    ref = ''

    def header(self):
        self.set_fill_color(*INK)
        self.rect(0, 0, self.w, 22, 'F')
        self.set_xy(15, 7)
        self.set_text_color(255, 255, 255)
        self.set_font('Helvetica', 'B', 13)
        self.cell(0, 6, clean(self.shop))
        self.set_xy(15, 13)
        self.set_font('Helvetica', '', 9)
        self.set_text_color(185, 204, 255)
        self.cell(0, 5, 'Service report')
        self.set_xy(-75, 9)
        self.set_font('Helvetica', 'B', 10)
        self.set_text_color(255, 255, 255)
        self.cell(60, 6, clean(self.ref), align='R')
        self.set_y(30)

    def footer(self):
        self.set_y(-14)
        self.set_draw_color(*LINE)
        self.line(15, self.get_y(), self.w - 15, self.get_y())
        self.set_font('Helvetica', '', 8)
        self.set_text_color(*MUTED)
        self.cell(0, 8, clean(f'{self.ref}  |  page {self.page_no()} of {{nb}}'), align='C')


def _section(pdf, title, body):
    if pdf.get_y() > pdf.h - 45:
        pdf.add_page()
    pdf.ln(3)
    pdf.set_font('Helvetica', 'B', 11)
    pdf.set_text_color(*BLUE)
    pdf.cell(0, 7, clean(title), new_x='LMARGIN', new_y='NEXT')
    pdf.set_font('Helvetica', '', 10)
    pdf.set_text_color(*INK)
    pdf.multi_cell(0, 5.2, clean(body.strip() if body and body.strip() else '-'), new_x='LMARGIN', new_y='NEXT')


def _facts(pdf, rows):
    """Two-column table of label / value pairs."""
    pdf.set_draw_color(*LINE)
    half = (pdf.w - 30) / 2
    for i in range(0, len(rows), 2):
        y = pdf.get_y()
        heights = []
        for j, (label, value) in enumerate(rows[i:i + 2]):
            x = 15 + j * half
            pdf.set_xy(x, y)
            pdf.set_fill_color(*WASH)
            pdf.set_font('Helvetica', '', 8)
            pdf.set_text_color(*MUTED)
            pdf.cell(half - 2, 5, clean(label), new_x='LEFT', new_y='NEXT', fill=True)
            pdf.set_x(x)
            pdf.set_font('Helvetica', 'B', 10)
            pdf.set_text_color(*INK)
            pdf.multi_cell(half - 2, 5.5, clean(value or '-'), new_x='LEFT', new_y='NEXT')
            heights.append(pdf.get_y() - y)
        pdf.set_y(y + max(heights) + 2)


def _image_bytes(data, mime):
    """JPEG/PNG bytes fpdf can place (WebP and GIF are converted)."""
    if mime in ('image/jpeg', 'image/png'):
        return io.BytesIO(data)
    with Image.open(io.BytesIO(data)) as im:
        out = io.BytesIO()
        im.convert('RGB').save(out, 'JPEG', quality=88)
        out.seek(0)
        return out


def _photos(pdf, files):
    """files: [(data, mime, caption, name)] for images. Two per row."""
    if not files:
        return
    if pdf.get_y() > pdf.h - 90:
        pdf.add_page()
    pdf.ln(3)
    pdf.set_font('Helvetica', 'B', 11)
    pdf.set_text_color(*BLUE)
    pdf.cell(0, 7, f'Photos and screenshots ({len(files)})', new_x='LMARGIN', new_y='NEXT')
    col_w, box_h = (pdf.w - 36) / 2, 62
    for i, (data, mime, caption, name) in enumerate(files):
        if i % 2 == 0 and pdf.get_y() + box_h + 14 > pdf.h - 18:
            pdf.add_page()
        x = 15 + (i % 2) * (col_w + 6)
        y = pdf.get_y()
        try:
            img = _image_bytes(data, mime)
            with Image.open(io.BytesIO(img.getvalue())) as probe:
                w, h = probe.size
            scale = min(col_w / w, box_h / h)
            iw, ih = w * scale, h * scale
            pdf.image(img, x=x + (col_w - iw) / 2, y=y, w=iw, h=ih)
        except Exception:                                   # unreadable image: say so, keep going
            pdf.set_xy(x, y + box_h / 2)
            pdf.set_font('Helvetica', 'I', 9)
            pdf.set_text_color(*MUTED)
            pdf.cell(col_w, 5, clean(f'Could not show {name}'), align='C')
        pdf.set_xy(x, y + box_h + 1)
        pdf.set_font('Helvetica', '', 8.5)
        pdf.set_text_color(*INK)
        pdf.multi_cell(col_w, 4.3, clean(caption or name), align='C')
        if i % 2 == 1 or i == len(files) - 1:
            pdf.set_y(y + box_h + 13)
        else:
            pdf.set_y(y)


def build(report, booking, technician_name, shop_name, approvals=(), attachments=()):
    """The report as PDF bytes. attachments: [(data, mime, caption, original name)]."""
    pdf = _Doc(format='A4')
    pdf.shop = shop_name or 'DEVTech Computer Services'
    pdf.ref = f'Report {booking.booking_number}'
    pdf.set_auto_page_break(True, margin=20)
    pdf.set_margins(15, 30, 15)
    pdf.alias_nb_pages()
    pdf.add_page()

    pdf.set_font('Helvetica', 'B', 17)
    pdf.set_text_color(*INK)
    service = booking.service.name if booking.service else 'Service'
    pdf.multi_cell(0, 8, clean(service), new_x='LMARGIN', new_y='NEXT')
    pdf.set_font('Helvetica', '', 9)
    pdf.set_text_color(*MUTED)
    pdf.cell(0, 6, clean(f'Submitted {report.submitted_at or report.updated_at or ""} by {technician_name}'),
             new_x='LMARGIN', new_y='NEXT')
    pdf.ln(2)

    device = ' '.join(x for x in (booking.device_type, booking.device_brand, booking.device_model) if x)
    _facts(pdf, [
        ('Booking', booking.booking_number),
        ('Customer', booking.customer.full_name if booking.customer else '-'),
        ('Device', device or '-'),
        ('Booked for', booking.booking_date.strftime('%b %d, %Y') if booking.booking_date else '-'),
        ('Outcome', OUTCOMES.get(report.outcome, (report.outcome or '-').replace('_', ' ').title())),
        ('Time spent', f'{report.hours_spent or 0:g} hours'),
        ('Technician', technician_name),
        ('Location', 'In-shop repair' if booking.is_in_shop else (booking.address or 'Home service')),
    ])

    if booking.description and booking.description != 'No description provided':
        _section(pdf, 'What the customer reported', booking.description)
    _section(pdf, 'Diagnosis and findings', report.diagnosis)
    _section(pdf, 'Tests performed', report.tests)
    _section(pdf, 'Work performed', report.work_performed)
    if report.outcome_notes:
        _section(pdf, 'Outcome notes', report.outcome_notes)
    approved = [a for a in approvals if a.status == 'approved']
    if approved:
        _section(pdf, 'Extra work approved by the customer', '\n'.join(
            f'- {a.proposed_work or a.findings}: PHP {float(a.additional_cost or 0):,.2f}'
            + (f', about {a.extra_days} more day(s)' if a.extra_days else '') for a in approved))
    _section(pdf, 'Recommendations for the customer', report.recommendations)
    if report.photos_note:
        _section(pdf, 'Notes on the photos', report.photos_note)
    if report.admin_note:
        _section(pdf, 'Private note to the admin', report.admin_note)

    images = [a for a in attachments if a[1].startswith('image/')]
    others = [a for a in attachments if not a[1].startswith('image/')]
    _photos(pdf, images)
    if others:
        _section(pdf, 'Other attached files', '\n'.join(f'- {a[3]}' + (f': {a[2]}' if a[2] else '') for a in others))

    pdf.ln(4)
    pdf.set_font('Helvetica', 'I', 8)
    pdf.set_text_color(*MUTED)
    pdf.cell(0, 5, clean(f'Generated {datetime.utcnow():%Y-%m-%d %H:%M} UTC from the DEVTech job record.'))
    return bytes(pdf.output())
