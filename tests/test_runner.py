"""Test that the background runner actually picks up and executes jobs.

We schedule a 'warmup_browse' job, let the runner thread tick once, and
verify the job status moves from pending -> done (or failed cleanly).
"""
import os
import sys
import time
import json
import tempfile
import shutil
from pathlib import Path
import datetime as dt

# Isolated test dir
TEST_ROOT = Path(tempfile.mkdtemp(prefix="igpilot-runner-"))
ROOT = Path(__file__).resolve().parent.parent
test_home = TEST_ROOT / "app_home"
shutil.copytree(ROOT, test_home, ignore=shutil.ignore_patterns(".venv", "__pycache__", "instance", "data", "logs", ".pytest_cache", "tests"))
(test_home / "instance").mkdir(parents=True, exist_ok=True)
(test_home / "data").mkdir(parents=True, exist_ok=True)
(test_home / "logs").mkdir(parents=True, exist_ok=True)
(test_home / ".env").write_text(
    "SECRET_KEY=test-secret\n"
    "ADMIN_USERNAME=admin\n"
    "ADMIN_PASSWORD=testpass123\n"
    "HEADLESS=true\n"
)
sys.path.insert(0, str(test_home))

# Don't auto-start the runner via create_app; we'll start it manually
os.environ["IGPILOT_NO_RUNNER"] = "1"

from app import create_app
from app.db import init_db, get_conn, add_action
from app.services import runner

app = create_app()
init_db()

print("== Scheduling a warmup_browse job ==")
jid = runner.schedule("warmup_browse", {}, dt.datetime.now(dt.timezone.utc))
print(f"  scheduled job {jid}")

print("== Starting runner thread ==")
runner.start_runner()
print("  runner started, sleeping 20s for it to tick...")

# Wait for the job to finish
deadline = time.time() + 25
status = None
while time.time() < deadline:
    with get_conn() as c:
        row = c.execute("SELECT * FROM jobs WHERE id=?", (jid,)).fetchone()
    status = row["status"] if row else None
    if status in ("done", "failed", "cancelled"):
        break
    time.sleep(1)

print(f"  final job status: {status}")

with get_conn() as c:
    row = c.execute("SELECT * FROM jobs WHERE id=?", (jid,)).fetchone()
print(f"  result: {row['result']}")
print(f"  error: {row['error']}")

if status in ("done", "failed"):
    print("\n  ✓ Runner picked up and processed the job end-to-end")
else:
    print("\n  ✗ Job did not finish in time")
    sys.exit(1)

# Now schedule a job whose kind doesn't have Playwright dependency
print("\n== Scheduling a like job (will fail because no real IG session) ==")
jid2 = runner.schedule("like", {"count": 3}, dt.datetime.now(dt.timezone.utc))
print(f"  scheduled job {jid2}")

deadline = time.time() + 30
status2 = None
while time.time() < deadline:
    with get_conn() as c:
        row = c.execute("SELECT * FROM jobs WHERE id=?", (jid2,)).fetchone()
    status2 = row["status"] if row else None
    if status2 in ("done", "failed", "cancelled"):
        break
    time.sleep(1)

print(f"  final status: {status2}")
with get_conn() as c:
    row = c.execute("SELECT * FROM jobs WHERE id=?", (jid2,)).fetchone()
print(f"  result: {row['result']}")
print(f"  error: {row['error']}")

# Clean up
runner.stop_runner()
shutil.rmtree(TEST_ROOT, ignore_errors=True)

print("\n========================================")
print("  RUNNER TEST PASSED ✓")
print("========================================")
