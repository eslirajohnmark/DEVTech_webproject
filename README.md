# DEVTech Web

Computer repair shop management system — customer portal, technician portal, and admin panel, all in one Flask application.

---

## Overview

- **Customer portal** (`/user/*`) — book repairs, buy parts from the shop, monitor repair progress in real time, approve or decline extra work the technician finds, message support and their technician (with image/PDF attachments), open support tickets, rate completed jobs
- **Technician portal** (`/technician/*`) — view assigned jobs, record device intake, write diagnoses and service reports, ask the customer to approve extra work or cost (the job waits on hold until they answer), file safety incidents
- **Admin panel** (`/admin/*`) — assign jobs, confirm payments, manage users, products and stock, services and prices, shop orders, support tickets and website inquiries, a messages inbox, technician activity (incidents, approvals, reports, ratings), analytics and settings
- **Public home page** — the contact form saves inquiries to the admin Support page

Everything shares one database. A job assigned in the admin panel appears instantly on the technician's dashboard. A technician marking it complete updates the customer's monitor page within 20 seconds.

---

## Stack

- **Backend** — Flask 3.1, Flask-SQLAlchemy, Flask-WTF (CSRF), Flask-Limiter (rate limits), Flask-Caching, Flask-Talisman (security headers)
- **Database** — MySQL (production) or SQLite (development)
- **Frontend** — server-rendered Jinja templates. Vanilla JavaScript as ES modules. No build step. No npm. No bundler.
- **Auth** — bcrypt password hashing, signed-cookie sessions re-checked against the database on every request, optional Google/Facebook OAuth (customers only, verified email required)
- **Uploads** — type-whitelisted and signature-checked, size-capped, stored under `instance/` and served through authenticated routes only

---

## Local setup

### Prerequisites

- Python 3.10 or newer
- MySQL 8 (or MariaDB 10.5+). SQLite also works but is not recommended past initial testing.
- Git

### Steps

```bash
# 1. Clone
git clone <your-repo-url>
cd DEVTech_Webproject

# 2. Virtual environment
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS / Linux:
source .venv/bin/activate

# 3. Dependencies
pip install -r requirements.txt

# 4. Environment
cp .env.example .env
# Open .env and edit DATABASE_URL to match your MySQL setup.
# Generate a real SECRET_KEY:
python -c "import secrets; print(secrets.token_urlsafe(64))"
# Paste the output into .env as SECRET_KEY=...

# 5. Database (creates the `devtech` database and every table)
mysql -u root -p < database/schema.sql
# or, with an empty database already created:  flask --app app upgrade-db

# 6. Create the first admin
flask --app app create-admin
# Prompts for email, full name, password. Password is hidden.

# 7. (Optional) default service categories with icons and colours
python -m scripts.seed_service_categories

# 8. Run
python app.py
```

Open `http://localhost:5000`.

For HTTPS locally (needed for testing Google OAuth callbacks):

```bash
DEV_SSL=1 python app.py
```

The first request will show a browser warning about the self-signed certificate. That's expected — accept it once per session.

---

## Keyboard shortcuts

Every page in the app supports these (including sign-in pages and while typing in a field). Each opens that portal's dashboard if you are already signed in there, or its sign-in page if not. Pressing the key for the portal you are already on does nothing.

| Keys | Goes to | Works from |
|---|---|---|
| `Ctrl+Shift+L` | Admin portal | customer and technician pages |
| `Ctrl+Shift+Y` | Technician portal | customer and admin pages |
| `Ctrl+Shift+U` | Customer portal | admin and technician pages |

All three are handled in one place, `static/js/portal-shortcuts.js`, through the `/go/<side>` route. The landing page footer also has a visible "Technician Sign-In" link, so the shortcuts are discoverable but not required.

## Live updates

Pages update on their own; nobody needs to press refresh. Every open page asks `/api/live` every 4 seconds (every 30 seconds while the tab is in the background) for unread counts and a fingerprint of the data that account can see.

- Unread message and notification badges, the bell and the tab title (`(3) DEVTech · …`) update immediately, and new messages and notifications pop up in the corner.
- Message inboxes (customer, technician, admin) swap the conversation list and the open chat in place, so a half-written reply is never lost.
- Other pages refresh themselves when their data changes, keeping the scroll position, but only while you are idle. If you are typing, have a dialog open or have unsaved changes, an "Updates available · Refresh" button appears instead.

The browser side is `static/js/live.js` and `static/css/live.css`; the server side is `live_state()` and `/api/live` in `app.py`.

---

## Accounts

There are no demo or default accounts. Customers, technicians and admins are
three separate tables (`customers`, `technicians`, `admins`), each with its own
email and password, so an account's type can't be changed later; create a new
account of the other type instead. An email can belong to only one account.

- **Admin:** created with `flask --app app create-admin`.
- **Technicians:** register at `/technician/register`; an admin activates them in User Management (or an admin adds them there directly).
- **Customers:** sign up at `/register`.

