# Hệ thống thi trắc nghiệm web offline

## Cập nhật hệ thống

**Cách chính — qua web, không cần SSH:** đăng nhập **Quản trị** → menu **Cập nhật**
→ bấm **"Cập nhật lên bản mới"**. Hệ thống tự kéo bản vá, build lại, cập nhật CSDL
và khởi động lại (gián đoạn vài phút). Tự từ chối nếu đang có thí sinh thi.

**Cách dự phòng — dòng lệnh trên máy chủ:**

```bash
cd ump_exam_room && ./update.sh
```

Nếu trang Cập nhật báo "Dịch vụ cập nhật chưa chạy": chạy `sudo ./install.sh` một
lần để bật (an toàn, idempotent). Nhật ký cập nhật: `logs/webupdate.log`.
