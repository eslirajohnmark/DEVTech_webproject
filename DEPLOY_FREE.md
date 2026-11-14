# Deploy DEVTech for free

Two free ways to put DEVTech online. Read the table, pick one, and follow only that part.
(The paid/VPS options are in [DEPLOY.md](DEPLOY.md).)

| | **Path A: PythonAnywhere** | **Path B: Render + Supabase + Brevo** |
|---|---|---|
| Web address | `https://YOURNAME.pythonanywhere.com` | `https://YOURNAME.onrender.com` |
| Database | SQLite file on the server | Supabase PostgreSQL (500 MB free) |
| Uploaded photos, ID documents, report PDFs | **Kept** on the server | **Kept** in Supabase Storage (1 GB free) |
| QR payments (PayMongo) | **Off** until PythonAnywhere adds PayMongo to its allowlist (you request it) | **Work** |
| Emails | Off until allowlisted | **Work** through Brevo (300 a day free) |
| Speed | Always awake | Sleeps after 15 minutes without visitors; the first visit after that takes about a minute (B7 keeps it awake) |
| Your effort to keep it up | Click one button once a month | Nothing, if you set up the free monitor in B7 |

**Which one?**
- **Path B** gives you everything: QR payments, emails, kept uploads. It takes about an hour across three websites.
- **Path A** is the quickest (about 30 minutes, one website) if you only need to show the system and can live without QR payments and emails.

Free plans change often. These limits were checked in November 2026; if a page looks different, follow what the site shows.

---

## Step 0: on your PC (both paths)

1. **Push your latest code to GitHub.** Both hosts download it from
   `https://github.com/eslirajohnmark/DEVTech_Webproject`. In the project folder:
   ```
   git add -A
   git commit -m "Prepare for deployment"
   git push
   ```
   Your `.env`, `instance/` (database, uploads) and `logs/` are in `.gitignore`, so passwords and uploaded files are not pushed. Keep it that way: the repository is public.

2. **Make two random secrets** and paste them somewhere safe (not in GitHub):
   ```
   .venv\Scripts\python -c "import secrets; print(secrets.token_hex(32))"
   .venv\Scripts\python -c "import secrets; print(secrets.token_hex(16))"
   ```
   The first is your `SECRET_KEY`. The second is your `SETUP_TOKEN`: it opens the page that creates the first admin account.

---

## Path A: PythonAnywhere (free, files are kept)

### A1. Create the account
Sign up for the free **Beginner** plan at <https://www.pythonanywhere.com>. Your username becomes your web address, so choose it carefully (e.g. `devtechtacloban` → `devtechtacloban.pythonanywhere.com`).

Below, replace **`YOURNAME`** with that username.

### A2. Download the code
Open **Consoles → Bash** and run:
```bash
git clone https://github.com/eslirajohnmark/DEVTech_Webproject.git
cd DEVTech_Webproject
```

### A3. Install the packages
```bash
ls /usr/bin/python3.1*          # shows the Python versions you can use
mkvirtualenv devtech --python=python3.13    # use 3.14 if it is in the list
pip install -r requirements.txt
```
This takes a few minutes. The free plan has 512 MB of disk; DEVTech fits.

### A4. Create the settings file
```bash
nano .env
```
Paste this, fill in the two secrets from Step 0, then save (Ctrl+O, Enter, Ctrl+X):
```
FLASK_ENV=production
SECRET_KEY=paste-your-64-character-secret-here
DATABASE_URL=sqlite:////home/YOURNAME/DEVTech_Webproject/instance/devtech.db
APP_BASE_URL=https://YOURNAME.pythonanywhere.com
SETUP_TOKEN=paste-your-setup-token-here
BEHIND_PROXY=1
LIVE_MAX_WAITERS=0
PAYMONGO_ENABLED=false
```
- `DATABASE_URL` has **four** slashes after `sqlite:`.
- `LIVE_MAX_WAITERS=0` matters: the free plan has one web worker, and live updates would otherwise hold it busy.
- With `PAYMONGO_ENABLED=false` the booking form offers only C.A.R (Cash After Repair) and charges no booking fee, because the fee is paid by QR. See A9 to switch QR on later.

