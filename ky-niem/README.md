# Kỷ niệm của tôi

Website lưu giữ ảnh và kỷ niệm cá nhân, viết bằng Python (Flask + SQLite + Pillow).

## Chạy
```bash
pip install -r requirements.txt
python app.py
```
Mở http://localhost:5000

## Đặt mật khẩu (nên làm nếu mở cho điện thoại/mạng khác)
- Windows (PowerShell): `$env:MEMORY_PASSWORD="matkhau"; python app.py`
- macOS / Linux: `MEMORY_PASSWORD=matkhau python app.py`

## Dữ liệu nằm ở đâu
Thư mục `data/`: `uploads/` (ảnh gốc), `thumbs/` (ảnh thu nhỏ), `memories.db` (thông tin kỷ niệm).
Chỉ cần sao chép thư mục `data/` là sao lưu toàn bộ.

## Xem trên điện thoại
Cùng Wi-Fi, mở `http://<IP máy tính>:5000` trên điện thoại.
