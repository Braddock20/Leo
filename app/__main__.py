"""Entry point for `python -m app` and gunicorn `app:app`."""
from . import create_app

app = create_app()