### A5. Create the database
```bash
mkdir -p instance
flask --app app init-db
```
You should see `Database ready.` This creates the tables, the 166 services and the default settings (downtown shop, ₱100 booking fee).

### A6. Create the web app
1. Open the **Web** tab → **Add a new web app** → **Next**.
2. Choose **Manual configuration** (not "Flask") → pick the **same Python version** as in A3 → Next.
3. On the web app page set:
   - **Virtualenv:** `/home/YOURNAME/.virtualenvs/devtech`
   - **Static files:** URL `/static/` → Directory `/home/YOURNAME/DEVTech_Webproject/static`
   - **Force HTTPS:** on
4. Click the **WSGI configuration file** link, delete everything in it, and paste:
   ```python
   import sys
   path = '/home/YOURNAME/DEVTech_Webproject'
   if path not in sys.path:
       sys.path.insert(0, path)
   from wsgi import app as application
   ```
   Save.
5. Press the green **Reload** button, then open `https://YOURNAME.pythonanywhere.com`. You should see the DEVTech home page.

### A7. Create the first admin
Open (with your own values):
```
https://YOURNAME.pythonanywhere.com/setup/first-admin?token=YOUR_SETUP_TOKEN
```
Fill in the form. After the first admin exists, this page stops working on its own. Then sign in at `/admin/login`.

### A8. Check the shop details
Sign in as admin → **Settings**. Set your real shop address, hours and phone, and use the shop's map pin. Save.

### A9. Turning on QR payments and emails (optional)
Free PythonAnywhere accounts can only reach websites on its allowlist. To use PayMongo and Brevo email:
1. Request them through PythonAnywhere's form (<https://help.pythonanywhere.com/pages/RequestingAllowlistAdditions/>): `api.paymongo.com` (docs <https://developers.paymongo.com>) and `api.brevo.com` (docs <https://developers.brevo.com>).
2. When they are added, set up Brevo as in **B3**, put these in `.env` and press **Reload**:
   ```
   PAYMONGO_ENABLED=true
   PAYMONGO_SECRET_KEY=sk_test_...
   PAYMONGO_PUBLIC_KEY=pk_test_...
   BREVO_API_KEY=xkeysib-...
   MAIL_FROM=DEVTech <your-verified-sender>
   ```
3. Add the PayMongo webhook (see **PayMongo webhook** below).

If a feature still fails, the error log (Web tab → Log files) shows `Tunnel connection failed: 403 Forbidden` for a site that is not allowed yet.

### A10. Keep it running
Free web apps stop after one month. Once a month, open the **Web** tab and press **Run until 1 month from today**.

### A11. Updating after you change the code
On your PC: commit and `git push`. Then in a PythonAnywhere Bash console:
```bash
cd ~/DEVTech_Webproject
git pull
workon devtech
pip install -r requirements.txt
flask --app app upgrade-db
```
Then **Reload** on the Web tab.

---

## Path B: Render + Supabase + Brevo (free, all features)

Three free accounts: **Supabase** keeps the database and the uploaded files, **Brevo** sends the emails, **Render** runs the website.

### B1. Supabase: the database
1. Sign up at <https://supabase.com> and create a **New project** on the Free plan.
   - **Database password:** use only letters and numbers (symbols like `@ : / ?` break the link below). Save it.
   - **Region:** Southeast Asia (Singapore), the closest to Tacloban.
2. When the project is ready, click **Connect** (top of the dashboard) → choose **Session pooler**. Copy the link. It looks like:
   ```
   postgresql://postgres.abcdefghijkl:[YOUR-PASSWORD]@aws-0-ap-southeast-1.pooler.supabase.com:5432/postgres
   ```
   Replace `[YOUR-PASSWORD]` with your password. This is your `DATABASE_URL`.
   Use **Session pooler**, not "Direct connection": Render cannot reach the direct one.

