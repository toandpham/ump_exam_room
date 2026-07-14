import { useEffect, useRef, useState } from "react";
import { Calculator, Keyboard, X } from "lucide-react";
import { evaluate, fmt, type Mode } from "../lib/calc";

interface Props {
  open: boolean;
  onClose: () => void;
}

export default function ScientificCalculator({ open, onClose }: Props) {
  const [display, setDisplay] = useState("");
  const [result, setResult] = useState<string>("");
  const [mode, setMode] = useState<Mode>("DEG");
  const [memory, setMemory] = useState(0);
  const [lastAns, setLastAns] = useState<number | null>(null);
  const [error, setError] = useState("");

  function append(s: string) {
    setError("");
    // After "=" pressed, the next digit/dot starts fresh; an operator chains the result.
    if (result && /^[\d.πe√]/.test(s)) {
      setDisplay(s);
      setResult("");
      return;
    }
    if (result && /[+\-×÷*/^]/.test(s)) {
      setDisplay(result + s);
      setResult("");
      return;
    }
    setDisplay((d) => d + s);
  }
  function clearAll() { setDisplay(""); setResult(""); setError(""); }
  function del() {
    setError("");
    if (result) { setResult(""); return; }
    setDisplay((d) => d.slice(0, -1));
  }
  function equals() {
    if (!display.trim()) return;
    try {
      const v = evaluate(display, mode);
      const out = fmt(v);
      setResult(out);
      setLastAns(v);
      setError("");
    } catch (e: any) {
      setError(e?.message || "Lỗi");
    }
  }
  function pushAns() {
    if (lastAns == null) return;
    append(fmt(lastAns));
  }
  function memOp(op: "MC" | "MR" | "M+" | "M-") {
    if (op === "MC") return setMemory(0);
    if (op === "MR") return append(fmt(memory));
    try {
      const v = display ? evaluate(display, mode) : 0;
      setMemory((m) => op === "M+" ? m + v : m - v);
    } catch {/* ignore */}
  }

  // Physical-keyboard support. Keep the handler in a ref so the listener (bound
  // once while open) always sees current state without re-subscribing.
  const keyRef = useRef<(e: KeyboardEvent) => void>(() => {});
  keyRef.current = (e: KeyboardEvent) => {
    // Khi con trỏ đang ở một ô nhập (vd <textarea> Giấy nháp, hoặc bất kỳ
    // input/contentEditable nào) thì KHÔNG cướp phím — để người dùng gõ nháp bình thường.
    const t = e.target as HTMLElement | null;
    if (t && (t.tagName === "INPUT" || t.tagName === "TEXTAREA" || t.isContentEditable)) return;
    const k = e.key;
    // Map a physical key to a calculator action; return true if we handled it.
    let handled = true;
    if (k >= "0" && k <= "9") append(k);
    else if (k === ".") append(".");
    else if (k === "+") append("+");
    else if (k === "-") append("−");
    else if (k === "*") append("×");
    else if (k === "/") append("÷");
    else if (k === "(") append("(");
    else if (k === ")") append(")");
    else if (k === "^") append("^");
    else if (k === "Enter" || k === "=") equals();
    else if (k === "Backspace") del();
    else if (k === "Delete" || k === "Escape") clearAll();
    else handled = false;
    if (handled) e.preventDefault();
  };
  useEffect(() => {
    if (!open) return;
    const fn = (e: KeyboardEvent) => keyRef.current(e);
    window.addEventListener("keydown", fn);
    return () => window.removeEventListener("keydown", fn);
  }, [open]);

  if (!open) return null;

  // w-64: mở cùng lúc 3 công cụ (nháp + máy tính + tham chiếu) vẫn còn chỗ cho đề.
  return (
    <aside className="w-64 shrink-0 h-full bg-white border-l border-slate-200 flex flex-col select-none">
      {/* Header */}
      <div className="flex items-center justify-between px-3 py-2 bg-slate-800 text-white">
        <div className="flex items-center gap-2 text-sm font-semibold">
          <Calculator size={15} /> Máy tính khoa học
        </div>
        <button onClick={onClose} title="Đóng" className="hover:bg-slate-700 rounded p-1">
          <X size={16} />
        </button>
      </div>

      {/* Display */}
      <div className="p-3 bg-slate-50 border-b">
        <div className="flex items-center justify-between text-[10px] text-slate-500 mb-1">
          <span className="font-mono">{mode}{memory !== 0 ? " · M" : ""}</span>
          <span className="text-rose-600">{error}</span>
        </div>
        <div className="bg-white border rounded h-20 p-2 flex flex-col justify-end font-mono">
          <div className="text-slate-400 text-sm truncate" title={display}>
            {display || " "}
          </div>
          <div className={`text-right ${error ? "text-rose-600" : "text-slate-800"} text-2xl font-bold truncate`}>
            {result || "0"}
          </div>
        </div>
      </div>

      {/* Buttons */}
      <div className="flex-1 p-2 grid grid-cols-5 gap-1.5 content-start overflow-auto">
        <Btn variant="mode" onClick={() => setMode((m) => m === "DEG" ? "RAD" : "DEG")}>{mode}</Btn>
        <Btn variant="mem" onClick={() => memOp("MC")}>MC</Btn>
        <Btn variant="mem" onClick={() => memOp("MR")}>MR</Btn>
        <Btn variant="mem" onClick={() => memOp("M+")}>M+</Btn>
        <Btn variant="mem" onClick={() => memOp("M-")}>M−</Btn>

        <Btn variant="fn" onClick={() => append("sin(")}>sin</Btn>
        <Btn variant="fn" onClick={() => append("cos(")}>cos</Btn>
        <Btn variant="fn" onClick={() => append("tan(")}>tan</Btn>
        <Btn variant="fn" onClick={() => append("log(")}>log</Btn>
        <Btn variant="fn" onClick={() => append("ln(")}>ln</Btn>

        <Btn variant="fn" onClick={() => append("sin⁻¹(")}>sin⁻¹</Btn>
        <Btn variant="fn" onClick={() => append("cos⁻¹(")}>cos⁻¹</Btn>
        <Btn variant="fn" onClick={() => append("tan⁻¹(")}>tan⁻¹</Btn>
        <Btn variant="fn" onClick={() => append("√(")}>√</Btn>
        <Btn variant="fn" onClick={() => append("^2")}>x²</Btn>

        <Btn variant="fn" onClick={() => append("(")}>(</Btn>
        <Btn variant="fn" onClick={() => append(")")}>)</Btn>
        <Btn variant="fn" onClick={() => append("π")}>π</Btn>
        <Btn variant="fn" onClick={() => append("e")}>e</Btn>
        <Btn variant="fn" onClick={() => append("^")}>^</Btn>

        <Btn onClick={() => append("7")}>7</Btn>
        <Btn onClick={() => append("8")}>8</Btn>
        <Btn onClick={() => append("9")}>9</Btn>
        <Btn variant="op" onClick={() => append("÷")}>÷</Btn>
        <Btn variant="danger" onClick={clearAll}>C</Btn>

        <Btn onClick={() => append("4")}>4</Btn>
        <Btn onClick={() => append("5")}>5</Btn>
        <Btn onClick={() => append("6")}>6</Btn>
        <Btn variant="op" onClick={() => append("×")}>×</Btn>
        <Btn variant="danger" onClick={del}>⌫</Btn>

        <Btn onClick={() => append("1")}>1</Btn>
        <Btn onClick={() => append("2")}>2</Btn>
        <Btn onClick={() => append("3")}>3</Btn>
        <Btn variant="op" onClick={() => append("−")}>−</Btn>
        <Btn variant="fn" onClick={pushAns} disabled={lastAns == null}>Ans</Btn>

        <Btn className="col-span-2" onClick={() => append("0")}>0</Btn>
        <Btn onClick={() => append(".")}>.</Btn>
        <Btn variant="op" onClick={() => append("+")}>+</Btn>
        <Btn variant="primary" onClick={equals}>=</Btn>
      </div>

      {/* Keyboard hint */}
      <div className="px-3 py-2 border-t bg-slate-50 text-[11px] text-slate-500 flex items-center gap-1.5">
        <Keyboard size={13} /> Gõ phím trực tiếp: số, + − × ÷ ( ) ^ · Enter = tính · Backspace xoá · Esc xoá hết
      </div>
    </aside>
  );
}

function Btn({
  children, onClick, variant, disabled, className = "",
}: {
  children: React.ReactNode;
  onClick: () => void;
  variant?: "primary" | "op" | "fn" | "mem" | "mode" | "danger";
  disabled?: boolean;
  className?: string;
}) {
  const base = "h-10 text-sm rounded font-medium transition active:scale-95 disabled:opacity-40";
  const cls = {
    primary: "bg-blue-600 text-white hover:bg-blue-700",
    op: "bg-slate-200 text-slate-800 hover:bg-slate-300",
    fn: "bg-slate-100 text-slate-700 hover:bg-slate-200 text-xs",
    mem: "bg-amber-50 text-amber-700 hover:bg-amber-100 text-xs",
    mode: "bg-emerald-100 text-emerald-700 hover:bg-emerald-200 text-xs",
    danger: "bg-rose-100 text-rose-700 hover:bg-rose-200",
    default: "bg-white border border-slate-200 text-slate-800 hover:bg-slate-50",
  }[variant || "default"];
  return (
    <button onClick={onClick} disabled={disabled} className={`${base} ${cls} ${className}`}>
      {children}
    </button>
  );
}
