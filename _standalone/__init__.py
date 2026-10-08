"""[STUB - XOÁ CẢ THƯ MỤC NÀY KHI GHÉP] Lớp "chạy độc lập" cho từng phần.

Thư mục này GIỐNG HỆT nhau ở cả 5 gói. Khi khởi động nó tự làm 4 việc, chỉ để phần
của bạn chạy riêng được mà không cần code của 4 phần còn lại:
  1. Seed dữ liệu mẫu (user1, user2, vài sự kiện, vài đăng ký) — chỉ lần chạy đầu.
  2. Với route thuộc phần khác (chưa có trong gói): đăng ký sẵn tên route nhưng trả về LỖI HỆ THỐNG
     404 (trang lỗi thật của app) — như thể chức năng đó không tồn tại. Không có trang giả nào cả.
     (Phải đăng ký tên route thì url_for() trong template mới không làm sập cả trang.)
  3. Trang đăng nhập "vào nhanh" (chỉ dùng khi gói KHÔNG có Phần 1) + đăng xuất.
  4. Nếu chưa cấu hình SMTP: email không gửi thật mà in ra terminal + ghi vào
     _standalone/outbox.txt (để xem mã quên mật khẩu, mã vé...).
Phần thật luôn được ưu tiên: route nào đã có thật thì stub KHÔNG đè lên."""
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

from flask import (render_template_string, redirect, url_for, flash, request,
                   session, g, abort)
from markupsafe import Markup, escape
from werkzeug.security import generate_password_hash

from app import mailer
from app.config import DB_PATH, VN_TZ
from app.db import get_db, now
from app.security import new_session_for

OUTBOX = Path(__file__).with_name("outbox.txt")
DEMO_PW = "User@123"

PART_NAME = {1: "Tài khoản", 2: "Sự kiện", 3: "Lọc & Trang chủ",
             4: "Đăng ký & admin", 5: "Cá nhân & lịch sử"}

# (endpoint, rule, methods, phần sở hữu thật, tên chức năng)
ROUTES = [
    ("auth.register", "/register", ["GET", "POST"], 1, "Đăng ký tài khoản"),
    ("auth.login", "/login", ["GET", "POST"], 1, "Đăng nhập"),
    ("auth.logout", "/logout", ["POST"], 1, "Đăng xuất"),
    ("auth.forgot", "/forgot", ["GET", "POST"], 1, "Quên mật khẩu"),
    ("auth.reset", "/reset", ["GET", "POST"], 1, "Đặt lại mật khẩu"),
    ("admin.create_event", "/admin/events", ["POST"], 2, "Tạo sự kiện"),
    ("admin.edit_event", "/admin/events/<int:eid>/edit", ["GET", "POST"], 2, "Sửa sự kiện"),
    ("admin.delete_event", "/admin/events/<int:eid>/delete", ["POST"], 2, "Xoá sự kiện"),
    ("events.index", "/", ["GET"], 3, "Trang chủ"),
    ("events.event_detail", "/events/<int:eid>", ["GET"], 3, "Chi tiết sự kiện"),
    ("events.join", "/events/<int:eid>/join", ["GET", "POST"], 4, "Đăng ký sự kiện"),
    ("admin.admin", "/admin", ["GET"], 2, "Trang quản trị"),
    ("admin.confirm_payment", "/admin/payments/<int:rid>/confirm", ["POST"], 2, "Xác nhận / duyệt"),
    ("admin.reject_payment", "/admin/payments/<int:rid>/reject", ["POST"], 2, "Từ chối"),
    ("admin.event_regs", "/admin/events/<int:eid>/registrations", ["GET"], 2, "Danh sách người tham gia"),
    ("events.leave", "/events/<int:eid>/leave", ["POST"], 5, "Huỷ đăng ký"),
    ("events.payment", "/payments/<int:rid>", ["GET"], 4, "Thanh toán QR / chờ duyệt"),
    ("events.payment_notify", "/payments/<int:rid>/notify", ["POST"], 4, "Báo đã chuyển khoản"),
    ("events.ticket", "/tickets/<int:rid>", ["GET"], 4, "Vé điện tử"),
    ("profile.profile", "/profile", ["GET", "POST"], 5, "Trang cá nhân"),
    ("profile.my", "/profile/registrations", ["GET"], 5, "Sự kiện đã đăng ký"),
    ("profile.history", "/profile/history", ["GET"], 5, "Lịch sử tham gia"),
]

SHELL = '{% extends "base.html" %}{% block t %}{{ title }}{% endblock %}{% block body %}' \
        '<div class="card" style="max-width:760px;margin:auto"><h1>{{ title }}</h1>' \
        '<p class="mut">{{ note }}</p>{{ inner }}</div>{% endblock %}'


def _page(title, note, inner=""):
    return render_template_string(SHELL, title=title, note=note, inner=Markup(inner))


