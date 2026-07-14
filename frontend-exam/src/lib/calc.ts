// Bộ máy biểu thức cho máy tính khoa học: chuyển hiển thị → kiểm tra allowlist
// nghiêm ngặt → đánh giá trong sandbox chỉ thấy Math + các hàm lượng giác theo độ.
// Tách riêng khỏi component để dễ kiểm thử (lib/calc.test.ts).

export type Mode = "DEG" | "RAD";

// Safe evaluator: tokenize → strict allowlist → Function() in a sandbox that
// only sees Math + our degree-aware trig wrappers. No access to globals.
const DEG_FNS = {
  sin: (x: number) => Math.sin((x * Math.PI) / 180),
  cos: (x: number) => Math.cos((x * Math.PI) / 180),
  tan: (x: number) => Math.tan((x * Math.PI) / 180),
  asin: (x: number) => (Math.asin(x) * 180) / Math.PI,
  acos: (x: number) => (Math.acos(x) * 180) / Math.PI,
  atan: (x: number) => (Math.atan(x) * 180) / Math.PI,
};
const RAD_FNS = {
  sin: Math.sin, cos: Math.cos, tan: Math.tan,
  asin: Math.asin, acos: Math.acos, atan: Math.atan,
};

const TOKEN_RE =
  /\s+|\d+(?:\.\d+)?|\.\d+|\*\*|[+\-*/(),]|Math\.(?:PI|E|sqrt|log|log10|abs|cbrt|exp)|F\.(?:sin|cos|tan|asin|acos|atan)/g;

function transform(display: string): string {
  let s = display
    .replace(/×/g, "*")
    .replace(/÷/g, "/")
    .replace(/−/g, "-")
    .replace(/\^/g, "**");
  // Implicit multiplication is applied **before** function substitution so we
  // never have to worry about chopping "log10" or "Math.E" later. In the raw
  // display, all identifiers are letter-only (sin/cos/tan/log/ln/π/e/√).
  s = s.replace(/(\d|\))(\s*)([a-zA-Zπ√(])/g, "$1*$3");
  // Functions — inverse trig before plain trig; negative lookbehind on
  // [a-zA-Z.] prevents re-matching inside an already-substituted name
  // (e.g. the "sin" inside "F.asin" or "log" inside "Math.log10").
  s = s
    .replace(/sin⁻¹\(/g, "F.asin(")
    .replace(/cos⁻¹\(/g, "F.acos(")
    .replace(/tan⁻¹\(/g, "F.atan(")
    .replace(/(?<![a-zA-Z.])sin\(/g, "F.sin(")
    .replace(/(?<![a-zA-Z.])cos\(/g, "F.cos(")
    .replace(/(?<![a-zA-Z.])tan\(/g, "F.tan(")
    .replace(/(?<![a-zA-Z.])log\(/g, "Math.log10(")
    .replace(/(?<![a-zA-Z.])ln\(/g, "Math.log(")
    .replace(/√\(/g, "Math.sqrt(")
    .replace(/√(\d+(?:\.\d+)?)/g, "Math.sqrt($1)")
    .replace(/π/g, "(Math.PI)")
    .replace(/(?<![a-zA-Z0-9_.)])e(?![a-zA-Z0-9_(])/g, "(Math.E)");
  return s;
}

function validate(transformed: string): boolean {
  let pos = 0;
  TOKEN_RE.lastIndex = 0;
  let m: RegExpExecArray | null;
  while ((m = TOKEN_RE.exec(transformed)) !== null) {
    if (m.index !== pos) return false;
    pos = m.index + m[0].length;
  }
  return pos === transformed.length;
}

export function evaluate(display: string, mode: Mode): number {
  const transformed = transform(display);
  if (!validate(transformed)) throw new Error("Biểu thức không hợp lệ");
  const F = mode === "DEG" ? DEG_FNS : RAD_FNS;
  // eslint-disable-next-line no-new-func
  const fn = new Function("Math", "F", `"use strict"; return (${transformed});`);
  const v = fn(Math, F);
  if (typeof v !== "number" || !isFinite(v)) throw new Error("Kết quả không hợp lệ");
  return v;
}

export function fmt(n: number): string {
  if (Number.isInteger(n) && Math.abs(n) < 1e15) return String(n);
  const s = n.toPrecision(12);
  // Trim trailing zeros after decimal point.
  return s.includes(".") && !s.includes("e") ? s.replace(/\.?0+$/, "") : s;
}
