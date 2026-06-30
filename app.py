"""
fileShare — a tiny self-hosted cloud file storage server.

Designed to be light enough for a Raspberry Pi Zero 2 W:
  * Flask for routing + templates
  * waitress as the production WSGI server (pure-Python, low memory)
  * single shared password, session-based login
  * files stored on disk under STORAGE_DIR

Configuration comes from environment variables (see .env.example):
  FILESHARE_PASSWORD   shared login password        (required in production)
  FILESHARE_SECRET     Flask session secret key     (auto-generated if unset)
  FILESHARE_STORAGE    folder to store files in      (default: ./storage)
  FILESHARE_HOST       bind address                  (default: 127.0.0.1)
  FILESHARE_PORT       bind port                     (default: 8000)
  FILESHARE_MAX_GB     max single upload size in GB  (default: 8)
"""

import os
import secrets
from datetime import datetime
from functools import wraps

from flask import (
    Flask,
    abort,
    flash,
    redirect,
    render_template,
    request,
    send_from_directory,
    session,
    url_for,
)
from werkzeug.utils import secure_filename

# --------------------------------------------------------------------------- #
# Configuration
# --------------------------------------------------------------------------- #
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

PASSWORD = os.environ.get("FILESHARE_PASSWORD", "changeme")
SECRET_KEY = os.environ.get("FILESHARE_SECRET") or secrets.token_hex(32)
STORAGE_DIR = os.environ.get(
    "FILESHARE_STORAGE", os.path.join(BASE_DIR, "storage")
)
HOST = os.environ.get("FILESHARE_HOST", "127.0.0.1")
PORT = int(os.environ.get("FILESHARE_PORT", "8000"))
MAX_GB = float(os.environ.get("FILESHARE_MAX_GB", "8"))

os.makedirs(STORAGE_DIR, exist_ok=True)

app = Flask(__name__)
app.config["SECRET_KEY"] = SECRET_KEY
app.config["MAX_CONTENT_LENGTH"] = int(MAX_GB * 1024 * 1024 * 1024)


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("logged_in"):
            return redirect(url_for("login", next=request.path))
        return view(*args, **kwargs)

    return wrapped


def human_size(num_bytes):
    size = float(num_bytes)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024 or unit == "TB":
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024


def safe_path(filename):
    """Resolve a filename to an absolute path inside STORAGE_DIR, or 404."""
    name = secure_filename(filename)
    if not name:
        abort(404)
    full = os.path.realpath(os.path.join(STORAGE_DIR, name))
    storage_root = os.path.realpath(STORAGE_DIR)
    if os.path.commonpath([full, storage_root]) != storage_root:
        abort(404)
    return name, full


def list_files():
    items = []
    for entry in os.scandir(STORAGE_DIR):
        if entry.is_file():
            stat = entry.stat()
            items.append(
                {
                    "name": entry.name,
                    "size": human_size(stat.st_size),
                    "modified": datetime.fromtimestamp(stat.st_mtime).strftime(
                        "%Y-%m-%d %H:%M"
                    ),
                }
            )
    items.sort(key=lambda f: f["name"].lower())
    return items


# --------------------------------------------------------------------------- #
# Routes
# --------------------------------------------------------------------------- #
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        if request.form.get("password") == PASSWORD:
            session["logged_in"] = True
            session.permanent = True
            nxt = request.args.get("next") or url_for("index")
            return redirect(nxt)
        flash("Wrong password.")
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/")
@login_required
def index():
    return render_template("index.html", files=list_files(), max_gb=MAX_GB)


@app.route("/upload", methods=["POST"])
@login_required
def upload():
    uploaded = request.files.getlist("files")
    saved = 0
    for f in uploaded:
        if not f or not f.filename:
            continue
        name = secure_filename(f.filename)
        if not name:
            continue
        f.save(os.path.join(STORAGE_DIR, name))
        saved += 1
    flash(f"Uploaded {saved} file(s)." if saved else "No files selected.")
    return redirect(url_for("index"))


@app.route("/download/<path:filename>")
@login_required
def download(filename):
    name, _ = safe_path(filename)
    return send_from_directory(STORAGE_DIR, name, as_attachment=True)


@app.route("/delete/<path:filename>", methods=["POST"])
@login_required
def delete(filename):
    name, full = safe_path(filename)
    if os.path.isfile(full):
        os.remove(full)
        flash(f"Deleted {name}.")
    return redirect(url_for("index"))


@app.errorhandler(413)
def too_large(_):
    return (
        f"File too large. Max upload size is {MAX_GB} GB "
        f"(set FILESHARE_MAX_GB to change).",
        413,
    )


# --------------------------------------------------------------------------- #
# Entry point
# --------------------------------------------------------------------------- #
def main():
    if PASSWORD == "changeme":
        print(
            "WARNING: using default password 'changeme'. "
            "Set FILESHARE_PASSWORD before exposing this to the internet!"
        )
    try:
        from waitress import serve

        print(f"fileShare serving on http://{HOST}:{PORT}  (storage: {STORAGE_DIR})")
        serve(app, host=HOST, port=PORT, threads=4)
    except ImportError:
        # Fallback for quick local testing without waitress installed.
        print("waitress not installed; falling back to Flask dev server.")
        app.run(host=HOST, port=PORT)


if __name__ == "__main__":
    main()
