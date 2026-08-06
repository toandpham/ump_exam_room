import { useOutletContext } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { ShieldAlert } from "lucide-react";
import { monitorApi } from "../api/monitor";
import { errorMessage } from "../api/client";
import type { Sitting } from "../api/types";

interface Ctx { examId: string; sittingId: string; sitting: Sitting }

/** Đối chiếu đáp án sau buổi thi — dấu hiệu chép bài.
 *
 * Phép đếm: hai bài CÙNG SAI MỘT KIỂU. Cùng đúng là chuyện bình thường của người
 * học được bài; cùng chọn *một đáp án sai giống nhau* ở nhiều câu thì xác suất
 * ngẫu nhiên rất thấp. Chỉ so trong cùng phòng — ngồi cạnh nhau mới chép được nhau.
 *
 * Đây là DẤU HIỆU để hội đồng xem xét, KHÔNG phải bằng chứng: đề trộn thứ tự nên
 * trùng ngẫu nhiên vẫn xảy ra, và hai người ôn cùng một tài liệu sai cũng sai
 * giống nhau. Trang phải nói rõ điều đó ngay trên đầu, không để ai hiểu nhầm. */
export default function CollusionPage() {
  const { sittingId, sitting } = useOutletContext<Ctx>();
  const closed = sitting.status === "closed";

  const { data: pairs = [], isLoading, error } = useQuery({
    queryKey: ["collusion", sittingId],
    queryFn: () => monitorApi.collusion(sittingId),
    enabled: !!sittingId && closed,
    retry: false,
  });

  if (!closed) {
    return (
      <div className="bg-white rounded-xl shadow-sm p-6 text-slate-600">
        <h2 className="text-lg font-semibold text-slate-800 mb-2">Đối chiếu đáp án</h2>
        <p>
          Chỉ đối chiếu được <strong>sau khi đóng buổi</strong> — lúc mọi bài đã chốt.
          Quét giữa giờ cho kết quả nửa vời vì thí sinh còn đang làm.
        </p>
      </div>
    );
  }

  return (
    <div>
      <h2 className="text-lg font-semibold text-slate-800 flex items-center gap-2 mb-2">
        <ShieldAlert size={18} className="text-orange-500" /> Đối chiếu đáp án
      </h2>

      <div className="mb-4 rounded-lg border border-amber-300 bg-amber-50 px-3 py-2 text-sm text-amber-900">
        <p>
          Bảng dưới liệt kê các cặp thí sinh <strong>ngồi cùng phòng</strong> có nhiều
          câu <strong>sai giống hệt nhau</strong> (cùng chọn một đáp án sai). Cùng làm
          đúng thì không tính — đó là chuyện bình thường.
        </p>
        <p className="mt-1">
          Đây là <strong>dấu hiệu để xem xét, không phải bằng chứng</strong>. Đề đã trộn
          thứ tự nên trùng ngẫu nhiên vẫn xảy ra; hai em ôn cùng một tài liệu sai cũng
          sai giống nhau. Hội đồng cần đối chiếu thêm sơ đồ chỗ ngồi và biên bản coi thi.
        </p>
      </div>

      {isLoading && <p className="text-slate-400">Đang đối chiếu…</p>}
      {error && (
        <p className="text-rose-700 bg-rose-50 border border-rose-200 rounded p-3">
          {errorMessage(error, "Không đối chiếu được")}
        </p>
      )}

      {!isLoading && !error && pairs.length === 0 && (
        <p className="bg-white rounded-xl shadow-sm p-6 text-slate-600">
          Không có cặp nào vượt ngưỡng đáng chú ý.
        </p>
      )}

      {pairs.length > 0 && (
        <div className="bg-white rounded-xl shadow-sm overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-slate-50 text-slate-500 text-left">
              <tr>
                <th className="px-3 py-2 w-12 text-center">STT</th>
                <th className="px-3 py-2">Thí sinh A</th>
                <th className="px-3 py-2">Thí sinh B</th>
                <th className="px-3 py-2">Phòng</th>
                <th className="px-3 py-2 text-center">Số câu sai giống nhau</th>
                <th className="px-3 py-2 text-center">Tỉ lệ</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {pairs.map((p, i) => (
                <tr key={`${p.a_candidate_id}-${p.b_candidate_id}`} className="hover:bg-slate-50">
                  <td className="px-3 py-2 text-center text-slate-400">{i + 1}</td>
                  <td className="px-3 py-2">
                    {p.a_name}
                    <span className="block font-mono text-xs text-slate-400">{p.a_cccd}</span>
                  </td>
                  <td className="px-3 py-2">
                    {p.b_name}
                    <span className="block font-mono text-xs text-slate-400">{p.b_cccd}</span>
                  </td>
                  <td className="px-3 py-2 text-slate-600">{p.room_name || "—"}</td>
                  <td className="px-3 py-2 text-center font-semibold text-slate-800">
                    {p.shared_wrong}
                    <span className="block text-xs font-normal text-slate-400">
                      A sai {p.wrong_a} · B sai {p.wrong_b}
                    </span>
                  </td>
                  <td className={`px-3 py-2 text-center font-semibold ${
                    p.ratio >= 0.8 ? "text-rose-700" : p.ratio >= 0.5 ? "text-amber-700" : "text-slate-600"
                  }`}>
                    {Math.round(p.ratio * 100)}%
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