## Shop data

The shop starts empty. Add products, prices and stock in **Admin > Products**, services and prices in **Admin > Services & Prices**, and the shop's phone, email, address, hours and GCash details in **Admin > Settings** (anything left blank is hidden from customers).

---

## Directory layout

```
DEVTech_Webproject/
├── app.py                  Flask app, routes, ORM models
├── commands.py             Flask CLI commands (admin management)
├── wsgi.py                 Production entry point (gunicorn)
├── requirements.txt
├── .env                    Real secrets — gitignored
├── .env.example            Template — committed
│
├── blueprints/             Route groups
│   ├── technician.py       Technician page routes
│   └── technician_api.py   Technician JSON API
│
├── models/                 Technician-side ORM models
├── services/               Business logic
├── scripts/                Seed and maintenance scripts
├── database/               schema.sql and migrations
│
├── static/
│   ├── css/                Stylesheets
│   ├── js/                 JavaScript (vanilla ES modules)
│   ├── images/
│   └── data/               GeoJSON boundary data
│
├── templates/              Jinja templates
│   ├── admin/              Admin panel
│   ├── user/               Customer portal
│   ├── technician/         Technician portal
│   └── errors/             404, 500
│
├── tests/                  pytest suite
├── instance/uploads/       User-uploaded files (gitignored)
└── logs/                   Rotating log files (gitignored)
```

---

## Upgrading an existing install

If you ran an older version of this app, do these once:

1. **Default admin.** Older versions created `admin@devtech.com` / `admin123` automatically. If that account exists, change its password now (`flask --app app reset-admin-password admin@devtech.com`) or deactivate it.
2. **Cart stock.** Stock used to be taken when an item was added to a cart; it is now taken at checkout. Return what open carts were holding with `flask --app app release-cart-stock` (runs once; `python app.py` also does it automatically).
3. **Receipts.** Payment receipts moved from `static/uploads/receipts/` (publicly reachable) to `instance/uploads/receipts/`. `python app.py` moves existing files automatically; on a server that only runs `wsgi.py`, move the folder by hand.
4. **Technician sign-up.** Self-registered technicians now start inactive. Admins get a notification and activate them in User Management.
5. **`.env`.** `DATABASE_URL` is now required (no built-in fallback), and `/setup/first-admin` is disabled unless `SETUP_TOKEN` is set.
6. **Separate account tables.** Older databases kept everyone in one `users` table. Copy such a database into the new layout with
   `python -m scripts.migrate_split_accounts --source mysql+pymysql://root@127.0.0.1:3306/devtech_db --target mysql+pymysql://root@127.0.0.1:3306/devtech`
   (backs up the source first and never changes it), then point `DATABASE_URL` at the new database.
7. **New tables.** Run `flask --app app upgrade-db` (safe to repeat; run it on every deploy). It creates new tables such as `contact_inquiries`, adds new columns, moves old receipts and does the cart-stock fix above. It never adds demo data.

---

## Tests

```bash
pytest tests/ -v
```

The test suite runs against an in-memory SQLite database. Your MySQL data is never touched. Every test starts with a clean database and ends with it destroyed.

What's covered:

- Technician login, logout, wrong password, deactivated account
- Cross-technician ownership (a tech cannot see another tech's job)
- CSRF enforcement on state-changing endpoints
- Upload MIME whitelist, size cap, and download ownership
- Login rate limiting (5 attempts per minute)
- Dynamic config endpoint shape
- End-to-end workflow: intake → diagnosis → report → release, with the guards between each step
- Security regressions: script-safe `tojson`, OAuth linking rules, sign-out of deactivated accounts, receipt access, upload signature checks
- Shop: cart quantity validation, checkout stock deduction, admin order and payment status sync

---

## Security posture

| Layer | What's in place |
|---|---|
| Passwords | bcrypt via Flask-Bcrypt |
| Sessions | Signed cookies, `HttpOnly`, `SameSite=Lax`, `Secure` in production; deactivated or deleted accounts are signed out on their next request |
| CSRF | Flask-WTF on every state-changing route |
| Rate limits | Customer, admin and technician login and registration, per-IP |
| Uploads | Type whitelist + file-signature check, 5–8 MB caps, kept outside `static/`; receipts are owner/admin-only, message attachments are sender/recipient-only |
| Headers | HSTS, X-Frame-Options, `Content-Security-Policy` per-route |
| CSP | Strict nonce policy on `/technician/*`; relaxed on admin/user routes that still use inline handlers |
| SQL | Parameterised through SQLAlchemy; no string concatenation |

---

## Deployment

See `DEPLOY.md`. Two paths are documented end to end:

- **PythonAnywhere** — simplest, ~30 minutes, no domain required
- **VPS + Gunicorn + Nginx + Let's Encrypt** — full production, ~2–3 hours, custom domain

---

## License

Proprietary.