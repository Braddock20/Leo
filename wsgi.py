"""WSGI entry point used by gunicorn on Render.

Single-worker: the Playwright session and the background runner must live
in the same process. Gunicorn's `-w 1` is set in the Procfile.
"""
import os

# IGPILOT_NO_RUNNER is intentionally NOT set — we want create_app() to start
# the background runner. Single-worker gunicorn ensures we have exactly one
# Playwright context and one job runner.

from app import create_app

app = create_app()


if __name__ == "__main__":
    # Dev convenience: `python wsgi.py`
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=False)
