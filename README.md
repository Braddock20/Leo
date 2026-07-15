# IG Pilot

A self-hosted Instagram automation dashboard for your **own** account. Single-user, single-account, designed to be deployed on Render.

## What it does

- **Like posts** on your home feed
- **Follow / unfollow** any user
- **Send DMs** with custom text
- **View stories**
- **Warm-up browse** (human-like scrolling, no actions — for new accounts)
- **Daily caps** per action type so you don't trip IG's behavior classifier
- **Encrypted cookie storage** (Fernet)
- **Stealth patches** to hide the Playwright fingerprints
- **Job queue + scheduler** with `now` or `schedule in N minutes`
- **Dashboard** with live counters and a recent-jobs table

## Stack

- Python 3.11
- Flask + Flask-Login
- Playwright (async, Chromium)
- SQLite (no external DB needed)
- APScheduler (in-process job runner)
- Gunicorn (1 worker — the runner and the Playwright context share the process)

## Local quick start

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium
cp .env.example .env
# Edit .env — set SECRET_KEY, ADMIN_PASSWORD at minimum
python wsgi.py
# Open http://localhost:5000
```

## Deploy to Render (one click)

1. Push this repo to GitHub.
2. On Render: **New → Blueprint** → point at the repo.
3. Render reads `render.yaml` and creates the service for you.
4. Wait for the first build (~3–5 min — Playwright Chromium is ~160 MB).
5. Open the URL Render gives you → log in with the `ADMIN_USERNAME` / `ADMIN_PASSWORD` that were auto-generated (find them in **Render Dashboard → Environment**).
6. **Important:** change `ADMIN_PASSWORD` from the auto-generated value to something you actually remember.
7. Go to **Session**, paste your cookies, save.

### Render notes

- **Disk is required.** The Playwright profile (cookies, cache) lives at `data/`. The `render.yaml` provisions a 1 GB disk mounted there. Without it, you'll lose your session on every redeploy.
- **Single worker only.** Gunicorn is started with `-w 1`. Multiple workers = multiple Playwright contexts = IG gets suspicious.
- **Region.** Default is `oregon`. If your account usually logs in from a different region, change the region in `render.yaml` to be closer.
- **First boot is slow.** Chromium takes a few seconds to launch on Render's free/cheap tiers. The `gunicorn -t 120` timeout gives it room.

## Getting your Instagram cookies

1. In your normal browser (Chrome/Firefox), open instagram.com and log in.
2. Install the **Cookie-Editor** or **EditThisCookie** extension.
3. Click the extension icon → **Export** → **JSON**.
4. Paste into the **Session** page on the dashboard → **Save cookies**.

The cookies are encrypted with Fernet and stored at `instance/igpilot.db` (in the `sessions_meta` table, the `encrypted_cookies` column).

## Safety rails (already enforced)

- Daily limits per action kind (configurable via env: `DAILY_LIKE_LIMIT`, etc.)
- Random Gaussian delays between actions (no metronome behavior)
- Smooth mouse moves, scroll, hover via the `humanizer` module
- Stealth patches hide `navigator.webdriver`, mask WebGL vendor, stub Chrome runtime, etc.
- Persistent Chromium profile → one fingerprint, not a new one each restart
- All actions skip the API and go through the real DOM (Playwright clicks real buttons)

## Anti-ban reminders (your responsibility)

This tool makes detection **harder**, not impossible. Things that still get accounts banned:

- Logging in from a new fingerprint (the tool reuses a profile to avoid this — don't clear `data/chromium_profile/`)
- Doing too much, too fast (use the daily caps)
- IG forcing a 2FA or "was this you?" challenge (the script can't solve these — if it happens, log in manually from your browser, accept the prompt, and the cookies will be valid again)
- Posting the exact same DM to many users (don't — vary your message)

## File layout

```
igpilot/
├── app/
│   ├── __init__.py        # Flask app factory (lazy imports)
│   ├── auth.py            # User model + bootstrap
│   ├── config.py          # Env-driven config
│   ├── crypto.py          # Fernet encrypt/decrypt for cookies
│   ├── db.py              # SQLite schema + helpers
│   ├── routes.py          # HTTP routes
│   ├── services/
│   │   ├── humanizer.py   # Random delays, scroll, type
│   │   ├── ig_session.py  # Playwright Chromium session
│   │   ├── runner.py      # Background job executor
│   │   └── stealth.py     # Browser fingerprint patches
│   ├── static/            # (empty — inline CSS in templates)
│   └── templates/         # base.html, login.html, dashboard.html, session.html
├── tests/
│   ├── test_e2e.py        # Boots app, hits every route, checks auth
│   └── test_runner.py     # Schedules a job, verifies the runner picks it up
├── app.py                 # (legacy shim — use wsgi.py for gunicorn)
├── wsgi.py                # Gunicorn entry point
├── build.sh               # Render build script
├── render.yaml            # Render blueprint
├── Procfile               # web: gunicorn wsgi:app
├── runtime.txt            # python-3.11.9
├── requirements.txt
└── .env.example
```

## License

Personal use. Not for resale. Don't use this to harass people.
