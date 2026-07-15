#!/usr/bin/env bash
# Render build script.
# Render runs us in /opt/render/project/src with a clean Python venv, so we
# don't create a new one — we just install into the active environment.
set -e
echo "==> Upgrading pip"
python -m pip install --upgrade pip
echo "==> Installing Python dependencies"
python -m pip install -r requirements.txt
echo "==> Installing Playwright Chromium"
python -m playwright install chromium
echo "==> Installing Chromium OS dependencies (best effort)"
python -m playwright install-deps chromium || echo "   (install-deps skipped — non-fatal on Render)"
echo "==> Build complete"