# ---------------------------------------------------------------- DỮ LIỆU MẪU
def _seed():
    d = sqlite3.connect(DB_PATH)
    d.row_factory = sqlite3.Row
    try:
        if d.execute("SELECT 1 FROM settings WHERE key='standalone_seeded'").fetchone():
            return
        t = now()
        admin = d.execute("SELECT id FROM users WHERE role='admin'").fetchone()["id"]
        for un, fn in (("user1", "Nguyễn Văn A"), ("user2", "Trần Thị B")):
            if not d.execute("SELECT 1 FROM users WHERE username=?", (un,)).fetchone():
                d.execute("INSERT INTO users(username,email,fullname,password,role,created_at)"
                          " VALUES(?,?,?,?,'user',?)",
                          (un, f"{un}@example.com", fn, generate_password_hash(DEMO_PW), t))
        u1 = d.execute("SELECT id FROM users WHERE username='user1'").fetchone()["id"]
        u2 = d.execute("SELECT id FROM users WHERE username='user2'").fetchone()["id"]

        def ts(days, hm):
            day = (datetime.now(VN_TZ) + timedelta(days=days)).strftime("%Y-%m-%d")
            return f"{day}T{hm}"

        def ev(title, cat, loc, days, h1, h2, paid, fee, cap):
            return d.execute(
                "INSERT INTO events(title,description,organizer,location,category,start_at,end_at,"
                "capacity,is_paid,fee,needs_approval,created_by,created_at)"
                " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (title, "Sự kiện mẫu để thử nghiệm (do _standalone tạo).", "", loc, cat,
                 ts(days, h1), ts(days, h2), cap, paid, fee, 1 if paid else 0, admin, t)).lastrowid

        e1 = ev("Hội thảo Công nghệ AI", "Hội thảo", "TP.HCM", 3, "09:00", "11:30", 0, 0, 100)
        e2 = ev("Workshop Thiết kế UI/UX", "Workshop", "Hà Nội", 5, "13:30", "17:00", 1, 150000, 30)
        e3 = ev("Giải chạy sức khoẻ cộng đồng", "Thể thao", "Đà Nẵng", 10, "06:00", "09:00", 0, 0, 200)
        ev("Đêm nhạc sinh viên", "Văn nghệ", "TP.HCM", 15, "19:00", "22:00", 0, 0, 150)
        e5 = ev("Ngày hội tình nguyện (đã diễn ra)", "Tình nguyện", "Cần Thơ", -7, "08:00", "12:00", 0, 0, 80)

        def reg(uid, eid, status, pay, amount, code, phone="0901234567", paid=None):
            d.execute("INSERT INTO registrations(user_id,event_id,status,payment_status,amount,"
                      "ticket_code,phone,paid_at,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
                      (uid, eid, status, pay, amount, code, phone, paid, t, t))

        reg(u1, e1, "confirmed", "free", 0, "10000001")              # sắp tham gia, đã có vé
        reg(u1, e2, "pending", "unpaid", 150000, "10000002")         # chờ thanh toán QR
        reg(u1, e5, "confirmed", "free", 0, "10000003")              # đã diễn ra -> lịch sử
        reg(u1, e3, "cancelled", "cancelled", 0, "10000004")         # đã huỷ -> lịch sử
        reg(u2, e2, "pending", "pending", 150000, "10000005")        # đã báo CK -> admin duyệt
        d.execute("INSERT OR REPLACE INTO settings(key,value) VALUES('standalone_seeded','1')")
        d.commit()
    finally:
        d.close()


# ---------------------------------------------------------------- EMAIL GIẢ
def _patch_mail():
    if mailer.HOST and mailer.USER and mailer.PASS:
        return                                    # đã cấu hình SMTP -> gửi mail thật

    def fake_send_mail(to, subject, body):
        text = f"\n===== [EMAIL GIẢ — chưa cấu hình SMTP] =====\nTới: {to}\nTiêu đề: {subject}\n\n{body}\n"
        print(text, flush=True)
        with OUTBOX.open("a", encoding="utf-8") as f:
            f.write(text)
        return True

    mailer.send_mail = fake_send_mail


# ---------------------------------------------------------------- STUB VIEWS
def _make_missing(endpoint):
    def view(**kw):
        if not g.user:      # giống @login_required của app thật: chưa đăng nhập thì về trang đăng nhập
            return redirect(url_for("auth.login", next=request.path))
        abort(404)          # đã đăng nhập: phần này chưa có trong gói -> lỗi hệ thống 404
    view.__name__ = "missing_" + endpoint.replace(".", "_")
    return view


def _stub_login():
    if g.user:
        return redirect(url_for("events.index"))
    nxt = request.args.get("next", "")
    html = ('<p>Gói này không có Phần 1 (Tài khoản) nên dùng đăng nhập nhanh để thử phần của bạn.</p>'
            '<div style="display:flex;gap:10px;flex-wrap:wrap">')
    for who, text in (("user", "Vào nhanh: user1 (thành viên)"), ("admin", "Vào nhanh: admin")):
        action = url_for("dev_login", who=who, next=nxt)
        html += (f'<form method="post" action="{escape(action)}"><input type="hidden" name="csrf" '
                 f'value="{escape(session_csrf())}"><button>{text}</button></form>')
    html += "</div>"
    return _page("Đăng nhập nhanh", "Đăng nhập thật nằm ở PHẦN 1.", html)


def session_csrf():
    from app.security import csrf_token
    return csrf_token()


def _dev_login(who):
    if who == "admin":
        u = get_db().execute("SELECT * FROM users WHERE role='admin'").fetchone()
    else:
        u = get_db().execute("SELECT * FROM users WHERE username='user1'").fetchone()
    new_session_for(u)
    nxt = request.args.get("next", "")
    return redirect(nxt if nxt.startswith("/") else url_for("events.index"))


def _stub_logout():
    if g.user:
        get_db().execute("UPDATE users SET session_token=NULL WHERE id=?", (g.user["id"],))
        get_db().commit()
    session.clear()
    flash("Bạn đã đăng xuất.", "ok")
    return redirect(url_for("auth.login"))


def apply(app):
    _patch_mail()
    _seed()
    have = set(app.view_functions)
    for endpoint, rule, methods, part, label in ROUTES:
        if endpoint in have:
            continue
        if endpoint == "auth.login":
            view = _stub_login
        elif endpoint == "auth.logout":
            view = _stub_logout
        else:
            view = _make_missing(endpoint)
        app.add_url_rule(rule, endpoint, view, methods=methods)
    app.add_url_rule("/dev-login/<who>", "dev_login", _dev_login, methods=["POST"])
