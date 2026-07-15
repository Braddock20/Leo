"""Top-level shim so gunicorn can find `app:app`."""
from app import create_app

app = create_app()
