# Deploy DEVTech for free: Vercel + Supabase + Brevo

DEVTech is an **educational project**, so it can use the free plans of these three services. (Vercel's free *Hobby* plan is for personal, non-commercial use only.)

| Service | What it does for DEVTech | Free plan |
|---|---|---|
| **Vercel** | Runs the website | Hobby |
| **Supabase** | Keeps the database and the uploaded files (photos, IDs, report PDFs) | 500 MB database, 1 GB files |
| **Brevo** | Sends the emails (notifications, password resets) | 300 emails a day |

Time needed: about 1 hour. You need your GitHub account with the DEVTech repository, and a notepad to keep the keys you collect.

---

## The keys you will collect

Fill this in as you go. **Keep it private**: never paste these into GitHub, chat or a web page.

| Name | Where it comes from |
|---|---|
| `SECRET_KEY` | Part 1 |
| `SETUP_TOKEN` | Part 1 |
| Database password | Part 2, step 1 |
| Transaction pooler link (port 6543) | Part 2, step 2 |
| Session pooler link (port 5432) | Part 2, step 2 |
| `SUPABASE_URL` | Part 2, step 4 |
| `SUPABASE_SECRET_KEY` | Part 2, step 4 |
| `BREVO_API_KEY` | Part 3, step 3 |
| `MAIL_FROM` | Part 3, step 2 |

---

## Part 1: On your PC

1. **Install the packages** (includes the PostgreSQL driver for Supabase). In the project folder:
   ```powershell
   .venv\Scripts\pip install -r requirements.txt
   ```
2. **Make two random secrets:**
   ```powershell
   .venv\Scripts\python -c "import secrets; print(secrets.token_hex(32))"
   .venv\Scripts\python -c "import secrets; print(secrets.token_hex(16))"
   ```
   The first is your `SECRET_KEY`, the second your `SETUP_TOKEN` (it unlocks the page that creates the first admin).
3. **Push the code to GitHub.** Vercel deploys from there.
   ```powershell
   git add -A
   git commit -m "Deploy to Vercel"
   git push
   ```
   Your `.env`, `instance/` and `logs/` are not pushed; `.gitignore` keeps them out.

---

## Part 2: Supabase (database and files)

1. **Create the project.** Sign up at <https://supabase.com> → **New project**:
   - **Name:** `devtech`
   - **Database password:** letters and numbers only (symbols such as `@ : / ?` break the links below). Write it down.
   - **Region:** Southeast Asia (Singapore)
   - **Plan:** Free

   Wait until the project is ready (a few minutes).

2. **Copy the two database links.** Click **Connect** at the top of the project → **Connection string**:
   - **Transaction pooler** (port **6543**) → copy. This one is for **Vercel**.
   - **Session pooler** (port **5432**) → copy. This one is for **your PC** in Part 4.

   In both, replace `[YOUR-PASSWORD]` with your database password.
   Do **not** use "Direct connection"; Vercel cannot reach it.

3. **Create the file storage.** **Storage** → **New bucket**:
   - **Name:** `devtech-uploads`
   - **Public bucket:** **off** (private: technicians' ID documents are stored here).

4. **Copy the project address and a secret key.** **Project Settings** → **API Keys**:
   - Copy a **secret key** (starts with `sb_secret_`; create one if none is listed). This is `SUPABASE_SECRET_KEY`. It gives full access to your project, so keep it private.
   - Your project address is `https://<project-ref>.supabase.co`, where `<project-ref>` is the code in your database links (the part after `postgres.`). This is `SUPABASE_URL`.

---

## Part 3: Brevo (emails)

1. Sign up at <https://www.brevo.com> on the Free plan. Brevo may ask you to complete your profile before you can send.
2. **Add a sender.** **Senders, Domains & Dedicated IPs** → **Senders** → **Add a sender**:
   - **From name:** `DEVTech`
   - **From email:** an address you can open.

   Confirm it with the code Brevo emails you. Your `MAIL_FROM` is `DEVTech <that-address>`.
3. **Create an API key.** **SMTP & API** → **API Keys** → **Generate a new API key**, name it `devtech-vercel`, and copy it (starts with `xkeysib-`). This is `BREVO_API_KEY`.

Emails sent from a free address (Gmail, Yahoo) may land in spam. For a class project, just check the spam folder.

---

## Part 4: Create the database tables (once, from your PC)

Vercel has no command line, so the tables are created from your PC, straight into Supabase. In PowerShell, in the project folder, using **your Session pooler link**:

```powershell
$env:DATABASE_URL = "postgresql://postgres.abcd:YOURPASSWORD@aws-0-ap-southeast-1.pooler.supabase.com:5432/postgres"
.venv\Scripts\flask --app app init-db
```

You should see `Database ready.` Supabase now has the tables, the 166 services, the ₱100 booking fee and the shop settings (check Supabase → **Table Editor**).

The `$env:DATABASE_URL` line only lasts in that PowerShell window; your local `.env` and database are not changed. Close the window afterwards.

---

## Part 5: Vercel (the website)

1. Sign up at <https://vercel.com> with your GitHub account (Hobby plan).
2. **Add New…** → **Project** → find `DEVTech_Webproject` → **Import**.
3. **Project Name:** e.g. `devtech-tacloban`. Your address will be `https://devtech-tacloban.vercel.app`.
   **Framework Preset:** Vercel picks **Flask** by itself (if it shows "Other", leave it). Leave the build settings as they are.
4. Open **Environment Variables** and add:

   | Key | Value |
   |---|---|
   | `FLASK_ENV` | `production` |
   | `SECRET_KEY` | from Part 1 |
   | `SETUP_TOKEN` | from Part 1 |
   | `DATABASE_URL` | the **Transaction pooler** link (port **6543**) |
   | `SUPABASE_URL` | from Part 2 |
   | `SUPABASE_SECRET_KEY` | from Part 2 |
   | `SUPABASE_BUCKET` | `devtech-uploads` |
   | `BREVO_API_KEY` | from Part 3 |
   | `MAIL_FROM` | from Part 3, e.g. `DEVTech <you@example.com>` |
   | `APP_BASE_URL` | `https://devtech-tacloban.vercel.app` (your own project name) |
   | `PAYMONGO_ENABLED` | `false` (see "QR payments" below to turn them on) |

5. Click **Deploy** and wait for it to finish. Open your address: you should see the DEVTech home page.

If Vercel gave your project a different address, change `APP_BASE_URL` in **Settings → Environment Variables**, then **Deployments → ⋯ → Redeploy**.

---

## Part 6: Create the first admin

1. Open (with your own values):
   ```
   https://devtech-tacloban.vercel.app/setup/first-admin?token=YOUR_SETUP_TOKEN
   ```
2. Fill in your name, email and a strong password. This page works only until the first admin exists.
3. Sign in at `/admin/login` → **Settings**. Check the shop address and hours, and the booking fee (₱100).

---

## Part 7: Check that everything works

- [ ] The home page and the sign-in pages load.
- [ ] Register a customer account (use an email address you can open).
- [ ] Upload a profile photo. It appears in Supabase → **Storage → devtech-uploads → avatars**.
- [ ] Book an in-shop repair. A "Booking Created" email arrives (check spam).
- [ ] Book a home-service repair: the map shows the red Tacloban City line, and a pin outside it is refused.
- [ ] Sign out, use **Forgot Password?** on the login page; the reset email arrives.
- [ ] As admin, assign the booking to a technician. As the technician, submit a service report with a photo; the admin opens it as a PDF.
- [ ] Ask the FAQ chatbot on the Support page a question.

---

## Keeping it running

- **Supabase pauses a free project after 7 days without use.** Open the website at least once a week. If it was paused, open Supabase and press **Restore**.
- **Updating the website:** change the code on your PC, then `git add -A`, `git commit -m "..."`, `git push`. Vercel deploys the new version by itself. If the change adds new database tables or columns, repeat **Part 4**. Your data and uploaded files stay in Supabase.

---

## QR payments (optional)

With `PAYMONGO_ENABLED=false`, bookings use C.A.R (Cash After Repair) and no booking fee is charged. To demonstrate QR payments with PayMongo's **test** keys (no real money moves):
1. In Vercel add `PAYMONGO_ENABLED` = `true`, `PAYMONGO_SECRET_KEY` = `sk_test_...` and `PAYMONGO_PUBLIC_KEY` = `pk_test_...`.
2. PayMongo Dashboard → **Developers → Webhooks → Create**: URL `https://devtech-tacloban.vercel.app/paymongo/webhook`, events `payment.paid` and `checkout_session.payment.paid`.
3. Copy the webhook secret (`whsk_...`) into Vercel as `PAYMONGO_WEBHOOK_SECRET`, then **Redeploy**.

---

## Limits to know

- **Educational use only** on Vercel's Hobby plan.
- **Upload size:** Vercel accepts at most about 4.5 MB per request. Keep ID scans and PDFs under 4 MB (photos are shrunk by the browser first).
- **First visit after a quiet period** can take a few seconds while Vercel starts the app.
- **Live updates** (new messages, notification counts) arrive within a few seconds instead of instantly.
- **Emails:** 300 a day on Brevo's free plan.

---

## If something goes wrong

Look at Vercel → your project → **Logs** first; the error is usually written there.

| What you see | Fix |
|---|---|
| Deployment fails while installing packages | Open the build log in Vercel; it names the package that failed. |
| `DATABASE_URL is not set` or `SECRET_KEY is not set` in Logs | Add it in Vercel's Environment Variables, then Redeploy. |
| `relation "..." does not exist` | The tables were not created. Do **Part 4**. |
| `Network is unreachable` / timeout to `db.xxxx.supabase.co` | You used the Direct connection link. Use the **Transaction pooler** link (port 6543). |
| `password authentication failed` | Wrong database password, or the user is not `postgres.<project-ref>`. Copy the link again from **Connect**. |
| Photos broken | `SUPABASE_URL`, `SUPABASE_SECRET_KEY` or the bucket name is wrong, or the bucket is missing. Logs show `Supabase Storage refused ...`. |
| Emails do not arrive | Brevo → **Transactional → Logs**. The `MAIL_FROM` address must be a verified sender. Check spam. |
| Upload fails with "413" | The file is over Vercel's 4.5 MB limit; use a smaller file. |
| `/setup/first-admin` shows "Not Found" | An admin already exists, or the token in the address does not match `SETUP_TOKEN`. |
| Site stopped working after a quiet week | Supabase paused the project. Press **Restore** in Supabase. |
