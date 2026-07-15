"""Flask-Login user model + helpers."""
from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash
from .config import Config
from .db import get_conn


class AdminUser(UserMixin):
    def __init__(self, id_, username):
        self.id = id_
        self.username = username

    @staticmethod
    def by_id(user_id: str):
        with get_conn() as c:
            row = c.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
        if not row:
            return None
        return AdminUser(row["id"], row["username"])

    @staticmethod
    def by_username(username: str):
        with get_conn() as c:
            row = c.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
        if not row:
            return None
        return AdminUser(row["id"], row["username"])

    @staticmethod
    def bootstrap(username: str, password: str):
        """Create the single admin user if missing."""
        with get_conn() as c:
            row = c.execute("SELECT id FROM users WHERE username=?", (username,)).fetchone()
            if row:
                return
            c.execute(
                "INSERT INTO users(username, password_hash, created_at) VALUES (?,?,?)",
                (username, generate_password_hash(password), "bootstrap"),
            )
