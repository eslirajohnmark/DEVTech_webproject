# Deployment Guide

How to take DEVTech from `localhost:5000` to a real URL.

Two paths, pick the one that matches your situation.

| Path | Best for | Difficulty | Time |
|---|---|---|---|
| **A. PythonAnywhere** | Simplest working deployment, no domain needed | Easy | ~30 min |
| **B. VPS + Gunicorn + Nginx + Let's Encrypt** | Custom domain, full control, real production | Moderate | 2–3 hours |

Everything below assumes the app runs locally and the demo accounts work.

---

## Pre-deployment checklist

Do these before touching any server. Skipping them is how production gets compromised.

### 1. Change every demo password

```sql
-- Delete demo technicians and customers entirely
DELETE FROM users WHERE username LIKE 'TECH-%' AND email LIKE '%@devtech.local';
DELETE FROM users WHERE username = 'customer1' AND email LIKE '%@devtech.local';
```

Then recreate real accounts through the admin panel.

### 2. Change the admin password

If you already created an admin and want to change the password:

```bash
flask --app app reset-admin-password you@yourdomain.com
```

Or, if you haven't created one yet, skip straight to `flask create-admin` on the server.

### 3. Generate a real SECRET_KEY

```bash
python -c "import secrets; print(secrets.token_urlsafe(64))"
```

Put it in `.env` as `SECRET_KEY=...`. `app.py` refuses to start in production with the default value.

### 4. Decide on a database

- **SQLite** — fine for local testing, not for real traffic. Not recommended once you have concurrent users.
- **MySQL** — what `app.py` is configured for. Use this.

On a VPS: `apt install mysql-server`. On PythonAnywhere: bundled with the account.

### 5. Prepare the production `.env`

```bash
FLASK_ENV=production
SECRET_KEY=<the-64-char-string-from-step-3>
DATABASE_URL=mysql+pymysql://devtech_user:STRONG_PASSWORD@localhost/devtech_db
DEV_HOST=127.0.0.1
DEV_SSL=0
RATELIMIT_STORAGE_URI=redis://localhost:6379/0
CACHE_TYPE=RedisCache
CACHE_REDIS_URL=redis://localhost:6379/1
SETUP_TOKEN=
```

Two things to watch:

- `FLASK_ENV=production` flips cookies to `Secure`, forces HTTPS, and hides stack traces. **Do not set this until HTTPS works** — you will lock yourself out over plain HTTP.
- The Redis URLs require `redis-server` running. If you're on PythonAnywhere, use their Redis add-on, or leave `RATELIMIT_STORAGE_URI=memory://` (fine for a single-process deploy).

---

## Path A — PythonAnywhere

The simplest path. Free tier works for testing; paid ($5/month) for real use.

### 1. Create an account

