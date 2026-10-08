"""Bảo mật dùng chung: CSRF token, vân tay trình duyệt, guard phiên,
decorator @login_required / @admin_required, security headers."""
import re
import hashlib
import secrets
from functools import wraps
from flask import g, session, request, redirect, url_for, flash, abort

from .db import get_db


def valid_password(p: str) -> bool:
    return (len(p) >= 8 and re.search(r"[A-Z]", p) and re.search(r"[a-z]", p)
            and re.search(r"\d", p))


def csrf_token() -> str:
    if "csrf" not in session:
        session["csrf"] = secrets.token_urlsafe(32)
    return session["csrf"]


def client_fingerprint() -> str:
    """Gắn phiên với trình duyệt -> chống đánh cắp cookie phiên."""
    raw = request.headers.get("User-Agent", "") + "|" + (request.remote_addr or "")
    return hashlib.sha256(raw.encode()).hexdigest()


def new_session_for(user_row):
    """Tạo phiên hoàn toàn mới sau khi đăng nhập -> chống Session Fixation.
       Trả về session_token mới, đã lưu vào cookie phiên."""
    token = secrets.token_urlsafe(32)
    get_db().execute("UPDATE users SET failed_count=0, locked_until=NULL, session_token=?"
                     " WHERE id=?", (token, user_row["id"]))
    get_db().commit()
    session.clear()
    session.permanent = True
    session.update(uid=user_row["id"], tok=token, fp=client_fingerprint(),
                   csrf=secrets.token_urlsafe(32))
    return token


def guard():
    """Chạy trước mọi request: kiểm tra CSRF (POST) và tính hợp lệ của phiên."""
    if request.method == "POST":
        if not secrets.compare_digest(request.form.get("csrf", ""), session.get("csrf", "x")):
            abort(400, "CSRF token không hợp lệ")

    g.user = None
    uid = session.get("uid")
    if uid:
        if session.get("fp") != client_fingerprint():
            session.clear()
            flash("Phiên không hợp lệ, vui lòng đăng nhập lại.", "error")
            return redirect(url_for("auth.login"))
        row = get_db().execute("SELECT * FROM users WHERE id=? AND is_active=1",
                               (uid,)).fetchone()
        # Token phiên lưu ở DB -> đăng nhập nơi khác hoặc bị admin đổi quyền
        # sẽ vô hiệu hoá ngay phiên cũ
        if not row or row["session_token"] != session.get("tok"):
            session.clear()
            flash("Phiên đã kết thúc. Vui lòng đăng nhập lại.", "error")
            return redirect(url_for("auth.login"))
        g.user = row
        session.permanent = True
        session.modified = True          # gia hạn thời gian sống của phiên
    return None


def secure_headers(resp):
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["X-Frame-Options"] = "DENY"
    resp.headers["Referrer-Policy"] = "same-origin"
    # script-src cần 'unsafe-inline' vì toàn bộ JS của app nằm inline trong template
    # (nút mắt xem mật khẩu, xác nhận xoá, tự làm mới trang thanh toán...) — dự án nhỏ,
    # không tải script từ nguồn ngoài nên rủi ro XSS qua script bên thứ 3 vẫn được chặn.
    resp.headers["Content-Security-Policy"] = (
        "default-src 'self'; style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline'")
    return resp


def login_required(f):
    """Bắt buộc đăng nhập mới được vào route (áp dụng cả trang chủ)."""
    @wraps(f)
    def wrapper(*a, **k):
        if not g.user:
            return redirect(url_for("auth.login", next=request.path))
        return f(*a, **k)
    return wrapper


def admin_required(f):
    @wraps(f)
    @login_required
    def wrapper(*a, **k):
        if g.user["role"] != "admin":
            abort(403)
        return f(*a, **k)
    return wrapper


def init_app(app):
    app.jinja_env.globals["csrf_token"] = csrf_token
    app.before_request(guard)
    app.after_request(secure_headers)
    app.context_processor(lambda: {"current_user": getattr(g, "user", None)})
