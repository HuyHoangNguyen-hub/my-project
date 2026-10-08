"""Blueprint ADMIN (chỉ role=admin xem được):
Trang "Công cụ quản trị" (/admin) TÁCH RIÊNG khỏi trang chủ — trang chủ hiển thị
giống hệt nhau cho admin và user. Trang này gồm:
  - Tạo sự kiện mới (có thể chọn: miễn phí/có phí, cần duyệt hay không)
  - Xác nhận thanh toán / duyệt đăng ký
  - Quản lý sự kiện (toàn bộ, kể cả đang/đã diễn ra) -> xem danh sách người tham gia
  - Đổi tên Ban tổ chức (hiển thị trên trang thanh toán, email, chi tiết sự kiện)

Chỉ có DUY NHẤT 1 admin trong toàn hệ thống (xem app/config.py: ADMIN_EMAIL)."""
import os
import secrets
from flask import (Blueprint, g, request, redirect, url_for, render_template, flash, abort)
from werkzeug.utils import secure_filename

from ..db import get_db, now, now_minute, JOINED_SQL
from ..config import CATEGORIES, BANNER_DIR, ALLOWED_IMG, DEFAULT_ORG_NAME
from ..security import admin_required
from ..mailer import ticket_mail, bill_mail

bp = Blueprint("admin", __name__, url_prefix="/admin")


def event_phase(e, nowmin):
    """Xác định trạng thái thời gian của sự kiện: sắp diễn ra / đang diễn ra / đã kết thúc."""
    end = e["end_at"] or e["start_at"]
    if e["start_at"] > nowmin:
        return "upcoming"
    if end >= nowmin:
        return "ongoing"
    return "ended"


@bp.get("")
@admin_required
def admin():
    """Trang Công cụ quản trị — TÁCH RIÊNG khỏi trang chủ."""
    d = get_db()
    pending_payments = d.execute(
        "SELECT r.*, e.title, e.fee, u.fullname, u.email, u.username"
        " FROM registrations r JOIN events e ON e.id=r.event_id JOIN users u ON u.id=r.user_id"
        " WHERE r.status='pending' ORDER BY r.payment_status DESC, r.updated_at").fetchall()
    nowmin = now_minute()
    rows = d.execute(f"SELECT e.*, {JOINED_SQL} AS joined FROM events e"
                     " ORDER BY e.start_at DESC").fetchall()
    all_events = []
    for r in rows:
        row = dict(r)
        row["phase"] = event_phase(r, nowmin)
        all_events.append(row)
    return render_template("admin_tools.html", pending_payments=pending_payments,
                           all_events=all_events)


# ---------------------------------------------------------------- SỰ KIỆN (CRUD)
def save_banner(file, old=None):
    """Upload banner: kiểm tra đuôi file, đổi tên ngẫu nhiên để tránh ghi đè/đường dẫn độc."""
    if not file or not file.filename:
        return old
    ext = os.path.splitext(secure_filename(file.filename))[1].lower()
    if ext not in ALLOWED_IMG:
        flash("Banner phải là ảnh png/jpg/webp/gif.", "error")
        return old
    os.makedirs(BANNER_DIR, exist_ok=True)
    name = secrets.token_hex(8) + ext
    file.save(os.path.join(BANNER_DIR, name))
    if old:
        try:
            os.remove(os.path.join(BANNER_DIR, old))
        except OSError:
            pass
    return name


