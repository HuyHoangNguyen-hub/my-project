"""Gửi email xác nhận vé, hoá đơn, và mã quên mật khẩu qua SMTP thật.

Cấu hình bằng file .env ở thư mục gốc dự án (xem .env.example) — được nạp tự
động qua python-dotenv (app/config.py gọi load_dotenv()), nên chỉ cần điền một
lần vào .env, không phải "export" biến môi trường mỗi lần mở terminal nữa.

Bắt buộc phải có: SMTP_HOST, SMTP_USER, SMTP_PASS
Tuỳ chọn: SMTP_PORT (mặc định 587), MAIL_FROM (mặc định = SMTP_USER)

Nếu chưa cấu hình hoặc gửi thất bại, hàm sẽ raise RuntimeError với thông báo
rõ ràng — không có chế độ thử/outbox nào cả, email luôn là email thật.
"""
import os
import smtplib
import ssl
from datetime import datetime
from email.message import EmailMessage

HOST = os.environ.get("SMTP_HOST")
PORT = int(os.environ.get("SMTP_PORT", 587))
USER = os.environ.get("SMTP_USER", "")
PASS = os.environ.get("SMTP_PASS", "")
SENDER = os.environ.get("MAIL_FROM", USER or "")


def _vn(value, with_time=True):
    """Định dạng ISO 'YYYY-MM-DDTHH:MM' -> 'DD/MM/YYYY HH:MM' để đưa vào nội dung mail."""
    if not value:
        return "—"
    try:
        dt = datetime.fromisoformat(str(value))
    except ValueError:
        return str(value)
    return dt.strftime("%d/%m/%Y %H:%M" if with_time else "%d/%m/%Y")


def send_mail(to, subject, body):
    """Gửi email thật qua SMTP. Raise RuntimeError nếu chưa cấu hình hoặc gửi lỗi."""
    if not HOST or not USER or not PASS:
        raise RuntimeError(
            "Chưa cấu hình SMTP. Hãy sao chép .env.example thành .env rồi điền "
            "SMTP_HOST, SMTP_USER, SMTP_PASS (xem hướng dẫn trong README.md).")

    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"] = SENDER, to, subject
    msg.set_content(body)
    try:
        with smtplib.SMTP(HOST, PORT, timeout=15) as s:
            s.starttls(context=ssl.create_default_context())
            s.login(USER, PASS)
            s.send_message(msg)
    except Exception as e:
        raise RuntimeError(f"Gửi email tới {to} thất bại: {e}") from e
    return True


def ticket_mail(user, event, reg, org_name="Ban Tổ Chức Sự Kiện"):
    """Mail: xác nhận đăng ký thành công + vé (dùng cho cả sự kiện có vé/không vé)."""
    body = f"""Xin chào {user['fullname']},

Bạn đã ĐĂNG KÝ THÀNH CÔNG sự kiện dưới đây.

  Sự kiện    : {event['title']}
  Loại       : {event['category']}
  Bắt đầu    : {_vn(event['start_at'])}
  Kết thúc   : {_vn(event['end_at'])}
  Địa điểm   : {event['location'] or 'Đang cập nhật'}
  Người tham dự: {user['fullname']} ({user['email']})

  Mã vé      : {reg['ticket_code']}

Vui lòng xuất trình mã vé này tại cổng check-in.
Trân trọng,
{org_name}."""
    return send_mail(user["email"], f"Đăng ký thành công: {event['title']}", body)


def bill_mail(user, event, reg, org_name="Ban Tổ Chức Sự Kiện"):
    """Mail: hoá đơn thanh toán (chỉ gửi khi sự kiện có phí, amount > 0)."""
    fee = f"{event['fee']:,.0f} VNĐ".replace(",", ".")
    body = f"""Xin chào {user['fullname']},

{org_name} đã NHẬN ĐƯỢC THANH TOÁN của bạn. Dưới đây là hoá đơn.

============== HOÁ ĐƠN =================
  Số hoá đơn : HD-{reg['id']:06d}
  Ngày thanh toán: {_vn(reg['paid_at'])}
  Khách hàng : {user['fullname']} ({user['email']})
  Nội dung   : Phí tham dự "{event['title']}"
  Mã vé      : {reg['ticket_code']}
  ----------------------------------------
  Số tiền    : {fee}
  Hình thức  : Chuyển khoản qua mã QR
  Trạng thái : ĐÃ THANH TOÁN
========================================

Cảm ơn bạn đã tham gia.
{org_name}."""
    return send_mail(user["email"], f"[Hoá đơn] HD-{reg['id']:06d} - {event['title']}", body)


def reset_code_mail(user, code, org_name="Ban Tổ Chức Sự Kiện"):
    """Mail: mã xác nhận 4 số để đặt lại mật khẩu (quên mật khẩu)."""
    body = f"""Xin chào {user['fullname']},

Có yêu cầu đặt lại mật khẩu cho tài khoản {user['username']} ({user['email']}).

============== MÃ XÁC NHẬN ==============
              {code}
==========================================

Mã có hiệu lực trong 10 phút. Nhập đúng mã này trên trang đặt lại mật khẩu để
tạo mật khẩu mới. Nếu không phải bạn yêu cầu, hãy bỏ qua email này.

Trân trọng,
{org_name}."""
    return send_mail(user["email"], "Mã xác nhận đặt lại mật khẩu", body)
