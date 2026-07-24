"use strict";
// Đo hiệu năng tiến trình CHÍNH (AD-103) — trả lời dứt điểm "lag nằm ở đâu" trên
// máy yếu thay vì đoán: renderer đã chứng minh khoẻ (đồng hồ nhảy đúng từng giây,
// bấm→vẽ 0ms) nhưng phím/chuột tới trễ vài giây → nghẽn ở tiến trình chính hoặc
// tầng OS (hook/AV). Bộ đo này ghi 2 tín hiệu vào perf.log trong userData:
//   - "stall":  vòng lặp sự kiện của tiến trình chính bị kẹt (> ngưỡng) — nếu CÓ
//               những cú kẹt vài giây trùng lúc lag → thủ phạm ở tiến trình chính.
//   - "keygap": khoảng cách giữa 2 phím liên tiếp lúc đang gõ (chỉ ghi 1.2–10s —
//               dưới là gõ bình thường, trên là nghỉ tay). Nếu keygap dày đặc mà
//               KHÔNG có stall → phím bị giữ ở tầng OS (keyblocker/AV), không phải app.
// KHÔNG import electron (test được dưới Node thường). Ghi file đồng bộ append —
// dòng nào cũng là bất thường hiếm, không tốn IO.

const MAX_BYTES = 512 * 1024;          // quá cỡ → xoá làm lại (log chỉ chứa bất thường)
const TICK_MS = 500;                   // nhịp lấy mẫu vòng lặp chính
const STALL_MS = 300;                  // trễ vượt ngưỡng này = 1 cú kẹt đáng ghi
const KEYGAP_MIN_MS = 1200;            // dưới ngưỡng = gõ bình thường, bỏ qua
const KEYGAP_MAX_MS = 10000;           // trên ngưỡng = nghỉ tay, bỏ qua

/** 1 dòng log: "2026-07-24T04:05:06.789Z stall 2140ms". */
function logLine(kind, ms, nowIso) {
  return `${nowIso} ${kind} ${Math.round(ms)}ms`;
}

/** Trễ vòng lặp: gap thực đo trừ nhịp kỳ vọng; >=STALL_MS thì đáng ghi. */
function stallOf(actualGapMs, tickMs = TICK_MS) {
  const over = actualGapMs - tickMs;
  return over >= STALL_MS ? over : 0;
}

/** Khoảng cách 2 phím có đáng ghi không (lọc gõ nhanh + nghỉ tay). */
function keygapOf(gapMs) {
  return gapMs >= KEYGAP_MIN_MS && gapMs <= KEYGAP_MAX_MS ? gapMs : 0;
}

/**
 * Tạo bộ ghi perf.log. fsMod/now tiêm được để test.
 * Trả về { start(header), tick(), key(), stop() } — main gọi tick() qua setInterval,
 * key() trong before-input-event (keyDown).
 */
function createPerf({ file, fsMod = require("fs"), now = Date.now }) {
  let lastTick = 0;
  let lastKey = 0;
  let timer = null;

  const write = (line) => {
    try {
      try {
        if (fsMod.existsSync(file) && fsMod.statSync(file).size > MAX_BYTES) fsMod.unlinkSync(file);
      } catch { /* ignore */ }
      fsMod.appendFileSync(file, line + "\n");
    } catch { /* ignore — đo đạc không được phép phá app */ }
  };

  return {
    start(header) {
      write(`${new Date(now()).toISOString()} start ${header}`);
      lastTick = now();
      timer = setInterval(() => {
        const n = now();
        const over = stallOf(n - lastTick);
        lastTick = n;
        if (over) write(logLine("stall", over, new Date(n).toISOString()));
      }, TICK_MS);
      // Node giữ process sống vì timer này? Kiosk luôn sống sẵn — không sao;
      // unref để chắc chắn không cản thoát.
      if (timer.unref) timer.unref();
    },
    key() {
      const n = now();
      if (lastKey) {
        const gap = keygapOf(n - lastKey);
        if (gap) write(logLine("keygap", gap, new Date(n).toISOString()));
      }
      lastKey = n;
    },
    stop() {
      if (timer) { clearInterval(timer); timer = null; }
    },
  };
}

module.exports = { createPerf, stallOf, keygapOf, logLine, TICK_MS, STALL_MS };
