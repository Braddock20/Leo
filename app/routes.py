"""HTTP routes — login, dashboard, job creation, cookie upload, status."""
import json
import logging
from datetime import datetime, timezone, timedelta

from flask import (
    Blueprint, render_template, request, redirect, url_for, flash, jsonify, current_app
)
from flask_login import login_user, login_required, logout_user, current_user

from .auth import AdminUser
from .services import runner
from .services.ig_session import SESSION
from .config import Config
from .crypto import encrypt, decrypt
from .db import get_conn

log = logging.getLogger("ig.routes")
bp = Blueprint("main", __name__)


@bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        u = request.form.get("username", "").strip()
        p = request.form.get("password", "")
        user = AdminUser.by_username(u)
        if user is None:
            from werkzeug.security import check_password_hash
            if u == Config.ADMIN_USERNAME and p == Config.ADMIN_PASSWORD:
                AdminUser.bootstrap(u, p)
                user = AdminUser.by_username(u)
        if user is not None and current_app.config.get("_PW_HASH") is None:
            pass
        # Verify password by re-fetching hash
        from werkzeug.security import check_password_hash
        with get_conn() as c:
            row = c.execute("SELECT * FROM users WHERE username=?", (u,)).fetchone()
        if row and check_password_hash(row["password_hash"], p):
            login_user(AdminUser(row["id"], row["username"]))
            return redirect(url_for("main.dashboard"))
        flash("Invalid credentials", "error")
    return render_template("login.html")


@bp.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("main.login"))


@bp.route("/")
@login_required
def dashboard():
    jobs = runner.list_jobs(50)
    counts = {
        "like": runner.daily_count("like"),
        "follow": runner.daily_count("follow"),
        "dm": runner.daily_count("dm"),
        "story_view": runner.daily_count("story_view"),
    }
    limits = {
        "like": Config.DAILY_LIKE_LIMIT,
        "follow": Config.DAILY_FOLLOW_LIMIT,
        "dm": Config.DAILY_DM_LIMIT,
        "story_view": Config.DAILY_STORY_VIEW_LIMIT,
    }
    has_session = False
    with get_conn() as c:
        has_session = c.execute("SELECT 1 FROM sessions_meta LIMIT 1").fetchone() is not None
    return render_template(
        "dashboard.html",
        jobs=jobs,
        counts=counts,
        limits=limits,
        has_session=has_session,
        session_active=SESSION.is_logged_in,
    )


@bp.route("/session", methods=["GET", "POST"])
@login_required
def session_view():
    if request.method == "POST":
        action = request.form.get("action")
        if action == "save":
            # Save live context cookies (the page must already have an active session)
            import asyncio
            try:
                loop = asyncio.new_event_loop()
                try:
                    loop.run_until_complete(SESSION.ensure_started())
                    loop.run_until_complete(SESSION.save_cookies())
                finally:
                    loop.close()
                flash("Cookies saved.", "success")
            except Exception as e:
                flash(f"Save failed: {e}", "error")
        elif action == "upload":
            raw = request.form.get("cookies", "").strip()
            if not raw:
                flash("Paste a cookies JSON array first.", "error")
            else:
                try:
                    parsed = json.loads(raw)
                    assert isinstance(parsed, list)
                    with get_conn() as c:
                        c.execute(
                            """INSERT INTO sessions_meta(account_username, encrypted_cookies, updated_at)
                               VALUES (?, ?, ?)
                               ON CONFLICT(account_username) DO UPDATE SET
                                 encrypted_cookies=excluded.encrypted_cookies,
                                 updated_at=excluded.updated_at""",
                            ("me", encrypt(json.dumps(parsed)), datetime.now(timezone.utc).isoformat()),
                        )
                    flash(f"Stored {len(parsed)} cookies. Restart the app (or re-login via /session) to apply.", "success")
                except Exception as e:
                    flash(f"Invalid JSON: {e}", "error")
        elif action == "clear":
            with get_conn() as c:
                c.execute("DELETE FROM sessions_meta")
            flash("Session cleared.", "success")
        return redirect(url_for("main.session_view"))

    has_session = False
    with get_conn() as c:
        row = c.execute("SELECT * FROM sessions_meta LIMIT 1").fetchone()
        if row:
            has_session = True
    return render_template("session.html", has_session=has_session, session_active=SESSION.is_logged_in)


@bp.route("/jobs/new", methods=["POST"])
@login_required
def create_job():
    kind = request.form.get("kind", "").strip()
    payload = {}
    if kind == "like":
        payload["count"] = int(request.form.get("count", 5))
    elif kind == "follow":
        payload["username"] = request.form.get("username", "").strip()
    elif kind == "dm":
        payload["username"] = request.form.get("username", "").strip()
        payload["text"] = request.form.get("text", "").strip()
    elif kind == "story_view":
        payload["count"] = int(request.form.get("count", 5))
    elif kind == "warmup_browse":
        pass
    else:
        flash(f"Unknown job kind: {kind}", "error")
        return redirect(url_for("main.dashboard"))

    when = request.form.get("when", "now")
    run_at = None
    if when == "schedule":
        try:
            minutes = int(request.form.get("minutes", 0))
            run_at = datetime.now(timezone.utc) + timedelta(minutes=minutes)
        except Exception:
            flash("Invalid schedule minutes", "error")
            return redirect(url_for("main.dashboard"))

    job_id = runner.schedule(kind, payload, run_at)
    flash(f"Job #{job_id} ({kind}) queued.", "success")
    return redirect(url_for("main.dashboard"))


@bp.route("/jobs/<int:job_id>/cancel", methods=["POST"])
@login_required
def cancel(job_id: int):
    runner.cancel_job(job_id)
    flash(f"Job #{job_id} cancelled.", "success")
    return redirect(url_for("main.dashboard"))


@bp.route("/api/status")
@login_required
def api_status():
    return jsonify({
        "session_active": SESSION.is_logged_in,
        "headless": Config.HEADLESS,
        "limits": {
            "like": Config.DAILY_LIKE_LIMIT,
            "follow": Config.DAILY_FOLLOW_LIMIT,
            "dm": Config.DAILY_DM_LIMIT,
            "story_view": Config.DAILY_STORY_VIEW_LIMIT,
        },
        "today": {
            "like": runner.daily_count("like"),
            "follow": runner.daily_count("follow"),
            "dm": runner.daily_count("dm"),
            "story_view": runner.daily_count("story_view"),
        },
    })
