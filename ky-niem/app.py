"""
Kỷ niệm của tôi - website lưu giữ ảnh và kỷ niệm cá nhân.
Chạy:  python app.py   rồi mở http://localhost:5000
"""
import os
import re
import secrets
import sqlite3
import uuid
from datetime import date, datetime
from functools import wraps

from flask import (Flask, abort, flash, g, jsonify, redirect, render_template,
                   request, send_from_directory, session, url_for)
from PIL import Image, ImageOps

BASE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(BASE, "data")
UPLOADS = os.path.join(DATA, "uploads")   # ảnh gốc
THUMBS = os.path.join(DATA, "thumbs")     # ảnh thu nhỏ (tải nhanh)
DB_PATH = os.path.join(DATA, "memories.db")
ALLOWED = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"}
PER_PAGE = 90

# Đặt mật khẩu bằng biến môi trường MEMORY_PASSWORD. Để trống = không cần đăng nhập.
PASSWORD = os.environ.get("MEMORY_PASSWORD", "")

for d in (DATA, UPLOADS, THUMBS):
    os.makedirs(d, exist_ok=True)


def _secret_key():
    path = os.path.join(DATA, "secret.key")
    if not os.path.exists(path):
        with open(path, "w") as f:
            f.write(secrets.token_hex(32))
    with open(path) as f:
        return f.read().strip()


app = Flask(__name__)
app.secret_key = _secret_key()
app.config["MAX_CONTENT_LENGTH"] = 1024 * 1024 * 1024  # 1 GB mỗi lần gửi (web gửi theo từng nhóm nhỏ)


# ---------- Cơ sở dữ liệu ----------
def db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


@app.teardown_appcontext
def close_db(_):
    conn = g.pop("db", None)
    if conn:
        conn.close()


