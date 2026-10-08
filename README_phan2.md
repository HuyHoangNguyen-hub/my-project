# Phần 2 — Sự kiện & Trang quản trị (admin)

Toàn bộ khu vực admin `/admin`: tạo/sửa/xoá sự kiện, upload banner, bảng quản lý sự kiện, **duyệt / từ chối đăng ký, xác nhận thanh toán (gửi mail vé + hoá đơn), danh sách người tham gia**.

## Chạy riêng phần này
```bash
pip install -r requirements.txt
python run.py            # http://127.0.0.1:5000
```
Lần đầu chạy sẽ tự tạo `data.db` + dữ liệu mẫu. **Không cần cấu hình SMTP**: email (mã quên mật khẩu, vé, hoá đơn)
được in ra terminal và ghi vào `_standalone/outbox.txt`. Muốn gửi mail thật thì `cp .env.example .env` rồi điền SMTP.

**Tài khoản thử:** `admin` / `Admin@123` · `user1` và `user2` / `User@123`

Đăng nhập bằng nút "Vào nhanh: admin" (trang chủ `/` báo 404 vì thuộc Phần 3), rồi gõ `/admin`: có sẵn 2 phiếu chờ duyệt (xác nhận → mail vé/hoá đơn hiện ở terminal).

## Quy tắc ghép (quan trọng)
- **Chỉ sửa file thuộc phần của mình** (danh sách bên dưới). Không đổi tên hàm, route, endpoint, tên bảng/cột.
- **Lõi dùng chung** (`app/config.py, db.py, security.py, mailer.py, app/__init__.py, app/blueprints/__init__.py, run.py,
  templates/base.html, error.html, _macros.html`) giống hệt nhau ở cả 5 gói, chủ sở hữu là người Phần 1.
  Cần sửa lõi → báo cả nhóm; `ghep.py` sẽ báo lỗi nếu lõi lệch nhau.
- `_standalone/` là lớp hỗ trợ chạy riêng (dữ liệu mẫu, đăng nhập nhanh, email in ra terminal) — **không** nộp, không sửa; `ghep.py` bỏ qua nó.

## File THUỘC phần này
- app/blueprints/admin.py (nguyên bản, không cắt)
- templates/admin_tools.html, event_form.html, _eventfields.html, event_regs.html

## Chức năng của phần khác
Route thuộc phần khác chưa có trong gói nên bấm vào (khi đã đăng nhập) sẽ ra **trang lỗi hệ thống (lỗi 404)** — bình thường, không phải bug. Khi ghép đủ 5 phần thì các trang đó hoạt động.
