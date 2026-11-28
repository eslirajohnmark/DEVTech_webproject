"""Builds the two defense documents in docs/ from the real test evidence:

    docs/DEVTech_Testing_Documentation.pdf   (from docs/test-evidence/pytest-results.xml
                                              and docs/test-evidence/a11y/a11y-report.json)
    docs/DEVTech_Defense_Reviewer.pdf

Run:  .venv\\Scripts\\python docs\\build_docs.py
"""
import ast
import collections
import datetime as dt
import json
import os
import xml.etree.ElementTree as ET

from fpdf import FPDF
from fpdf.fonts import FontFace

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
EVID = os.path.join(HERE, 'test-evidence')
FONTS = r'C:\Windows\Fonts'

NAVY = (19, 36, 92)
BLUE = (37, 99, 235)
YELLOW = (250, 204, 21)
INK = (24, 30, 48)
MUTED = (96, 106, 128)
LINE = (214, 220, 232)
PASS = (21, 128, 61)
FAIL = (185, 28, 28)
WARN = (161, 98, 7)
WASH = (241, 245, 252)


class Doc(FPDF):
    def __init__(self, title):
        super().__init__(format='A4')
        self.doc_title = title
        self.set_margins(20, 20, 20)
        self.set_auto_page_break(True, 20)
        self.add_font('Body', '', os.path.join(FONTS, 'segoeui.ttf'))
        self.add_font('Body', 'B', os.path.join(FONTS, 'segoeuib.ttf'))
        self.add_font('Body', 'I', os.path.join(FONTS, 'segoeuii.ttf'))
        self.add_font('Body', 'BI', os.path.join(FONTS, 'segoeuiz.ttf'))
        self.add_font('Head', '', os.path.join(FONTS, 'georgia.ttf'))
        self.add_font('Head', 'B', os.path.join(FONTS, 'georgiab.ttf'))
        self.add_font('Mono', '', os.path.join(FONTS, 'consola.ttf'))
        self.set_title(title)
        self.set_author('DEVTech capstone team')
        self.cover = True

    def multi_cell(self, *args, **kwargs):
        kwargs.setdefault('align', 'L')          # ragged right: no stretched gaps between words
        return super().multi_cell(*args, **kwargs)

    # ---- page furniture
    def header(self):
        if self.cover or self.page_no() == 1:
            return
        self.set_font('Body', '', 8)
        self.set_text_color(*MUTED)
        self.cell(0, 6, self.doc_title, align='L')
        self.cell(0, 6, 'DEVTech Computer Repair and Services System', align='R', new_x='LMARGIN', new_y='NEXT')
        self.set_draw_color(*LINE)
        self.line(20, 27, 190, 27)
        self.ln(6)

    def footer(self):
        if self.cover or self.page_no() == 1:
            return
        self.set_y(-14)
        self.set_font('Body', '', 8)
        self.set_text_color(*MUTED)
        self.cell(0, 6, f'Page {self.page_no()}', align='C')

    # ---- blocks
    def title_page(self, kicker, title, subtitle, lines):
        self.add_page()
        self.set_fill_color(*NAVY)
        self.rect(0, 0, 210, 297, 'F')
        self.set_fill_color(*YELLOW)
        self.rect(20, 70, 34, 3, 'F')
        self.set_xy(20, 80)
        self.set_font('Body', 'B', 11)
        self.set_text_color(*YELLOW)
        self.cell(0, 8, kicker, new_x='LMARGIN', new_y='NEXT')
        self.set_font('Head', 'B', 30)
        self.set_text_color(255, 255, 255)
        self.multi_cell(170, 13, title, new_x='LMARGIN', new_y='NEXT')
        self.ln(4)
        self.set_font('Body', '', 13)
        self.set_text_color(200, 214, 245)
        self.multi_cell(160, 7, subtitle, new_x='LMARGIN', new_y='NEXT')
        self.set_xy(20, 225)
        self.set_font('Body', '', 10)
        for line in lines:
            self.cell(0, 6.5, line, new_x='LMARGIN', new_y='NEXT')
        self.cover = False

    def h1(self, text):
        self.add_page()
        self.set_font('Head', 'B', 19)
        self.set_text_color(*NAVY)
        self.multi_cell(0, 9, text, new_x='LMARGIN', new_y='NEXT')
        self.set_fill_color(*YELLOW)
        self.rect(20, self.get_y() + 1, 22, 1.6, 'F')
        self.ln(6)

    def h2(self, text):
        if self.get_y() > 245:
            self.add_page()
        self.ln(3)
        self.set_font('Head', 'B', 13)
        self.set_text_color(*NAVY)
        self.multi_cell(0, 7, text, new_x='LMARGIN', new_y='NEXT')
        self.ln(1)

    def h3(self, text):
        if self.get_y() > 255:
            self.add_page()
        self.ln(1.5)
        self.set_font('Body', 'B', 10.5)
        self.set_text_color(*INK)
        self.multi_cell(0, 6, text, new_x='LMARGIN', new_y='NEXT')

    def para(self, text, size=10, color=INK, style=''):
        self.set_font('Body', style, size)
        self.set_text_color(*color)
        self.multi_cell(0, 5.4, text, new_x='LMARGIN', new_y='NEXT')
        self.ln(1.6)

    def bullets(self, items, size=10):
        self.set_font('Body', '', size)
        self.set_text_color(*INK)
        for item in items:
            if self.get_y() > 270:
                self.add_page()
            x = self.get_x()
            self.cell(5, 5.4, '•')
            self.set_x(x + 5)
            if isinstance(item, tuple):
                # one paragraph that starts in bold, so wrapped lines line up under the text
                safe = lambda t: t.replace('**', '* *').replace('__', '_ _').replace('--', '- -')   # only doubled marks are markup
                self.multi_cell(0, 5.4, f'**{safe(item[0])}** {safe(item[1])}', markdown=True,
                                new_x='LMARGIN', new_y='NEXT')
            else:
                self.multi_cell(0, 5.4, item, new_x='LMARGIN', new_y='NEXT')
        self.ln(1.6)

    def numbered(self, items, size=10):
        self.set_font('Body', '', size)
        self.set_text_color(*INK)
        for i, item in enumerate(items, 1):
            if self.get_y() > 270:
                self.add_page()
            x = self.get_x()
            self.cell(7, 5.4, f'{i}.')
            self.set_x(x + 7)
            self.multi_cell(0, 5.4, item, new_x='LMARGIN', new_y='NEXT')
        self.ln(1.6)

    def callout(self, title, text, color=BLUE):
        if self.get_y() > 250:
            self.add_page()
        y = self.get_y()
        self.set_fill_color(*WASH)
        self.set_x(24)
        self.set_font('Body', 'B', 10)
        self.set_text_color(*color)
        start = self.get_y()
        self.multi_cell(162, 6, title, fill=True, new_x='LMARGIN', new_y='NEXT')
        self.set_x(24)
        self.set_font('Body', '', 9.5)
        self.set_text_color(*INK)
        self.multi_cell(162, 5.2, text, fill=True, new_x='LMARGIN', new_y='NEXT')
        self.set_fill_color(*color)
        self.rect(20, start, 2, self.get_y() - start, 'F')
        self.ln(3)

    def table(self, rows, widths, size=8.5, status_col=None, head=True):
        self.set_fill_color(*WASH)               # the striped rows use the current fill colour
        self.set_font('Body', '', size)
        self.set_text_color(*INK)
        self.set_draw_color(*LINE)
        style = FontFace(emphasis='BOLD', color=(255, 255, 255), fill_color=NAVY)
        with self.table(col_widths=widths, line_height=4.6, first_row_as_headings=head, headings_style=style,
                        cell_fill_color=WASH, cell_fill_mode='ROWS', text_align='LEFT', padding=1.6) as t:
            for i, row in enumerate(rows):
                r = t.row()
                for j, value in enumerate(row):
                    value = str(value)
                    if head and i and status_col is not None and j == status_col:
                        c = PASS if value.startswith(('Pass', 'Fixed', 'OK', 'Meets', 'Resolved')) or value == 'Yes' else \
                            FAIL if value.startswith(('Fail', 'Open', 'Does not')) or value == 'No' else WARN
                        r.cell(value, style=FontFace(emphasis='BOLD', color=c))
                    else:
                        r.cell(value)
        self.ln(3)


# ---------------------------------------------------------------- flow diagrams
def _text_lines(pdf, w, text, size):
    pdf.set_font('Body', '', size)
    return pdf.multi_cell(w, 3.4, text, dry_run=True, output='LINES')


def _arrow_head(pdf, x, y, direction):
    s = 1.6
    pts = {'down': [(x, y), (x - s, y - 2.6), (x + s, y - 2.6)], 'up': [(x, y), (x - s, y + 2.6), (x + s, y + 2.6)],
           'right': [(x, y), (x - 2.6, y - s), (x - 2.6, y + s)], 'left': [(x, y), (x + 2.6, y - s), (x + 2.6, y + s)]}
    pdf.polygon(pts[direction], style='F')


def _edge_label(pdf, x, y, text, align='L', w=40):
    if not text:
        return
    pdf.set_font('Body', 'I', 6.4)
    pdf.set_text_color(*MUTED)
    pdf.set_xy(x if align in ('L', 'C') else x - w, y)
    pdf.multi_cell(w, 2.8, text, align=align)


def flow_diagram(pdf, title, lanes, nodes, note=None):
    """A swimlane flowchart: one node per row, in its lane; arrows follow 'go'
    (default: the next node). Forward arrows drop into the gap below, cross over,
    then drop into the target; arrows back go round the side."""
    if pdf.get_y() > 70:
        pdf.add_page()
    pdf.h2(title)
    x0, width = 20, 170
    lane_w = width / len(lanes)
    node_w = min(52, lane_w - 8)
    gap = 6.5
    top = pdf.get_y() + 2
    # lane headers
    pdf.set_font('Body', 'B', 8.5)
    for i, name in enumerate(lanes):
        pdf.set_fill_color(*NAVY)
        pdf.set_text_color(255, 255, 255)
        pdf.set_xy(x0 + i * lane_w, top)
        pdf.cell(lane_w, 7, name, align='C', fill=True, border=0)
    y = top + 7 + 4
    boxes = []
    for n in nodes:
        lines = _text_lines(pdf, node_w - 4, n['text'], 7.3)
        h = max(9, len(lines) * 3.4 + 4) + (5 if n.get('kind') == 'decision' else 0)
        cx = x0 + n['lane'] * lane_w + lane_w / 2
        boxes.append({'x': cx - node_w / 2, 'y': y, 'w': node_w, 'h': h, 'cx': cx, 'lines': lines, **n})
        y += h + gap
    bottom = y - gap + 3
    # lane stripes
    for i in range(len(lanes)):
        pdf.set_fill_color(*(WASH if i % 2 == 0 else (250, 251, 254)))
        pdf.rect(x0 + i * lane_w, top + 7, lane_w, bottom - top - 7, 'F')
        pdf.set_draw_color(*LINE)
        pdf.line(x0 + i * lane_w, top + 7, x0 + i * lane_w, bottom)
    pdf.line(x0 + width, top + 7, x0 + width, bottom)
    pdf.line(x0, bottom, x0 + width, bottom)

    # arrows
    pdf.set_draw_color(*NAVY)
    pdf.set_fill_color(*NAVY)
    pdf.set_line_width(0.35)
    for i, a in enumerate(boxes):
        targets = a.get('go', [(i + 1, '')] if i + 1 < len(boxes) else [])
        for t, label in targets:
            b = boxes[t]
            if t > i:
                sx, sy = a['cx'], a['y'] + a['h']
                mid = sy + gap / 2
                blocked = any(m['lane'] == b['lane'] for m in boxes[i + 1:t])
                if blocked:                         # a box in the way: go round its right side
                    side = b['x'] + b['w'] + 3.5
                    ay, by = a['y'] + a['h'] / 2, b['y'] + b['h'] / 2
                    start_x = a['x'] + a['w'] if a['lane'] == b['lane'] else a['cx']
                    pdf.line(start_x, ay, side, ay)
                    pdf.line(side, ay, side, by)
                    pdf.line(side, by, b['x'] + b['w'], by)
                    _arrow_head(pdf, b['x'] + b['w'], by, 'left')
                    _edge_label(pdf, start_x + 1, ay - 3.4, label)
                    continue
                if abs(b['cx'] - sx) < 0.1:
                    pdf.line(sx, sy, sx, b['y'])
                    _edge_label(pdf, sx + 1.2, sy + 0.6, label)
                else:
                    pdf.line(sx, sy, sx, mid)
                    pdf.line(sx, mid, b['cx'], mid)
                    pdf.line(b['cx'], mid, b['cx'], b['y'])
                    # label in the middle of the crossing line, clear of a "Yes" that drops straight down
                    _edge_label(pdf, min(sx, b['cx']) + abs(b['cx'] - sx) / 2 - 18, mid - 3.2, label, 'C', 36)
                _arrow_head(pdf, b['cx'], b['y'], 'down')
            else:                                   # back to an earlier step
                ty = b['y'] + b['h'] / 2
                if a['lane'] == b['lane']:
                    side = a['x'] - 3.5
                    pdf.line(a['x'], a['y'] + a['h'] / 2, side, a['y'] + a['h'] / 2)
                    pdf.line(side, a['y'] + a['h'] / 2, side, ty)
                    pdf.line(side, ty, b['x'], ty)
                    _arrow_head(pdf, b['x'], ty, 'right')
                    # the label goes beside the decision, in the next lane (empty on this row)
                    if a['lane'] < len(lanes) - 1:
                        _edge_label(pdf, a['x'] + a['w'] + 2, a['y'] + a['h'] / 2 - 3, label, 'L', lane_w - 6)
                    else:
                        _edge_label(pdf, a['x'] - 5, a['y'] + a['h'] / 2 - 3, label, 'R', lane_w - 8)
                else:
                    edge = x0 + width - 2.5
                    sx = a['x'] + a['w']
                    pdf.line(sx, a['y'] + a['h'] / 2, edge, a['y'] + a['h'] / 2)
                    pdf.line(edge, a['y'] + a['h'] / 2, edge, ty)
                    pdf.line(edge, ty, b['x'] + b['w'], ty)
                    _arrow_head(pdf, b['x'] + b['w'], ty, 'left')
                    if b['lane'] == len(lanes) - 1:        # next to the target it would hide behind it
                        _edge_label(pdf, sx + 1.5, a['y'] + a['h'] / 2 - 3.4, label, 'L', edge - sx - 3)
                    else:
                        _edge_label(pdf, edge - 1.5, ty - 3.4, label, 'R', 60)
    pdf.set_line_width(0.2)

    # nodes
    for n in boxes:
        kind = n.get('kind', 'box')
        pdf.set_draw_color(*NAVY)
        if kind in ('start', 'end'):
            pdf.set_fill_color(*NAVY)
            pdf.rect(n['x'], n['y'], n['w'], n['h'], 'DF', round_corners=True, corner_radius=n['h'] / 2 - 0.5)
            color = (255, 255, 255)
        elif kind == 'decision':
            pdf.set_fill_color(255, 246, 204)
            pdf.set_draw_color(*WARN)
            cx, cy = n['cx'], n['y'] + n['h'] / 2
            pdf.polygon([(cx, n['y']), (n['x'] + n['w'], cy), (cx, n['y'] + n['h']), (n['x'], cy)], style='DF')
            color = INK
        else:
            pdf.set_fill_color(255, 255, 255)
            pdf.rect(n['x'], n['y'], n['w'], n['h'], 'DF', round_corners=True, corner_radius=1.6)
            color = INK
        pdf.set_text_color(*color)
        pdf.set_font('Body', 'B' if kind != 'box' else '', 7.3)
        ty = n['y'] + (n['h'] - len(n['lines']) * 3.4) / 2
        for k, line in enumerate(n['lines']):
            pdf.set_xy(n['x'] + 2, ty + k * 3.4)
            pdf.cell(n['w'] - 4, 3.4, line, align='C')
    pdf.set_xy(20, bottom + 3)
    if note:
        pdf.para(note, size=8.5, color=MUTED)


