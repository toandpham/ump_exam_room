import { useMemo, useState } from "react";
import { ChevronDown, ChevronRight, FlaskConical, Search, X } from "lucide-react";
import { LAB_GROUPS, LAB_NOTES, LAB_SOURCE, filterGroups } from "../lib/labReference";

interface Props {
  open: boolean;
  onClose: () => void;
}

/**
 * Panel tra cứu bảng giá trị tham chiếu xét nghiệm (cạnh Giấy nháp + Máy tính).
 * Thuần client — dữ liệu tĩnh trong lib/labReference. Có ô tìm kiếm nhanh (khớp
 * tên xét nghiệm hoặc đơn vị, bỏ dấu tiếng Việt) và nhóm thu gọn/mở được.
 */
export default function LabReference({ open, onClose }: Props) {
  const [query, setQuery] = useState("");
  // Nhóm đang bị người dùng thu gọn (mặc định tất cả đều mở).
  const [collapsed, setCollapsed] = useState<Record<string, boolean>>({});

  const searching = query.trim().length > 0;
  const groups = useMemo(() => filterGroups(LAB_GROUPS, query), [query]);

  if (!open) return null;

  function toggle(title: string) {
    setCollapsed((c) => ({ ...c, [title]: !c[title] }));
  }

  // w-72 + chữ xs: đủ đọc bảng 3 cột mà mở cùng lúc 3 công cụ không chiếm hết màn hình.
  return (
    <aside className="w-72 shrink-0 h-full bg-white border-l border-slate-200 flex flex-col select-none">
      {/* Header */}
      <div className="flex items-center justify-between px-3 py-2 bg-teal-700 text-white">
        <div className="flex items-center gap-2 text-sm font-semibold">
          <FlaskConical size={15} /> Tham chiếu xét nghiệm
        </div>
        <button onClick={onClose} title="Đóng" className="hover:bg-teal-600 rounded p-1">
          <X size={16} />
        </button>
      </div>

      {/* Ô tìm kiếm */}
      <div className="p-2 border-b bg-slate-50">
        <div className="relative">
          <Search size={15} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-slate-400" />
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Tìm chỉ số (vd creatinin, Na, TSH)…"
            className="w-full pl-8 pr-8 py-1.5 text-sm border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-teal-500"
          />
          {searching && (
            <button
              onClick={() => setQuery("")}
              title="Xoá tìm kiếm"
              className="absolute right-2 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600"
            >
              <X size={15} />
            </button>
          )}
        </div>
      </div>

      {/* Nội dung */}
      <div className="flex-1 overflow-auto text-xs">
        {groups.length === 0 ? (
          <p className="p-4 text-center text-slate-500">Không tìm thấy chỉ số phù hợp.</p>
        ) : (
          groups.map((g) => {
            // Khi đang tìm kiếm luôn mở nhóm để thấy kết quả.
            const isOpen = searching || !collapsed[g.title];
            return (
              <div key={g.title} className="border-b border-slate-100">
                <button
                  onClick={() => toggle(g.title)}
                  disabled={searching}
                  className="w-full flex items-center gap-1.5 px-3 py-2 bg-slate-100 text-slate-700 font-semibold text-left sticky top-0 hover:bg-slate-200 disabled:cursor-default"
                >
                  {isOpen ? <ChevronDown size={15} /> : <ChevronRight size={15} />}
                  <span className="flex-1">{g.title}</span>
                  <span className="text-xs font-normal text-slate-400">{g.rows.length}</span>
                </button>
                {isOpen && (
                  <table className="w-full border-collapse">
                    <thead>
                      <tr className="text-[10px] uppercase text-slate-400">
                        <th className="text-left font-medium px-2 py-1 w-2/5">Xét nghiệm</th>
                        <th className="text-left font-medium px-2 py-1 w-1/4">Đơn vị</th>
                        <th className="text-left font-medium px-2 py-1">Tham chiếu</th>
                      </tr>
                    </thead>
                    <tbody>
                      {g.rows.map((r, i) => (
                        <tr key={`${r.test}-${r.unit}-${i}`} className="border-t border-slate-100 align-top">
                          <td className="px-2 py-1.5 font-medium text-slate-800">{r.test}</td>
                          <td className="px-2 py-1.5 text-slate-500 whitespace-pre-line">{r.unit}</td>
                          <td className="px-2 py-1.5 text-slate-700 whitespace-pre-line">{r.ref}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
              </div>
            );
          })
        )}

        {/* Chú thích + nguồn */}
        {!searching && (
          <div className="p-3 text-[11px] leading-relaxed text-slate-500 space-y-1">
            <p className="font-semibold text-slate-600">Chú thích</p>
            <ul className="list-disc pl-4 space-y-1">
              {LAB_NOTES.map((n, i) => (
                <li key={i}>{n}</li>
              ))}
            </ul>
            <p className="pt-1 italic">{LAB_SOURCE}</p>
          </div>
        )}
      </div>
    </aside>
  );
}
