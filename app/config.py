"""Cấu hình & hằng số dùng chung. File này được import ĐẦU TIÊN (app/__init__.py)
để nạp .env bằng python-dotenv trước khi mailer.py đọc biến môi trường SMTP_*."""
import os
import secrets
from datetime import timedelta, timezone
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

# ---------------------------------------------------------------- DỮ LIỆU
DB_PATH = os.environ.get("DATABASE") or str(BASE_DIR / "data.db")
BANNER_DIR = str(BASE_DIR / "static" / "banners")
ALLOWED_IMG = {".png", ".jpg", ".jpeg", ".webp", ".gif"}

# Giờ sự kiện nhập/hiển thị theo giờ Việt Nam (UTC+7), không phụ thuộc múi giờ máy chủ
VN_TZ = timezone(timedelta(hours=7))

CATEGORIES = ["Hội thảo", "Workshop", "Thể thao", "Văn nghệ", "Tình nguyện", "Đào tạo", "Khác"]
DEFAULT_ORG_NAME = "Ban Tổ Chức Sự Kiện"

# ---------------------------------------------------------------- TÀI KHOẢN ADMIN DUY NHẤT
ADMIN_EMAIL = "hahuysv123@gmail.com"
ADMIN_USERNAME = "admin"
ADMIN_FULLNAME = "Quản trị viên"
ADMIN_DEFAULT_PASSWORD = "Admin@123"      # đổi ngay sau lần đăng nhập đầu tiên

# ---------------------------------------------------------------- ĐĂNG NHẬP / QUÊN MẬT KHẨU
MAX_FAILED = 5              # sai quá 5 lần -> khoá tạm thời
LOCK_MINUTES = 15
RESET_CODE_MINUTES = 10     # mã 4 số hết hạn sau 10 phút (khớp nội dung email)

# ---------------------------------------------------------------- THANH TOÁN QR
PAYMENT_QR = "payment-qr.png"            # nằm trong thư mục static/
BANK_INFO = {"bank": os.environ.get("BANK_NAME", "Xem trong mã QR (app ngân hàng sẽ tự nhận diện)")}


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY") or secrets.token_hex(32)
    PERMANENT_SESSION_LIFETIME = timedelta(minutes=30)      # hết hạn sau 30' không hoạt động
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = bool(os.environ.get("HTTPS"))
    MAX_CONTENT_LENGTH = 5 * 1024 * 1024                     # giới hạn upload banner 5MB