def system_overview(pdf):
    """Who uses DEVTech and what it talks to."""
    pdf.h2('Figure 1. System overview')
    top = pdf.get_y() + 2
    users = ['Customer\n(phone or computer)', 'Technician\n(phone or computer)', 'Admin / shop owner\n(computer)']
    services = ['Supabase PostgreSQL\nall records', 'Supabase Storage\nIDs, receipts, photos', 'PayMongo\nQR Ph payments, refunds',
                'Brevo / Resend\nemails', 'OpenStreetMap\nmaps and pins']

    def box(x, y, w, h, text, fill, color, bold=False):
        pdf.set_fill_color(*fill)
        pdf.set_draw_color(*NAVY)
        pdf.rect(x, y, w, h, 'DF', round_corners=True, corner_radius=2)
        pdf.set_text_color(*color)
        lines = text.split('\n')
        for k, line in enumerate(lines):
            pdf.set_font('Body', 'B' if (k == 0 or bold) else '', 8 if k == 0 else 7)
            pdf.set_xy(x, y + (h - len(lines) * 4) / 2 + k * 4)
            pdf.cell(w, 4, line, align='C')

    uw, ux = 50, [20, 80, 140]
    for x, u in zip(ux, users):
        box(x, top, uw, 14, u, WASH, INK)
    app_y = top + 34
    box(20, app_y, 170, 22, 'DEVTech web application\nPython Flask on Vercel (HTTPS)\nCustomer, technician and admin portals',
        NAVY, (255, 255, 255))
    sw, sy = 31, app_y + 44
    sx = [20 + i * (sw + 4.75) for i in range(5)]
    for x, t in zip(sx, services):
        box(x, sy, sw, 16, t, (255, 251, 230), INK)
    pdf.set_draw_color(*NAVY)
    pdf.set_fill_color(*NAVY)
    pdf.set_line_width(0.35)
    for x in ux:
        pdf.line(x + uw / 2, top + 14, x + uw / 2, app_y)
        _arrow_head(pdf, x + uw / 2, app_y, 'down')
    for x in sx:
        pdf.line(x + sw / 2, app_y + 22, x + sw / 2, sy)
        _arrow_head(pdf, x + sw / 2, sy, 'down')
    pdf.set_line_width(0.2)
    pdf.set_xy(20, sy + 20)
    pdf.para('Everyone uses a web browser; there is nothing to install. The application keeps all records in PostgreSQL, '
             'private files in Supabase Storage, takes payments through PayMongo, sends emails through Brevo or Resend, '
             'and shows maps from OpenStreetMap.', size=8.5, color=MUTED)


# FPDF has its own table(); keep ours under a different name.
Doc.data_table = Doc.table
Doc.table = FPDF.table


# ============================================================ evidence
def load_tests():
    root = ET.parse(os.path.join(EVID, 'pytest-results.xml')).getroot()
    suite = root if root.tag == 'testsuite' else root.find('testsuite')
    cases = []
    for c in root.iter('testcase'):
        status = 'Fail' if (c.find('failure') is not None or c.find('error') is not None) else \
            'Skipped' if c.find('skipped') is not None else 'Pass'
        cases.append({'file': c.get('classname').split('.')[-1], 'name': c.get('name'), 'time': float(c.get('time') or 0),
                      'status': status})
    return suite, cases


def docstring_of(test_file):
    path = os.path.join(ROOT, 'tests', test_file + '.py')
    try:
        doc = ast.get_docstring(ast.parse(open(path, encoding='utf-8').read())) or ''
    except OSError:
        return ''
    return ' '.join(doc.split())


def load_a11y():
    path = os.path.join(EVID, 'a11y', 'a11y-report.json')
    return json.load(open(path, encoding='utf-8')) if os.path.exists(path) else None


def status_of(cases, test):
    found = [c for c in cases if c['name'] == test or c['name'].startswith(test + '[')]
    if not found:
        return 'Not run'
    bad = [c for c in found if c['status'] != 'Pass']
    return 'Pass' + (f' ({len(found)} runs)' if len(found) > 1 else '') if not bad else 'Fail'


# ============================================================ testing documentation
FILE_LABELS = {
    'test_login_security': 'Sign-in security and sessions', 'test_registration_form': 'Customer registration',
    'test_paymongo': 'Online payment (PayMongo)', 'test_payments_and_ids': 'Booking fee, bills, QR, IDs, orders',
    'test_workflow_integrity': 'Booking rules and data integrity', 'test_jobs_activity_credentials': 'Technician jobs and release',
    'test_technician_verification': 'Technician registration and ID verification',
    'test_technician_workflow': 'Repair workflow (technician)', 'test_technician_auth': 'Technician sign-in',
    'test_technician_csrf': 'Technician form protection (CSRF)', 'test_technician_ownership': 'Technicians see only their jobs',
    'test_security_fixes': 'Security regressions', 'test_refunds': 'Refunds', 'test_shop_and_orders': 'Shop and orders',
    'test_rmtech_features': 'Features ported from RMTech', 'test_service_catalog': 'Service catalog',
    'test_support_chat': 'Support chat', 'test_reports_and_bot': 'Service reports and FAQ chatbot',
    'test_static_data': 'No invented data on pages', 'test_profiles': 'Profiles', 'test_city_boundary_and_shop': 'Tacloban City boundary',
    'test_troubleshooting': 'Troubleshooting assistant', 'test_message_attachments': 'Message attachments',
    'test_notifications_and_inboxes': 'Notifications and inboxes', 'test_new_features': 'Admin pages and inbox',
    'test_supabase_brevo': 'Supabase storage and Brevo email', 'test_deploy_support': 'Deployment (Vercel / Render)',
    'test_ui_fixes': 'Page fixes', 'test_admin_lists_and_evidence': 'Admin lists and evidence',
    'test_live_and_shortcuts': 'Live updates and shortcuts',
    'test_account_tables': 'Accounts (customer, technician, admin)', 'test_email': 'Email and password reset',
    'test_technician_rate_limit': 'Technician sign-in rate limit', 'test_technician_uploads': 'Technician uploads',
    'test_sidebar_badges': 'Sidebar badges',
}

CASES = [
    # id, module, scenario, input / steps, expected, test
    ('TC-01', 'Sign-in', 'Five wrong passwords pause sign-in', 'Wrong password 5 times, then the right one (customer, admin, technician)',
     'Sign-in paused 10 s; even the right password waits', 'test_five_wrong_passwords_pause_sign_in_even_with_the_right_one'),
    ('TC-02', 'Sign-in', 'The pause doubles and resets', 'Fail 5 more times after the pause; then sign in correctly',
     'Pause 10 s, then 20 s (max 15 min); counter cleared after success', 'test_the_pause_doubles_each_time_and_a_success_starts_over'),
    ('TC-03', 'Sign-in', 'Wrong password keeps the email', 'Wrong password on each portal',
     'Email/Tech ID kept, password cleared, redirect (no form resubmission on Back)', 'test_a_wrong_password_keeps_the_email_and_clears_the_password'),
    ('TC-04', 'Sessions', 'Pages not cached after sign-out', 'Sign in, sign out, request the dashboard again',
     'Account pages sent with no-store; after sign-out the dashboard redirects to sign-in', 'test_account_and_sign_in_pages_are_never_cached'),
    ('TC-05', 'Sessions', 'Idle timeout', 'No activity for 30 minutes without "Remember me"',
     'Signed out with a message; "Remember me" keeps the session', 'test_idle_sessions_end_unless_remember_me'),
    ('TC-06', 'All forms', 'Double-click protection on every page', 'Open sign-in, registration, booking, admin and technician pages',
     'busy-guard.js loaded on every page type', 'test_every_kind_of_page_stops_double_submits'),
    ('TC-07', 'Registration', 'Valid registration, both phone formats', 'Name, email, strong password; 09171234567, '
     'then (new database) +639171234567', 'Account created both times, mobile saved as +639171234567, redirect to sign-in',
     'test_registration_with_either_format_saves_one_format'),
    ('TC-08', 'Registration', 'Weak password refused', 'Password "secret123"',
     'Refused; message lists the missing capital letter and special character', 'test_a_weak_password_is_refused_at_registration'),
    ('TC-09', 'Registration', 'Email already used', 'Register with an existing account\'s email',
     'Refused; form blank: no name, email or number shown back', 'test_an_email_already_used_shows_nothing_about_the_account_or_what_was_typed'),
    ('TC-10', 'Booking fee', 'Fee paid by PayMongo QR before booking', 'Submit without paying; pay QR; submit without screenshot; submit with screenshot',
     'Refused until paid AND screenshot attached; then booking created, fee attached, balance PHP 1,400', 'test_the_fee_is_paid_by_paymongo_qr_and_proven_by_a_screenshot_before_booking'),
    ('TC-11', 'Booking fee', 'A paid fee cannot be reused by someone else', 'Another customer submits with a paid fee id',
     'Refused; no booking created', 'test_someone_else_cannot_use_my_paid_booking_fee'),
    ('TC-12', 'Booking fee', 'Leaving PayMongo\'s page returns to the form', 'Cancel on PayMongo\'s hosted page',
     'Back to the booking form with the kept-form script on the page', 'test_returning_from_paymongos_page_with_a_booking_fee_goes_back_to_the_form'),
    ('TC-13', 'Payments', 'A wrong QR amount is never confirmed', 'PayMongo reports a different amount than owed',
     'Payment stays pending; admins warned', 'test_a_wrong_qr_amount_is_never_confirmed'),
    ('TC-14', 'Payments', 'Signed webhook confirms once', 'PayMongo webhook sent twice with a valid signature',
     'Confirmed once; no CSRF token needed for the signed webhook', 'test_signed_webhook_confirms_once_and_needs_no_csrf_token'),
    ('TC-15', 'Approval', 'Booking approved only after the fee', 'Admin approves before and after the fee is confirmed',
     'Refused before; approved after', 'test_a_booking_is_approved_only_after_its_fee_is_confirmed'),
    ('TC-16', 'Billing', 'Approved extra work is added to the bill', 'Technician asks PHP 350 extra; customer approves',
     'Unpaid bill becomes PHP 1,850; bill lists the extra and the booking fee deduction', 'test_approved_extra_work_is_added_to_the_unpaid_bill'),
    ('TC-17', 'Billing', 'The bill is paid after the repair, with a screenshot', 'Pay before repair; after repair without and with a screenshot',
     'Refused before repair and without screenshot; accepted with screenshot', 'test_a_repair_bill_is_paid_after_the_repair_with_a_screenshot'),
    ('TC-18', 'Release', 'GCash: technician checks the screenshot', 'Release without payment, without the tick, then with the tick',
     'Refused until the technician confirms the screenshot; then released', 'test_gcash_job_is_released_once_the_technician_checks_the_screenshot'),
    ('TC-19', 'Release', 'C.A.R: cash confirmed before release', 'Release a cash-after-repair job without and with "cash collected"',
     'Refused without the tick; released and payment recorded with it', 'test_cash_after_repair_needs_the_cash_confirmed'),
    ('TC-20', 'Privacy', 'Other technicians cannot open a payment screenshot', 'Another technician opens the receipt URL',
     'Not found (404)', 'test_other_technicians_cannot_open_a_payment_screenshot'),
    ('TC-21', 'Booking', 'Time-slot capacity', 'Six customers book the same slot',
     'Only five bookings accepted', 'test_slot_capacity_is_enforced'),
    ('TC-22', 'Booking', 'No double booking by the same customer', 'Submit the same booking twice',
     'One booking', 'test_same_customer_cannot_double_book_a_slot'),
    ('TC-23', 'Booking', 'Invalid bookings refused', 'No terms, unknown payment, 10:30, 19:00, 200 days ahead, long device name',
     'Each refused', 'test_invalid_bookings_are_refused'),
    ('TC-24', 'Booking', 'Home service outside Tacloban refused', 'Map pin in Santa Fe',
     'Refused; no booking', 'test_home_service_outside_the_city_line_is_refused'),
    ('TC-25', 'Admin', 'Payment QR upload', 'Upload PNG, try GIF, remove',
     'PNG saved and shown to customers; GIF refused; removal works; guests cannot see it', 'test_admin_uploads_the_payment_qr_and_customers_see_it'),
    ('TC-26', 'Admin', 'Edit a whole category', 'Change prices/fees of two services; then one invalid row',
     'Both saved; with one invalid row nothing is saved', 'test_admin_edits_every_price_in_a_category_at_once'),
    ('TC-27', 'Roster', 'ID front and back required', 'Roster entry without back, without front, without address; passport',
     'Refused for IDs with a back; passport accepted without one', 'test_the_roster_needs_both_sides_of_an_id_with_a_back_and_an_address'),
    ('TC-28', 'Roster', 'Only admins open ID photos', 'Admin and customer open a roster ID photo',
     'Admin: shown, no-store, logged; customer: redirected', 'test_only_admins_open_roster_id_photos_and_each_view_is_logged'),
    ('TC-29', 'Technician', 'Registration stores a private ID', 'Register with an ID photo',
     'Account pending and inactive; ID stored privately', 'test_registration_saves_a_pending_inactive_account_with_a_private_document'),
    ('TC-30', 'Technician', 'ID details must match the roster', 'Register with a different name/birth date/ID number',
     'Refused with one neutral message', 'test_the_ids_details_must_match_the_employee_record'),
    ('TC-31', 'Technician', 'Only verified technicians get jobs', 'Assign a job to an unverified technician',
     'Refused', 'test_only_verified_technicians_can_be_assigned'),
    ('TC-32', 'Privacy', 'Location removed from photos', 'Upload a JPEG with GPS data',
     'Stored file has no location data', 'test_location_data_is_removed_from_jpeg_photos'),
    ('TC-33', 'Orders', 'Admin orders page', 'Open Admin > Shop Orders with an order being prepared',
     'Card with progress rail, items and search', 'test_admin_orders_show_progress_items_and_search'),
    ('TC-34', 'Orders', 'Customer order tracking', 'Open My Orders with an order on the way',
     'Card shows the tracker at "On the way" and the items', 'test_my_orders_cards_track_each_order'),
    ('TC-35', 'Refunds', 'Cancelling a paid booking opens a refund', 'Cancel a booking with a confirmed payment',
     'Refund opened for the paid amount', 'test_cancelling_a_paid_booking_opens_a_refund'),
    ('TC-36', 'Online refund', 'QR-paid order refunded automatically', 'Cancel an order paid by QR Ph',
     'Full refund sent through PayMongo', 'test_cancelling_a_qr_paid_order_refunds_it_in_full_automatically'),
    ('TC-37', 'Access', 'Technicians see only their own jobs', 'Another technician opens / advances a job',
     'Not shown; refused', 'test_other_tech_cannot_advance'),
    ('TC-38', 'Support', 'Customers see only their own conversations', 'Open another customer\'s support thread',
     'Refused', 'test_customers_only_see_their_own_conversations'),
    ('TC-39', 'Security', 'Names are escaped on admin pages', 'A user named <script>...',
     'Shown as text, never run', 'test_admin_users_page_escapes_user_names'),
    ('TC-40', 'Sign-in page', 'Customer sign-in layout', 'Open /login',
     'Portal layout with "Create an account"', 'test_customer_sign_in_uses_the_portal_layout'),
    ('TC-41', 'Registration', 'Invalid mobile numbers refused with a reason', '0917123, 0917123456789, 12345678901, '
     '09001234567, 0917ABC4567, 0917#123456, empty', 'Each refused: too short, too long, incorrect prefix, not a network '
     'prefix, letters, symbols, empty', 'test_invalid_numbers_are_refused_with_a_clear_reason'),
    ('TC-42', 'Registration', 'One account per mobile number', 'Register a number already saved as +639..., 09... or 639...',
     'Refused: "already registered to another account"', 'test_a_number_already_registered_is_refused_in_any_saved_format'),
    ('TC-43', 'Registration', 'Database error not shown', 'Saving the account fails inside the database',
     'Plain message; no SQL or server detail on the page', 'test_a_database_error_is_not_shown_to_the_customer'),
    ('TC-44', 'Billing', 'A bill the booking fee fully covers', 'PHP 0 bill after the repair; customer opens Transactions; '
     'technician releases', 'Says "Nothing to pay"; no pay button; QR request refused without calling PayMongo; release allowed',
     'test_a_bill_the_booking_fee_fully_covers_asks_for_nothing_and_the_device_can_be_released'),
    ('TC-45', 'Payments', 'The QR dialog always gets an answer', 'Starting the QR payment crashes on the server',
     'JSON error with a "try again" message (no endless spinner)',
     'test_the_qr_dialog_gets_an_answer_even_when_starting_the_payment_crashes'),
    ('TC-46', 'Password reset', 'Reset uses the registration password rule', 'Weak password, current password, then a strong one',
     'First two refused; strong one saved; "password was changed" email sent',
     'test_reset_needs_the_same_strong_password_as_registration_and_confirms_by_email'),
    ('TC-47', 'Email', 'A Resend refusal is explained', 'Resend answers 403 (sandbox sender)',
     'Not sent; the log says how to fix it (verify a domain)', 'test_a_resend_refusal_explains_the_sandbox_sender'),
    ('TC-48', 'Deployment', 'The database updates itself', 'Database missing a new column and a new table; open the home page',
     'Column and table added; home page loads (200); nothing to do the second time',
     'test_missing_columns_and_tables_are_added_and_the_home_page_works'),
]