def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS memories (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        description TEXT NOT NULL DEFAULT '',
        memory_date TEXT NOT NULL,
        created_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS photos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        memory_id INTEGER NOT NULL REFERENCES memories(id) ON DELETE CASCADE,
        filename TEXT NOT NULL,
        thumb TEXT NOT NULL,
        width INTEGER NOT NULL,
        height INTEGER NOT NULL,
        size INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL
    );
    CREATE INDEX IF NOT EXISTS idx_photos_memory ON photos(memory_id);
    CREATE INDEX IF NOT EXISTS idx_memories_date ON memories(memory_date);
    """)
    conn.commit()
    conn.close()


init_db()


# ---------- Đăng nhập (tuỳ chọn) ----------
@app.before_request
def require_login():
    if not PASSWORD:
        return
    if request.endpoint in ("login", "static"):
        return
    if not session.get("ok"):
        if request.path.startswith("/api/"):
            return jsonify(error="Chưa đăng nhập"), 401
        return redirect(url_for("login", next=request.path))


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        if secrets.compare_digest(request.form.get("password", ""), PASSWORD):
            session["ok"] = True
            nxt = request.args.get("next", "/")
            return redirect(nxt if nxt.startswith("/") and not nxt.startswith("//") else "/")
        flash("Mật khẩu chưa đúng.")
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login") if PASSWORD else url_for("index"))


# ---------- Tiện ích ----------
@app.template_filter("vdate")
def vdate(value):
    try:
        return datetime.strptime(value, "%Y-%m-%d").strftime("%d/%m/%Y")
    except (TypeError, ValueError):
        return value or ""


@app.template_filter("filesize")
def filesize(n):
    n = float(n or 0)
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024


def parse_date(value):
    try:
        return datetime.strptime(value, "%Y-%m-%d").strftime("%Y-%m-%d")
    except (TypeError, ValueError):
        return date.today().isoformat()


def save_photo(memory_id, storage):
    ext = os.path.splitext(storage.filename or "")[1].lower()
    if ext not in ALLOWED:
        return False
    stem = uuid.uuid4().hex
    name = stem + ext
    thumb = stem + ".jpg"
    path = os.path.join(UPLOADS, name)
    storage.save(path)
    try:
        with Image.open(path) as im:
            im = ImageOps.exif_transpose(im)
            im.thumbnail((640, 640))
            if im.mode != "RGB":
                im = im.convert("RGB")
            im.save(os.path.join(THUMBS, thumb), "JPEG", quality=82, optimize=True)
            w, h = im.size
    except Exception:
        for p in (path, os.path.join(THUMBS, thumb)):
            if os.path.exists(p):
                os.remove(p)
        return False
    db().execute(
        "INSERT INTO photos (memory_id, filename, thumb, width, height, size, created_at) VALUES (?,?,?,?,?,?,?)",
        (memory_id, name, thumb, w, h, os.path.getsize(path), datetime.now().isoformat()),
    )
    return True


def remove_photo_files(rows):
    for r in rows:
        for folder, fn in ((UPLOADS, r["filename"]), (THUMBS, r["thumb"])):
            try:
                os.remove(os.path.join(folder, fn))
            except FileNotFoundError:
                pass


def get_memory(memory_id):
    m = db().execute("SELECT * FROM memories WHERE id=?", (memory_id,)).fetchone()
    if not m:
        abort(404)
    return m


# ---------- Trang ----------
@app.route("/")
def index():
    q = request.args.get("q", "").strip()
    like = f"%{q}%"
    rows = db().execute(
        """SELECT m.*, (SELECT COUNT(*) FROM photos p WHERE p.memory_id = m.id) AS n
           FROM memories m
           WHERE (? = '' OR m.title LIKE ? OR m.description LIKE ?)
           ORDER BY m.memory_date DESC, m.id DESC""",
        (q, like, like),
    ).fetchall()
    years = {}
    for m in rows:
        thumbs = db().execute(
            "SELECT * FROM photos WHERE memory_id=? ORDER BY id LIMIT 4", (m["id"],)
        ).fetchall()
        years.setdefault(m["memory_date"][:4], []).append({"m": m, "thumbs": thumbs})
    stats = db().execute("SELECT COUNT(*) c, COALESCE(SUM(size),0) s FROM photos").fetchone()
    total_memories = db().execute("SELECT COUNT(*) FROM memories").fetchone()[0]
    return render_template("index.html", years=years, q=q, stats=stats,
                           total_memories=total_memories, found=len(rows))


@app.route("/photos")
def all_photos():
    page = max(1, request.args.get("page", 1, type=int))
    total = db().execute("SELECT COUNT(*) FROM photos").fetchone()[0]
    photos = db().execute(
        """SELECT p.*, m.title, m.memory_date FROM photos p
           JOIN memories m ON m.id = p.memory_id
           ORDER BY m.memory_date DESC, p.id DESC LIMIT ? OFFSET ?""",
        (PER_PAGE, (page - 1) * PER_PAGE),
    ).fetchall()
    pages = max(1, -(-total // PER_PAGE))
    return render_template("photos.html", photos=photos, page=page, pages=pages, total=total)


@app.route("/new")
def new_memory():
    return render_template("new.html", today=date.today().isoformat())


@app.route("/memory/<int:memory_id>")
def memory(memory_id):
    m = get_memory(memory_id)
    photos = db().execute("SELECT * FROM photos WHERE memory_id=? ORDER BY id", (memory_id,)).fetchall()
    return render_template("memory.html", m=m, photos=photos)


@app.route("/memory/<int:memory_id>/edit", methods=["POST"])
def edit_memory(memory_id):
    get_memory(memory_id)
    title = request.form.get("title", "").strip() or "Kỷ niệm không tên"
    db().execute(
        "UPDATE memories SET title=?, description=?, memory_date=? WHERE id=?",
        (title, request.form.get("description", "").strip(),
         parse_date(request.form.get("memory_date")), memory_id),
    )
    db().commit()
    return redirect(url_for("memory", memory_id=memory_id))


@app.route("/memory/<int:memory_id>/delete", methods=["POST"])
def delete_memory(memory_id):
    get_memory(memory_id)
    rows = db().execute("SELECT filename, thumb FROM photos WHERE memory_id=?", (memory_id,)).fetchall()
    db().execute("DELETE FROM memories WHERE id=?", (memory_id,))
    db().commit()
    remove_photo_files(rows)
    return redirect(url_for("index"))


@app.route("/photo/<int:photo_id>/delete", methods=["POST"])
def delete_photo(photo_id):
    row = db().execute("SELECT * FROM photos WHERE id=?", (photo_id,)).fetchone()
    if not row:
        abort(404)
    db().execute("DELETE FROM photos WHERE id=?", (photo_id,))
    db().commit()
    remove_photo_files([row])
    return jsonify(ok=True)


@app.route("/media/<kind>/<path:name>")
def media(kind, name):
    folder = {"uploads": UPLOADS, "thumbs": THUMBS}.get(kind)
    if not folder or not re.fullmatch(r"[0-9a-f]{32}\.\w+", name):
        abort(404)
    resp = send_from_directory(folder, name)
    resp.headers["Cache-Control"] = "private, max-age=31536000, immutable"
    return resp


# ---------- API (trang web gửi ảnh theo từng nhóm nhỏ để chịu được rất nhiều ảnh) ----------
@app.route("/api/memories", methods=["POST"])
def api_create_memory():
    data = request.get_json(silent=True) or {}
    title = (data.get("title") or "").strip() or "Kỷ niệm không tên"
    cur = db().execute(
        "INSERT INTO memories (title, description, memory_date, created_at) VALUES (?,?,?,?)",
        (title, (data.get("description") or "").strip(),
         parse_date(data.get("memory_date")), datetime.now().isoformat()),
    )
    db().commit()
    return jsonify(id=cur.lastrowid, url=url_for("memory", memory_id=cur.lastrowid))


@app.route("/api/memories/<int:memory_id>/photos", methods=["POST"])
def api_add_photos(memory_id):
    get_memory(memory_id)
    saved = failed = 0
    for f in request.files.getlist("photos"):
        if save_photo(memory_id, f):
            saved += 1
        else:
            failed += 1
    db().commit()
    return jsonify(saved=saved, failed=failed)


if __name__ == "__main__":
    # host="0.0.0.0" cho phép điện thoại cùng mạng Wi-Fi truy cập bằng IP của máy tính
    app.run(host="0.0.0.0", port=5000, debug=False)