Sign up at [pythonanywhere.com](https://www.pythonanywhere.com).

### 2. Open a Bash console

Dashboard → **Consoles** → **Bash**.

### 3. Clone the code

```bash
cd ~
git clone https://github.com/yourname/devtech.git
cd devtech
```

For a private repo, use a Personal Access Token in the URL:
`https://YOUR_TOKEN@github.com/yourname/devtech.git`

### 4. Create a virtualenv

```bash
mkvirtualenv --python=/usr/bin/python3.11 devtech-env
pip install -r requirements.txt
```

### 5. Set up MySQL

Dashboard → **Databases** → **Create a MySQL database**.

Note the three values:
- Database name (e.g. `yourname$devtech`)
- Username (e.g. `yourname`)
- Hostname (e.g. `yourname.mysql.pythonanywhere-services.com`)

Load the schema:

```bash
mysql -u yourname -h yourname.mysql.pythonanywhere-services.com \
      -p 'yourname$devtech' < database/schema.sql
mysql -u yourname -h yourname.mysql.pythonanywhere-services.com \
      -p 'yourname$devtech' < database/migrate_service_categories.sql
mysql -u yourname -h yourname.mysql.pythonanywhere-services.com \
      -p 'yourname$devtech' < database/migrate_ratings.sql
```

### 6. Create the `.env`

```bash
nano ~/devtech/.env
```

```bash
FLASK_ENV=development
SECRET_KEY=<your-real-64-char-key>
DATABASE_URL=mysql+pymysql://yourname:DB_PASSWORD@yourname.mysql.pythonanywhere-services.com/yourname$devtech
DEV_HOST=127.0.0.1
DEV_SSL=0
RATELIMIT_STORAGE_URI=memory://
CACHE_TYPE=SimpleCache
SETUP_TOKEN=
```

Note `FLASK_ENV=development` for now — you'll flip it once HTTPS works.

### 7. Create a Web App

Dashboard → **Web** → **Add a new web app** → **Manual configuration** → **Python 3.11**.

Fill in:

| Field | Value |
|---|---|
| Source code | `/home/yourname/devtech` |
| Working directory | `/home/yourname/devtech` |
| Virtualenv | `/home/yourname/.virtualenvs/devtech-env` |

### 8. Configure the WSGI file

Click the WSGI configuration file link. Replace the contents with:

```python
import sys
path = '/home/yourname/devtech'
if path not in sys.path:
    sys.path.insert(0, path)

from app import app as application
```

Save.

### 9. Static files

In the Web tab, under **Static files**, add:

| URL | Directory |
|---|---|
| `/static/` | `/home/yourname/devtech/static/` |

### 10. Reload

Green **Reload** button. Visit `https://yourname.pythonanywhere.com`.

You should see the landing page.

### 11. Fix the uploads path

PythonAnywhere's filesystem is read-only outside your home directory. Edit `app.py` so uploads write under your project:

```python
app.config['TECH_UPLOAD_FOLDER'] = os.path.join(
    os.path.expanduser('~'), 'devtech', 'instance', 'uploads', 'tech'
)
```

Reload.

### 12. Create the first admin

From the PythonAnywhere Bash console:

```bash
cd ~/devtech
source ~/.virtualenvs/devtech-env/bin/activate
export FLASK_APP=app.py
flask create-admin
```

Prompts for email, name, password.

### 13. Enable HTTPS and flip to production

PythonAnywhere gives you HTTPS on `*.pythonanywhere.com` automatically.

Web tab → **Force HTTPS** → turn it on.

Then:

```bash
nano ~/devtech/.env
# change FLASK_ENV=development to FLASK_ENV=production
```

Reload. Test:

- The site loads at `https://yourname.pythonanywhere.com`
- HTTP redirects to HTTPS
- Technician login at `/technician/login` works
- Uploading a file from the technician portal works

### 14. Custom domain (paid tier)

Web tab → add your domain → follow PythonAnywhere's CNAME instructions in your registrar.

---

## Path B — VPS + Gunicorn + Nginx + Let's Encrypt

Full production setup. Assumes a fresh Ubuntu 22.04 VPS (DigitalOcean, Linode, Hetzner).

### 1. Point your domain

In your registrar's DNS panel:

| Type | Name | Value |
|---|---|---|
| A | `devtech` | `<your-server-IP>` |
| A | `www.devtech` | `<your-server-IP>` |

Wait for propagation (5 min – 24 hours). Verify:

```bash
dig devtech.yourdomain.com
```

Should return your server IP.

### 2. SSH in and update

```bash
ssh root@your-server-ip

apt update && apt upgrade -y
```

### 3. Create a non-root user

```bash
adduser devtech
usermod -aG sudo devtech
su - devtech
```

Every command below runs as `devtech`.

### 4. Install system packages

```bash
sudo apt install -y python3.11 python3.11-venv python3-pip \
                    mysql-server nginx redis-server git \
                    build-essential libssl-dev libffi-dev \
                    python3-dev default-libmysqlclient-dev pkg-config \
                    certbot python3-certbot-nginx ufw
```

### 5. Configure MySQL

```bash
sudo mysql_secure_installation
# Answer yes to everything, set a root password
```

Create the database and user:

```bash
sudo mysql -u root -p
```

```sql
CREATE DATABASE devtech_db CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'devtech_user'@'localhost' IDENTIFIED BY 'a-long-random-password';
GRANT ALL PRIVILEGES ON devtech_db.* TO 'devtech_user'@'localhost';
FLUSH PRIVILEGES;
EXIT;
```

Load the schema:

```bash
mysql -u devtech_user -p devtech_db < database/schema.sql
mysql -u devtech_user -p devtech_db < database/migrate_service_categories.sql
mysql -u devtech_user -p devtech_db < database/migrate_ratings.sql
```

### 6. Configure Redis

Redis is running after the install. Verify:

```bash
redis-cli ping
# PONG
```

Secure it:

```bash
sudo nano /etc/redis/redis.conf
```

Find `bind 127.0.0.1 ::1` — leave as-is (localhost only).
Find `requirepass` — uncomment, add a strong password.

```bash
sudo systemctl restart redis-server
```

### 7. Deploy the code

```bash
cd ~
git clone https://github.com/yourname/devtech.git
cd devtech
```

### 8. Set up Python

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

### 9. Create `.env`

```bash
nano .env
```

```bash
FLASK_ENV=development
SECRET_KEY=<your-real-64-char-key>
DATABASE_URL=mysql+pymysql://devtech_user:DB_PASSWORD@localhost/devtech_db
DEV_HOST=127.0.0.1
DEV_SSL=0
RATELIMIT_STORAGE_URI=redis://:redis-password@localhost:6379/0
CACHE_TYPE=RedisCache
CACHE_REDIS_URL=redis://:redis-password@localhost:6379/1
SETUP_TOKEN=
```

```bash
chmod 600 .env
```

`FLASK_ENV=development` for now. You'll change it after HTTPS works.

### 10. Create the uploads directory

```bash
mkdir -p instance/uploads/tech
chmod 755 instance/uploads/tech
```

### 11. Initialize the database

```bash
source .venv/bin/activate
python -c "from app import app, db; app.app_context().push(); db.create_all()"
```

### 12. Create the first admin

```bash
export FLASK_APP=app.py
flask create-admin
```

### 13. Test Gunicorn manually

```bash
source .venv/bin/activate
gunicorn --workers 4 --bind 127.0.0.1:8000 wsgi:app
```

Visit `http://your-server-ip:8000` from your browser. You should see the site.

Ctrl+C to stop.

If it errors:
- Confirm `.venv` was activated
- Confirm `.env` has the correct `DATABASE_URL`
- Confirm MySQL is running: `sudo systemctl status mysql`

### 14. Create a systemd service

```bash
sudo nano /etc/systemd/system/devtech.service
```

```ini
[Unit]
Description=DEVTech Gunicorn service
After=network.target mysql.service redis.service

[Service]
User=devtech
Group=www-data
WorkingDirectory=/home/devtech/devtech
Environment="PATH=/home/devtech/devtech/.venv/bin"
ExecStart=/home/devtech/devtech/.venv/bin/gunicorn \
    --workers 4 \
    --bind 127.0.0.1:8000 \
    --access-logfile /home/devtech/devtech/logs/access.log \
    --error-logfile /home/devtech/devtech/logs/error.log \
    --timeout 60 \
    wsgi:app
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```bash
mkdir -p ~/devtech/logs
sudo systemctl daemon-reload
sudo systemctl enable devtech
sudo systemctl start devtech
sudo systemctl status devtech
```

Should show `active (running)`.

If not:

```bash
sudo journalctl -u devtech -n 50
```

### 15. Configure Nginx

```bash
sudo nano /etc/nginx/sites-available/devtech
```

```nginx
server {
    listen 80;
    server_name devtech.yourdomain.com www.devtech.yourdomain.com;

    client_max_body_size 20M;

    location /static/ {
        alias /home/devtech/devtech/static/;
        expires 30d;
        add_header Cache-Control "public, immutable";
    }

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 60s;
    }
}
```

Enable:

```bash
sudo ln -s /etc/nginx/sites-available/devtech /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl restart nginx
```

Visit `http://devtech.yourdomain.com`. Should load.