BROWSER = [
    ('BT-01', 'Wrong password, Back button, sign-out, Back', 'No "Confirm Form Resubmission"; Back after sign-out shows sign-in',
     'As expected', 'Pass', 'Nov 19'),
    ('BT-02', 'Sign-in clicked three times while the server is slow', 'One request; button shows "Please wait..." and is disabled',
     'One request; disabled with "Please wait..."; usable again after the answer', 'Pass', 'Nov 20'),
    ('BT-03', 'A no-reload button clicked three times', 'One request; unlocked after the answer',
     'First run: 3 requests (bug); after the fix: 1 request', 'Pass (after fix)', 'Nov 20'),
    ('BT-04', 'Booking with the shop QR and a screenshot (no PayMongo)', 'Send stays disabled until a screenshot is attached; booking created',
     'As expected; screenshot preview was broken (bug), fixed and re-checked', 'Pass (after fix)', 'Nov 20'),
    ('BT-05', 'Transactions: View details', 'Opens at once with the right transaction',
     'Opened in under 1 s (including automation overhead)', 'Pass', 'Nov 20'),
    ('BT-06', 'Pay with GCash dialog', 'QR, amount and screenshot preview; sends', 'As expected', 'Pass', 'Nov 20'),
    ('BT-07', 'Admin Shop Orders and My Orders', 'Progress rail matches the order state',
     'Progress line ran half-way to the next step (bug); fixed and re-checked', 'Pass (after fix)', 'Nov 20'),
    ('BT-08', 'Edit a whole category (64 services)', 'All rows saved after confirming', '64 services changed', 'Pass', 'Nov 20'),
    ('BT-09', 'Technician registration with a UMID', 'Back-of-ID field marked required', 'As expected', 'Pass', 'Nov 20'),
    ('BT-10', 'Booking fee via PayMongo QR, then screenshot, then submit (simulated PayMongo)',
     'Receipt step opens only after paying; booking created', 'Run interrupted twice (browser crash, session ended)', 'Not completed', 'Nov 20'),
    ('BT-11', 'Form kept after an abandoned / failed fee payment', 'All fields restored after a reload; draft cleared after booking',
     'Run interrupted (session ended)', 'Not completed', 'Nov 20'),
    ('BT-13', 'Transactions: Pay with GCash through PayMongo, then the receipt', 'QR opens; after paying the receipt step '
     'opens; screenshot saved', 'First runs: page reloaded before the receipt step (bug B-12); after the fix: as expected',
     'Pass (after fix)', 'Nov 23'),
    ('BT-14', 'Registration: mobile number field at 1280 px and 375 px (local server)', 'Right message while typing for '
     'each example; a wrong number is not submitted; no script errors',
     'All 7 examples gave the right message; 0 requests sent for a wrong number; no errors; no sideways scroll. The '
     'screenshot showed the red error border replaced by the blue focus border (B-19): CSS fixed, not re-checked',
     'Pass (fix not re-checked)', 'Nov 25'),
    ('BT-15', 'Smoke check of the live Vercel site: /, /login, /forgot-password, /healthz', 'Every page 200; database connected',
     '1st check: home page 500 (B-16), other pages 200. Later check: / and /login 500, /healthz 503 "database '
     'unreachable" (database password changed, Vercel not updated). Re-check Nov 25, 14:22 UTC: all pages 200, '
     'database connected (section 4.2)', 'Pass (after fix)', 'Nov 23-25'),
    ('BT-16', 'Real email through Resend (command line)', 'Accepted for Resend\'s test inbox; a clear reason when refused',
     'Accepted (id returned). Refused for example.com with 422, and our fix hint blamed the wrong setting (B-18); fixed',
     'Pass (after fix)', 'Nov 23'),
    ('BT-17', 'Real PayMongo test-mode QR code (API, no payment)', 'QR created for small amounts',
     'QR created in about 1 s for PHP 5, 19.99 and 20; PHP 0 refused before calling PayMongo (explains B-13)', 'Pass', 'Nov 23'),
    ('BT-12', 'Accessibility spot check of 13 pages', 'WCAG 2.1 AA contrast, labels, names, reflow', 'See section 9', 'See section 9', 'Nov 22'),
]

LIVE_URL = 'https://devtech-taclobancity.vercel.app'
LIVE_WHEN = 'Nov 25, 2026, 14:22 UTC (10:22 PM Philippine time)'
# Checks of the deployed website. Read-only: pages were opened, nothing was submitted.
LIVE = [
    ('LT-01', 'Public pages answer', 'Home, sign-in (3 portals), register (customer, technician), forgot password, '
     'CSS and JS files', 'Every page 200', 'All 200', 'Pass'),
    ('LT-02', 'Health check', '/healthz', 'Database connected', '{"database":"connected","status":"ok"}', 'Pass'),
    ('LT-03', 'Unknown page', '/this-page-does-not-exist', '404 page, no crash', '404', 'Pass'),
    ('LT-04', 'Protected pages while signed out', 'Customer, admin and technician dashboards',
     'Sent to that portal\'s sign-in page', '302 to /login, /admin/login, /technician/login', 'Pass'),
    ('LT-05', 'HTTPS only', 'http:// address; Strict-Transport-Security header',
     'Redirect to https; browsers told to use HTTPS', '308 to https; HSTS 1 year with subdomains', 'Pass'),
    ('LT-06', 'Security headers and cookie', 'Headers of the sign-in page',
     'CSP, nosniff, frame protection, no-store; cookie Secure, HttpOnly, SameSite',
     'All present: CSP, nosniff, X-Frame-Options SAMEORIGIN, Referrer-Policy, no-store; cookie Secure, HttpOnly, '
     'SameSite=Lax', 'Pass'),
    ('LT-07', 'Form sent without its CSRF token', 'Sign-in form posted from outside the site', 'Refused, not processed',
     'Redirected back with "Your form session expired"; nothing processed', 'Pass'),
    ('LT-08', 'Pages in a real browser', '7 pages in Microsoft Edge at 1280 px (desktop) and 375 px (phone)',
     'No script errors, no failed files, no sideways scrolling', '14 of 14 loads clean', 'Pass'),
    ('LT-09', 'Basic accessibility on the live pages', 'Same 14 loads', 'Language set; images have alt text; '
     'fields have labels', 'lang="en" everywhere; 0 images without alt; 0 unlabeled fields (contrast not re-measured)', 'Pass'),
    ('LT-10', 'Live mobile number field', 'Typed 09171234567, +639171234567, 0917123456789, 12345678901, 0917ABC4567 '
     '(never submitted)', 'Valid, valid, too long, incorrect prefix, letters', 'Exactly as expected', 'Pass'),
    ('LT-11', 'The deployed version is the latest', 'Register and forgot-password pages', 'New phone check and email reset '
     'present', 'Both present ("Send reset link" shown)', 'Pass'),
    ('LT-12', 'Response time', 'Home page timed 4 times; sign-in twice', 'Server answer under about 3 s',
     'Home 6.1 to 6.5 s every time (11 to 12 s full load in the browser); sign-in 1.7 to 2.0 s', 'Fail'),
]

FIXED = [
    ('B-01', 'Transactions "View Details" stayed on "Loading..." and always read the first transaction (script error).',
     'High', 'Details are now written into the page; opens instantly.', 'Fixed'),
    ('B-02', 'Payment screenshot preview showed a broken image (the page\'s security policy blocks blob: images).',
     'Low', 'Preview uses a data: image.', 'Fixed'),
    ('B-03', 'Deleting a technician account left the photo of the back of their ID on the server.',
     'High (privacy)', 'Both sides are deleted.', 'Fixed'),
    ('B-04', 'The booking saved the payment screenshot while holding the time-slot lock ("database is locked" seen in the demo).',
     'Medium', 'The screenshot is saved before the lock and removed if the booking fails.', 'Fixed'),
    ('B-05', 'Order progress lines were drawn half-way toward a step not yet reached.', 'Low', 'Each line now ends at its own step.', 'Fixed'),
    ('B-06', 'Back after signing out could show the dashboard: a background request revived the old session.',
     'High (security)', 'Only real page visits count as activity.', 'Fixed'),
    ('B-07', '"Confirm Form Resubmission" after a failed sign-in and Back.', 'Medium', 'Post/Redirect/Get on every sign-in.', 'Fixed'),
    ('B-08', 'A double click could send a form twice (duplicate booking/order risk).', 'High', 'busy-guard.js on every page.', 'Fixed'),
    ('B-09', 'Repeated click events still reached a button that was already waiting.', 'Medium', 'Clicks on a waiting button are ignored.', 'Fixed'),
    ('B-10', 'Registering with an existing email re-showed what was typed.', 'Medium (privacy)', 'The form comes back blank.', 'Fixed'),
    ('B-11', 'Category editor inputs were hard to read on the dark admin theme.', 'Low', 'Dark input style.', 'Fixed'),
    ('B-12', 'The automatic refresh did not notice the QR payment dialog was open, so a confirmed payment reloaded the page '
             'and skipped the receipt step (Transactions and booking fee).', 'High',
     'Any pop-up inside a fixed layer now counts as open; the refresh waits.', 'Fixed'),
    ('B-13', 'A repair bill fully covered by the booking fee (PHP 0) still showed "Pay with GCash". PayMongo cannot make '
             'a PHP 0 QR, the server error was not caught, the dialog spun forever, and the technician could not release '
             'the device.', 'High', '"Nothing to pay" on the page; release settles it; the QR route always answers.', 'Fixed'),
    ('B-14', '"Pay with card or e-wallet instead" sent the form to the Transactions page itself (405 Method Not Allowed) '
             'while the QR was still loading.', 'Medium', 'The button gets its address when the dialog opens.', 'Fixed'),
    ('B-15', 'The QR dialog had no time limit and ignored non-JSON answers, so a slow or failed request kept "Creating your '
             'QR code..." on screen.', 'Medium', '45 s limit; clear message and "Try again" for every failure.', 'Fixed'),
    ('B-16', 'Live site: home page 500. The production database (Supabase) never received the new columns and tables, '
             'because Vercel does not run the database update.', 'High',
     'The site adds missing tables/columns on its first request; SQL script for Supabase.', 'Fixed (re-checked live)'),
    ('B-17', 'Password reset accepted weaker passwords than registration (found while reviewing the reset code).',
     'Medium (security)', 'Same rule and live checklist as registration; current password refused.', 'Fixed'),
    ('B-18', 'When Resend refused an address (422), the fix hint wrongly blamed the sender setting.', 'Low',
     'The hint now names the field Resend refused.', 'Fixed'),
    ('B-19', 'Mobile number field: while focused, the blue focus border hid the red error border.', 'Low',
     'Error and success borders kept on focus.', 'Fixed (not re-checked)'),
]

