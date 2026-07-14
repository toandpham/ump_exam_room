import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { Activity, ClipboardList, Cpu, Database, HardDrive, MemoryStick, Network, Server, ShieldAlert, UserCog } from "lucide-react";
import { adminsApi, type MetricStatus, type ServerStats } from "../api/admins";
import { licenseApi } from "../api/license";

function fmtBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 ** 2) return `${(n / 1024).toFixed(0)} KB`;
  if (n < 1024 ** 3) return `${(n / 1024 ** 2).toFixed(1)} MB`;
  return `${(n / 1024 ** 3).toFixed(2)} GB`;
}
function fmtRate(n: number): string {
  return `${fmtBytes(n)}/s`;
}
function fmtUptime(s: number): string {
  const d = Math.floor(s / 86400), h = Math.floor((s % 86400) / 3600), m = Math.floor((s % 3600) / 60);
  if (d > 0) return `${d} ngày ${h} giờ`;
  if (h > 0) return `${h} giờ ${m} phút`;
  return `${m} phút`;
}

export default function DashboardPage() {
  const { data, isLoading } = useQuery({ queryKey: ["dashboard"], queryFn: adminsApi.dashboard });
  const { data: srv } = useQuery({
    queryKey: ["server-stats"], queryFn: adminsApi.serverStats, refetchInterval: 5000,
  });
  const { data: license } = useQuery({ queryKey: ["license"], queryFn: licenseApi.get });

  return (
    <div>
      <h1 className="text-2xl font-bold text-slate-800 mb-1">Bảng điều khiển hệ thống</h1>
      <p className="text-sm text-slate-500 mb-4">
        Tổng quan toàn hệ thống. Tài khoản quản trị chỉ quản lý hệ thống + tài khoản + xoá kỳ thi —
        việc tổ chức thi (nạp đề, giám sát…) do giám thị thực hiện.
      </p>

      {/* AD-74: cảnh báo giấy phép sắp hết hạn (≤14 ngày) hoặc đã có vấn đề. */}
      {license?.warn && (
        <Link to="/license"
          className="mb-4 flex items-center gap-3 rounded-xl border border-rose-300 bg-rose-50 px-4 py-3 text-rose-800 hover:bg-rose-100">
          <ShieldAlert size={20} className="shrink-0" />
          <span className="text-sm font-semibold">
            {license.status === "valid" || license.status === "trial"
              ? `${license.status === "trial" ? "Bản dùng thử" : "Giấy phép"} còn ${license.days_left} ngày — lấy key gia hạn từ nhà cung cấp rồi nhập tại trang Giấy phép.`
              : "Giấy phép không hợp lệ — bấm để mở trang Giấy phép."}
          </span>
        </Link>
      )}

      {isLoading || !data ? (
        <p className="text-slate-400">Đang tải…</p>
      ) : (
        <>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 mb-6">
            <Card icon={<ClipboardList size={20} className="text-blue-500" />} label="Kỳ thi"
              value={data.exams.total} sub={`${data.exams.active} đang mở · ${data.exams.closed} đã đóng`} />
            <Card icon={<Activity size={20} className="text-green-500" />} label="Đang thi"
              value={data.sessions_in_progress} sub="thí sinh đang làm bài" />
            <Card icon={<UserCog size={20} className="text-slate-500" />} label="Tài khoản"
              value={data.accounts.total} sub={`${data.accounts.super_admin} quản trị · ${data.accounts.proctor} giám thị`} />
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 max-w-2xl mb-6">
            <Quick to="/admins" icon={<UserCog size={18} />} title="Quản lý tài khoản"
              desc="Thêm giám thị, đổi mật khẩu" />
            <Quick to="/exams" icon={<ClipboardList size={18} />} title="Quản lý kỳ thi"
              desc="Xem danh sách + xoá kỳ thi" />
          </div>

          {srv && <ServerHealth srv={srv} />}
        </>
      )}
    </div>
  );
}

