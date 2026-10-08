import os
import secrets
import sys
from datetime import datetime

from flask import Flask, g, session
from werkzeug.security import generate_password_hash

from . import db as dbm
from . import service as S


def create_app(config=None):
    app = Flask(__name__)
    data_dir = os.environ.get("DATA_DIR", os.path.join(os.path.dirname(app.root_path), "data"))
    app.config.update(
        DATA_DIR=data_dir,
        DB_PATH=os.path.join(data_dir, "torneo.db"),
        UPLOAD_DIR=os.path.join(data_dir, "uploads"),
        MAX_CONTENT_LENGTH=10 * 1024 * 1024,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=os.environ.get("COOKIE_SECURE", "0") == "1",
        PERMANENT_SESSION_LIFETIME=60 * 60 * 24 * 14,
    )
    if config:
        app.config.update(config)
    os.makedirs(app.config["UPLOAD_DIR"], exist_ok=True)
    if not app.config.get("SECRET_KEY"):
        app.config["SECRET_KEY"] = _secret_key(app.config["DATA_DIR"])

    dbm.init_db(app.config["DB_PATH"])
    app.teardown_appcontext(dbm.close_db)

    from .routes import bp, register_helpers
    register_helpers(app)
    app.register_blueprint(bp)
    _ensure_boss(app)
    return app


def _secret_key(data_dir):
    if os.environ.get("SECRET_KEY"):
        return os.environ["SECRET_KEY"]
    path = os.path.join(data_dir, "secret_key")
    if os.path.exists(path):
        return open(path).read().strip()
    key = secrets.token_hex(32)
    with open(path, "w") as f:
        f.write(key)
    os.chmod(path, 0o600)
    return key


def _ensure_boss(app):
    """Crea il primo account boss (da variabili d'ambiente o con password casuale)."""
    conn = dbm.connect(app.config["DB_PATH"])
    try:
        if conn.execute("SELECT 1 FROM users WHERE role = 'boss'").fetchone():
            return
        email = os.environ.get("BOSS_EMAIL", "boss@torneo.local")
        password = os.environ.get("BOSS_PASSWORD")
        generated = password is None
        if generated:
            password = secrets.token_urlsafe(9)
        conn.execute("INSERT INTO users(email, password_hash, role, name) VALUES (?, ?, 'boss', 'Boss')",
                     (email.lower(), generate_password_hash(password)))
        conn.commit()
        if generated:
            print("=" * 60, file=sys.stderr)
            print("Account boss creato.  Email: %s  Password: %s" % (email, password), file=sys.stderr)
            print("Impostare BOSS_EMAIL / BOSS_PASSWORD per sceglierli voi.", file=sys.stderr)
            print("=" * 60, file=sys.stderr)
    finally:
        conn.close()
