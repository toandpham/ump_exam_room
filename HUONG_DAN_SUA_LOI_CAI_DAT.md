# Sửa lỗi cài đặt: backend "unhealthy", Caddy không chạy

Áp dụng cho lỗi khi cài mới:

```
Container exam-backend-1   Error  dependency backend failed to start
dependency failed to start: container exam-backend-1 is unhealthy
curl: (7) Failed to connect to localhost port 80
```
Log Postgres kèm dòng: `relation "exam_sessions" does not exist` /
`relation "system_license" does not exist`.

**Nguyên nhân**: cơ sở dữ liệu mới chưa có bảng; backend cần bảng để khởi động,
mà lệnh tạo bảng lại nằm sau bước chờ backend khởi động → vòng luẩn quẩn, cài
không xong. Đã sửa: backend tự tạo bảng khi khởi động.

---

## Máy CHƯA CÀI BAO GIỜ — cài mới từ đầu

```bash
sudo apt-get update && sudo apt-get install -y git && cd ~ && git clone https://github.com/toandpham/ump_exam_room.git && cd ump_exam_room && sudo ./install.sh
```

Xong là dùng được ngay: `http://<IP-máy-chủ>/admin` — `admin` / `admin123`.

## Máy CÀI DỞ DANG, chưa chạy được lần nào — làm lại từ đầu

Dán nguyên dòng này (thay `/srv/exam` bằng thư mục đã `git clone`):

```bash
cd /srv/exam && docker compose down -v; rm -f .env; git stash; git pull && sudo ./install.sh
```

Chạy mất 5–10 phút. Xong là hệ thống chạy được ngay, có sẵn tài khoản.

> ⚠️ **Chỉ dùng cho máy CHƯA cài xong lần nào.** Lệnh này xoá sạch cơ sở dữ liệu để
> làm lại từ đầu — máy đã tổ chức thi và có kết quả thí sinh thì **không được dùng**,
> máy đó chỉ chạy: `cd /srv/exam && git pull && sudo ./install.sh`

> Vì sao xoá `.env` cùng lúc với cơ sở dữ liệu: `.env` giữ mật khẩu CSDL, còn CSDL nhớ
> mật khẩu từ lần tạo đầu tiên. Xoá một trong hai rồi cài lại sẽ sinh mật khẩu lệch
> nhau → backend báo `password authentication failed`, triệu chứng nhìn y hệt lỗi cũ.

---

## Kiểm tra đã chạy được

```bash
docker compose ps
curl -fsS http://localhost/api/health && echo "  -- OK"
```

Đúng thì thấy **backend, postgres, redis, frontend-admin, frontend-exam ở trạng
thái healthy** và `caddy` đang chạy; lệnh `curl` in ra `{"status":"ok"...}  -- OK`.

Xem backend đã tự tạo bảng chưa:

```bash
docker compose logs backend | grep -i alembic | head
```
Thấy dòng `Running upgrade ... initial schema` là đã tạo bảng xong.

---

## Sau khi hệ thống lên — tạo tài khoản (nếu chưa có)

Chạy lại script cài, an toàn tuyệt đối (không ghi đè `.env`, tài khoản đã có thì bỏ qua):

```bash
cd /srv/exam
sudo ./install.sh
```

Script sẽ in ra địa chỉ truy cập + tài khoản mặc định:

| Vai trò | Đường dẫn | Tài khoản | Mật khẩu |
|---|---|---|---|
| Quản trị | `http://<IP-server>/admin` | `admin` | `admin123` |
| Chủ tịch hội đồng thi | `http://<IP-server>/chutich` | `proctor1` | `proctor123` |
| Giám thị | `http://<IP-server>/giamthi` | `giamthi1`…`giamthi10` | chủ tịch cấp mã PIN |
| Thí sinh | `http://<IP-server>/thisinh` | (đăng nhập bằng CCCD) | — |

> **Đổi mật khẩu mặc định trước khi thi thật** (nút "Đổi mật khẩu" ở góc trên bên phải).

Giấy phép: cài xong **tự dùng thử 90 ngày**, không cần nhập gì.

---

## Nếu vẫn lỗi

```bash
cd /srv/exam
docker compose down
docker compose up -d --build
docker compose logs backend --tail 50
```

Gửi lại 50 dòng log đó để bên phát triển xem tiếp.

**Trường hợp muốn cài lại từ đầu, XOÁ SẠCH dữ liệu** (chỉ dùng khi chưa có dữ
liệu thi thật — thao tác này xoá toàn bộ kỳ thi, thí sinh, kết quả):

```bash
cd /srv/exam
docker compose down -v
sudo ./install.sh
```

---

## Lỗi "port is already allocated" (cổng 80 bị chiếm)

Máy chủ đã có sẵn web server (Apache/nginx/webhost) giữ cổng 80 → Caddy không
khởi động được. Xem ai đang giữ cổng rồi dừng dịch vụ đó:

```bash
sudo ss -ltnp | grep -E ':80|:443'
sudo systemctl stop apache2 && sudo systemctl disable apache2   # hoặc nginx
cd /srv/exam && sudo ./install.sh
```

Bản `install.sh` mới kiểm tra sẵn điều này và báo tên tiến trình đang chiếm cổng
trước khi build.

## Lưu ý về lớp webhost đặt trước server

Nếu trường đặt thêm một lớp webhost/proxy phía trước, cần bật chuyển tiếp
**WebSocket** cho đường dẫn `/ws/*`. Không có nó hệ thống vẫn chạy, nhưng màn
hình thí sinh sẽ nhận lệnh "Bắt đầu thi" chậm hơn (5–15 giây thay vì tức thì).
