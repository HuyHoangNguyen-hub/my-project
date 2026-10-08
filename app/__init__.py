"""Application factory: ráp config, DB, bảo mật, filter Jinja, blueprint, trang lỗi."""
# config PHẢI import đầu tiên: nạp .env trước khi mailer.py đọc SMTP_* từ môi trường.
from . import config  # noqa: F401
import os
from datetime import datetime
from importlib import import_module

from flask import Flask, render_template
from werkzeug.exceptions import HTTPException

from .config import Config, BASE_DIR, BANNER_DIR, CATEGORIES, DEFAULT_ORG_NAME
from . import db, security

ERROR_MESSAGES = {
    403: "Bạn không có quyền truy cập trang này.",
    404: "Không tìm thấy trang hoặc dữ liệu bạn yêu cầu.",
    405: "Phương thức không được hỗ trợ.",
    413: "Tệp tải lên quá lớn (tối đa 5MB).",
    500: "Đã xảy ra lỗi hệ thống, vui lòng thử lại sau.",
}


def _parse(value):
    try:
        return datetime.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None


def vnd(value):
    """1500000 -> '1.500.000 VNĐ'"""
    try:
        return f"{int(value or 0):,}".replace(",", ".") + " VNĐ"
    except (TypeError, ValueError):
        return str(value)


def vndate(value):
    """ISO -> dd/mm/yyyy"""
    dt = _parse(value)
    return dt.strftime("%d/%m/%Y") if dt else "—"


def vnrange(e):
    """Khoảng thời gian của sự kiện: 'dd/mm/yyyy HH:MM → dd/mm/yyyy HH:MM'
    (cùng ngày thì rút gọn phần ngày của giờ kết thúc)."""
    s, en = _parse(e["start_at"]), _parse(e["end_at"])
    if not s:
        return "—"
    if not en:
        return s.strftime("%d/%m/%Y %H:%M")
    if s.date() == en.date():
        return f"{s:%d/%m/%Y %H:%M} → {en:%H:%M}"
    return f"{s:%d/%m/%Y %H:%M} → {en:%d/%m/%Y %H:%M}"


def create_app():
    app = Flask(__name__, template_folder=str(BASE_DIR / "templates"),
                static_folder=str(BASE_DIR / "static"))
    app.config.from_object(Config)
    os.makedirs(BANNER_DIR, exist_ok=True)

    db.init_db()                                   # tạo bảng + seed admin (an toàn khi gọi lại)
    app.teardown_appcontext(db.close_db)
    security.init_app(app)                         # CSRF, guard phiên, security headers

    app.jinja_env.filters.update(vnd=vnd, vndate=vndate, vnrange=vnrange)
    app.jinja_env.globals.update(CATEGORIES=CATEGORIES, DEFAULT_ORG_NAME=DEFAULT_ORG_NAME)

    # Đăng ký các blueprint CÓ MẶT trong gói này. (Bản gốc import cứng cả 4; ở đây
    # bỏ qua blueprint chưa có để mỗi phần chạy độc lập — khi ghép đủ 5 phần thì đủ cả 4.)
    for name in ("auth", "events", "profile", "admin"):
        modname = f"{__name__}.blueprints.{name}"
        try:
            mod = import_module(modname)
        except ModuleNotFoundError as ex:
            if ex.name != modname:
                raise
            continue
        app.register_blueprint(mod.bp)

    # >>> STANDALONE (STUB - XOÁ KHI GHÉP; ghep.py tự gỡ khối này)
    try:
        from _standalone import apply as _apply_standalone
    except ModuleNotFoundError as ex:
        if ex.name != "_standalone":
            raise
    else:
        _apply_standalone(app)
    # <<< STANDALONE

    @app.errorhandler(HTTPException)
    def http_error(e):
        # 400 (vd CSRF) giữ nguyên thông điệp tiếng Việt do code đặt
        msg = e.description if e.code == 400 else ERROR_MESSAGES.get(e.code, e.description)
        return render_template("error.html", code=e.code, msg=msg), e.code

    return app