### 16. HTTPS with Let's Encrypt

```bash
sudo certbot --nginx -d devtech.yourdomain.com -d www.devtech.yourdomain.com
```

Follow the prompts. Certbot handles everything: certificate, Nginx config, HTTP→HTTPS redirect, and an auto-renewal timer.

Test renewal:

```bash
sudo certbot renew --dry-run
```

Should print "all simulated renewals succeeded."

### 17. Flip to production mode

```bash
nano ~/devtech/devtech/.env
# change FLASK_ENV=development to FLASK_ENV=production
```

```bash
sudo systemctl restart devtech
```

This turns on:
- `SESSION_COOKIE_SECURE=True`
- `force_https=True` in Talisman
- HSTS
- Debug off

Test immediately. If something breaks, flip back to `development`, restart, and debug.

### 18. Firewall

```bash
sudo ufw allow OpenSSH
sudo ufw allow 'Nginx Full'
sudo ufw enable
sudo ufw status
```

Expected:

```
22                         ALLOW
Nginx Full                 ALLOW
```

MySQL and Redis stay unreachable from outside. That's correct.

### 19. Log rotation

```bash
sudo nano /etc/logrotate.d/devtech
```

```
/home/devtech/devtech/logs/*.log {
    daily
    rotate 14
    compress
    delaycompress
    missingok
    notifempty
    create 0640 devtech www-data
    sharedscripts
    postrotate
        systemctl reload devtech > /dev/null
    endscript
}
```

