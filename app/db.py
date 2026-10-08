"""Tầng dữ liệu SQLite: kết nối theo request, schema, migration, seed admin,
cài đặt (settings) và các hàm thời gian dùng chung."""
import sqlite3
from datetime import datetime, timezone

from flask import g
from werkzeug.security import generate_password_hash

from .config import (DB_PATH, VN_TZ, ADMIN_EMAIL, ADMIN_USERNAME, ADMIN_FULLNAME,
                     ADMIN_DEFAULT_PASSWORD, DEFAULT_ORG_NAME)

# Số người đã giữ chỗ của sự kiện (đã xác nhận + đang chờ thanh toán/duyệt).
# Dùng trong câu SELECT có bí danh bảng events là "e":  f"... {JOINED_SQL} AS joined ..."
JOINED_SQL = ("(SELECT COUNT(*) FROM registrations rj WHERE rj.event_id=e.id"
              " AND rj.status IN ('confirmed','pending'))")

SCHEMA = """
CREATE TABLE IF NOT EXISTS users(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  username TEXT UNIQUE NOT NULL,
  email    TEXT UNIQUE NOT NULL,
  fullname TEXT NOT NULL,
  password TEXT NOT NULL,
  role     TEXT NOT NULL DEFAULT 'user',
  is_active INTEGER NOT NULL DEFAULT 1,
  failed_count INTEGER NOT NULL DEFAULT 0,
  locked_until TEXT,
  session_token TEXT,
  reset_code TEXT,
  reset_code_expires TEXT,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS events(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  title TEXT NOT NULL,
  description TEXT,
  location TEXT,
  category TEXT NOT NULL DEFAULT 'Khác',
  is_paid INTEGER NOT NULL DEFAULT 0,
  fee INTEGER NOT NULL DEFAULT 0,
  needs_approval INTEGER NOT NULL DEFAULT 0,
  banner TEXT,
  start_at TEXT NOT NULL,
  end_at TEXT,
  capacity INTEGER NOT NULL DEFAULT 100,
  created_by INTEGER REFERENCES users(id),
  created_at TEXT NOT NULL,
  organizer TEXT
);
CREATE TABLE IF NOT EXISTS registrations(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id  INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  event_id INTEGER NOT NULL REFERENCES events(id) ON DELETE CASCADE,
  status TEXT NOT NULL DEFAULT 'confirmed',
  payment_status TEXT NOT NULL DEFAULT 'free',
  amount INTEGER NOT NULL DEFAULT 0,
  ticket_code TEXT,
  phone TEXT,
  note TEXT,
  paid_at TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT,
  UNIQUE(user_id, event_id)
);
CREATE TABLE IF NOT EXISTS settings(
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_reg_event ON registrations(event_id, status);
CREATE INDEX IF NOT EXISTS idx_reg_user  ON registrations(user_id, status);
CREATE INDEX IF NOT EXISTS idx_events_start ON events(start_at);
"""

# Cột bổ sung cho DB tạo từ phiên bản cũ (migration nhẹ, chạy lặp lại an toàn)
MIGRATIONS = [
    ("events", "organizer", "TEXT"),
    ("events", "needs_approval", "INTEGER NOT NULL DEFAULT 0"),
    ("events", "end_at", "TEXT"),
    ("registrations", "phone", "TEXT"),
    ("registrations", "note", "TEXT"),
    ("registrations", "paid_at", "TEXT"),
    ("registrations", "updated_at", "TEXT"),
    ("users", "reset_code", "TEXT"),
    ("users", "reset_code_expires", "TEXT"),
    ("users", "session_token", "TEXT"),
]


# ---------------------------------------------------------------- THỜI GIAN
def now() -> str:
    """Thời điểm hiện tại theo UTC, ISO giây — dùng cho created_at, khoá tài khoản, mã OTP..."""
    return datetime.now(timezone.utc).replace(tzinfo=None).isoformat(timespec="seconds")


def now_minute() -> str:
    """Giờ Việt Nam hiện tại dạng 'YYYY-MM-DDTHH:MM' — so sánh trực tiếp với start_at/end_at
    của sự kiện (được lưu theo cùng định dạng, giờ Việt Nam)."""
    return datetime.now(VN_TZ).strftime("%Y-%m-%dT%H:%M")


# ---------------------------------------------------------------- KẾT NỐI
def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys=ON")
    return g.db


def close_db(exc=None):
    d = g.pop("db", None)
    if d is not None:
        d.close()


# ---------------------------------------------------------------- SETTINGS
def get_setting(key, default=None):
    r = get_db().execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    return r["value"] if r else default


def set_setting(key, value):
    get_db().execute(
        "INSERT INTO settings(key,value) VALUES(?,?)"
        " ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, value))
    get_db().commit()


# ---------------------------------------------------------------- KHỞI TẠO
def init_db():
    """Tạo bảng (nếu chưa có), migration cột còn thiếu, seed DUY NHẤT 1 admin.
    Dùng kết nối riêng nên gọi được ngoài request (run.py / create_app)."""
    d = sqlite3.connect(DB_PATH)
    d.row_factory = sqlite3.Row
    try:
        d.executescript(SCHEMA)
        for table, col, ddl in MIGRATIONS:
            cols = {r["name"] for r in d.execute(f"PRAGMA table_info({table})")}
            if col not in cols:
                d.execute(f"ALTER TABLE {table} ADD COLUMN {col} {ddl}")

        # Chỉ seed admin khi hệ thống chưa có admin nào -> luôn đúng 1 admin duy nhất
        if not d.execute("SELECT 1 FROM users WHERE role='admin'").fetchone():
            existing = d.execute("SELECT id FROM users WHERE email=?", (ADMIN_EMAIL,)).fetchone()
            if existing:
                d.execute("UPDATE users SET role='admin' WHERE id=?", (existing["id"],))
            else:
                username = ADMIN_USERNAME
                if d.execute("SELECT 1 FROM users WHERE username=?", (username,)).fetchone():
                    username = ADMIN_USERNAME + "_sk"
                d.execute(
                    "INSERT INTO users(username,email,fullname,password,role,created_at)"
                    " VALUES(?,?,?,?,'admin',?)",
                    (username, ADMIN_EMAIL, ADMIN_FULLNAME,
                     generate_password_hash(ADMIN_DEFAULT_PASSWORD), now()))
        d.execute("INSERT OR IGNORE INTO settings(key,value) VALUES('org_name',?)",
                  (DEFAULT_ORG_NAME,))
        d.commit()
    finally:
        d.close()
