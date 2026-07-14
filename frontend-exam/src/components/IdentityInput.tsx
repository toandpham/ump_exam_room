// Ô nhập giấy tờ tuỳ thân dùng chung cho LoginScreen + RegisterScreen (AD-58):
// nút chọn loại (CCCD / Hộ chiếu) + ô nhập có làm sạch (sanitize) theo loại.
// Quy tắc kiểm tra/làm sạch để tập trung 1 chỗ, tránh lệch giữa 2 màn hình.

export type IdType = "cccd" | "passport";

const TYPES: ReadonlyArray<readonly [IdType, string]> = [
  ["cccd", "CCCD"],
  ["passport", "Hộ chiếu"],
] as const;

const ID_RE: Record<IdType, RegExp> = {
  cccd: /^\d{12}$/,
  passport: /^[A-Z0-9]{6,9}$/,
};

export const ID_ERROR: Record<IdType, string> = {
  cccd: "CCCD phải gồm đúng 12 chữ số.",
  passport: "Số hộ chiếu gồm 6–9 ký tự chữ và số.",
};

/** Làm sạch theo loại: CCCD chỉ giữ chữ số; hộ chiếu in hoa + chữ/số. */
export function sanitizeId(idType: IdType, raw: string): string {
  return idType === "cccd"
    ? raw.replace(/\D/g, "")
    : raw.toUpperCase().replace(/[^A-Z0-9]/g, "");
}

/** Kiểm tra hợp lệ: CCCD = đúng 12 số; hộ chiếu = 6–9 ký tự chữ/số. */
export function validateId(idType: IdType, value: string): boolean {
  return ID_RE[idType].test(value);
}

// Placeholder giữ nguyên y như bản cũ của từng màn hình.
const PLACEHOLDERS: Record<"login" | "register", Record<IdType, string>> = {
  login: { cccd: "Số CCCD (12 số)", passport: "Số hộ chiếu (6–9 ký tự)" },
  register: { cccd: "12 chữ số", passport: "6–9 ký tự chữ/số" },
};

interface Props {
  idType: IdType;
  value: string;
  onIdTypeChange: (t: IdType) => void;
  onValueChange: (v: string) => void;     // nhận giá trị đã làm sạch
  variant: "login" | "register";
  autoFocus?: boolean;
}

export default function IdentityInput({
  idType, value, onIdTypeChange, onValueChange, variant, autoFocus,
}: Props) {
  const handleValue = (raw: string) => onValueChange(sanitizeId(idType, raw));

  if (variant === "login") {
    return (
      <>
        <div className="grid grid-cols-2 gap-2">
          {TYPES.map(([t, label]) => (
            <button
              key={t}
              type="button"
              onClick={() => onIdTypeChange(t)}
              className={`py-2 rounded-lg text-sm font-medium border ${
                idType === t
                  ? "bg-blue-600 text-white border-blue-600"
                  : "bg-white text-slate-600 border-slate-300 hover:bg-slate-50"
              }`}
            >
              {label}
            </button>
          ))}
        </div>
        <input
          inputMode={idType === "cccd" ? "numeric" : "text"}
          maxLength={idType === "cccd" ? 12 : 9}
          className="w-full border border-slate-300 rounded-lg px-4 py-3 text-center text-lg tracking-widest focus:ring-2 focus:ring-blue-500 outline-none uppercase"
          placeholder={PLACEHOLDERS.login[idType]}
          value={value}
          onChange={(e) => handleValue(e.target.value)}
          autoFocus={autoFocus}
        />
      </>
    );
  }

  // variant === "register" — bố cục gọn, đặt trong <Field>
  return (
    <>
      <div className="flex gap-1.5 mb-1.5">
        {TYPES.map(([t, label]) => (
          <button
            key={t}
            type="button"
            onClick={() => onIdTypeChange(t)}
            className={`flex-1 py-1 rounded text-xs font-medium border ${
              idType === t
                ? "bg-blue-600 text-white border-blue-600"
                : "bg-white text-slate-600 border-slate-300"
            }`}
          >
            {label}
          </button>
        ))}
      </div>
      <input
        inputMode={idType === "cccd" ? "numeric" : "text"}
        maxLength={idType === "cccd" ? 12 : 9}
        value={value}
        placeholder={PLACEHOLDERS.register[idType]}
        onChange={(e) => handleValue(e.target.value)}
        className="input tracking-widest uppercase"
      />
    </>
  );
}