### B2. Supabase: storage for uploaded files
1. In the same project open **Storage → New bucket**. Name it `devtech-uploads` and leave **Public bucket off** (private: photos and ID documents must not be public).
2. Open **Project Settings → API Keys**. Create (or copy) a **secret key**; it starts with `sb_secret_`. This is your `SUPABASE_SECRET_KEY`. Never put it in GitHub or in a web page.
3. Your `SUPABASE_URL` is `https://abcdefghijkl.supabase.co` (shown in Project Settings → Data API; the same `abcdefghijkl` as in the database link).

### B3. Brevo: emails
1. Sign up at <https://www.brevo.com> (free plan: 300 emails a day).
2. **Senders, Domains & Dedicated IPs → Senders → Add a sender**: enter the name `DEVTech` and the email address customers will see, then confirm the code Brevo sends to that address. Brevo may ask you to complete your profile before it lets you send.
3. **SMTP & API → API keys → Generate a new API key**. It starts with `xkeysib-`. This is your `BREVO_API_KEY`.
4. Your `MAIL_FROM` is `DEVTech <the-sender-address-you-verified>`.

Emails sent from a free address (like Gmail) through Brevo can land in spam. If you own a domain, add it under **Domains** and follow Brevo's steps; then use an address on that domain as the sender.

### B4. Render: the website
1. Sign up at <https://render.com> with your GitHub account.
2. **New → Web Service** → choose the `DEVTech_Webproject` repository.
3. Fill in:
   - **Name:** e.g. `devtech-tacloban` (your address becomes `https://devtech-tacloban.onrender.com`)
   - **Region:** Singapore
   - **Branch:** `main`
   - **Runtime:** Python 3
   - **Build Command:**
     ```
     pip install -r requirements.txt && flask --app app init-db
     ```
   - **Start Command:**
     ```
     gunicorn wsgi:app --bind 0.0.0.0:$PORT --worker-class gthread --workers 1 --threads 8 --timeout 120
     ```
   - **Instance Type:** Free
4. Under **Environment Variables**, add:

   | Key | Value |
   |---|---|
   | `PYTHON_VERSION` | `3.14.2` (the same as `python --version` on your PC; if the build says it is not available, use `3.13.9`) |
   | `FLASK_ENV` | `production` |
   | `SECRET_KEY` | your 64-character secret |
   | `DATABASE_URL` | the Supabase Session pooler link from B1 |
   | `SUPABASE_URL` | from B2 |
   | `SUPABASE_SECRET_KEY` | from B2 (`sb_secret_...`) |
   | `SUPABASE_BUCKET` | `devtech-uploads` |
   | `BREVO_API_KEY` | from B3 (`xkeysib-...`) |
   | `MAIL_FROM` | `DEVTech <your-verified-sender>` |
   | `APP_BASE_URL` | `https://devtech-tacloban.onrender.com` (your own name) |
   | `SETUP_TOKEN` | your setup token |
   | `BEHIND_PROXY` | `1` |
   | `LIVE_MAX_WAITERS` | `4` |
   | `PAYMONGO_ENABLED` | `true` |
   | `PAYMONGO_SECRET_KEY` / `PAYMONGO_PUBLIC_KEY` | your PayMongo keys (test keys while testing) |
   | `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` | only if you use Google sign-in |
   | `FACEBOOK_CLIENT_ID` / `FACEBOOK_CLIENT_SECRET` | only if you use Facebook sign-in |

5. Click **Create Web Service**. Watch the log: the build ends with `Database ready.` (the tables, 166 services and default settings now exist in Supabase), and the start shows `Listening at`. Then open your address.

### B5. Create the first admin
```
https://devtech-tacloban.onrender.com/setup/first-admin?token=YOUR_SETUP_TOKEN
```
Then sign in at `/admin/login` and check **Settings** (shop address, hours, booking fee).

### B6. Check that files are kept
Upload a profile photo, then in Render click **Manual Deploy → Restart service**. After it restarts the photo still shows: it comes back from Supabase Storage. You can see the files in Supabase under **Storage → devtech-uploads**.

