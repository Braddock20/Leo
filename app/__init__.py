"""Flask app factory.

Routes, services, etc. are imported inside create_app() to keep the module
import graph from getting tangled when submodules are loaded in isolation
(e.g. for the test harness or for ad-hoc scripts).
"""
import logging
import os
import atexit

from flask import Flask
from flask_login import LoginManager

from .config import Config
from .db import init_db
from .auth import AdminUser


def create_app() -> Flask:
    # Imports are deferred so that submodules can be imported on their own
    # (e.g. for testing) without triggering the full app init cycle.
    from .routes import bp as main_bp
    from .services import runner

    app = Flask(
        __name__,
        instance_path=str(Config.INSTANCE_DIR),
        template_folder="templates",
        static_folder="static",
    )
    app.config["SECRET_KEY"] = Config.SECRET_KEY
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    app.config["MAX_CONTENT_LENGTH"] = 4 * 1024 * 1024  # 4 MB

    init_db()
    AdminUser.bootstrap(Config.ADMIN_USERNAME, Config.ADMIN_PASSWORD)

    lm = LoginManager()
    lm.init_app(app)
    lm.login_view = "main.login"

    @lm.user_loader
    def load_user(uid):
        return AdminUser.by_id(uid)

    app.register_blueprint(main_bp)

    # Start the background runner (one persistent thread with its own asyncio loop)
    if os.environ.get("IGPILOT_NO_RUNNER") != "1":
        try:
            runner.start_runner()
        except Exception as e:
            app.logger.warning(f"Runner start failed: {e}")

        @atexit.register
        def _stop():
            try:
                runner.stop_runner()
            except Exception:
                pass

    return app