def read_event_form(f):
    """Đọc form tạo/sửa sự kiện. Ngày giờ bắt đầu/kết thúc nhập riêng 2 ô
    (ngày kiểu dd/mm/yyyy theo định dạng trình duyệt + giờ) rồi ghép lại thành ISO."""
    is_paid = 1 if f.get("is_paid") == "1" else 0
    # Sự kiện có phí luôn cần duyệt (để xác nhận đã nhận tiền) -> ép needs_approval=1
    needs_approval = 1 if (is_paid or f.get("needs_approval") == "1") else 0
    try:
        fee = max(0, int(f.get("fee") or 0))
    except ValueError:
        fee = 0

    def combine(date_key, time_key, default_time):
        d = f.get(date_key, "").strip()
        t = f.get(time_key, "").strip() or default_time
        return f"{d}T{t}" if d else ""

    return dict(
        title=f.get("title", "").strip(),
        description=f.get("description", "").strip(),
        organizer=f.get("organizer", "").strip()[:120],
        location=f.get("location", "").strip(),
        category=f.get("category") if f.get("category") in CATEGORIES else "Khác",
        start_at=combine("start_date", "start_time", "00:00"),
        end_at=combine("end_date", "end_time", "23:59"),
        capacity=max(1, int(f.get("capacity") or 100)),
        is_paid=is_paid, fee=fee if is_paid else 0, needs_approval=needs_approval)


@bp.post("/events")
@admin_required
def create_event():
    d = read_event_form(request.form)
    if not d["title"] or not d["start_at"] or not d["end_at"]:
        flash("Thiếu tên sự kiện hoặc thời gian bắt đầu/kết thúc.", "error")
    elif d["end_at"] <= d["start_at"]:
        flash("Thời gian kết thúc phải sau thời gian bắt đầu.", "error")
    elif d["is_paid"] and d["fee"] <= 0:
        flash("Sự kiện có phí phải nhập mức phí lớn hơn 0.", "error")
    else:
        d["banner"] = save_banner(request.files.get("banner"))
        get_db().execute(
            "INSERT INTO events(title,description,organizer,location,category,start_at,end_at,"
            "capacity,is_paid,fee,needs_approval,banner,created_by,created_at)"
            " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (d["title"], d["description"], d["organizer"], d["location"], d["category"],
             d["start_at"], d["end_at"], d["capacity"], d["is_paid"], d["fee"],
             d["needs_approval"], d["banner"], g.user["id"], now()))
        get_db().commit()
        flash("Đã tạo sự kiện.", "ok")
    return redirect(url_for("admin.admin"))


@bp.route("/events/<int:eid>/edit", methods=["GET", "POST"])
@admin_required
def edit_event(eid):
    e = get_db().execute(f"SELECT e.*, {JOINED_SQL} AS joined FROM events e WHERE e.id=?",
                         (eid,)).fetchone()
    if not e:
        abort(404)
    if request.method == "POST":
        d = read_event_form(request.form)
        if not d["title"] or not d["start_at"] or not d["end_at"]:
            flash("Thiếu tên sự kiện hoặc thời gian bắt đầu/kết thúc.", "error")
        elif d["end_at"] <= d["start_at"]:
            flash("Thời gian kết thúc phải sau thời gian bắt đầu.", "error")
        elif d["is_paid"] and d["fee"] <= 0:
            flash("Sự kiện có phí phải nhập mức phí lớn hơn 0.", "error")
        elif d["capacity"] < e["joined"]:
            flash(f"Sức chứa không được nhỏ hơn số người đã đăng ký ({e['joined']}).", "error")
        else:
            banner = save_banner(request.files.get("banner"), e["banner"])
            if request.form.get("remove_banner") == "1" and banner == e["banner"]:
                banner = None
            get_db().execute(
                "UPDATE events SET title=?,description=?,organizer=?,location=?,category=?,"
                "start_at=?,end_at=?,capacity=?,is_paid=?,fee=?,needs_approval=?,banner=?"
                " WHERE id=?",
                (d["title"], d["description"], d["organizer"], d["location"], d["category"],
                 d["start_at"], d["end_at"], d["capacity"], d["is_paid"], d["fee"],
                 d["needs_approval"], banner, eid))
            get_db().commit()
            flash("Đã cập nhật sự kiện.", "ok")
            return redirect(url_for("admin.admin"))
    return render_template("event_form.html", e=e)