OPEN = [
    ('O-01', 'Times on the customer Transactions page are shown in UTC, 8 hours behind Philippine time (a 2:16 PM payment shows 06:16 AM).',
     'Medium', 'Show Philippine time, as My Orders already does.', 'Open'),
    ('O-02', 'The "kept form" (BT-11) and PayMongo fee-first browser runs (BT-10) were not completed.',
     'Medium', 'Re-run both before the defense. The server side is covered by TC-10 to TC-12.', 'Open'),
    ('O-03', 'PayMongo: real test-mode QR codes were created (BT-17), but no test-mode payment was completed and no live '
             'webhook was received; the full flow was tested against a simulated PayMongo.',
     'Medium', 'Make one test-mode QR payment with the PayMongo test key and check the webhook.', 'Open'),
    ('O-04', 'A payment screenshot can be an edited image.', 'Medium',
     'By design the admin or technician checks the money in the shop\'s GCash account; keep this as a written policy.', 'Accepted risk'),
    ('O-05', 'No load test, no real phone test, no screen-reader test and no user acceptance test with real users.',
     'Medium', 'Run the UAT checklist in Appendix B with classmates or the panel.', 'Open'),
    ('O-06', 'The demo server (SQLite) reported "database is locked" under simultaneous requests.',
     'Low', 'Production uses PostgreSQL (Supabase), which allows concurrent writes; not load-tested there.', 'Monitor'),
    ('O-07', 'WCAG 2.1 AA contrast: 71 text styles on 10 of 13 pages are below 4.5:1 (mostly small grey hints, badges and '
             'muted labels on the customer and admin pages). The sign-in pages and the home page pass.',
     'Medium', 'Darken the muted text colours (customer) and lighten them (admin dark theme) to reach 4.5:1; re-run the scan.',
     'Open'),
    ('O-08', 'Admin Services & Prices: the per-service edit forms have labels that are not linked to their fields '
             '(1,005 fields counted), so a screen reader cannot announce what each field is.',
     'Medium', 'Give each field an id and the label a matching "for" (or an aria-label); re-run the scan.', 'Open'),
    ('O-09', 'Live site was down (BT-15): home and sign-in pages 500, database unreachable.', 'High',
     'Done: new database password in Vercel, self-updating database code deployed. Re-checked on Nov 25 (LT-01, LT-02).',
     'Resolved'),
    ('O-12', 'The live server runs in Washington DC (Vercel region iad1) while the database is in Singapore, so every '
             'database query crosses the Pacific: the home page takes about 6 s to answer (LT-12).', 'Medium',
     'Set the Vercel Function Region to Singapore (sin1), redeploy, and time the pages again.', 'Open'),
    ('O-10', 'Resend still uses its sandbox sender, which only delivers to the Resend account owner, so most customers '
             'would not receive reset emails.', 'Medium', 'Verify a domain in Resend and set MAIL_FROM to it.', 'Open'),
    ('O-11', 'The Profile page lets a customer change the mobile number without the new Philippine mobile check; the '
             'technician forms use their own rule.', 'Low', 'Use services/ph_phone.py there too.', 'Open'),
]


# Every test run that failed during development, as it happened.
FAILED_RUNS = [
    ('R-01', 'Nov 19', 'Full suite after the sign-in security change', '73 failed',
     'Real bug: a decorator was attached to the wrong function, so every page raised TypeError '
     '"_end_session() missing 1 required positional argument".', 'Code fixed; all passed'),
    ('R-02', 'Nov 19', 'Technician app sign-in lockout test', '1 failed',
     'Real bug: when sign-in was paused, the technician app received an HTML "429 Too Many Requests" page instead '
     'of a JSON answer (the 5-per-minute rate limit was hit first).', 'Limit raised to 20/min; passed'),
    ('R-03', 'Nov 20', 'Full suite after the booking-fee, payment and ID-photo changes', '32 failed, 358 passed',
     'Tests written for the old rules (booking without a fee screenshot, registration without an address or the back '
     'of the ID, booking balance paid by QR Ph, release after admin confirmation). They failed because the '
     'requirements changed, not because of a defect.', 'Tests updated to the new rules'),
    ('R-04', 'Nov 20', 'Re-run of the files that failed in R-03', '6 failed, 181 passed',
     '5 tests still expected old behaviour or had no admin account in their set-up. 1 real bug: deleting a technician '
     'account left the photo of the back of their ID on the server.', 'Bug fixed; tests updated; passed'),
    ('R-05', 'Nov 20', 'New payment and ID tests, first run', '1 failed, 12 passed',
     'Test set-up error: an extra-work request was created without a technician (database NOT NULL rule).',
     'Test fixed; passed'),
    ('R-06', 'Nov 22', 'New registration test (email already used)', '1 failed',
     'Test mistake: the phone number it looked for also appears in the field\'s example text.',
     'Test fixed; passed'),
    ('R-07', 'Nov 22', 'Live-update tests after the sidebar badge change', '2 failed, 34 passed',
     'The tests built the live-update request without the new badge value, so the server answered at once '
     'instead of waiting.', 'Test helper updated; passed'),
    ('R-08', 'Nov 22', 'New sidebar badge tests, first runs', '3 failed, 14 passed; then 1 failed, 4 passed',
     '2 test mistakes (records dated in the future; a wrong assumption about the Notifications page). 1 real bug: '
     'new jobs without a recorded assignment time never showed in the technician\'s My Jobs badge.',
     'Bug fixed; tests fixed; passed'),
    ('R-09', 'Nov 23', 'Manual test by the developer: Transactions > Pay with GCash on the local server',
     'Failed', 'Real bug: the dialog stayed on "Creating your QR code..." and the card button showed 405 Method Not Allowed. '
     'Cause: a PHP 0 bill was offered for payment (B-13, B-14, B-15).', 'Bugs fixed; 2 tests added'),
    ('R-10', 'Nov 23-25', 'Smoke check of the live site (BT-15)', 'Failed (500, then 503)',
     'Real bug: the production database lacked the new columns (B-16). Later the database password was changed '
     'without updating Vercel, so the site could not reach its database (configuration, not code).',
     'Fixed and deployed; live re-check passed on Nov 25 (section 4.2)'),
    ('R-11', 'Nov 25', 'Registration tests after the 13-character phone limit', '1 failed, 41 passed',
     'Outdated test: it still looked for the old hint text "12 digits starting with 63 9".', 'Test updated; passed'),
    ('R-12', 'Nov 25', 'Registration tests after the digits-only phone rule', '1 failed, 40 passed',
     'Test mistake: its "wrong" example 0912 345 has 7 digits, which that rule allowed.', 'Test fixed; passed'),
]

# Which test or check found each real bug.
BUG_FINDERS = [
    ('BF-01', 'Full test suite (R-01)', 'Sign-in pages crashed: decorator on the wrong function',
     '73 tests failed with TypeError', 'Every page test'),
    ('BF-02', 'test_technician_api_sign_in_is_paused_too', 'Technician app got HTML instead of JSON when paused',
     'Assertion on the response', 'Same test'),
    ('BF-03', 'Browser check BT-01', 'Back after sign-out could show the dashboard (a background request revived the session)',
     'Back landed on the dashboard', 'test_background_polling_does_not_keep_an_idle_session_alive'),
    ('BF-04', 'test_deleting_the_account_deletes_the_id', 'Back-of-ID photo stayed on the server after deletion',
     'Leftover file in the upload folder', 'Same test'),
    ('BF-05', 'Browser check BT-05', 'Transactions "View Details" stuck on "Loading..."',
     'Script error in the browser', 'test_a_repair_bill_is_paid_after_the_repair_with_a_screenshot'),
    ('BF-06', 'Browser check BT-04', 'Payment screenshot preview broken (blob: images blocked)', 'Screenshot review',
     'Browser re-check'),
    ('BF-07', 'Browser check BT-03', 'A waiting button still accepted repeated clicks (3 requests)',
     'Request count', 'Browser re-check: 1 request'),
    ('BF-08', 'Browser check BT-07', 'Order progress line drawn toward a step not reached', 'Screenshot review',
     'Browser re-check'),
    ('BF-09', 'Demo server log (BT-04)', 'Payment screenshot saved while the time-slot lock was held',
     '"database is locked"', 'Booking tests'),
    ('BF-10', 'test_technician_and_customer_badges_follow_the_same_rule', 'My Jobs badge missed jobs with no assignment time',
     'Badge 0 instead of 1', 'Same test'),
    ('BF-12', 'Browser check: Transactions, Pay with GCash (PayMongo simulated)',
     'The automatic refresh reloaded the page the moment PayMongo confirmed a payment, before the receipt step opened',
     'Page reloaded; receipt step never shown', 'Browser re-check: receipt step opens and saves'),
    ('BF-11', 'Accessibility scan (BT-12)', 'Text below AA contrast; unlabeled fields on Services & Prices',
     'Measured contrast ratios and labels', 'Still open (section 10)'),
    ('BF-13', 'Manual test on the local server (R-11)', 'PHP 0 bill offered for payment; card button 405; endless spinner '
     '(B-13, B-14, B-15)', 'Stuck "Creating your QR code..."; 405 page', 'test_a_bill_the_booking_fee_fully_covers..., '
     'test_the_qr_dialog_gets_an_answer...'),
    ('BF-14', 'Smoke check of the live site (BT-15)', 'Production database missing new columns (B-16)', 'Home page 500',
     'test_missing_columns_and_tables_are_added_and_the_home_page_works'),
    ('BF-15', 'Code review of the reset page', 'Weaker password rule on reset (B-17)', 'Rule differed from registration',
     'test_reset_needs_the_same_strong_password_as_registration...'),
    ('BF-16', 'Real Resend email (BT-16)', 'Wrong fix hint (B-18)', 'Hint blamed MAIL_FROM for a recipient error',
     'Command-line re-check'),
    ('BF-17', 'Screenshot review (BT-14)', 'Error border hidden on focus (B-19)', 'Blue border on a wrong number',
     'Not re-checked yet'),
]

# Errors while running the tests (tools and environment, not the system).
RUN_ERRORS = [
    ('E-01', 'Browser checks timed out waiting for a page', 'The demo server (SQLite) was slow while the full test suite ran '
     'on the same PC.', 'Checks run one at a time with longer limits'),
    ('E-02', '"database is locked" in the demo server log', 'SQLite allows one writer at a time; production uses PostgreSQL.',
     'Led to fixing BF-09'),
    ('E-03', 'Browser tab crashed ("Target crashed")', 'The PC ran low on resources during a long run.', 'Run repeated'),
    ('E-04', 'Checks stopped mid-run', 'The editor session ended, which stops background jobs.', 'BT-10 and BT-11 not completed'),
    ('E-05', 'Errors in our own browser scripts', 'A selector did not match the page (a hidden radio button, a field that '
     'did not exist).', 'Scripts corrected; not system defects'),
    ('E-06', 'The full suite takes 25 to 28 minutes', 'Slow development PC.', 'No effect on results'),
    ('E-07', 'Could not read the live site\'s error log or its database', 'The Vercel and Supabase tools were signed in to '
     'another account than the one that owns the live site.', 'Diagnosed from page status codes (BT-15) instead'),
    ('E-08', 'Command to update the live database failed', 'Git Bash read the "!" in the password as a command ("event not '
     'found"); then the password had been changed ("password authentication failed").',
     'SQL script for the Supabase SQL Editor prepared (scripts/supabase_update_schema.sql)'),
]

NEGATIVE_WORDS = ('refus', 'invalid', 'cannot', 'cant_', 'wrong', 'never', 'only', 'not_', 'denied', 'outsider', 'reject',
                  'block', 'unauthor', 'without', 'duplicat', 'escap', 'pause', 'mismatch', 'expired', 'other_', 'someone_else',
                  'weak', 'outside', 'too_', 'stale', 'empty', 'missing', 'fail', 'locked', 'no_', 'twice', 'double',
                  'deactivat', 'suspend', 'nobody', 'guest', 'forbidden', 'limit', 'capped', 'bad_', 'error')


# Names that contain one of the words above but check normal behaviour, not an error.
NOT_NEGATIVE = ('test_the_outline_is_the_city_not_a_box', 'test_init_db_command_sets_up_an_empty_database',
                'test_on_vercel_the_app_writes_only_to_the_temp_folder', 'test_presence_pings_do_not_change_the_admin_stamp',
                'test_attachment_only_message_and_preview', 'test_a_verified_technician_without_a_photo_gets_a_two_day_notice',
                'test_being_online_is_not_a_profile_change', 'test_pages_update_when_the_other_side_edits_their_profile',
                'test_reader_reads_other_valid_ids', 'test_replacing_keeps_ids_and_bookings_and_hides_what_is_not_listed',
                'test_pages_render_items_without_descriptions', 'test_without_supabase_files_stay_on_disk_only',
                'test_background_polls_are_not_rate_limited', 'test_chat_list_view_does_not_jump_into_a_thread',
                'test_admin_list_view_does_not_jump_into_a_chat', 'test_rejected_booking_detail_includes_reason',
                'test_no_screenshot_is_needed_when_the_fee_is_off', 'test_overdue_photo_tells_admins_once',
                'test_adding_to_cart_does_not_hold_stock', 'test_customer_without_history_is_deleted',
                'test_home_has_no_invented_numbers_or_contacts', 'test_notes_do_not_overwrite_customer_description',
                'test_draft_without_diagnosis_keeps_saved_diagnosis', 'test_booking_fee_follows_the_setting_and_never_exceeds_the_price')


def negative_tests(cases):
    return [c for c in cases if any(w in c['name'].lower() for w in NEGATIVE_WORDS)
            and not c['name'].startswith(NOT_NEGATIVE)]


