# Hệ thống thi trắc nghiệm web offline

## Cài đặt máy chủ (Ubuntu/Debian)

```bash
git clone https://github.com/toandpham/ump_exam_room.git
cd ump_exam_room
sudo ./install.sh
```

Script tự cài Docker, sinh mật khẩu ngẫu nhiên, chỉnh tham số theo RAM/số nhân của
máy, dựng toàn bộ hệ thống rồi in ra địa chỉ + tài khoản. Chạy lại lúc nào cũng
được (không ghi đè `.env`, không mất dữ liệu). Yêu cầu: **cổng 80/443 phải trống**
(dừng Apache/nginx nếu có) và còn tối thiểu **8 GB đĩa**.

Cài xong hệ thống **tự dùng thử 90 ngày**; gia hạn bằng key ở trang Giấy phép.

| Vai trò | Đường dẫn | Tài khoản mặc định |
|---|---|---|
| Quản trị | `http://<IP-máy-chủ>/admin` | `admin` / `admin123` |
| Chủ tịch hội đồng thi | `http://<IP-máy-chủ>/chutich` | `proctor1` / `proctor123` |
| Giám thị | `http://<IP-máy-chủ>/giamthi` | `giamthi1`…`giamthi10` (chủ tịch cấp PIN) |
| Thí sinh | `http://<IP-máy-chủ>/thisinh` | đăng nhập bằng CCCD/hộ chiếu |

**Đổi mật khẩu mặc định trước khi tổ chức thi thật.**

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

## Tra cứu khi có tranh cãi về bài thi

Thí sinh nói đã nộp nhưng bảng giám sát báo khác? Xem sự thật trong CSDL:

```bash
docker compose exec backend python -m app.check_candidate <CCCD hoặc hộ chiếu>
```

In ra mọi phiên của thí sinh: thuộc buổi nào, trạng thái, giờ bắt đầu / hết giờ /
nộp bài, số câu đã trả lời, điểm.

## Chỉ cho thi bằng phần mềm kiosk

Mặc định máy chủ **từ chối mọi trình duyệt thường** ở phần thi: mở `/thisinh/` bằng
Firefox/Chrome/Edge sẽ hiện màn "Phải thi bằng phần mềm thi". Trang quản trị (chủ
tịch/giám thị/quản trị) **không bị ảnh hưởng** — vẫn dùng trình duyệt bình thường.

Cần cho thi tạm bằng trình duyệt (máy chưa cài kịp kiosk, sự cố...):

```bash
# trong .env trên máy chủ
KIOSK_ONLY=false
docker compose up -d backend
```

Bật lại: đổi về `true` rồi chạy lại lệnh trên.
