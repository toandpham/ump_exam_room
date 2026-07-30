import { Fragment, type ReactNode } from "react";

/** Ký tự Unicode "số mũ" / "chỉ số dưới" → chữ tương ứng ở dạng ASCII.
 *
 * VÌ SAO PHẢI ĐỔI: máy thi chạy Windows 7, font hệ thống KHÔNG có glyph cho khối
 * U+2070 (⁹ ⁺ ⁻ ₂ ₃…) nên bảng Tham chiếu xét nghiệm hiện `10⁹/L` thành `10□/L`,
 * `Ca²⁺` thành `Ca²□` (buổi thi 30-07). Riêng ¹ ² ³ nằm trong Latin-1 nên font nào
 * cũng có — đó là lý do `10¹²` hiện đúng mà `10⁹` thì hỏng. Chữ số ASCII trong thẻ
 * <sup>/<sub> thì không phụ thuộc font, và trông đúng kiểu khoa học hơn.
 *
 * Đổi lúc RENDER (không sửa 24 chỗ trong dữ liệu): dữ liệu gốc giữ nguyên nên ô tìm
 * kiếm vẫn khớp như cũ, và dòng nào thêm sau này cũng tự được xử lý. */
const SUP: Record<string, string> = {
  "⁰": "0", "¹": "1", "²": "2", "³": "3", "⁴": "4", "⁵": "5", "⁶": "6", "⁷": "7",
  "⁸": "8", "⁹": "9", "⁺": "+", "⁻": "-", "⁼": "=", "⁽": "(", "⁾": ")", "ⁿ": "n",
};
const SUB: Record<string, string> = {
  "₀": "0", "₁": "1", "₂": "2", "₃": "3", "₄": "4", "₅": "5", "₆": "6", "₇": "7",
  "₈": "8", "₉": "9", "₊": "+", "₋": "-", "₌": "=", "₍": "(", "₎": ")",
};

type Kind = "text" | "sup" | "sub";

function kindOf(ch: string): Kind {
  if (ch in SUP) return "sup";
  if (ch in SUB) return "sub";
  return "text";
}

/** Chuyển chuỗi có ký tự mũ/chỉ số Unicode thành node React dùng <sup>/<sub>.
 * Các ký tự mũ LIỀN NHAU được gộp vào một thẻ ("10¹²" → 10<sup>12</sup>). */
export function sciText(input: string): ReactNode {
  if (!input) return input;
  // Đường nhanh: phần lớn dòng không có ký tự nào cần đổi.
  let needs = false;
  for (const ch of input) if (kindOf(ch) !== "text") { needs = true; break; }
  if (!needs) return input;

  const parts: { kind: Kind; text: string }[] = [];
  for (const ch of input) {
    const kind = kindOf(ch);
    const mapped = kind === "sup" ? SUP[ch] : kind === "sub" ? SUB[ch] : ch;
    const last = parts[parts.length - 1];
    if (last && last.kind === kind) last.text += mapped;
    else parts.push({ kind, text: mapped });
  }
  return parts.map((p, i) =>
    p.kind === "sup" ? <sup key={i}>{p.text}</sup>
      : p.kind === "sub" ? <sub key={i}>{p.text}</sub>
        : <Fragment key={i}>{p.text}</Fragment>,
  );
}