### B7. Keep it awake (recommended)
Two free-plan behaviours: Render puts the site to sleep after 15 minutes without visitors, and Supabase **pauses a free project after 7 days without database activity** (you then have to press "Restore" in Supabase).
A free uptime monitor fixes both:
1. Sign up at <https://uptimerobot.com> (free).
2. **New monitor → HTTP(S)**, URL `https://devtech-tacloban.onrender.com/healthz`, every **10 minutes**.

`/healthz` asks the database a tiny question, so Supabase sees activity and Render stays awake. One always-awake service uses about 744 of Render's 750 free hours a month, so run only this one free service.

### B8. Updating after you change the code
Commit and `git push` on your PC. Render rebuilds and redeploys by itself (the build runs `init-db`, which is safe to repeat). Uploaded files and data are not affected.

---

## Both paths: after the site is up

### PayMongo webhook (when QR payments are on)
PayMongo Dashboard → **Developers → Webhooks → Add**:
- URL: `https://YOUR-ADDRESS/paymongo/webhook`
- Events: `payment.paid` and `checkout_session.payment.paid`

Copy its secret (`whsk_...`) into `PAYMONGO_WEBHOOK_SECRET` (`.env` on PythonAnywhere, then Reload; Environment on Render). Payments are then confirmed even when the customer closes the QR window.

Use **test keys** (`sk_test_...`) until PayMongo approves your account for live payments, then swap in the live keys.

### Google / Facebook sign-in (optional)
Add the new address to each provider, exactly:
- Google Cloud Console → Credentials → your OAuth client → **Authorized redirect URIs**: `https://YOUR-ADDRESS/login/google/callback`
- Facebook for Developers → Facebook Login → **Valid OAuth Redirect URIs**: `https://YOUR-ADDRESS/login/facebook/callback`

### Final check
1. Register a customer account and book an in-shop repair.
2. Book a home-service repair: the map shows the red Tacloban City line, and a pin outside it is refused.
3. Sign in as admin, assign the booking to a technician, and as the technician submit a service report with a photo; the admin opens it as a PDF.
4. Ask the FAQ chatbot on the Support page a question.
5. With QR on: pay a booking fee with PayMongo's test QR and check it turns "Confirmed".

---

## If something goes wrong

| What you see | Fix |
|---|---|
| `DATABASE_URL is not set` | The variable is missing or misspelled (`.env` on PythonAnywhere, Environment on Render). |
| `SECRET_KEY is not set` | Production needs it. Add the 64-character secret. |
| Page has no styles (PythonAnywhere) | The Static files row in A6 is missing or the path is wrong. Reload after fixing. |
| `Tunnel connection failed: 403` (PythonAnywhere) | That website is not on the free allowlist. Request it (A9) or keep that feature off. |
| `Network is unreachable` or a timeout to `db.xxxx.supabase.co` | You used Supabase's Direct connection. Use the **Session pooler** link (B1). |
| `password authentication failed` (Supabase) | Wrong password, or the user is not `postgres.yourprojectref` as in the Session pooler link. |
| Site cannot reach the database after a quiet week | Supabase paused the project. Open Supabase and press **Restore**, then set up B7. |
| Photos show as broken after a restart (Path B) | `SUPABASE_URL`, `SUPABASE_SECRET_KEY` or the bucket name is wrong, or the bucket does not exist. Render's log shows `Supabase Storage refused ...`. |
| Emails do not arrive | Check Brevo → Transactional → Logs. The sender in `MAIL_FROM` must be verified in Brevo; check the spam folder. |
| Google says `redirect_uri_mismatch` | Add the exact callback address above, and make sure `BEHIND_PROXY=1` is set. |
| `/setup/first-admin` shows "Not Found" | An admin already exists, or the token in the address does not match `SETUP_TOKEN`. |
| Site very slow, then fine (Render) | It was asleep (B4). |

Logs: PythonAnywhere → Web tab → **Error log**. Render → your service → **Logs**. Supabase → **Logs**. Brevo → **Transactional → Logs**.