def build_testing(tests_suite, cases, a11y):
    total = len(cases)
    passed = sum(c['status'] == 'Pass' for c in cases)
    failed = sum(c['status'] == 'Fail' for c in cases)
    skipped = sum(c['status'] == 'Skipped' for c in cases)
    seconds = float(tests_suite.get('time') or sum(c['time'] for c in cases))
    stamp = (tests_suite.get('timestamp') or '')[:16].replace('T', ' ')

    pdf = Doc('Software Testing Documentation')
    pdf.title_page('CAPSTONE PROJECT  ·  SOFTWARE TESTING DOCUMENTATION',
                   'DEVTech Computer Repair and Services System',
                   'Test plan, test cases, honest results, defects found, open issues and a WCAG 2.1 AA accessibility check.',
                   ['Tacloban City, Leyte', f'Test run: {stamp or "November 2026"}',
                    'Prepared by: ______________________________', 'Adviser: ______________________________'])

    # 1 summary
    pdf.h1('1. Summary of results')
    pdf.data_table([
        ['Measure', 'Result'],
        ['Automated tests run', f'{total}'],
        ['Passed', f'{passed}'],
        ['Failed', f'{failed}'],
        ['Skipped', f'{skipped}'],
        ['Test files (modules)', f'{len({c["file"] for c in cases})}'],
        ['Time for the full run', f'{seconds / 60:.1f} minutes on the development PC'],
        ['Browser (system) checks', f'{sum(1 for b in BROWSER if b[4].startswith("Pass"))} passed, '
                                    f'{sum(1 for b in BROWSER if b[4] == "Not completed")} not completed, 1 reported in section 9'],
        ['Checks of the deployed website', f'{sum(1 for l in LIVE if l[5] == "Pass")} passed, '
                                           f'{sum(1 for l in LIVE if l[5] == "Fail")} failed (section 4.2)'],
        ['Failed test runs during development', f'{len(FAILED_RUNS)} (section 5), all resolved'],
        ['Error and negative tests', f'{len(negative_tests(cases))} (section 7)'],
        ['Defects found and fixed during testing', f'{len(FIXED)}'],
        ['Open issues / needs fixing', f'{sum(1 for o in OPEN if o[4] == "Open")} open, '
                                       f'{sum(1 for o in OPEN if o[4] == "Resolved")} resolved, '
                                       f'{sum(1 for o in OPEN if o[4] not in ("Open", "Resolved"))} accepted or monitored'],
    ], (70, 100))
    verdict = ('All automated tests passed.' if failed == 0 else f'{failed} automated tests failed.')
    pdf.callout('Honest verdict',
                f'{verdict} The main functions (accounts, booking, booking fee, payments, repair workflow, release, '
                'shop orders, refunds, technician verification, admin tools) work as specified in the automated tests. '
                'This does not mean the system is free of defects: sections 5 and 6 list the tests that failed and the bugs '
                'they found, section 10 lists what is still open (including times shown in UTC on the Transactions page), '
                'and section 3 lists '
                'what was not tested at all (load, real phones, screen readers, real users).', NAVY)

    # 2 approach
    pdf.h1('2. Test plan and approach')
    pdf.h2('2.1 Objectives')
    pdf.bullets(['Check that every function works as specified, including the error cases (wrong input, wrong user, double submit).',
                 'Check that money is handled safely: no payment confirmed twice, no amount accepted that differs from what is owed, '
                 'no device released before payment is checked.',
                 'Check privacy and security: customers, technicians and admins see only what they should; IDs and receipts are private.',
                 'Check that pages meet WCAG 2.1 level AA where it can be measured automatically.'])
    pdf.h2('2.2 Levels of testing')
    pdf.data_table([
        ['Level', 'What it checks', 'How'],
        ['Unit', 'Single functions: password rules, phone numbers, prices, ID-card reader, map boundary',
         'pytest, direct function calls'],
        ['Integration', 'A route with its database and rules: booking, payment, release, refunds',
         'pytest with the Flask test client and an in-memory SQLite database (fresh for every test)'],
        ['System (browser)', 'Whole flows in a real browser: sign-in, booking, payments, orders',
         'Playwright driving Microsoft Edge against a demo server with demo data'],
        ['Security / regression', 'Access control, CSRF, escaping, lockout, caching, private files',
         'pytest; each fixed bug keeps a test so it cannot come back'],
        ['Accessibility', 'Contrast, labels, names, language, reflow at 320 px',
         'Script in the browser computing WCAG contrast ratios on 13 pages'],
    ], (30, 75, 65))
    pdf.h2('2.3 Test environment')
    pdf.bullets([('Computer:', 'Windows 11 Home, the development laptop.'),
                 ('Software:', 'Python 3.14, Flask 3.1, SQLAlchemy 2.0, pytest 8.3, Playwright with Microsoft Edge (headless).'),
                 ('Data:', 'Only made-up test data. Tests use an in-memory database that is created and destroyed for every test, '
                           'so they never touch the real MySQL or Supabase database.'),
                 ('Outside services:', 'PayMongo is replaced by a simulated PayMongo API in tests (no real money, no real keys). '
                                       'Email (Brevo or Resend) and file storage (Supabase) are also simulated.')])
    pdf.h2('2.4 How bias was kept out')
    pdf.para('The tests were written by the development team (with an AI coding assistant) together with the features. That is a '
             'known source of bias: a test can share the same wrong assumption as the code. These steps were taken to reduce it:')
    pdf.bullets(['Every feature is tested on the failure side as well as the success side (wrong user, missing screenshot, '
                 'amount mismatch, double click, expired session).',
                 'Results are reported as they came out of the test runner (pytest-results.xml in docs/test-evidence), '
                 'including runs that did not finish.',
                 'Every failed test run and every bug found is listed in sections 5 and 6, even when it was fixed the same day.',
                 'What was NOT tested is stated in section 3.3 instead of being left out.',
                 'Recommendation: before the defense, let people outside the team run the checklist in Appendix B.'])

    pdf.h2('2.5 Pass and fail criteria')
    pdf.bullets(['A test passes when the actual result equals the expected result in every check of that test.',
                 'A browser check passes when the page behaves as expected and the browser reports no script errors.',
                 'An accessibility item meets AA when its measured value reaches the WCAG 2.1 threshold '
                 '(contrast 4.5:1 for normal text, 3:1 for large text).'])

    pdf.h2('2.6 Types of web testing used')
    pdf.para('The table names each kind of web testing, whether it was done, and how. "Partly" and "No" are stated '
             'plainly so the panel can see the gaps.')
    pdf.data_table([
        ['Type of testing', 'Used?', 'How it was done in DEVTech', 'Example'],
        ['Functional testing', 'Yes', 'Every feature checked against its rules with pytest and the Flask test client',
         'TC-10 booking fee before booking'],
        ['Unit testing', 'Yes', 'Single functions called directly', 'TC-41 phone number rule'],
        ['Integration testing', 'Yes', 'A page or API together with its database and rules, on a fresh in-memory database',
         'TC-17 bill paid after the repair'],
        ['System / end-to-end (browser)', 'Yes', 'Playwright drives Microsoft Edge through whole flows', 'BT-13, BT-14'],
        ['Regression testing', 'Yes', 'Full suite re-run after changes; every fixed bug keeps a test', 'Sections 5 and 6'],
        ['API testing', 'Yes', 'JSON endpoints checked for status code and content (QR payment, live updates, '
                               'technician app)', 'TC-45 QR dialog answer'],
        ['Form / input validation testing', 'Yes', 'Valid and invalid input for every form; server checked without the '
                                                   'browser script', 'TC-23, TC-41'],
        ['Security testing', 'Partly', 'Access control, CSRF, escaping, sign-in lockout, caching headers, upload checks. '
                                       'No outside penetration test', 'TC-20, TC-39'],
        ['Accessibility testing', 'Partly', 'Automated WCAG 2.1 AA scan of 13 pages; no screen reader test', 'Section 9'],
        ['Responsive / compatibility', 'Partly', 'Edge at 1280, 390, 375 and 320 px; no other browsers, no real phones',
         'BT-14'],
        ['Third-party integration', 'Partly', 'Simulated PayMongo, email and storage in tests; real PayMongo test-mode QR '
                                              'and a real Resend email by hand', 'BT-16, BT-17'],
        ['Deployed-site (live) testing', 'Yes', 'Read-only checks of the real website on the internet: pages, '
                                                'redirects, HTTPS, headers, CSRF, browser at two widths', 'Section 4.2'],
        ['Exploratory / manual testing', 'Yes', 'The developer used the site on the local server like a customer', 'R-09'],
        ['Database / schema testing', 'Yes', 'Self-updating schema test; SQL script checked with PostgreSQL\'s own parser',
         'TC-48'],
        ['Performance / load testing', 'Partly', 'Response times of the live pages measured; no load test with '
                                                    'many users', 'LT-12 (failed)'],
        ['Usability / user acceptance', 'No', 'Checklist prepared, not yet run with real users', 'Appendix B'],
    ], (40, 14, 82, 34), size=7.6, status_col=1)
    pdf.h2('2.7 Test design methods')
    pdf.bullets([
        ('Black-box testing:', 'tests written from the user\'s side, comparing expected and actual results without '
                               'looking at the code (section 4 test cases, browser checks).'),
        ('White-box testing:', 'tests written knowing the code, for paths a user cannot easily reach: two requests racing '
                               'for the same payment, a database error while saving, a crash while starting a QR payment.'),
        ('Equivalence partitioning:', 'inputs grouped into classes that behave the same, one test per class. Example: '
                                      'mobile numbers split into valid local, valid international, letters, symbols, wrong '
                                      'prefix, too short and too long.'),
        ('Boundary value analysis:', 'tests at the edges of a rule: 11 digits accepted but 7 and 13 refused; a 5th booking '
                                     'in a time slot accepted and a 6th refused; a password of 8 characters; a PHP 0 bill.'),
        ('Negative testing and error guessing:', 'deliberately wrong input, wrong user and double clicks (section 7).'),
        ('Test doubles (simulation):', 'PayMongo, email and file storage replaced by simulated versions, so tests never '
                                       'spend money, send mail or touch real data.'),
        ('Automated and manual testing:', 'pytest and Playwright run automatically; manual use of the local and live site '
                                          'found the bugs in R-09 and R-10.'),
    ])

    # 3 coverage
    pdf.h1('3. What was tested')
    pdf.h2('3.1 Results by module')
    by = collections.OrderedDict()
    for c in sorted(cases, key=lambda c: c['file']):
        by.setdefault(c['file'], []).append(c)
    rows = [['Module (test file)', 'What it covers', 'Tests', 'Passed', 'Failed']]
    for f, items in by.items():
        about = docstring_of(f)
        about = (about[:150] + '...') if len(about) > 150 else about
        rows.append([FILE_LABELS.get(f, f.replace('test_', '').replace('_', ' ').capitalize()) + f'\n{f}.py',
                     about or '-', len(items), sum(i['status'] == 'Pass' for i in items),
                     sum(i['status'] == 'Fail' for i in items)])
    rows.append(['Total', '', total, passed, failed])
    pdf.data_table(rows, (45, 85, 13, 14, 13), size=7.6)
    pdf.h2('3.2 Functions covered')
    pdf.bullets(['Accounts: registration, sign-in on three portals, lockout, idle timeout, password reset, profiles.',
                 'Booking: service catalog, device filter, time slots and capacity, Tacloban map boundary, terms, booking fee.',
                 'Payments: PayMongo QR Ph, webhook, the shop QR with screenshot, bills after the repair, extra work, refunds.',
                 'Repair workflow: intake, diagnosis, repair, extra-work approval, ready for collection, customer receipt, release.',
                 'Technicians: roster, registration with ID front and back, verification, suspension, job ownership.',
                 'Shop: products, cart, checkout, delivery estimates, riders, order tracking, cancellation.',
                 'Admin: dashboard, users, requests, payments, services and category editing, settings, danger zone.',
                 'Support: live chat, FAQ chatbot, notifications, messages with attachments.'])
    pdf.h2('3.3 Not tested (limitations)')
    pdf.bullets(['Load and performance (many users at once).',
                 'Real payments through PayMongo\'s servers (only a simulated PayMongo).',
                 'Real phones and tablets (only browser windows at 1280 px, 390 px and 320 px).',
                 'Screen readers and a full keyboard-only walkthrough.',
                 'User acceptance testing with real customers, technicians and the shop owner.',
                 'On the live site, anything that writes data: signing in, booking, paying, sending email, admin '
                 'actions. Only read-only checks were run there (section 4.2).'])

    # 4 cases
    pdf.h1('4. Test cases: expected and actual results')
    pdf.para('Each row is an automated test that runs in the full suite. "Actual" is what happened in the run of '
             f'{stamp or "this documentation"}. The test name is given so the panel can re-run any single case with '
             '"pytest -k <name>".', size=9.5, color=MUTED)
    rows = [['ID', 'Module', 'Scenario and input', 'Expected result', 'Actual result', 'Status']]
    for cid, module, scenario, steps, expected, test in CASES:
        st = status_of(cases, test)
        actual = 'Same as expected.' if st.startswith('Pass') else ('Did not run.' if st == 'Not run' else 'See failure log.')
        rows.append([cid, module, f'{scenario}\nInput: {steps}\nTest: {test}', expected, actual, st])
    pdf.data_table(rows, (12, 18, 62, 42, 20, 16), size=7.2, status_col=5)

    pdf.h2('4.1 Browser (system) checks')
    pdf.para('Run with Playwright and Microsoft Edge on the demo server. These were run during development; two did not finish '
             'and are reported as such.', size=9.5, color=MUTED)
    rows = [['ID', 'Check', 'Expected', 'Actual', 'Status', 'Date']]
    rows += [list(b) for b in BROWSER]
    pdf.data_table(rows, (12, 45, 40, 42, 18, 13), size=7.4, status_col=4)

    pdf.h2('4.2 Testing the deployed website (live)')
    pdf.para(f'The real website at {LIVE_URL} was tested over the internet on {LIVE_WHEN}, from the development PC. '
             'These checks only open pages and read their answers: nothing was submitted, so no account, booking or '
             'payment was created in the real database. Pages were loaded with curl (status, headers, timing) and in '
             'Microsoft Edge with Playwright (script errors, failed files, layout, accessibility basics).')
    rows = [['ID', 'Check', 'Input', 'Expected', 'Actual', 'Status']] + [list(l) for l in LIVE]
    pdf.data_table(rows, (12, 30, 38, 36, 40, 14), size=7.4, status_col=5)
    live_fail = [l for l in LIVE if l[5] == 'Fail']
    pdf.callout('Live result', f'{len(LIVE) - len(live_fail)} of {len(LIVE)} live checks passed. '
                + ('Failed: ' + '; '.join(f'{l[0]} {l[1].lower()}' for l in live_fail) + '. The home page answers slowly '
                   'because the server runs in Washington DC while the database is in Singapore (open issue O-12). '
                   if live_fail else '')
                + 'An earlier live check had failed (BT-15: home page 500, then database unreachable); after the fix, '
                'this re-check passed.', WARN if live_fail else PASS)

    # 5 failed tests
    pdf.h1('5. Failed tests during development')
    pdf.para('Every test run that did not pass, in the order it happened. A failure is one of three things: a real bug in '
             'the system, a test that still described an old rule after the requirements changed, or a mistake in the '
             'test itself. Each one is labelled honestly below.')
    real = [r[0] for r in FAILED_RUNS if 'real bug' in r[4].lower()]
    pending = [r[0] for r in FAILED_RUNS if 'pending' in r[5].lower()]
    pdf.callout('In numbers', f'{len(FAILED_RUNS)} failed runs (automated tests, manual tests and live-site checks). '
                f'{len(real)} of them uncovered real bugs in the system ({", ".join(real)}); the others were outdated '
                'tests or mistakes in the tests. '
                + (f'All are resolved except {", ".join(pending)} (see section 10). ' if pending else 'All were resolved. ')
                + 'The final automated run is in section 1.', WARN)
    rows = [['Run', 'Date', 'What ran', 'Result', 'Why it failed', 'Outcome']] + [list(r) for r in FAILED_RUNS]
    pdf.data_table(rows, (11, 11, 32, 22, 70, 24), size=7.2)

    # 6 bugs
    pdf.h1('6. Bugs found by testing, and how they were fixed')
    pdf.h2('6.1 Which test found each bug')
    rows = [['ID', 'Found by', 'Bug', 'How it showed', 'Guarded now by']] + [list(b) for b in BUG_FINDERS]
    pdf.data_table(rows, (12, 40, 52, 30, 36), size=7.2)
    pdf.h2('6.2 Defects fixed, with severity')
    rows = [['ID', 'Defect', 'Severity', 'Fix', 'Status']] + [list(f) for f in FIXED]
    pdf.data_table(rows, (12, 78, 22, 44, 14), size=7.8, status_col=4)

    # 7 negative / error tests
    neg = negative_tests(cases)
    pdf.h1('7. Error and negative tests')
    pdf.para(f'{len(neg)} of the {total} automated tests check that the system refuses something or handles an error: wrong '
             'passwords, invalid bookings, other people\'s data, missing screenshots, wrong payment amounts, double '
             'submits, expired links and so on. They are listed below with their result in the final run. A system that only '
             'passes "happy path" tests is not tested; these show the failure side.')
    rows = [['#', 'Test (what must be refused or handled)', 'Module', 'Result']]
    for i, c in enumerate(sorted(neg, key=lambda c: (c['file'], c['name'])), 1):
        name = c['name'].replace('_', ' ').replace('test ', '', 1)
        if '[' in name:                                      # a parameter set: keep it short
            base, param = name.split('[', 1)
            name = f'{base}[{param[:40].rstrip("]")}]' if len(param) > 1 else base
        rows.append([i, name, FILE_LABELS.get(c['file'], c['file']), c['status']])
    pdf.data_table(rows, (9, 109, 40, 12), size=6.9, status_col=3)

    # 8 errors while testing
    pdf.h1('8. Errors during test execution')
    pdf.para('Problems with the tools or the computer while tests ran. They are not defects of DEVTech, but they explain '
             'why some checks did not finish.')
    rows = [['ID', 'Error', 'Cause', 'What was done']] + [list(e) for e in RUN_ERRORS]
    pdf.data_table(rows, (12, 52, 64, 42), size=7.6)

    # 9 accessibility
    pdf.h1('9. Accessibility: WCAG 2.1 level AA')
    pdf.para('A script ran on 13 pages in the browser and measured: text contrast (1.4.3), pictures without text (1.1.1), '
             'form fields without a label (1.3.1, 4.1.2), buttons and links without a name (4.1.2), page language (3.1.1) '
             'and reflow at 320 px width (1.4.10). Contrast is computed from each text\'s colour against the solid colour '
             'behind it; text on a picture or gradient is counted as "not measurable" and not guessed.')
    if a11y:
        rows = [['Page', 'Text styles checked', 'Contrast below AA', 'Fields without label', 'Nameless buttons/links',
                 'Reflow 320 px', 'Language']]
        for r in a11y:
            rows.append([r['page'], r['checked'], len(r['fails']), len(r['unlabeled']), len(r['nameless']),
                         'OK' if r['reflow_ok'] else 'Scrolls sideways', r['lang'] or 'missing'])
        pdf.data_table(rows, (40, 22, 22, 22, 24, 22, 18), size=7.6)
        contrast = sum(len(r['fails']) for r in a11y)
        unl = sum(len(r['unlabeled']) for r in a11y)
        nameless = sum(len(r['nameless']) for r in a11y)
        reflow = sum(1 for r in a11y if not r['reflow_ok'])
        all_ok = not (contrast or unl or nameless or reflow)
        pdf.callout('Result', ('All measured items meet AA on the 13 pages checked.' if all_ok else
                               f'Not every page meets AA yet: {contrast} text styles below the contrast ratio, {unl} fields '
                               f'without a label, {nameless} buttons or links without a name, {reflow} pages that scroll '
                               'sideways at 320 px. The details are listed below and in docs/test-evidence/a11y/a11y-report.json. '
                               'These need to be fixed to claim WCAG 2.1 AA.'),
                    PASS if all_ok else FAIL)
        details = []
        for r in a11y:
            for f in r['fails'][:6]:
                details.append([r['page'], f'"{f["text"]}"', f'{f["ratio"]}:1', f'{f["need"]}:1', f'{f["size"]} px'])
        if details:
            pdf.h2('9.1 Contrast below AA (first items per page)')
            pdf.data_table([['Page', 'Text', 'Measured', 'Needed', 'Size']] + details[:60], (38, 78, 18, 18, 18), size=7.4)
        other = [[r['page'], ', '.join(r['unlabeled'])[:120] or '-', str(len(r['nameless']))] for r in a11y
                 if r['unlabeled'] or r['nameless']]
        if other:
            pdf.h2('9.2 Fields without a label / nameless buttons')
            pdf.data_table([['Page', 'Fields without a label', 'Nameless buttons/links']] + other, (40, 100, 30), size=7.6)
    else:
        pdf.callout('Not completed', 'The accessibility scan did not finish, so no AA result is claimed.', FAIL)
    pdf.h2('9.3 Not covered by the automated check')
    pdf.bullets(['Screen reader use (NVDA, TalkBack), full keyboard-only use, and focus order: to be checked by hand.',
                 'Text on pictures and gradients (reported as "not measurable").',
                 'Meaningful wording of alternative text: the script only checks that it exists.'])

    # 10 open
    pdf.h1('10. Open issues and what needs to be fixed')
    rows = [['ID', 'Issue', 'Severity', 'Recommended action', 'Status']] + [list(o) for o in OPEN]
    pdf.data_table(rows, (12, 74, 18, 54, 22), size=7.8, status_col=4)

    # 11 conclusion
    pdf.h1('11. Conclusion and recommendations')
    pdf.para(f'{passed} of {total} automated tests passed and {failed} failed in the final run. During development '
             f'{len(FAILED_RUNS)} test runs failed; they uncovered real bugs that were fixed, and each fix kept a test. The functions the system is built for work as '
             'specified, including the safety rules around money (fee before booking, payment checked before release, no '
             'double payments, refunds) and privacy (private IDs and receipts, role-based access).')
    pdf.para('Before the defense the team should: (1) move the Vercel server to Singapore (O-12) and re-time the pages; '
             '(2) fix O-01 (times in UTC); (3) re-run BT-10 and BT-11 to completion; (4) make one PayMongo test-mode '
             'payment (O-03); (5) verify a Resend domain (O-10); (6) fix the accessibility items in section 9; '
             '(7) run the UAT checklist in Appendix B with people outside the team and record the results honestly.')

    # appendices
    pdf.h1('Appendix A. How to re-run the tests')
    pdf.set_font('Mono', '', 9)
    pdf.set_text_color(*INK)
    for line in ['.venv\\Scripts\\python -m pytest -q',
                 '.venv\\Scripts\\python -m pytest -q --junitxml=docs\\test-evidence\\pytest-results.xml',
                 '.venv\\Scripts\\python -m pytest -q -k "booking_fee or paymongo"',
                 '.venv\\Scripts\\python docs\\build_docs.py']:
        pdf.multi_cell(0, 5.5, line, new_x='LMARGIN', new_y='NEXT')
    pdf.ln(3)
    pdf.para('Evidence files: docs/test-evidence/pytest-results.xml (every test and its result), pytest-output.txt '
             '(console output), a11y/a11y-report.json and the page screenshots in a11y/.', size=9.5)

    pdf.h1('Appendix B. User acceptance test checklist (to be filled in)')
    pdf.para('Give this to testers outside the team. Write what actually happened; do not correct it afterwards.', size=9.5,
             color=MUTED)
    uat = [['#', 'Task for the tester', 'Expected', 'Actual (tester writes)', 'Pass / Fail'],
           ['1', 'Create a customer account', 'Account created; sign-in works', '', ''],
           ['2', 'Sign in with a wrong password 5 times', 'Sign-in paused, countdown shown', '', ''],
           ['3', 'Book a repair and pay the booking fee by QR', 'Receipt step after paying; booking sent', '', ''],
           ['4', 'Close the QR without paying, then try again', 'Form still filled in; can pay again', '', ''],
           ['5', 'Double-click "Create account" / "Book Now"', 'Only one account / booking', '', ''],
           ['6', 'Admin: approve the booking and assign a technician', 'Approved only after the fee is paid', '', ''],
           ['7', 'Technician: intake, diagnosis, report, ready for collection', 'Status updates for the customer', '', ''],
           ['8', 'Customer: approve extra work', 'Bill total increases by the extra', '', ''],
           ['9', 'Customer: pay the bill with a screenshot after the repair', 'Accepted only after the repair', '', ''],
           ['10', 'Technician: release after checking the payment', 'Release refused until checked', '', ''],
           ['11', 'Shop: order, track and cancel', 'Tracking updates; refund opened if paid', '', ''],
           ['12', 'Use the site on a phone', 'Readable, no sideways scrolling', '', '']]
    pdf.data_table(uat, (8, 58, 48, 40, 16), size=8)
    out = os.path.join(os.environ.get('DOCS_OUT') or HERE, 'DEVTech_Testing_Documentation.pdf')
    pdf.output(out)
    return out