function ServerHealth({ srv }: { srv: ServerStats }) {
  const { cpu, memory, disk, network, uptime_seconds } = srv.system;
  return (
    <div>
      <div className="flex items-center gap-2 mb-2">
        <Server size={18} className="text-slate-600" />
        <h2 className="font-bold text-slate-800">Tài nguyên máy chủ</h2>
        <span className="text-xs text-slate-400">cập nhật mỗi 5 giây · uptime {fmtUptime(uptime_seconds)}</span>
      </div>
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
        <Gauge icon={<Cpu size={18} />} title="CPU" status={cpu.status}
          percent={cpu.percent}
          detail={`${cpu.cores} nhân · tải ${cpu.load_avg[0]} / ${cpu.load_avg[1]} / ${cpu.load_avg[2]}`} />
        <Gauge icon={<MemoryStick size={18} />} title="Bộ nhớ (RAM)" status={memory.status}
          percent={memory.percent}
          detail={`${fmtBytes(memory.used)} / ${fmtBytes(memory.total)}`} />
        <Gauge icon={<HardDrive size={18} />} title="Ổ đĩa" status={disk.status}
          percent={disk.percent}
          detail={`${fmtBytes(disk.used)} / ${fmtBytes(disk.total)}`} />

        <Plain icon={<Network size={18} className="text-sky-500" />} title="Băng thông mạng">
          <div className="flex gap-4 text-sm">
            <span className="text-green-600">↓ {fmtRate(network.recv_per_sec)}</span>
            <span className="text-blue-600">↑ {fmtRate(network.sent_per_sec)}</span>
          </div>
          <p className="text-xs text-slate-400 mt-1">
            Tổng nhận {fmtBytes(network.bytes_recv)} · gửi {fmtBytes(network.bytes_sent)}
          </p>
        </Plain>

        <Plain icon={<Database size={18} className="text-indigo-500" />} title="Cơ sở dữ liệu">
          {srv.database.ok ? (
            <>
              <StatusText status={srv.database.status!}>
                {srv.database.connections_used}/{srv.database.connections_max} kết nối ({srv.database.connections_percent}%)
              </StatusText>
              <p className="text-xs text-slate-400 mt-1">Dung lượng DB {fmtBytes(srv.database.size_bytes ?? 0)}</p>
            </>
          ) : <p className="text-sm text-rose-600">Không đọc được</p>}
        </Plain>

        <Plain icon={<Database size={18} className="text-rose-500" />} title="Redis (bộ nhớ đệm)">
          {srv.redis.ok ? (
            <>
              <p className="text-sm text-slate-700">{srv.redis.connected_clients} client</p>
              <p className="text-xs text-slate-400 mt-1">Dùng {fmtBytes(srv.redis.used_memory ?? 0)} RAM</p>
            </>
          ) : <p className="text-sm text-rose-600">Không đọc được</p>}
        </Plain>
      </div>
      <p className="text-xs text-slate-400 mt-2">
        * Chỉ số CPU/RAM/ổ đĩa phản ánh máy ảo Linux chạy hệ thống (OrbStack trên Mac Mini) — đây
        chính là phần chịu tải của hệ thống thi.
      </p>
    </div>
  );
}

const TONE: Record<MetricStatus, { bar: string; text: string; chip: string }> = {
  ok:     { bar: "bg-green-500",  text: "text-green-700",  chip: "Bình thường" },
  warn:   { bar: "bg-amber-500",  text: "text-amber-700",  chip: "Cảnh báo" },
  danger: { bar: "bg-rose-600",   text: "text-rose-700",   chip: "Quá tải" },
};

function Gauge({ icon, title, percent, detail, status }: {
  icon: React.ReactNode; title: string; percent: number; detail: string; status: MetricStatus;
}) {
  const t = TONE[status];
  return (
    <div className="bg-white rounded-xl shadow-sm p-4">
      <div className="flex items-center justify-between">
        <span className="flex items-center gap-2 text-sm font-medium text-slate-700">{icon} {title}</span>
        <span className={`text-xs font-semibold ${t.text}`}>{t.chip}</span>
      </div>
      <div className="flex items-baseline gap-2 mt-2">
        <span className="text-2xl font-bold text-slate-800">{percent}%</span>
      </div>
      <div className="h-2 bg-slate-100 rounded overflow-hidden mt-1">
        <div className={`h-full ${t.bar} transition-all`} style={{ width: `${Math.min(100, percent)}%` }} />
      </div>
      <p className="text-xs text-slate-500 mt-1.5">{detail}</p>
    </div>
  );
}

function Plain({ icon, title, children }: { icon: React.ReactNode; title: string; children: React.ReactNode }) {
  return (
    <div className="bg-white rounded-xl shadow-sm p-4">
      <span className="flex items-center gap-2 text-sm font-medium text-slate-700 mb-2">{icon} {title}</span>
      {children}
    </div>
  );
}

function StatusText({ status, children }: { status: MetricStatus; children: React.ReactNode }) {
  return <p className={`text-sm font-semibold ${TONE[status].text}`}>{children}</p>;
}

function Card({ icon, label, value, sub }: { icon: React.ReactNode; label: string; value: number; sub: string }) {
  return (
    <div className="bg-white rounded-xl shadow-sm p-4">
      <div className="flex items-center justify-between text-slate-500 text-xs">
        <span>{label}</span>{icon}
      </div>
      <p className="text-3xl font-bold text-slate-800 mt-1">{value}</p>
      <p className="text-xs text-slate-500 mt-1">{sub}</p>
    </div>
  );
}

function Quick({ to, icon, title, desc }: { to: string; icon: React.ReactNode; title: string; desc: string }) {
  return (
    <Link to={to} className="block rounded-xl border border-slate-200 bg-white p-4 hover:bg-slate-50 transition">
      <div className="flex items-center gap-2 font-semibold text-slate-800">{icon} {title}</div>
      <p className="text-xs text-slate-500 mt-1">{desc}</p>
    </Link>
  );
}
