/** Mã đăng nhập 6 số của giám thị, nhớ trên MÁY CHỦ TỊCH.
 *
 * VÌ SAO: mã chỉ được server trả về đúng một lần lúc bấm "Đặt lại MK" (server chỉ
 * lưu bản băm, không lưu mã gốc). Trước đây nó nằm trong state của component nên
 * chuyển tab hay tải lại trang là mất — chủ tịch buộc phải đặt mã MỚI, trong khi
 * giám thị đang cầm mã cũ (lỗi hiện trường 30-07).
 *
 * Cố ý KHÔNG lưu xuống cơ sở dữ liệu: mã 6 số dạng đọc được nằm trong CSDL và trong
 * bản sao lưu là hạ cấp bảo mật. Đổi lại, chủ tịch dùng máy khác thì phải đặt lại
 * mã (một cú bấm). */
export interface PinInfo {
  pin: string;
  username: string;
  full_name: string | null;
}

const key = (roomId: string) => `proctor_pin_${roomId}`;

export function savePin(roomId: string, info: PinInfo): void {
  try {
    localStorage.setItem(key(roomId), JSON.stringify(info));
  } catch { /* hết quota / chế độ riêng tư — không được làm vỡ trang */ }
}

export function loadPin(roomId: string): PinInfo | null {
  try {
    const raw = localStorage.getItem(key(roomId));
    if (!raw) return null;
    const v = JSON.parse(raw);
    return typeof v?.pin === "string" ? (v as PinInfo) : null;
  } catch {
    return null;   // dữ liệu hỏng → coi như chưa có, đặt lại mã là xong
  }
}

export function clearPin(roomId: string): void {
  try {
    localStorage.removeItem(key(roomId));
  } catch { /* bỏ qua */ }
}
