"""Background job runner + scheduler.

Jobs are pulled from SQLite, executed by IGSession, and the result is logged
back. A single APScheduler instance ticks every 30s; concurrency is 1
because IG hates parallel sessions.
"""
import json
import logging
import asyncio
import os
import signal
import sys
from datetime import datetime, timezone

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.events import EVENT_JOB_ERROR

from .ig_session import SESSION
from ..config import Config
from ..db import get_conn, add_action

log = logging.getLogger("ig.runner")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    handlers=[
        logging.FileHandler(Config.SESSION_LOG_PATH),
        logging.StreamHandler(sys.stdout),
    ],
)


SCHED = BackgroundScheduler(timezone="UTC")
_LOOP: asyncio.AbstractEventLoop | None = None
_RUNNER_TASK: asyncio.Task | None = None
_STOP = False


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def schedule(kind: str, payload: dict, run_at: datetime | None = None) -> int:
    """Insert a pending job and return its id."""
    from datetime import datetime, timezone, timedelta
    if run_at is None:
        run_at = datetime.now(timezone.utc) + timedelta(seconds=10)
    with get_conn() as c:
        cur = c.execute(
            "INSERT INTO jobs(kind, status, payload, scheduled_at, created_at) VALUES (?,?,?,?,?)",
            (kind, "pending", json.dumps(payload), run_at.isoformat(), _now()),
        )
        return int(cur.lastrowid)


def list_jobs(limit: int = 50):
    with get_conn() as c:
        rows = c.execute(
            "SELECT * FROM jobs ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]


def cancel_job(job_id: int) -> bool:
    with get_conn() as c:
        cur = c.execute(
            "UPDATE jobs SET status='cancelled' WHERE id=? AND status='pending'",
            (job_id,),
        )
        return cur.rowcount > 0


def daily_count(kind: str) -> int:
    from .humanizer import should_act_today
    # Lightweight reuse: count from action_log
    from ..db import count_actions_today
    return count_actions_today(kind)


# ---- async dispatch ----

async def _execute_job(job: dict):
    from .humanizer import short_pause, medium_pause, sleep_async
    kind = job["kind"]
    payload = json.loads(job["payload"]) if job.get("payload") else {}
    log.info(f"Running job {job['id']} kind={kind} payload={payload}")

    limits = {
        "like": Config.DAILY_LIKE_LIMIT,
        "follow": Config.DAILY_FOLLOW_LIMIT,
        "dm": Config.DAILY_DM_LIMIT,
        "story_view": Config.DAILY_STORY_VIEW_LIMIT,
    }
    cap = limits.get(kind)
    if cap is not None and daily_count(kind) >= cap:
        msg = f"Daily cap reached for {kind} ({cap})"
        log.warning(msg)
        with get_conn() as c:
            c.execute(
                "UPDATE jobs SET status='done', finished_at=?, result=? WHERE id=?",
                (_now(), msg, job["id"]),
            )
        return

    success = False
    result_msg = ""
    error_msg = ""
    try:
        if kind == "like":
            n = int(payload.get("count", 5))
            liked = await SESSION.like_first_posts_on_feed(n)
            success = liked > 0
            result_msg = f"Liked {liked} posts"
        elif kind == "follow":
            target = payload.get("username", "").strip().lstrip("@")
            if not target:
                raise ValueError("Missing username")
            success = await SESSION.follow_from_profile(target)
            result_msg = f"Followed @{target}" if success else "Already following or button missing"
        elif kind == "dm":
            target = payload.get("username", "").strip().lstrip("@")
            text = payload.get("text", "").strip()
            if not target or not text:
                raise ValueError("Missing username or text")
            success = await SESSION.send_dm(target, text)
            result_msg = f"DM sent to @{target}" if success else "Send failed"
        elif kind == "story_view":
            n = int(payload.get("count", 5))
            viewed = await SESSION.view_stories(n)
            success = viewed > 0
            result_msg = f"Viewed {viewed} stories"
        elif kind == "warmup_browse":
            # Pure human-like browsing. No log entry.
            await SESSION.ensure_started()
            await SESSION.page.goto("https://www.instagram.com/", wait_until="domcontentloaded")
            await sleep_async(medium_pause())
            from .humanizer import human_scroll
            await human_scroll(SESSION.page, 600)
            await sleep_async(medium_pause())
            success = True
            result_msg = "Warmup browse done"
        else:
            error_msg = f"Unknown job kind: {kind}"

        if success:
            add_action(datetime.now(timezone.utc).date().isoformat(), kind, payload.get("username", ""), True)
    except Exception as e:
        error_msg = str(e)
        log.exception(f"Job {job['id']} failed")

    with get_conn() as c:
        c.execute(
            "UPDATE jobs SET status=?, finished_at=?, result=?, error=? WHERE id=?",
            (
                "done" if success or not error_msg else "failed",
                _now(),
                result_msg,
                error_msg,
                job["id"],
            ),
        )
    # Cooldown between jobs
    await sleep_async(short_pause())


def _claim_due_job():
    """Atomically pick the next due pending job and mark it running."""
    with get_conn() as c:
        row = c.execute(
            "SELECT * FROM jobs WHERE status='pending' AND scheduled_at <= ? ORDER BY scheduled_at ASC LIMIT 1",
            (_now(),),
        ).fetchone()
        if not row:
            return None
        c.execute(
            "UPDATE jobs SET status='running', started_at=? WHERE id=?",
            (_now(), row["id"]),
        )
        return dict(row)


async def _runner_loop():
    log.info("Runner loop started")
    while not _STOP:
        try:
            job = _claim_due_job()
            if job is None:
                await asyncio.sleep(5)
                continue
            await _execute_job(job)
        except asyncio.CancelledError:
            break
        except Exception as e:
            log.exception(f"Runner loop error: {e}")
            await asyncio.sleep(10)
    log.info("Runner loop exiting")


def start_runner():
    global _LOOP, _RUNNER_TASK
    if _RUNNER_TASK is not None:
        return

    async def _bootstrap():
        try:
            await SESSION.start()
        except Exception as e:
            log.warning(f"Initial session start deferred: {e}")
        await _runner_loop()

    def _thread_entry():
        global _LOOP
        _LOOP = asyncio.new_event_loop()
        asyncio.set_event_loop(_LOOP)
        try:
            _LOOP.run_until_complete(_bootstrap())
        finally:
            _LOOP.close()

    import threading
    t = threading.Thread(target=_thread_entry, name="ig-runner", daemon=True)
    t.start()


def stop_runner():
    global _STOP
    _STOP = True