# ============================================================ reviewer
QUESTIONS = [
    ('What is DEVTech and who is it for?',
     'A web system for a computer repair shop in Tacloban City. Customers book repairs, pay, follow the repair live and buy '
     'parts; technicians record each stage of the job; the admin runs bookings, payments, technicians, the shop and support.'),
    ('What problem does it solve?',
     'Repair shops usually work on paper and chat messages: tickets get lost, customers keep asking for updates, prices and '
     'extra charges are disputed, payments are hard to trace, and customers cannot verify who the technician is. DEVTech '
     'records every step, shows it to the customer, and asks the customer to approve any extra cost before it is charged.'),
    ('Why is a booking fee paid first?',
     'It reduces no-shows and fake bookings that block time slots. It is deducted from the final bill, so it is not an '
     'extra charge, and the booking is only sent once the fee is paid by QR and a receipt screenshot is attached.'),
    ('Why both PayMongo and a screenshot?',
     'PayMongo confirms the payment automatically (it is the proof the money arrived). The screenshot is the customer\'s own '
     'record that the shop keeps with the booking; it helps in disputes. Without PayMongo the shop QR and the screenshot '
     'are checked by an admin.'),
    ('How do you prevent paying twice or confirming a wrong amount?',
     'A payment is confirmed in one database update that only works while it is still unpaid, and only when PayMongo\'s '
     'amount equals what is owed. A paid booking fee is attached to one booking only. Buttons lock after the first click.'),
    ('Why can the device only be released after payment?',
     'To protect the shop: the technician must tick that the cash was collected (C.A.R) or that the GCash payment reached the '
     'shop account, and the customer must confirm they received the device. The server refuses the release otherwise.'),
    ('How are extra charges handled?',
     'The technician puts the job on hold and sends the findings and the extra cost. The customer approves or declines in '
     'the app. Only approved extras are added to the bill, and the bill shows each one.'),
    ('Why Flask (Python) and not PHP/Laravel or Node?',
     'Python is what the team knows best, Flask is small and easy to explain line by line, and it has mature libraries for '
     'security (CSRF, rate limiting, security headers), PDFs and testing (pytest).'),
    ('Why SQLAlchemy, MySQL and PostgreSQL?',
     'SQLAlchemy lets the same code run on MySQL (local, XAMPP/Laragon style) and PostgreSQL (Supabase, free hosting). It '
     'also prevents SQL injection by using parameters.'),
    ('Why Vercel, Supabase and Brevo?',
     'They have free tiers suitable for a capstone: Vercel hosts the Flask app, Supabase provides PostgreSQL and private file '
     'storage, Brevo sends email (password reset, notifications).'),
    ('Why Leaflet and OpenStreetMap?',
     'Free maps without an API bill. The system checks pins against the real Tacloban City boundary (138 barangays), not a box.'),
    ('How do you protect passwords and accounts?',
     'Passwords are hashed with bcrypt. Strong passwords are required. After 5 wrong tries sign-in pauses for 10 seconds, '
     'doubling each time up to 15 minutes. Sessions end after 30 minutes idle unless "Remember me" is ticked. Account pages '
     'are not cached, so Back after sign-out does not show them.'),
    ('How do you protect forms and pages?',
     'CSRF tokens on every form, a Content Security Policy, escaping of all user text, rate limits on sign-in, and role checks '
     'on every route (a customer cannot open admin pages, a technician only sees their own jobs).'),
    ('How do you protect the technicians\' IDs?',
     'ID photos are stored outside the public folder with random names, served only to admins (each view is logged), never '
     'shown to customers; location data is removed from phone photos; they are deleted with the account.'),
    ('How do you know a technician is real?',
     'An admin adds every hired technician to the roster with their ID (front and back). A technician can only register with '
     'a roster Tech ID whose name, birth date and ID number match, and stays inactive until an admin verifies the ID.'),
    ('How did you test the system?',
     'With {N} automated tests (pytest) run on a fresh database every time, browser tests with Playwright and Microsoft Edge, '
     'security regression tests for every fixed bug, and a WCAG 2.1 AA accessibility check. Results and limits are in the '
     'Testing Documentation.'),
    ('Did any test fail?',
     'In the final run all {N} automated tests passed. During development, browser testing found bugs (for example a View '
     'Details button stuck on loading, and double clicks sending twice); they were fixed and each got a test. Two browser '
     'checks did not finish and there are open issues; we report them honestly.'),
    ('What are the limitations?',
     'No load testing, PayMongo tested with a simulated API, no real-phone or screen-reader test, no UAT with real users yet, '
     'and times on the Transactions page are still shown in UTC. Screenshots can be edited, so the money is always checked in '
     'the shop account.'),
    ('Is the system accessible?',
     'We measured WCAG 2.1 AA items (contrast, labels, names, language, reflow) on 13 pages. The Testing Documentation shows the '
     'exact results, including any item that does not meet AA yet.'),
    ('What happens if the internet or the payment fails while booking?',
     'Nothing typed is lost: the form is kept in the browser tab, an expired QR is replaced with a new one, and a paid fee is '
     'kept for the booking. The customer just presses Book Now again.'),
    ('How does the customer follow the repair?',
     'The Monitor Device page shows each stage live (assigned, diagnosis, repair, ready for collection, released), the '
     'technician\'s notes and photos, and any extra-work request to approve.'),
    ('What reports does the system produce?',
     'A service report PDF per job (diagnosis, work done, parts, photos, the bill), the admin dashboard and analytics, payment '
     'and refund lists, and the activity log.'),
    ('How are refunds handled?',
     'Cancelling a paid booking or order opens a refund automatically. Online (PayMongo) payments are refunded through '
     'PayMongo; GCash/cash refunds are recorded by the admin with a reference number.'),
    ('Why did you choose this study?',
     'Computer repair is a common local business where trust and communication are the main problems; a booking and tracking '
     'system has a clear, measurable benefit for both the shop and its customers.'),
    ('Who benefits?',
     'Customers (convenience, transparency, safer payments), technicians (clear job list and records), the shop owner (control '
     'of bookings, payments and staff), and the community (verified technicians for home service).'),
    ('What would you add next?',
     'An Android app, SMS notifications, inventory for spare parts, warranty tracking, ratings analytics per technician, and '
     'a load test before a real launch.'),
    ('How is data privacy handled (Data Privacy Act of 2012)?',
     'Only the data needed is collected, consent is asked for ID upload, IDs and receipts are private, customers can download '
     'or delete their data, and access to IDs is logged.'),
    ('Can the admin change prices?',
     'Yes: per service, or a whole category at once (prices, service fees, hours). New bookings use the new prices; existing '
     'bookings keep what they were billed.'),
    ('What happens if two people book the last slot at the same time?',
     'The slot is locked in the database while a booking is saved, so only one gets the last place (5 per hour).'),
    ('How is the database protected?',
     'The password and address are only in environment variables, never in the code. All queries use parameters (no SQL '
     'injection). Passwords are stored as bcrypt hashes. IDs and receipts are in a private bucket, not the public folder. '
     'Money actions use updates that can only succeed once.'),
    ('What if someone steals the database?',
     'They would not get passwords (only bcrypt hashes), and ID photos and receipts are not in the database but in private '
     'storage. We would still rotate the secret key and database password and tell affected users.'),
    ('How do you stop someone guessing passwords?',
     'Strong-password rules, a pause after 5 wrong tries that doubles up to 15 minutes, a rate limit per IP, and the same '
     'message for unknown emails.'),
    ('What stops another person from using my session?',
     'The session cookie is signed, HttpOnly, SameSite=Lax and HTTPS-only in production; it expires after 30 minutes idle '
     'unless "Remember me" is ticked, and ends at sign-out or when an admin deactivates the account.'),
    ('Can a customer open another customer\'s booking or receipt?',
     'No. Every page and file checks that it belongs to the signed-in account; others get "not found". This is covered by '
     'automated tests.'),
    ('What would you improve in security?',
     'Row Level Security on every Supabase table, enforced SSL on the database connection, two-step verification for admins, '
     'and an outside penetration test before launch.'),
    ('How do you keep the technicians\' IDs safe?',
     'Only hired staff on the roster can upload one, with consent. The photo is checked, its location data removed, and '
     'it is stored under a random name in a private bucket with no public link. Only admins and the technician can open '
     'it, every admin view is logged, it is never cached, the ID number is masked, and it is deleted with the account. '
     'What we would add: encryption of ID numbers and files, and deleting IDs some time after verification.'),
    ('What kinds of testing did you do?',
     'Functional, unit, integration, end-to-end in a real browser, regression, API, security, input validation, '
     'accessibility (WCAG 2.1 AA), smoke checks of the live site and manual testing. We designed tests with black-box and '
     'white-box methods, equivalence partitioning and boundary values. Not done: load testing and user acceptance with '
     'real users.'),
    ('Why a web system and not a mobile app?',
     'One system works on phones and computers without installing anything, it is cheaper to host and update, and the layout '
     'adapts to phone screens.'),
]


