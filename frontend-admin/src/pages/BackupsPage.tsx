import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Download, DatabaseBackup, RefreshCw } from "lucide-react";
import { api, errorMessage } from "../api/client";
import { triggerDownload } from "../api/exams";

interface BackupFile { name: string; size_bytes: number; created_at: string }
interface BackupList { files: BackupFile[]; latest_age_seconds: number | null }

const backupsApi = {
  list: async (): Promise<BackupList> => (await api.get("/admin/admins/backups")).data,
  create: async (): Promise<BackupFile> => (await api.post("/admin/admins/backups")).data,
  // Dùng chung khuôn tải file với báo cáo/danh sách — đi qua axios nên tự gắn token.
  download: async (name: string) => {
    const res = await api.get(`/admin/admins/backups/${encodeURIComponent(name)}`,
      { responseType: "blob" });
    triggerDownload(res.data, name);
  },
};

const fmtSize = (n: number) =>
  n >= 1024 * 1024 ? `${(n / 1024 / 1024).toFixed(1)} MB` : `${Math.round(n / 1024)} KB`;

function fmtAge(sec: number): string {
  if (sec < 90) return "vừa xong";
  const m = Math.round(sec / 60);
  if (m < 60) return `${m} phút trước`;
  const h = Math.floor(m / 60);
  return h < 24 ? `${h} giờ ${m % 60} phút trước` : `${Math.floor(h / 24)} ngày trước`;
}

/** Trang Sao lưu (quản trị).
 *
 * Trước đây sao lưu chỉ chạy ngầm theo hẹn giờ trên máy chủ: không ai biết nó còn
 * chạy hay đã chết, và không tự tạo được một bản trước khi mở buổi thi. Trang này
 * trả lời cả hai.
 *
 * CỐ Ý KHÔNG có nút khôi phục: bấm nhầm là mất sạch, và khôi phục trong lúc hệ
 * thống đang chạy để lại trạng thái hỏng. Khôi phục vẫn phải có người ngồi trước
 * máy chủ, chạy scripts/restore.sh. */
export default function BackupsPage() {
  const qc = useQueryClient();
  const { data, isLoading, error } = useQuery({
    queryKey: ["backups"],
    queryFn: backupsApi.list,
    refetchInterval: 60000,
  });

  const create = useMutation({
    mutationFn: backupsApi.create,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["backups"] }),
  });

  const age = data?.latest_age_seconds ?? null;
  // Hẹn giờ mặc định là 10 phút; quá một giờ mà chưa có bản mới nghĩa là nó đã chết.
  const stale = age === null || age > 3600;

  return (
    <div>
      <div className="flex items-center justify-between mb-3">
        <h1 className="text-xl font-bold text-slate-800 flex items-center gap-2">
          <DatabaseBackup size={20} /> Sao lưu
        </h1>
        <button onClick={() => create.mutate()} disabled={create.isPending}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-blue-600 text-white text-sm font-semibold hover:bg-blue-700 disabled:opacity-60">
          <RefreshCw size={15} className={create.isPending ? "animate-spin" : ""} />
          {create.isPending ? "Đang sao lưu…" : "Sao lưu ngay"}
        </button>
      </div>

      <div className={`mb-4 rounded-lg border px-3 py-2 text-sm ${
        stale ? "border-rose-300 bg-rose-50 text-rose-800"
              : "border-green-300 bg-green-50 text-green-800"}`}>
        {age === null
          ? "⚠️ CHƯA CÓ BẢN SAO LƯU NÀO. Hỏng ổ đĩa lúc này là mất toàn bộ kết quả thi."
          : stale
            ? `⚠️ Bản gần nhất đã ${fmtAge(age)} — sao lưu tự động có thể đã ngừng chạy. Kiểm tra dịch vụ exam-backup trên máy chủ.`
            : `✓ Bản gần nhất: ${fmtAge(age)}. Sao lưu tự động đang chạy bình thường.`}
      </div>

      <p className="mb-4 text-sm text-slate-600 bg-slate-50 border border-slate-200 rounded-lg px-3 py-2">
        Nên bấm <strong>Sao lưu ngay</strong> trước mỗi buổi thi. Bản sao lưu gồm
        toàn bộ cơ sở dữ liệu (thí sinh, bài làm, điểm).{" "}
        <strong>Khôi phục không làm được trên web</strong> — đó là thao tác nguy hiểm,
        phải chạy <code className="bg-white px-1 rounded border">./scripts/restore.sh</code>{" "}
        trực tiếp trên máy chủ.
      </p>

      {isLoading && <p className="text-slate-400">Đang tải…</p>}
      {error && (
        <p className="text-rose-700 bg-rose-50 border border-rose-200 rounded p-3">
          {errorMessage(error, "Không đọc được danh sách sao lưu")}
        </p>
      )}
      {create.isError && (
        <p className="mb-3 text-rose-700 bg-rose-50 border border-rose-200 rounded p-3">
          {errorMessage(create.error, "Sao lưu thất bại")}
        </p>
      )}

      {data && data.files.length > 0 && (
        <div className="bg-white rounded-xl shadow-sm overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-slate-50 text-slate-500 text-left">
              <tr>
                <th className="px-3 py-2">Tên file</th>
                <th className="px-3 py-2">Thời điểm</th>
                <th className="px-3 py-2">Dung lượng</th>
                <th className="px-3 py-2"></th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {data.files.map((f) => (
                <tr key={f.name} className="hover:bg-slate-50">
                  <td className="px-3 py-2 font-mono text-xs">{f.name}</td>
                  <td className="px-3 py-2">{new Date(f.created_at).toLocaleString("vi-VN")}</td>
                  <td className="px-3 py-2 text-slate-600">{fmtSize(f.size_bytes)}</td>
                  <td className="px-3 py-2 text-right">
                    <button onClick={() => backupsApi.download(f.name)}
                      className="inline-flex items-center gap-1 px-2 py-1 rounded border border-slate-200 hover:bg-slate-50 text-xs text-slate-600">
                      <Download size={14} /> Tải về
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
