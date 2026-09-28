# DEVTech Web

Computer repair shop management system — customer portal, technician portal, and admin panel, all in one Flask application.

---

## Overview

- **Customer portal** (`/user/*`) — book repairs, buy parts from the shop, monitor repair progress in real time, chat with support, rate completed jobs
- **Technician portal** (`/technician/*`) — view assigned jobs, record device intake, write service reports, file safety incidents
- **Admin panel** (`/admin/*`) — assign jobs, confirm payments, manage users, view analytics, adjust system settings

Everything shares one database. A job assigned in the admin panel appears instantly on the technician's dashboard. A technician marking it complete updates the customer's monitor page within 20 seconds.

---

## Stack

- **Backend** — Flask 2.3, Flask-SQLAlchemy, Flask-WTF (CSRF), Flask-Limiter (rate limits), Flask-Caching, Flask-Talisman (security headers)
- **Database** — MySQL (production) or SQLite (development)
- **Frontend** — server-rendered Jinja templates. Vanilla JavaScript as ES modules. No build step. No npm. No bundler.
- **Auth** — bcrypt password hashing, server-side sessions, optional Google/Facebook OAuth
- **Uploads** — MIME-whitelisted, size-capped, served through authenticated routes only

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

# 5. Database
mysql -u root -p < database/schema.sql
mysql -u root -p devtech_db < database/migrate_service_categories.sql
mysql -u root -p devtech_db < database/migrate_ratings.sql

# 6. Create the first admin
flask --app app create-admin
# Prompts for email, full name, password. Password is hidden.

# 7. Seed demo data (optional)
python -m scripts.seed_technician
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

Every page in the app supports these. They are no-ops if you're already on the target page, and they do not fire while a text field has focus.

| Keys | Destination |
|---|---|
| `Ctrl+Shift+L` | Admin login |
| `Ctrl+Shift+T` | Technician login |
| `Ctrl+Shift+R` | Technician registration |

The landing page footer also has a visible "Technician Sign-In" link, so the shortcut is discoverable but not required.

---

## Demo accounts

Seeded by `scripts/seed_technician.py`:

| Role | Username | Password |
|---|---|---|
| Technician | `TECH-0001` | `1234` |
| Technician | `TECH-0002` | `1234` |
| Customer | `customer1` | `customer1234` |

The admin account is whatever you created with `flask create-admin`. There is no default admin.

**Change every one of these before any deployment that leaves your laptop.**

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
- End-to-end workflow: assign → advance → intake → report → incident

---

## Security posture

| Layer | What's in place |
|---|---|
| Passwords | bcrypt via Flask-Bcrypt |
| Sessions | Server-side, `HttpOnly`, `SameSite=Lax`, `Secure` in production |
| CSRF | Flask-WTF on every state-changing route |
| Rate limits | Login and registration, per-IP |
| Uploads | MIME whitelist, 8 MB cap, authenticated download |
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