### 20. Backups

```bash
mkdir -p ~/backups
nano ~/backup.sh
```

```bash
#!/bin/bash
DATE=$(date +%Y%m%d)
mysqldump -u devtech_user -p'YOUR_DB_PASSWORD' devtech_db \
    | gzip > ~/backups/devtech-$DATE.sql.gz
find ~/backups -name 'devtech-*.sql.gz' -mtime +30 -delete
```

```bash
chmod +x ~/backup.sh
crontab -e
```

Add:

```
0 3 * * 0 /home/devtech/backup.sh
```

Every Sunday at 3 AM. Consider syncing `~/backups` to S3 or Backblaze for off-server storage.

### 21. Uptime monitoring (recommended)

[uptimerobot.com](https://uptimerobot.com) free tier checks every 5 minutes. Point it at:

```
https://devtech.yourdomain.com/healthz
```

That endpoint returns 200 when the app and its DB connection are healthy, 503 when not.

---

## Common problems after deploy

### "MySQL server has gone away"

`app.py` sets `pool_recycle` and `pool_pre_ping`, so this shouldn't happen. If it does, confirm those two lines are still in the config block.

### Static files 404

Nginx alias path is wrong, or the directory isn't readable by `www-data`.

```bash
sudo -u www-data ls /home/devtech/devtech/static/
```

If "permission denied":

```bash
chmod 755 /home/devtech
chmod -R 755 /home/devtech/devtech/static
```

### Uploads fail

The `instance/uploads/tech` directory must be writable by the user Gunicorn runs as.

```bash
sudo chown -R devtech:www-data ~/devtech/instance
chmod -R 775 ~/devtech/instance
```

### Rate limiting resets on restart

You're on `memory://`. Switch to Redis:

```
RATELIMIT_STORAGE_URI=redis://:your-password@localhost:6379/0
```

### Session cookies don't persist over HTTPS

You flipped `FLASK_ENV=production` before HTTPS worked. Cookies became `Secure`, and the browser silently drops them over HTTP. Fix: enable HTTPS first, then flip the flag.

### `Ctrl+Shift+T` doesn't work

Firefox and Safari reserve that combination for "reopen closed tab." Chrome and Edge generally don't. If you're on Firefox, use the visible footer link, or change the shortcut in `static/js/admin.js`, `user.js`, and `home.js` to `Ctrl+Alt+Shift+T` instead — that combination is not bound by any browser.

---

## Post-deploy checklist

- [ ] HTTPS works and HTTP redirects to it
- [ ] Demo accounts deleted
- [ ] `FLASK_ENV=production` in `.env`
- [ ] `SECRET_KEY` is a real random string, not the default
- [ ] Admin password changed
- [ ] First real technician account created and verified via admin panel
- [ ] End-to-end test: customer books → admin assigns → technician sees it → technician advances → customer's monitor page updates
- [ ] File upload works from the technician side
- [ ] Backups running (verify the first cron job fired)
- [ ] Uptime monitor configured on `/healthz`
- [ ] Log rotation working (check after a few days)

---

## When something goes wrong

```bash
# App logs
sudo journalctl -u devtech -n 100 --no-pager

# Gunicorn logs
tail -f ~/devtech/logs/error.log

# Nginx errors
sudo tail -f /var/log/nginx/error.log

# MySQL errors
sudo tail -f /var/log/mysql/error.log

# Restart
sudo systemctl restart devtech
sudo systemctl restart nginx
```