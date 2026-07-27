# Hệ thống thi trắc nghiệm web offline

Hệ thống tổ chức thi trắc nghiệm chạy **trong mạng nội bộ, không cần Internet**. Một
máy chủ Linux phục vụ tới **500 máy thi đồng thời**; thí sinh làm bài bằng phần mềm
thi riêng (khoá máy), giám thị theo dõi theo phòng, chủ tịch hội đồng điều phối toàn
bộ kỳ thi và xuất báo cáo.

**Mục lục**

1. [Yêu cầu](#1-yêu-cầu)
2. [Cài đặt máy chủ](#2-cài-đặt-máy-chủ)
3. [Cài phần mềm thi lên máy thí sinh](#3-cài-phần-mềm-thi-lên-máy-thí-sinh)
4. [Tổ chức một kỳ thi](#4-tổ-chức-một-kỳ-thi)
5. [Sao lưu và khôi phục](#5-sao-lưu-và-khôi-phục)
6. [Cập nhật hệ thống](#6-cập-nhật-hệ-thống)
7. [Xử lý sự cố](#7-xử-lý-sự-cố)
8. [Lệnh quản trị](#8-lệnh-quản-trị)
9. [Bảo mật và giấy phép](#9-bảo-mật-và-giấy-phép)

---

## 1. Yêu cầu

**Máy chủ**

| Hạng mục | Tối thiểu | Khuyến nghị (400–500 máy thi) |
|---|---|---|
| Hệ điều hành | Ubuntu / Debian (64-bit) | Ubuntu Server 22.04 trở lên |
| RAM | 8 GB | 16 GB trở lên |
| CPU | 4 nhân | 8 nhân trở lên |
| Ổ đĩa trống | 8 GB | 50 GB trở lên |
| Mạng | LAN nối tới mọi máy thi | Gigabit, cùng dải mạng |

Cổng **80 và 443 phải trống** — nếu máy đã chạy Apache/nginx thì dừng lại trước khi
cài. Máy chủ **cần Internet lúc cài đặt và lúc cập nhật**; lúc thi thì không cần.

Nên đặt **IP tĩnh** cho máy chủ để phần mềm thi và người dùng luôn tìm được.

**Máy thí sinh:** Windows 7 trở lên. Phần mềm thi tự chạy được trên cả máy cũ 32-bit.

---

## 2. Cài đặt máy chủ

```bash
sudo apt-get update && sudo apt-get install -y git
cd ~ && git clone https://github.com/toandpham/ump_exam_room.git
cd ump_exam_room && sudo ./install.sh
```

Mất khoảng 5–10 phút. Script tự cài Docker, sinh mật khẩu ngẫu nhiên, chỉnh tham số
theo RAM và số nhân của máy, bật sao lưu tự động, rồi in ra địa chỉ truy cập kèm tài
khoản. **Chạy lại lúc nào cũng được** — không ghi đè cấu hình, không mất dữ liệu.

Cài xong hệ thống **tự dùng thử 90 ngày**, không cần nhập gì thêm.

### Địa chỉ truy cập và tài khoản mặc định

| Vai trò | Đường dẫn | Tài khoản |
|---|---|---|
| Quản trị hệ thống | `http://<IP-máy-chủ>/admin` | `admin` / `admin123` |
| Chủ tịch hội đồng thi | `http://<IP-máy-chủ>/chutich` | `proctor1` / `proctor123` |
| Giám thị | `http://<IP-máy-chủ>/giamthi` | `giamthi1`…`giamthi10`, chủ tịch cấp mã PIN |
| Thí sinh | `http://<IP-máy-chủ>/thisinh` | đăng nhập bằng CCCD hoặc số hộ chiếu |

> ⚠️ **Đổi mật khẩu mặc định trước khi tổ chức thi thật.** Nút "Đổi mật khẩu" nằm ở
> góc trên bên phải sau khi đăng nhập.

### Ba vai trò làm gì

- **Quản trị** — quản lý tài khoản, xem nhật ký hệ thống, giấy phép, cập nhật phần
  mềm. Không can thiệp vào kỳ thi.
- **Chủ tịch hội đồng thi** — tạo kỳ thi, nhập danh sách thí sinh, phân phòng và giám
  thị, nạp đề, điều khiển buổi thi, xuất báo cáo.
- **Giám thị** — chỉ thấy phòng mình phụ trách: ai đã đăng nhập, ai đang làm bài, tạm
  dừng / cho tiếp tục từng thí sinh, thêm thí sinh đến muộn.

---

## 3. Cài phần mềm thi lên máy thí sinh

Máy thí sinh **không dùng trình duyệt thường** — mở `/thisinh/` bằng Chrome hay
Firefox sẽ bị từ chối. Phải cài phần mềm thi (khoá máy, chặn thoát ra ngoài).

**Tải bộ cài** — trên máy thí sinh, mở trình duyệt vào:

```
http://<IP-máy-chủ>/kiosk/UMP_ExamKiosk-Setup.exe
```

Cài xong sẽ có biểu tượng **UMP ExamKiosk** trên màn hình. Mở lên là phần mềm **tự
tìm máy chủ** trong mạng và hiện màn đăng nhập.

**Nếu máy không tự tìm được máy chủ** (mạng chặn phát hiện tự động), tạo file
`kiosk.config.json` trong thư mục cài đặt (`C:\Program Files (x86)\UMP_ExamKiosk\`):

```json
{ "serverIp": "192.168.1.10", "emergencyPassword": "matkhaumoi" }
```

**Thoát phần mềm thi:**

- Cách thường: chủ tịch bấm **"Thoát máy thi"** trên trang giám sát — mọi máy tự
  đóng sau khoảng 5 giây.
- Cách khẩn cấp (máy chủ hỏng): bấm **Ctrl + Alt + Shift + Q** rồi nhập mật khẩu.
  Mặc định là `ump@2026` — **nên đổi** bằng `emergencyPassword` ở trên.

**Tự cập nhật:** mỗi lần khởi động, phần mềm tự kiểm tra bản mới trên máy chủ và tự
cập nhật. Sau khi cập nhật máy chủ, chỉ cần khởi động lại phần mềm trên máy thi.

**Nếu phần mềm diệt virus chặn:** phần mềm thi khoá bàn phím và chạy quyền quản trị
nên dễ bị nghi nhầm. Khai báo ngoại lệ (PowerShell quyền Administrator):

```powershell
Add-MpPreference -ExclusionPath "C:\Program Files (x86)\UMP_ExamKiosk"
Add-MpPreference -ExclusionProcess "UMP_ExamKiosk.exe"
Add-MpPreference -ExclusionProcess "keyblocker.exe"
```

Dùng Kaspersky/BKAV/Symantec thì khai 2 đường dẫn và 2 tiến trình đó trong console
quản trị rồi đẩy chính sách xuống toàn bộ máy — không nên đi gõ từng máy.

---

## 4. Tổ chức một kỳ thi

Đăng nhập bằng tài khoản **chủ tịch hội đồng thi** (`/chutich`).

**Bước 1 — Tạo kỳ thi.** Khai tên kỳ thi, thời lượng mặc định, **số phòng**, và danh
sách **buổi thi**. Một kỳ thi gồm nhiều buổi; mỗi buổi có đề riêng và chạy lần lượt.

**Bước 2 — Nhập danh sách thí sinh.** Tab **Thí sinh** → tải file Excel mẫu → điền →
nhập lên. Trong file có cột **"Phòng"**: điền tên phòng thì hệ thống **tự chia thí
sinh vào phòng**, phòng chưa có sẽ được tạo tự động.

Định danh dùng **CCCD (12 số) hoặc số hộ chiếu**; hệ thống tự nhận loại.

Ảnh thí sinh (không bắt buộc): nén các file **JPG hoặc PNG** đặt tên theo CCCD/hộ
chiếu (`079203001234.jpg`) thành một file ZIP rồi tải lên.

**Bước 3 — Gán giám thị.** Tab **Phòng & giám thị**: mỗi phòng chọn một tài khoản
giám thị, ghi tên người coi thi thật, bấm **"Đặt lại mật khẩu (6 số)"** để lấy mã PIN
đọc cho giám thị.

**Bước 4 — Nạp đề.** Vào buổi thi → tab **Đề thi** → chọn file đề `.qenc` do người ra
đề gửi + nhập **mật khẩu mở đề** (người ra đề đọc cho hội đồng lúc nạp). Đề được mã
hoá cả lúc lưu trữ; mỗi file chỉ dùng được trong thời hạn ghi sẵn trong file.

**Bước 5 — Ngày thi.** Vào buổi thi → tab **Giám sát**:

1. Thí sinh mở phần mềm thi, đăng nhập, xác nhận thông tin → trạng thái **Sẵn sàng**.
2. Chờ tới khi bảng báo **đã tải đề đủ** cho mọi máy — nút **"Bắt đầu thi"** mới bật
   (tránh máy yếu vừa tải đề vừa làm bài). Có máy hỏng không tải được thì dùng đường
   "Vẫn bắt đầu" bên cạnh.
3. Bấm **Bắt đầu thi** — mọi máy đếm ngược 30 giây rồi vào đề cùng lúc.
4. Trong giờ: **Tạm dừng / Tiếp tục** từng thí sinh hoặc cả buổi; **Cộng giờ** nếu
   có sự cố; **Duyệt vào thi** cho thí sinh đến muộn.
5. Hết giờ, máy nào chưa nộp hệ thống **tự nộp và chấm**.

**Bước 6 — Đóng buổi và lấy báo cáo.** Bấm **Đóng buổi** (chấm nốt bài còn lại và
**xoá đề khỏi máy chủ**), rồi vào tab **Báo cáo** tải file Excel. File gồm 2 sheet:
**Kết quả** (điểm, số câu đúng) và **Đáp án** (từng câu thí sinh chọn, kèm dòng đáp án
đúng). Khi tải, hệ thống hỏi mật khẩu để nén file thành ZIP mã hoá.

Thi xong hết các buổi thì bấm **Đóng kỳ thi** để lưu trữ.

---

## 5. Sao lưu và khôi phục

### Sao lưu tự động

Bật sẵn ngay khi cài. Máy chủ tự sao lưu **mỗi 10 phút** vào thư mục `backups/`, mỗi
bản gồm cơ sở dữ liệu, file cấu hình `.env` và toàn bộ ảnh trong `uploads/`.

Hệ thống giữ **48 bản gần nhất** (khoảng 8 giờ), tự giới hạn **10 GB**, và **tự
ngừng nếu ổ đĩa còn dưới 2 GB** để không bao giờ làm đầy đĩa máy chủ.

```bash
systemctl status exam-backup.timer     # kiểm tra sao lưu có đang chạy
./scripts/backup.sh                    # sao lưu ngay lập tức
```

Sao lưu **ra ổ USB ngoài** (nên làm trong ngày thi): sửa dòng `ExecStart` trong
`/etc/systemd/system/exam-backup.service` thành đường dẫn USB, rồi:

```bash
sudo systemctl daemon-reload && sudo systemctl restart exam-backup.timer
```

### Khôi phục

```bash
./scripts/restore.sh backups/exam_db_<thời-điểm>.sql.gz
```

Script tự dừng ứng dụng, tạo lại cơ sở dữ liệu, đổ dữ liệu vào rồi bật lại.

> ⚠️ **Khôi phục sang máy KHÁC:** chép `backups/env.backup` thành `.env` **trước khi**
> chạy lệnh trên, và chép thư mục `backups/uploads/` về `backend/uploads/`. File
> `.env` chứa khoá mã hoá đề — thiếu nó thì dữ liệu khôi phục xong vẫn còn nhưng
> **không mở được đề đã nạp**.

Sao lưu chạy được **cả trong lúc đang thi** (chỉ đọc dữ liệu). **Khôi phục thì
không** — nó dừng ứng dụng, chỉ làm khi không có buổi thi nào đang chạy.

---

## 6. Cập nhật hệ thống

**Cách chính — qua web:** đăng nhập **Quản trị** → menu **Cập nhật** → bấm **"Cập
nhật lên bản mới"**. Hệ thống tự tải bản vá, dựng lại và khởi động lại (gián đoạn vài
phút). **Tự từ chối nếu đang có thí sinh làm bài.**

**Cách dự phòng — dòng lệnh:**

```bash
cd ~/ump_exam_room && ./update.sh
```

Cập nhật **không đụng tới dữ liệu và cấu hình**. Sau khi cập nhật, người đang mở trang
quản trị cần tải lại trang; máy thi khởi động lại phần mềm để nhận bản mới.

> Nếu trang Cập nhật báo *"Dịch vụ cập nhật chưa chạy"*, chạy `sudo ./install.sh` một
> lần để bật. Nhật ký: `logs/webupdate.log`.

---

## 7. Xử lý sự cố

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Cài đặt dừng giữa chừng, `backend is unhealthy` | Máy đang chạy bản cũ | `git pull && sudo ./install.sh` |
| `port is already allocated` | Apache/nginx giữ cổng 80 | Dừng dịch vụ đó rồi cài lại (xem dưới) |
| Trang quản trị tự tải lại liên tục | Bản cũ chạy chế độ phát triển | Cập nhật lên bản mới nhất |
| Máy thi báo "Phải thi bằng phần mềm thi" | Đang mở bằng trình duyệt thường | Mở bằng phần mềm UMP ExamKiosk |
| Máy thi không tìm thấy máy chủ | Mạng chặn phát hiện tự động | Khai `serverIp` trong `kiosk.config.json` |
| Phần mềm diệt virus chặn phần mềm thi | Chưa khai ngoại lệ | Xem [mục 3](#3-cài-phần-mềm-thi-lên-máy-thí-sinh) |
| Quên mật khẩu quản trị | — | `docker compose exec backend python -m app.reset_password admin <mật-khẩu-mới>` |
| Hết hạn giấy phép | Quá 90 ngày dùng thử | Nhập key gia hạn ở trang **Giấy phép** |
| Thí sinh nói đã nộp nhưng bảng báo khác | — | `docker compose exec backend python -m app.check_candidate <CCCD>` |

**Cổng 80 bị chiếm:**

```bash
sudo ss -ltnp | grep -E ':80|:443'                 # xem ai đang giữ cổng
sudo systemctl stop apache2 && sudo systemctl disable apache2   # hoặc nginx
cd ~/ump_exam_room && sudo ./install.sh
```

**Máy cài dở dang, chưa chạy được lần nào** — xoá sạch làm lại (chỉ dùng khi máy
**chưa có dữ liệu thi**, vì lệnh này xoá cơ sở dữ liệu):

```bash
cd ~/ump_exam_room && docker compose down -v; rm -f .env; git stash; git pull && sudo ./install.sh
```

**Xem trạng thái và nhật ký:**

```bash
docker compose ps                      # trạng thái các dịch vụ
docker compose logs backend --tail 50  # nhật ký máy chủ
curl -fsS http://localhost/api/health  # kiểm tra máy chủ còn sống
```

Không tự xử lý được thì gửi kết quả 2 lệnh đầu cho bên phát triển.

> ⚠️ **Tuyệt đối không cập nhật hoặc khởi động lại hệ thống khi đang có buổi thi**
> — thí sinh sẽ bị văng khỏi bài làm. Các script đã tự chặn việc này, nhưng đừng dùng
> tuỳ chọn `--force` nếu chưa chắc chắn.

---

## 8. Lệnh quản trị

Chạy trong thư mục cài đặt:

```bash
# Đặt lại mật khẩu một tài khoản
docker compose exec backend python -m app.reset_password <tài-khoản> <mật-khẩu-mới>

# Tra cứu toàn bộ bài thi của một thí sinh
docker compose exec backend python -m app.check_candidate <CCCD hoặc hộ chiếu>

# Nhập key gia hạn giấy phép bằng dòng lệnh
docker compose exec backend python -m app.set_license '<key>'

# Dừng / khởi động lại hệ thống
docker compose down
docker compose up -d
```

---

## 9. Bảo mật và giấy phép

**Việc phải làm trước kỳ thi thật:**

- Đổi mật khẩu cả 3 tài khoản mặc định (`admin`, `proctor1`, và PIN giám thị).
- Đổi mật khẩu thoát khẩn cấp của phần mềm thi (`emergencyPassword`).
- Kiểm tra sao lưu đang chạy: `systemctl status exam-backup.timer`.
- Cắm ổ USB và trỏ sao lưu sang đó.
- Thi thử trên một máy thật để chắc chắn đường truyền và cấu hình phòng máy ổn.

**Giấy phép:** cài xong dùng thử 90 ngày. Trước khi hết hạn, nhập key gia hạn tại
trang **Giấy phép** (tài khoản Quản trị). Hết hạn thì chức năng thi bị khoá nhưng
**dữ liệu vẫn còn nguyên** — nhập key mới là chạy tiếp.

**Chỉ cho thi bằng phần mềm thi:** mặc định máy chủ từ chối mọi trình duyệt thường ở
phần thi. Trang quản trị không bị ảnh hưởng. Trường hợp bất khả kháng cần cho thi tạm
bằng trình duyệt:

```bash
# trong .env trên máy chủ
KIOSK_ONLY=false
docker compose up -d backend
```

Khi đó **mất hoàn toàn phần khoá máy** — chỉ dùng khi có đủ giám thị coi trực tiếp, và
nhớ đổi lại `true` sau đó.
