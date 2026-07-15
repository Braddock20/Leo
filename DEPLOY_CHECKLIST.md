# Render deploy — verify checklist

Run through these in order once your service is live. Each step has a clear pass/fail signal.

---

## Phase 1: Build & boot (5 min after first deploy)

- [ ] **Build log shows `Build complete`** at the end of `build.sh`
  - Render → your service → **Logs** → **Build**
  - Last line should be `==> Build complete`
  - If you see errors about missing libs → I need to add them to `build.sh`

- [ ] **Service is "Live" (green)** in the Render dashboard
  - If it's "Deploy failed" → check logs, send me the error

- [ ] **First request doesn't timeout**
  - Open the URL Render gave you
  - First load can take 30-60s because Chromium has to launch
  - If you see a 502/gateway timeout → wait and refresh; if it persists, the disk might not be mounted (check the disk config in `render.yaml`)

---

## Phase 2: Login & dashboard

- [ ] **Login page loads** (200, has "Sign in" form)
- [ ] **Login works** with the auto-generated `ADMIN_PASSWORD` from **Environment**
- [ ] **Dashboard shows "No Instagram session stored"** in a red flash — this is expected
- [ ] **All 4 action forms render** (Like, Follow, DM, Story view)

**If the dashboard 500s:** check the logs for the actual error. Most likely a missing Python module → `requirements.txt` issue.

---

## Phase 3: Cookie upload (the real test)

This is the moment of truth. From a regular browser (not Render):

1. Log into instagram.com normally
2. Install **Cookie-Editor** extension (Chrome/Firefox)
3. Open instagram.com → click the extension → **Export** → **JSON**
4. On your Render dashboard, go to **Session** page
5. Paste the JSON in the textarea → **Save cookies**
6. You should see a green flash: "Stored N cookies."

- [ ] **Cookie upload returns success** with the right count
- [ ] **Reload the Session page** — status should now say "Cookies are stored"

**Common pitfalls:**
- Some extensions use `expirationDate` (CamelCase) or `expires` — my code normalizes both, but if cookies don't take effect, send me the JSON shape
- If cookie count is 0 or wildly low (like 3), the extension exported a different format

---

## Phase 4: Verify session is live (the SCARIEST test)

On the Session page, click **"Apply & verify"**. This restarts the Chromium context with your stored cookies and checks if IG sees you as logged in.

- [ ] **Status pill in the header goes green** → "Session active"
- [ ] **No error flash** about save failed

**If it stays red / errors:**
- Open the live logs: **Render Dashboard → Logs → Live**
- Look for `Session active.` or `Cookie injection failed: ...` or `No active session.`
- The most common cause: cookies are older than 2-3 weeks and were invalidated. **Re-export from your browser and re-upload.**
- Send me the log line and I'll diagnose

---

## Phase 5: Smoke test with the safest action

DO NOT start with follows or DMs. Do this:

1. Go to **Dashboard**
2. **Warm-up browse** → click **Run now**
3. Watch the **Recent jobs** table — it should go from `pending` → `running` → `done` within ~10 seconds
4. Result should say "Warmup browse done"

- [ ] **Warmup browse job completes successfully**
- [ ] **Log line shows** `Running job N kind=warmup_browse`

**If it fails:**
- Check the error in the Recent jobs table
- "Not logged in" → cookies didn't take, re-do Phase 4
- Any Playwright timeout → Chromium is having a hard time on Render; might need to bump the gunicorn timeout (already at 120s, but check)

---

## Phase 6: First real action (likes, count=1)

Now try a real action, smallest possible:

1. **Like posts on feed** → count = 1 → **Run now**
2. Wait ~10-20s
3. Recent jobs should show `done` with "Liked 1 posts"

- [ ] **Single like completes**
- [ ] **The like actually appears on your IG** (check your phone / browser)

**If likes complete in the app but don't show on IG:**
- The selector is wrong. Most common: IG changed the `aria-label` from "Like" to something else (e.g. localized text)
- **Debug:** I can add a "dump page HTML" button to the dashboard if this happens
- For now, if you hit this, send me one line from the log and the error from the Recent jobs table

---

## Phase 7: Schedule a real job

1. **Follow a user** → username = a real account → **Schedule in 15 min** → submit
2. Confirm the job appears in Recent jobs with status `pending`
3. Wait 15 min (or less, you can also click Run now after confirming it scheduled)
4. Verify the follow happened on IG

- [ ] **Scheduled job runs at the right time**
- [ ] **Follow shows on IG**

---

## What to send me if something breaks

For any failure, copy these from Render:

1. **Service Logs → Live** — last 30-50 lines
2. **The error message** from the Recent jobs table in the dashboard
3. **What step you were on** (1-7 above)

I'll diagnose fast.

---

## Daily cap reminders (already enforced, but FYI)

Defaults from `render.yaml`:
- 80 likes / day
- 40 follows / day
- 20 DMs / day
- 100 story views / day

**For the first 1-2 weeks**, halve these. Edit the env vars in **Render → Environment** and redeploy.

Warmup browse is uncapped — use it freely for the first week of an account.
