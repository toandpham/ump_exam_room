import { UserCheck, UserX, Users } from "lucide-react";
import { STATUS_LABEL, type Filter } from "./constants";

/** The clickable stat boxes that double as table filters, plus a paper-collection
 * indicator. Thí sinh KHÔNG đăng nhập coi như vắng (không còn tick vắng) — nên
 * "dự thi" = số đã đăng nhập. "Đã nộp" gộp cả timeout (hết-giờ-tự-nộp) — nộp là nộp. */
export default function StatFilters({ counts, assignedTotal, loggedIn, notLoggedIn, filter, setFilter }: {
  counts: Record<string, number>;
  assignedTotal: number;
  loggedIn: number;
  notLoggedIn: number;
  filter: Filter;
  setFilter: (f: Filter) => void;
}) {
  const submitted = (counts["submitted"] ?? 0) + (counts["timeout"] ?? 0);
  const allCollected = loggedIn > 0 && submitted >= loggedIn;
  const noPresent = loggedIn === 0;

  return (
    <div className="mb-4">
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3 mb-2">
        <Stat icon={Users} label="Đã đăng ký" value={assignedTotal} tone="blue"
          active={filter === "all"} onClick={() => setFilter("all")} />
        <Stat icon={UserX} label="Chưa đăng nhập" value={notLoggedIn} tone="red"
          active={filter === "not_logged_in"} onClick={() => setFilter("not_logged_in")} />
        <Stat icon={UserCheck} label="Đã đăng nhập" value={loggedIn} tone="green"
          active={filter === "logged_in"} onClick={() => setFilter("logged_in")} />
        {(["ready", "in_progress", "submitted"] as const).map((st) => (
          <Stat key={st} label={STATUS_LABEL[st]}
            value={st === "submitted" ? submitted : (counts[st] ?? 0)}
            active={filter === st} onClick={() => setFilter(st)} />
        ))}
      </div>

      {/* Chỉ báo thu bài: đã nộp / số thí sinh đã đăng nhập (người không đăng nhập = vắng). */}
      <div className={`text-sm px-3 py-2 rounded border ${
        noPresent
          ? "bg-slate-50 text-slate-500 border-slate-200"
          : allCollected
          ? "bg-green-50 text-green-800 border-green-200"
          : "bg-amber-50 text-amber-800 border-amber-200"
      }`}>
        <p className="text-xs opacity-70 mb-0.5">Thu bài</p>
        <p>
          {noPresent
            ? <span>Chưa có thí sinh đăng nhập</span>
            : <>
                Đã nộp <strong>{submitted}/{loggedIn}</strong> bài —{" "}
                {allCollected
                  ? <span className="font-semibold">✓ Đã thu đủ bài</span>
                  : <span>Còn <strong>{Math.max(0, loggedIn - submitted)}</strong> bài chưa nộp</span>
                }
              </>
          }
        </p>
      </div>
    </div>
  );
}

function Stat({ icon: Icon, label, value, onClick, active, tone }: {
  icon?: any; label: string; value: number; onClick: () => void; active?: boolean;
  tone?: "blue" | "green" | "red";
}) {
  const toneCls = active
    ? (tone === "green" ? "bg-green-600 text-white"
      : tone === "red" ? "bg-rose-600 text-white"
      : "bg-blue-600 text-white")
    : "bg-white";
  const subCls = active ? "text-white/80" : "text-slate-500";
  return (
    <button onClick={onClick} className={`text-left rounded-xl shadow-sm p-3 ${toneCls}`}>
      <p className={`text-xs flex items-center gap-1 ${subCls}`}>
        {Icon && <Icon size={12} />} {label}
      </p>
      <p className="text-xl font-bold">{value}</p>
    </button>
  );
}
