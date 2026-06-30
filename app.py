"""
fileShare — a tiny self-hosted cloud file storage server.

Designed to be light enough for a Raspberry Pi Zero W / Zero 2 W:
  * Flask for routing + templates (no heavy deps, no Pillow)
  * waitress as the production WSGI server (pure-Python, low memory)
  * single shared password, session-based login
  * files stored on disk under STORAGE_DIR
  * file metadata (download counts) kept in a small JSON sidecar

Configuration comes from environment variables (see .env.example):
  FILESHARE_PASSWORD   shared login password        (required in production)
  FILESHARE_SECRET     Flask session secret key     (auto-generated if unset)
  FILESHARE_STORAGE    folder to store files in      (default: ./storage)
  FILESHARE_HOST       bind address                  (default: 127.0.0.1)
  FILESHARE_PORT       bind port                     (default: 8000)
  FILESHARE_MAX_GB     max single upload size in GB  (default: 8)
"""

import json
import os
import secrets
import shutil
import threading
from datetime import datetime
from functools import wraps

from flask import (
    Flask,
    abort,
    flash,
    jsonify,
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

# Where we keep download counts. A hidden sidecar inside STORAGE_DIR so it
# travels with the files (e.g. on a USB drive) but is never shown in listings.
META_PATH = os.path.join(STORAGE_DIR, ".fileshare_meta.json")
_meta_lock = threading.Lock()

app = Flask(__name__)
app.config["SECRET_KEY"] = SECRET_KEY
app.config["MAX_CONTENT_LENGTH"] = int(MAX_GB * 1024 * 1024 * 1024)

# --------------------------------------------------------------------------- #
# File categories (by extension)
# --------------------------------------------------------------------------- #
CATEGORY_EXT = {
    "image": {
        "png", "jpg", "jpeg", "gif", "webp", "bmp", "svg",
        "heic", "heif", "avif", "ico", "tiff",
    },
    "video": {
        "mp4", "mkv", "mov", "avi", "webm", "m4v", "flv", "wmv", "mpeg", "3gp",
    },
    "audio": {
        "mp3", "wav", "flac", "aac", "ogg", "m4a", "opus", "wma", "aiff",
    },
}
# Anything that is not image/video/audio is treated as a "document".


def category_for(ext):
    ext = ext.lower().lstrip(".")
    for cat, exts in CATEGORY_EXT.items():
        if ext in exts:
            return cat
    return "document"


# --------------------------------------------------------------------------- #
# Metadata (download counts)
# --------------------------------------------------------------------------- #
def _load_meta():
    try:
        with open(META_PATH, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return {}


def _save_meta(meta):
    tmp = META_PATH + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(meta, fh)
        os.replace(tmp, META_PATH)
    except OSError:
        pass


def get_downloads(name):
    with _meta_lock:
        return _load_meta().get(name, {}).get("downloads", 0)


def bump_downloads(name):
    with _meta_lock:
        meta = _load_meta()
        entry = meta.setdefault(name, {})
        entry["downloads"] = entry.get("downloads", 0) + 1
        _save_meta(meta)


def forget_file(name):
    with _meta_lock:
        meta = _load_meta()
        if name in meta:
            del meta[name]
            _save_meta(meta)


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
    if not name or name.startswith("."):
        abort(404)
    full = os.path.realpath(os.path.join(STORAGE_DIR, name))
    storage_root = os.path.realpath(STORAGE_DIR)
    if os.path.commonpath([full, storage_root]) != storage_root:
        abort(404)
    return name, full


def list_files():
    meta = _load_meta()
    items = []
    for entry in os.scandir(STORAGE_DIR):
        if not entry.is_file() or entry.name.startswith("."):
            continue
        stat = entry.stat()
        ext = os.path.splitext(entry.name)[1].lower().lstrip(".")
        items.append(
            {
                "name": entry.name,
                "ext": ext,
                "category": category_for(ext),
                "size": human_size(stat.st_size),
                "size_bytes": stat.st_size,
                "modified": datetime.fromtimestamp(stat.st_mtime).strftime(
                    "%b %d, %Y"
                ),
                "modified_ts": stat.st_mtime,
                "downloads": meta.get(entry.name, {}).get("downloads", 0),
            }
        )
    # Newest first — most useful default on a phone.
    items.sort(key=lambda f: f["modified_ts"], reverse=True)
    return items


def storage_stats(files):
    used_by_files = sum(f["size_bytes"] for f in files)
    try:
        usage = shutil.disk_usage(STORAGE_DIR)
        total, free = usage.total, usage.free
    except OSError:
        total = free = 0
    counts = {"image": 0, "video": 0, "audio": 0, "document": 0}
    for f in files:
        counts[f["category"]] = counts.get(f["category"], 0) + 1
    return {
        "files_bytes": used_by_files,
        "files_human": human_size(used_by_files),
        "disk_total": total,
        "disk_total_human": human_size(total) if total else "—",
        "disk_free": free,
        "disk_free_human": human_size(free) if total else "—",
        "disk_used": (total - free) if total else used_by_files,
        "disk_used_human": human_size(total - free) if total else "—",
        "percent_used": round((total - free) / total * 100) if total else 0,
        "total_files": len(files),
        "counts": counts,
    }


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
    files = list_files()
    return render_template(
        "index.html",
        files=files,
        stats=storage_stats(files),
        max_gb=MAX_GB,
    )


@app.route("/upload", methods=["POST"])
@login_required
def upload():
    uploaded = request.files.getlist("files")
    saved = 0
    for f in uploaded:
        if not f or not f.filename:
            continue
        name = secure_filename(f.filename)
        if not name or name.startswith("."):
            continue
        f.save(os.path.join(STORAGE_DIR, name))
        saved += 1
    # AJAX uploads expect JSON; classic form posts get a redirect.
    if request.headers.get("X-Requested-With") == "fetch":
        return jsonify({"saved": saved})
    flash(f"Uploaded {saved} file(s)." if saved else "No files selected.")
    return redirect(url_for("index"))


@app.route("/view/<path:filename>")
@login_required
def view(filename):
    """Serve a file inline (for in-page image thumbnails / doc previews)."""
    name, _ = safe_path(filename)
    return send_from_directory(STORAGE_DIR, name, as_attachment=False)


@app.route("/download/<path:filename>")
@login_required
def download(filename):
    name, _ = safe_path(filename)
    bump_downloads(name)
    return send_from_directory(STORAGE_DIR, name, as_attachment=True)


@app.route("/delete/<path:filename>", methods=["POST"])
@login_required
def delete(filename):
    name, full = safe_path(filename)
    if os.path.isfile(full):
        os.remove(full)
        forget_file(name)
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
