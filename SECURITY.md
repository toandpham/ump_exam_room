# Chính sách bảo mật / Security Policy

## Báo cáo lỗ hổng / Reporting a vulnerability

Nếu bạn phát hiện lỗ hổng bảo mật, vui lòng **KHÔNG mở issue công khai**.
Gửi email riêng tới: **toanphamduong@icloud.com** với mô tả + cách tái hiện.
Chúng tôi sẽ phản hồi sớm nhất có thể.

If you find a security vulnerability, please **do not open a public issue**.
Email the maintainer at **toanphamduong@icloud.com** instead.

## Lưu ý khi triển khai thực tế / Hardening checklist

Đây là phần mềm thi cử — trước khi dùng thật, BẮT BUỘC:

- Đặt `ENVIRONMENT=production` và `JWT_SECRET` ngẫu nhiên mạnh trong `.env`
  (`openssl rand -hex 32`). Không bao giờ commit `.env`.
- **Đổi mọi mật khẩu mặc định** (`admin/admin123`, tài khoản giám thị mẫu) —
  chúng chỉ dùng cho môi trường dev.
- Đổi `POSTGRES_PASSWORD` mặc định.
- Bật HTTPS (Caddy `tls internal` đã cấu hình) + chạy hoàn toàn trong mạng LAN
  nội bộ, không expose ra Internet.
- Sao lưu định kỳ cơ sở dữ liệu.