@bp.post("/events/<int:eid>/delete")
@admin_required
def delete_event(eid):
    """Admin có quyền xoá bất kỳ sự kiện hiện có nào (kèm toàn bộ đăng ký liên quan)."""
    e = get_db().execute("SELECT * FROM events WHERE id=?", (eid,)).fetchone()
    if not e:
        abort(404)
    if e["banner"]:
        try:
            os.remove(os.path.join(BANNER_DIR, e["banner"]))
        except OSError:
            pass
    get_db().execute("DELETE FROM registrations WHERE event_id=?", (eid,))
    get_db().execute("DELETE FROM events WHERE id=?", (eid,))
    get_db().commit()
    flash("Đã xoá sự kiện và toàn bộ đăng ký liên quan.", "ok")
    return redirect(url_for("admin.admin"))


# ---------------------------------------------------------- ĐỐI SOÁT THANH TOÁN / DUYỆT
@bp.post("/payments/<int:rid>/confirm")
@admin_required
def confirm_payment(rid):
    """Chỉ khi admin xác nhận (đã nhận tiền HOẶC duyệt đăng ký) mới gửi mail vé.
    Chỉ gửi thêm hoá đơn nếu sự kiện thực sự có phí (amount > 0)."""
    r = get_db().execute("SELECT * FROM registrations WHERE id=?", (rid,)).fetchone()
    if not r:
        abort(404)
    if r["status"] == "confirmed":
        flash("Phiếu này đã được xác nhận trước đó.", "error")
        return redirect(url_for("admin.admin"))
    e = get_db().execute("SELECT * FROM events WHERE id=?", (r["event_id"],)).fetchone()
    u = get_db().execute("SELECT * FROM users WHERE id=?", (r["user_id"],)).fetchone()
    get_db().execute("UPDATE registrations SET status='confirmed', payment_status='paid',"
                     " paid_at=?, updated_at=? WHERE id=?", (now(), now(), rid))
    get_db().commit()
    r = get_db().execute("SELECT * FROM registrations WHERE id=?", (rid,)).fetchone()
    org_name = e["organizer"] or DEFAULT_ORG_NAME
    # Tiền/đăng ký đã ghi nhận vào DB rồi (status='confirmed') dù email có gửi được
    # hay không, nên không rollback — chỉ báo rõ cho admin biết nếu gửi mail bị lỗi.
    try:
        ticket_mail(u, e, r, org_name)                 # Mail: xác nhận đăng ký + vé
        if r["amount"] > 0:
            bill_mail(u, e, r, org_name)                # Mail: hoá đơn (chỉ khi có phí)
        flash("Đã xác nhận. Đã gửi email vé" +
              (" và hoá đơn" if r["amount"] > 0 else "") + " tới " + u["email"], "ok")
    except RuntimeError as ex:
        flash("Đã xác nhận, NHƯNG GỬI EMAIL THẤT BẠI: " + str(ex), "error")
    return redirect(url_for("admin.admin"))


@bp.post("/payments/<int:rid>/reject")
@admin_required
def reject_payment(rid):
    get_db().execute("UPDATE registrations SET status='cancelled', payment_status='rejected',"
                     " updated_at=? WHERE id=?", (now(), rid))
    get_db().commit()
    flash("Đã từ chối phiếu đăng ký.", "ok")
    return redirect(url_for("admin.admin"))


# ---------------------------------------------------------------- DANH SÁCH NGƯỜI THAM GIA
@bp.get("/events/<int:eid>/registrations")
@admin_required
def event_regs(eid):
    e = get_db().execute("SELECT * FROM events WHERE id=?", (eid,)).fetchone() or abort(404)
    rows = get_db().execute(
        "SELECT u.fullname,u.username,u.email,r.* FROM registrations r"
        " JOIN users u ON u.id=r.user_id WHERE r.event_id=? ORDER BY r.status, r.created_at",
        (eid,)).fetchall()
    return render_template("event_regs.html", e=e, rows=rows)