def build_reviewer(total, failed=0):
    pdf = Doc('Capstone Defense Reviewer')
    pdf.title_page('CAPSTONE PROJECT  ·  DEFENSE REVIEWER',
                   'DEVTech Computer Repair and Services System',
                   'Why the system is needed, how it works, why these technologies, how it was tested, and the questions '
                   'the panel may ask, with suggested answers.',
                   ['Tacloban City, Leyte', 'Prepared by: ______________________________',
                    'Adviser: ______________________________'])

    pdf.h1('1. The system in one page')
    pdf.para('DEVTech is a web-based repair booking, tracking and payment system for a computer repair shop in Tacloban City. '
             'It has three portals:')
    pdf.bullets([('Customer:', 'books a repair (in-shop or home service), pays the booking fee by QR, follows the repair live, '
                               'approves or declines extra work, pays the bill after the repair, buys parts in the shop, '
                               'and chats with the shop.'),
                 ('Technician:', 'registers with a verified ID, records intake, diagnosis and repair, asks for approval of extra '
                                 'work, writes the service report, checks the payment and releases the device.'),
                 ('Admin:', 'approves bookings and assigns technicians, confirms payments and refunds, manages services and '
                            'prices, the shop, riders, technicians (roster and verification), users, support and settings.')])
    pdf.h2('Objectives')
    pdf.numbered(['Let customers book repairs online and know the price before the work starts.',
                  'Show every stage of the repair to the customer as it happens.',
                  'Make payments traceable and safe (booking fee, approved extras, payment checked before release, refunds).',
                  'Make sure only verified technicians do the work.',
                  'Give the shop owner one place to manage bookings, staff, payments and the shop.'])
    pdf.h2('Scope and limits')
    pdf.bullets(['Covers Tacloban City only (home service pins must be inside the city).',
                 'Payments: PayMongo QR Ph (GCash, Maya, bank apps), the shop\'s own QR with a screenshot, and cash after repair.',
                 'Not included: spare-parts inventory, SMS, a native mobile app, payroll.'])

    pdf.h1('2. Why the system is needed')
    pdf.para('Problems observed in the usual way of running a repair shop:')
    pdf.bullets([('Lost or unclear records:', 'repairs written on paper slips or chat messages; hard to find history.'),
                 ('No visibility:', 'customers call or visit to ask "is it done?"; staff time is spent answering.'),
                 ('Price disputes:', 'extra parts or work charged without clear approval.'),
                 ('Payment problems:', 'payments not traced to a job; devices released without full payment.'),
                 ('Trust in home service:', 'customers cannot verify the person coming to their house.'),
                 ('No-shows:', 'slots blocked by people who never come.')])
    pdf.para('How DEVTech answers each one: every booking has a number and a full history; the Monitor Device page shows the '
             'stage live; extra work needs the customer\'s approval in the app; payments are linked to the booking and checked '
             'before release; technicians are verified against the shop\'s roster and their ID; the booking fee discourages '
             'fake bookings and is deducted from the bill.')
    pdf.h2('Significance')
    pdf.bullets([('Customers:', 'convenience, transparency, safer payments.'),
                 ('Technicians:', 'clear job list, records that protect them in disputes.'),
                 ('Shop owner:', 'control and reports on bookings, payments, staff and sales.'),
                 ('Researchers / students:', 'a reference for similar service-booking systems.')])

    pdf.h1('3. System workflow')
    system_overview(pdf)
    flow_diagram(pdf, 'Figure 2. Repair booking: request, booking fee and approval', ['Customer', 'Admin', 'Technician'], [
        {'lane': 0, 'kind': 'start', 'text': 'Customer signs in'},
        {'lane': 0, 'text': 'Fills in the repair request: device, service, problem, date and time, in-shop or home'},
        {'lane': 0, 'text': 'Presses Book Now: the PayMongo QR Ph code for the booking fee opens'},
        {'lane': 0, 'kind': 'decision', 'text': 'Fee paid?',
         'go': [(4, 'Yes'), (2, 'No: QR expired or failed. Form is kept; try again')]},
        {'lane': 0, 'text': 'Attaches the receipt screenshot and submits the request'},
        {'lane': 1, 'text': 'Sees the new request (badge); the fee is already paid'},
        {'lane': 1, 'kind': 'decision', 'text': 'Approve?', 'go': [(7, 'Yes'), (8, 'No')]},
        {'lane': 1, 'text': 'Assigns a verified technician; the customer is notified'},
        {'lane': 1, 'kind': 'end', 'text': 'Rejected: customer notified, paid fee refunded'},
    ], note='Continued in Figure 3. One booking per time slot per customer; at most 5 bookings per hour.')
    flow_diagram(pdf, 'Figure 3. Repair, payment and release', ['Customer', 'Admin', 'Technician'], [
        {'lane': 2, 'kind': 'start', 'text': 'Job assigned (from Figure 2)'},
        {'lane': 2, 'text': 'Records the device intake with photos'},
        {'lane': 2, 'text': 'Writes the diagnosis'},
        {'lane': 2, 'kind': 'decision', 'text': 'Extra work needed?', 'go': [(4, 'Yes'), (5, 'No')]},
        {'lane': 0, 'text': 'Approves or declines the extra cost (added to the bill if approved)'},
        {'lane': 2, 'text': 'Repairs and submits the service report'},
        {'lane': 2, 'text': 'Marks Ready for Collection'},
        {'lane': 0, 'text': 'Pays the bill: GCash with a screenshot, or cash at the shop (C.A.R)'},
        {'lane': 0, 'text': 'Confirms "I received my device"'},
        {'lane': 2, 'kind': 'decision', 'text': 'Payment checked?', 'go': [(10, 'Yes'), (7, 'No: release refused')]},
        {'lane': 2, 'text': 'Releases the device'},
        {'lane': 0, 'kind': 'end', 'text': 'Rates the technician'},
    ], note='Each stage appears live on the customer\'s Monitor Device page. Admins can see every job and payment.')
    flow_diagram(pdf, 'Figure 4. Shop order', ['Customer', 'Admin'], [
        {'lane': 0, 'kind': 'start', 'text': 'Adds products to the cart and checks out'},
        {'lane': 0, 'kind': 'decision', 'text': 'Pay by QR Ph?', 'go': [(2, 'Yes'), (3, 'No: cash on delivery')]},
        {'lane': 0, 'text': 'Scans the PayMongo QR; payment confirmed automatically'},
        {'lane': 1, 'text': 'Prepares the order'},
        {'lane': 1, 'text': 'Assigns a rider on duty and sends it out (QR orders only once paid)'},
        {'lane': 0, 'text': 'Follows the order and the delivery time on My Orders'},
        {'lane': 1, 'text': 'Marks it delivered'},
        {'lane': 0, 'kind': 'end', 'text': 'Order received'},
    ], note='Cancelling a paid order opens a refund; QR payments are refunded automatically through PayMongo.')
    flow_diagram(pdf, 'Figure 5. Technician onboarding', ['Admin', 'Technician'], [
        {'lane': 0, 'kind': 'start', 'text': 'Hires a technician'},
        {'lane': 0, 'text': 'Adds them to the roster: Tech ID, name, birth date, ID number, address, ID front and back'},
        {'lane': 1, 'text': 'Registers with that Tech ID: ID front and back, address, password'},
        {'lane': 1, 'kind': 'decision', 'text': 'Matches the roster?',
         'go': [(4, 'Yes'), (2, 'No: refused, check the details')]},
        {'lane': 0, 'text': 'Checks the ID photos against the details'},
        {'lane': 0, 'kind': 'decision', 'text': 'Verified?', 'go': [(6, 'Yes'), (2, 'No: correction requested')]},
        {'lane': 1, 'kind': 'end', 'text': 'Account active: can sign in and be assigned jobs'},
    ])
    pdf.h2('3.1 Repair booking (main flow), step by step')
    pdf.numbered(['Customer signs in and opens Service Request: device, service, problem, in-shop or home (map pin), date and '
                  'hour, payment choice for the bill (GCash/online or C.A.R), terms.',
                  'Book Now: PayMongo\'s QR Ph opens for the booking fee. The customer scans and pays; PayMongo confirms it.',
                  'The receipt step opens: the customer attaches a screenshot and submits. The booking is created with the fee '
                  'attached (deducted from the bill). If payment fails or the QR expires, the form is kept and they try again.',
                  'Admin approves the booking (only possible when the fee is paid) and assigns a verified technician.',
                  'Technician records the device intake (with photos); diagnosis starts automatically.',
                  'Technician writes the diagnosis; the repair starts automatically.',
                  'If more work or parts are needed: the job goes on hold, the customer approves or declines the extra cost.',
                  'Technician submits the service report and moves the job to Ready for Collection.',
                  'Customer pays the bill (GCash with a screenshot, or cash at the shop) and presses "I received my device".',
                  'Technician checks the payment (ticks the box) and releases the device. The customer can rate the technician.'])
    pdf.h2('3.2 Shop order')
    pdf.numbered(['Customer adds products to the cart and checks out (QR Ph or cash on delivery).',
                  'Admin prepares the order, assigns a rider on duty and sends it out (online payment must be confirmed first).',
                  'Customer follows the order (placed, preparing, out for delivery, delivered) with a delivery estimate.',
                  'Cancelling a paid order opens a refund (online payments are refunded through PayMongo).'])
    pdf.h2('3.3 Technician onboarding')
    pdf.numbered(['Admin adds the hired technician to the roster: Tech ID, name, birth date, ID type and number, address, '
                  'photos of the front and back of the ID.',
                  'The technician registers with that Tech ID, uploads the same ID (front and back) and their address.',
                  'The details must match the roster; the account stays inactive until an admin verifies the ID.',
                  'Only verified technicians can be assigned jobs.'])
    pdf.h2('3.4 Booking statuses')
    pdf.data_table([['Status', 'Meaning', 'Moved by'],
                    ['Pending', 'Request sent with the fee paid', 'Customer'],
                    ['Confirmed', 'Approved and assigned', 'Admin'],
                    ['Diagnosis', 'Device received, being checked', 'Automatic after intake'],
                    ['On Repair', 'Diagnosis done, repair in progress', 'Automatic after diagnosis'],
                    ['On Hold', 'Waiting for the customer to approve extra work', 'Technician request'],
                    ['Ready for Collection', 'Repair done, report submitted', 'Technician'],
                    ['Released', 'Paid, checked and handed over', 'Technician'],
                    ['Cancelled', 'Cancelled by the customer or rejected', 'Customer / Admin']], (40, 85, 45))

    pdf.h1('4. Technologies and why we used them')
    pdf.data_table([
        ['Technology', 'Used for', 'Why'],
        ['Python 3 + Flask', 'The web application (routes, pages, rules)', 'Simple, readable, well documented, the team\'s strongest language'],
        ['Jinja2 templates', 'HTML pages', 'Comes with Flask; escapes user text automatically (prevents XSS)'],
        ['SQLAlchemy', 'Database access', 'Same code on MySQL and PostgreSQL; parameterised queries (no SQL injection)'],
        ['MySQL (local) / PostgreSQL on Supabase (online)', 'Data', 'Free, reliable relational databases'],
        ['Supabase Storage', 'Private files (IDs, receipts, photos)', 'Free private bucket; files survive server restarts'],
        ['Vercel', 'Hosting', 'Free tier, deploys from GitHub, HTTPS by default'],
        ['PayMongo (QR Ph)', 'Online payments and refunds', 'Philippine gateway: GCash, Maya and bank apps by QR; signed webhooks'],
        ['Brevo', 'Email', 'Free tier for password reset and notifications'],
        ['Leaflet + OpenStreetMap', 'Maps and pins', 'Free maps; real Tacloban City boundary check'],
        ['Flask-WTF, Talisman, Flask-Limiter, bcrypt', 'Security', 'CSRF tokens, security headers/CSP, rate limits, password hashing'],
        ['fpdf2', 'Service report PDFs', 'Pure-Python PDF generation'],
        ['jsQR, Tesseract.js', 'Reading IDs in the browser', 'Fill the roster/registration from a PhilSys QR or printed text'],
        ['HTML, CSS, JavaScript', 'Responsive glass design, live updates', 'No heavy framework: fast and easy to explain'],
        ['pytest, Playwright', 'Testing', 'Automated tests on a fresh database; real-browser checks'],
    ], (45, 50, 75), size=8)

    pdf.h2('4.1 Why each one is crucial to the website')
    pdf.para('Each part of the stack does a job the website cannot work without. If it were taken away, this is what '
             'would break:')
    pdf.data_table([
        ['Technology', 'Why it is crucial', 'Without it'],
        ['Python + Flask', 'Runs every page and rule: bookings, the fee check, who may see what, release only after '
                           'payment. All the business rules live on the server where users cannot change them.',
         'No website; rules in the browser could be bypassed'],
        ['Jinja2 templates', 'Builds each page for the signed-in user and escapes everything people type.',
         'A name like <script> could run code in other users\' browsers (XSS)'],
        ['SQLAlchemy', 'The only way the code talks to the database; always uses parameters, and lets one code base run on '
                       'MySQL and PostgreSQL.', 'Hand-written SQL open to SQL injection; two code versions'],
        ['PostgreSQL (Supabase) / MySQL', 'Keeps accounts, bookings, payments and logs safely, with unique rules and '
                                          'transactions so two people cannot take the last slot or pay twice.',
         'Data lost on restart; double bookings and payments'],
        ['Supabase Storage', 'Private place for ID photos, payment screenshots and repair photos that survives restarts.',
         'Files lost when the server restarts, or left in a public folder'],
        ['Vercel', 'Puts the site on the internet over HTTPS without managing a server.', 'Only reachable on the developer\'s PC'],
        ['PayMongo QR Ph', 'Takes the booking fee and bills by GCash, Maya or bank apps and confirms them automatically; '
                           'signed webhooks prove the payment is real.', 'Every payment checked by hand from screenshots'],
        ['Brevo / Resend', 'Sends password-reset links and notifications by email.', 'Forgotten passwords cannot be reset'],
        ['Leaflet + OpenStreetMap', 'Customers pin their home for home service; the system checks it is inside Tacloban City.',
         'Wrong or out-of-area addresses'],
        ['Flask-WTF, Talisman, Flask-Limiter, bcrypt', 'Protection against forged forms, missing HTTPS, password guessing '
                                                       'and stolen password lists (see section 5).', 'Easy to attack'],
        ['pytest + Playwright', 'Prove that the rules work and keep working after every change.',
         'Bugs found by users instead of by tests'],
    ], (36, 92, 42), size=7.6)

    pdf.h1('5. Security: database, user accounts and the website')
    pdf.para('Security is built in three layers: the database that stores everything, the accounts people sign in with, '
             'and the website that sits in between. Each item below is what the code actually does.')
    pdf.h2('5.1 Database security')
    pdf.bullets([
        ('No secrets in the code.', 'The database address and password (DATABASE_URL) and the SECRET_KEY are read from '
                                    'environment variables (Vercel settings, or a local .env file that git ignores). The '
                                    'app refuses to start in production without a SECRET_KEY.'),
        ('No SQL injection.', 'Every query goes through SQLAlchemy with parameters; text typed by users is never pasted into '
                              'SQL.'),
        ('Passwords are never stored.', 'Only a bcrypt hash is saved. Even someone who copied the database could not read '
                                        'the passwords.'),
        ('Rules enforced by the database.', 'Unique emails, Tech IDs, booking and transaction numbers; foreign keys between '
                                            'bookings, payments and accounts.'),
        ('No race conditions with money.', 'A payment is confirmed, an approval answered or a booking fee used with one '
                                           'conditional UPDATE that only works once, so a double click or two tabs cannot '
                                           'confirm, answer or pay twice. A time slot is locked while a booking is saved.'),
        ('Separate account tables.', 'Customers, technicians and admins are in three tables; a customer account can never '
                                     'become an admin by changing a field.'),
        ('Private files.', 'ID photos and payment screenshots are not in the public website folder. They get random names, '
                           'are copied to a private Supabase Storage bucket with a server-only key, location data is removed '
                           'from phone photos, and they are deleted with the account.'),
        ('Sensitive data kept small.', 'ID numbers are never written to logs or notifications and are shown masked '
                                       '(•••• 3333) to the technician; every admin view of an ID is recorded in the activity log.'),
        ('Tests never touch real data.', 'The test suite uses a throw-away in-memory database.'),
    ])
    pdf.h2('5.2 User account security')
    pdf.bullets([
        ('Strong passwords.', 'At least 8 characters with a capital, a small letter, a number and a special character, '
                              'checked in the browser and again on the server.'),
        ('Password guessing stopped.', 'After 5 wrong passwords sign-in pauses for 10 seconds, doubling up to 15 minutes, '
                                       'even with the right password; plus a rate limit per IP. Unknown emails get the same '
                                       'answer, so attackers cannot find out who has an account.'),
        ('Safe sessions.', 'The session cookie is signed with the SECRET_KEY, is HttpOnly (scripts cannot read it), SameSite=Lax '
                           '(other sites cannot use it) and Secure in production (HTTPS only). It ends after 30 minutes idle '
                           'without "Remember me", at sign-out, and at once if an admin deactivates the account.'),
        ('Nothing left behind.', 'Account pages are sent with "no-store", so Back after sign-out shows the sign-in page, not '
                                 'a saved copy of the account.'),
        ('Safe password reset.', 'The emailed link is signed, expires after 1 hour and stops working once the password is '
                                 'changed. Asking for a reset never reveals whether the email exists.'),
        ('Roles checked on every page.', 'Customer, technician and admin pages each require their own role; technicians see '
                                         'only their own jobs; customers only their own bookings, receipts and chats.'),
        ('Trusted staff only.', 'Nobody can sign up as an admin: admin accounts are made by an existing admin in User '
                                'Management, from the command line, or with a one-time setup token. Technicians must match '
                                'the roster and be verified by an admin before they can sign in.'),
        ('Privacy (Data Privacy Act of 2012).', 'Consent before an ID is uploaded; customers can download their data or delete '
                                                'their account.'),
    ])
    pdf.h2('5.3 Website security')
    pdf.bullets([
        ('HTTPS everywhere.', 'In production every request is redirected to HTTPS and browsers are told to use HTTPS only '
                              '(HSTS).'),
        ('Content Security Policy.', 'The browser only runs scripts from the site and a few named sources, which blocks '
                                     'injected scripts. The technician portal uses a stricter per-page nonce.'),
        ('Forged forms blocked (CSRF).', 'Every form carries a secret token; a form submitted from another site is refused.'),
        ('Escaping.', 'Everything users type is escaped when shown, also inside scripts.'),
        ('Uploads checked.', 'Only allowed file types; the file\'s first bytes must match its type (a renamed .exe is '
                             'refused); size limits (5 MB for IDs and screenshots, 16 MB per request).'),
        ('Private files served through checks.', 'IDs and receipts are only sent to their owner, an admin, or the technician '
                                                 'on that job, never cached, and with "nosniff".'),
        ('Payments verified.', 'PayMongo webhooks must carry a valid signature, and a payment is accepted only for the exact '
                               'amount owed.'),
        ('No double submits.', 'Buttons lock after the first click, and the server refuses duplicates on its own.'),
        ('Rate limits.', 'Sign-in, password reset and other sensitive actions are limited per minute or per hour.'),
        ('Maintenance switch.', 'An admin can take the site offline for everyone except admins (Danger Zone, password and '
                                'typed phrase required).'),
    ])
    pdf.h2('5.4 How technicians\' IDs are kept safe online')
    pdf.para('Technicians upload a photo of a government ID (front and back) so the admin can confirm who they are. This '
             'is the most sensitive data in the system, so it is protected at every step:')
    pdf.bullets([
        ('Only with consent, only for hired staff.', 'The technician must agree to how the ID is used (Data Privacy Act '
                                                        'of 2012) before uploading. Registration only works for a person the '
                                                        'admin already recorded on the roster, so strangers cannot upload '
                                                        'IDs. One ID number can belong to one account only.'),
        ('The file is checked and cleaned.', 'Only JPG, PNG, WEBP or PDF up to 5 MB; the file\'s first bytes must '
                                                'match its type. Location (GPS) data is removed from phone photos.'),
        ('Stored where no web address reaches it.', 'Saved under a random 32-character name (never the original file '
                                                       'name), outside the public website folder, and never in GitHub. '
                                                       'On the live site it is copied to a private Supabase Storage bucket '
                                                       'that only the server can open, with a secret key.'),
        ('Shown only to the right people.', 'Only admins and the technician (while their registration is being '
                                               'checked) can open it. Customers and other technicians never can. Every '
                                               'time an admin opens an ID, the activity log records who and when.'),
        ('Sent safely.', 'Only over HTTPS, marked "no-store, private" so the browser does not keep a copy, and '
                            '"nosniff" so it cannot be run as a script.'),
        ('The ID number is hidden.', 'Shown masked (•••• and the last 4 characters) on the technician\'s status page, '
                                        'and never written in logs, notifications or emails.'),
        ('No outside scanning service.', 'When the admin scans an ID on the roster, the text is read inside the admin\'s '
                                            'own browser (Tesseract.js). The photo is not sent to any outside service.'),
        ('Deleted with the account.', 'Deleting the account removes both sides of the ID. Testing found that the back '
                                         'side was being left behind (bug B-03); it was fixed and a test guards it.'),
    ])
    pdf.para('Tested by TC-27 to TC-30 and TC-32 in the Testing Documentation, plus the tests for consent, for the ID number '
             'never appearing in notifications, and for deletion.', size=9.5, color=MUTED)
    pdf.callout('Honest limits', 'The app does not encrypt the ID files or the ID numbers itself: files rely on the '
                'storage provider\'s protection, and ID numbers are plain text in the database, readable by anyone with '
                'database access. IDs are kept until the account is deleted. See 5.5 for the fixes we would add.', WARN)

    pdf.h2('5.5 What we would still improve (honest list)')
    pdf.bullets([
        'Encrypt ID numbers in the database and ID files before storing them, and delete ID photos a set time after the '
        'technician is verified.',
        'Turn on Row Level Security for every table in Supabase. The app only connects from the server, but RLS would also '
        'block Supabase\'s automatic web API if its public key were ever used.',
        'Enable "Enforce SSL" for database connections in Supabase, and keep regular database backups.',
        'Two-step verification (a code sent by email) for admin accounts.',
        'Error monitoring and alerts for repeated failed sign-ins.',
        'An outside security review or penetration test before a real launch.',
    ])

    pdf.h1('6. How we tested the website')
    final = 'all passed' if not failed else f'{total - failed} passed, {failed} failed'
    pdf.bullets([('Automated tests:', f'{total} tests with pytest. Each test starts with an empty in-memory database, so results do '
                                      f'not depend on each other. Final run: {final}.'),
                 ('Browser tests:', 'Playwright drives Microsoft Edge through real flows (sign-in, booking, payment, orders, '
                                    'double clicks).'),
                 ('Security tests:', 'every fixed security bug keeps a test (access control, escaping, lockout, caching).'),
                 ('Accessibility:', 'WCAG 2.1 AA contrast, labels, names, language and reflow measured on 13 pages.'),
                 ('Live website:', 'read-only checks of the deployed site over the internet: every public page, '
                                   'HTTPS, security headers, CSRF, desktop and phone layout (Testing Documentation 4.2).'),
                 ('Methods:', 'functional, unit, integration, end-to-end, regression, API, security, validation, '
                              'live-site and manual testing; black-box and white-box tests designed with equivalence '
                              'partitioning and boundary values (Testing Documentation, sections 2.6 and 2.7).'),
                 ('Honesty:', 'failed and unfinished checks and open issues are written down in the Testing Documentation.')])
    pdf.callout('Tip for the defense', 'Bring the Testing Documentation. If asked "did anything fail?", say yes for the bugs '
                'found during development (sections 5 and 6 of the Testing Documentation) and explain the fix and the test '
                'that now guards it. Name the open '
                'issues before the panel finds them.', NAVY)

    pdf.h1('7. Possible defense questions and suggested answers')
    for i, (q, a) in enumerate(QUESTIONS, 1):
        pdf.h3(f'{i}. {q}')
        pdf.para(a.replace('{N}', str(total)), size=9.8)
    pdf.h1('8. Quick facts to remember')
    pdf.data_table([['Item', 'Value'],
                    ['Portals', 'Customer, Technician, Admin'],
                    ['Booking fee', 'PHP 100 by default (set in Settings), deducted from the bill'],
                    ['Slots', 'Hourly, 8 AM to 5 PM, 5 bookings per hour, up to the set days ahead'],
                    ['Sign-in lockout', '5 tries; 10 s pause doubling up to 15 min'],
                    ['Idle timeout', '30 minutes (7 days with "Remember me")'],
                    ['Automated tests', f'{total}, ' + ('all passing in the final run' if not failed
                                                         else f'{failed} failing in the final run')],
                    ['Hosting', 'Vercel + Supabase (PostgreSQL, Storage) + Brevo'],
                    ['Payments', 'PayMongo QR Ph; shop QR + screenshot; cash after repair']], (50, 120))
    out = os.path.join(os.environ.get('DOCS_OUT') or HERE, 'DEVTech_Defense_Reviewer.pdf')
    pdf.output(out)
    return out


if __name__ == '__main__':
    suite, cases = load_tests()
    print(build_testing(suite, cases, load_a11y()))
    print(build_reviewer(len(cases), sum(c['status'] == 'Fail' for c in cases)))
