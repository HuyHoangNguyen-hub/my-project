"""Tiện ích ráp các module route của từng PHẦN vào chung 1 blueprint.

Bản gốc có 2 file lớn (events.py, admin.py). Khi chia 5 phần, mỗi file được tách
thành các module nhỏ theo phần (events_home / events_join / events_personal,
admin_events / admin_approval). File events.py và admin.py chỉ còn giữ `bp` và
nạp những module nào CÓ MẶT trong gói — nên 5 gói chạy độc lập, ghép lại là đủ."""
from importlib import import_module


def load_parts(package, names):
    for n in names:
        full = f"{package}.{n}"
        try:
            import_module(full)
        except ModuleNotFoundError as ex:
            if ex.name != full:      # chỉ bỏ qua đúng module chưa có, lỗi import khác vẫn báo
                raise
