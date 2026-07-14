// Bảng giá trị tham chiếu xét nghiệm (Laboratory Reference Intervals).
// Nguồn: Quyết định 320/QĐ-BYT (23/01/2014); thuật ngữ/đơn vị đối chiếu theo
// Quyết định 1227/QĐ-BYT (11/04/2025). Trích nguyên từ file Word nhà trường cung
// cấp. Dữ liệu TĨNH (chuẩn Bộ Y tế, không đổi theo kỳ thi) — không cần backend/DB.
//
// Panel tra cứu hiển thị cho thí sinh trong lúc thi (cạnh Giấy nháp + Máy tính).
// Các dòng cùng một xét nghiệm ở đơn vị quy đổi khác (vd Glucose mmol/L & mg/dL)
// được giữ nguyên thành 2 dòng riêng như file gốc.

export interface LabRow {
  /** Tên xét nghiệm (Test). */
  test: string;
  /** Đơn vị (Units). */
  unit: string;
  /** Khoảng tham chiếu (Ref. ranges) — có thể nhiều dòng, ngăn bằng "\n". */
  ref: string;
}

export interface LabGroup {
  title: string;
  rows: LabRow[];
}

export const LAB_SOURCE =
  "Nguồn: Quyết định số 320/QĐ-BYT ngày 23/01/2014. Thuật ngữ và đơn vị được đối " +
  "chiếu theo Quyết định số 1227/QĐ-BYT ngày 11/04/2025.";

export const LAB_NOTES: string[] = [
  "% biểu thị tỷ lệ phần trăm; # biểu thị số lượng tuyệt đối của từng loại tế bào, thường được báo cáo theo đơn vị 10⁹/L.",
  "Khoảng tham chiếu có thể thay đổi theo phương pháp, thiết bị, tuổi, giới, thai kỳ và quần thể; ưu tiên khoảng tham chiếu do phòng xét nghiệm thực hiện công bố.",
  "Cùng một xét nghiệm có thể được trình bày ở hai đơn vị (SI và đơn vị thường dùng); giá trị quy đổi được làm tròn từ khoảng tham chiếu theo đơn vị SI.",
  "HPF: vi trường phóng đại cao; LPF: vi trường phóng đại thấp; FEU: đơn vị tương đương fibrinogen.",
  "PT, APTT, D-dimer, fibrinogen, CRP, ESR, eGFR và các chỉ số soi cặn nước tiểu phụ thuộc phương pháp; các giá trị bổ sung dùng làm khoảng tham khảo người lớn.",
];

export const LAB_GROUPS: LabGroup[] = [
  {
    title: "Huyết học – Công thức máu",
    rows: [
      { test: "WBC", unit: "10⁹/L", ref: "4,0-10,0" },
      { test: "NEU %", unit: "%", ref: "45-75" },
      { test: "NEU#", unit: "10⁹/L", ref: "1,8-7,5" },
      { test: "LYM %", unit: "%", ref: "20-35" },
      { test: "LYM#", unit: "10⁹/L", ref: "0,8-3,5" },
      { test: "MONO %", unit: "%", ref: "4-10" },
      { test: "MONO#", unit: "10⁹/L", ref: "0,16-1,0" },
      { test: "EOS %", unit: "%", ref: "1-8" },
      { test: "EOS#", unit: "10⁹/L", ref: "0,01-0,8" },
      { test: "BASO %", unit: "%", ref: "0-2" },
      { test: "BASO#", unit: "10⁹/L", ref: "0-0,2" },
      { test: "IG %", unit: "%", ref: "0,0-0,6" },
      { test: "RBC", unit: "10¹²/L", ref: "Nam: 4,5-5,9\nNữ: 4,1-5,1" },
      { test: "Hb", unit: "g/L", ref: "Nam: 135-175\nNữ: 120-155" },
      { test: "HCT", unit: "L/L", ref: "Nam: 0,41-0,53\nNữ: 0,36-0,46" },
      { test: "MCV", unit: "fL", ref: "80-100" },
      { test: "MCH", unit: "pg", ref: "27-32" },
      { test: "MCHC", unit: "g/L", ref: "320-350" },
      { test: "RDW", unit: "%", ref: "11,5-14,5" },
      { test: "NRBC %", unit: "%", ref: "0" },
      { test: "NRBC#", unit: "10⁹/L", ref: "0" },
      { test: "PLT", unit: "10⁹/L", ref: "150-450" },
      { test: "MPV", unit: "fL", ref: "7-12" },
      { test: "RET %", unit: "%", ref: "0,5-2,5" },
      { test: "RET#", unit: "10⁹/L", ref: "25-100" },
      { test: "ESR (Westergren)", unit: "mm/giờ", ref: "Nam: 0-15\nNữ: 0-20" },
    ],
  },
  {
    title: "Đông máu",
    rows: [
      { test: "PT", unit: "giây", ref: "10-14" },
      { test: "PT %", unit: "%", ref: "70-140" },
      { test: "INR", unit: "Tỷ số", ref: "0,8-1,2" },
      { test: "APTT", unit: "giây", ref: "25-35" },
      { test: "APTT ratio", unit: "Tỷ số", ref: "0,8-1,2" },
      { test: "Fibrinogen", unit: "g/L", ref: "2,0-4,0" },
      { test: "D-dimer", unit: "mg/L FEU", ref: "<0,5" },
    ],
  },
  {
    title: "Sinh hóa: Enzym – chức năng gan, tụy và cơ",
    rows: [
      { test: "ALT", unit: "U/L", ref: "Nam: <41\nNữ: <31" },
      { test: "AST", unit: "U/L", ref: "Nam: <40\nNữ: <31" },
      { test: "ALP", unit: "U/L", ref: "Nam: 40-129\nNữ: 35-104" },
      { test: "GGT", unit: "U/L", ref: "Nam: 8-61\nNữ: 5-36" },
      { test: "Amylase", unit: "U/L", ref: "<100" },
      { test: "Lipase", unit: "U/L", ref: "13-60" },
      { test: "CK", unit: "U/L, 37 °C", ref: "Nam: 38-174\nNữ: 26-140" },
      { test: "CK-MB", unit: "U/L", ref: "<24" },
      { test: "LDH", unit: "U/L", ref: "240-480" },
      {
        test: "ChE",
        unit: "U/L",
        ref:
          "Trẻ em, nam và nữ >40 tuổi: 5.300-12.900\n" +
          "Nữ 16-39 tuổi, không mang thai/không dùng tránh thai hormon: 4.260-11.250\n" +
          "Nữ 18-41 tuổi, mang thai hoặc dùng tránh thai hormon: 3.650-9.120",
      },
      { test: "Bilirubin toàn phần", unit: "µmol/L", ref: "<17,1" },
      { test: "Bilirubin toàn phần", unit: "mg/dL", ref: "<1,0" },
      { test: "Bilirubin trực tiếp", unit: "µmol/L", ref: "<5,1" },
      { test: "Bilirubin trực tiếp", unit: "mg/dL", ref: "<0,3" },
      { test: "Bilirubin gián tiếp", unit: "µmol/L", ref: "<12" },
      { test: "Bilirubin gián tiếp", unit: "mg/dL", ref: "<0,7" },
      { test: "Glucose", unit: "mmol/L", ref: "3,9-5,6" },
      { test: "Glucose", unit: "mg/dL", ref: "70-101" },
    ],
  },
  {
    title: "Sinh hóa: Chuyển hóa và chức năng thận",
    rows: [
      { test: "Urê", unit: "mmol/L", ref: "1,7-8,3" },
      { test: "Urê", unit: "mg/dL", ref: "10,2-49,7" },
      { test: "Creatinin", unit: "µmol/L", ref: "Nam: 59-104\nNữ: 45-84" },
      { test: "Creatinin", unit: "mg/dL", ref: "Nam: 0,67-1,17\nNữ: 0,51-0,95" },
      { test: "Acid uric", unit: "µmol/L", ref: "Nam: 202-416\nNữ: 143-399" },
      { test: "Acid uric", unit: "mg/dL", ref: "Nam: 3,4-7,0\nNữ: 2,4-6,7" },
      { test: "HbA1c", unit: "%", ref: "4-6" },
      { test: "eGFR", unit: "mL/phút/1,73 m²", ref: "≥90 (người lớn; diễn giải theo tuổi)" },
    ],
  },
  {
    title: "Sinh hóa: Ion đồ và khoáng chất",
    rows: [
      { test: "Na⁺", unit: "mmol/L", ref: "133-147" },
      { test: "K⁺", unit: "mmol/L", ref: "3,4-4,5" },
      { test: "Cl⁻", unit: "mmol/L", ref: "94-111" },
      { test: "Ca", unit: "mmol/L", ref: "2,15-2,55" },
      { test: "Ca", unit: "mg/dL", ref: "8,6-10,2" },
      { test: "Ca²⁺", unit: "mmol/L", ref: "1,17-1,29" },
      { test: "Ca²⁺", unit: "mg/dL", ref: "4,7-5,2" },
      { test: "Mg²⁺", unit: "mmol/L", ref: "0,65-1,05" },
      { test: "Mg²⁺", unit: "mg/dL", ref: "1,59-2,56" },
      { test: "P", unit: "mmol/L", ref: "0,87-1,45" },
      { test: "P", unit: "mg/dL", ref: "2,7-4,5" },
      { test: "CO₂ toàn phần", unit: "mmol/L", ref: "22-29" },
    ],
  },
  {
    title: "Sinh hóa: Lipid, protein và chuyển hóa sắt",
    rows: [
      { test: "Cholesterol", unit: "mmol/L", ref: "3,9-5,2" },
      { test: "Cholesterol", unit: "mg/dL", ref: "150-200" },
      { test: "HDL-C", unit: "mmol/L", ref: ">0,9" },
      { test: "HDL-C", unit: "mg/dL", ref: ">35" },
      { test: "LDL-C", unit: "mmol/L", ref: "<3,4" },
      { test: "LDL-C", unit: "mg/dL", ref: "<131" },
      { test: "Triglycerid", unit: "mmol/L", ref: "0,46-1,88" },
      { test: "Triglycerid", unit: "mg/dL", ref: "40-166" },
      { test: "Protein TP", unit: "g/L", ref: "66-87" },
      { test: "Protein TP", unit: "g/dL", ref: "6,6-8,7" },
      { test: "Albumin", unit: "g/L", ref: "34-48" },
      { test: "Albumin", unit: "g/dL", ref: "3,4-4,8" },
      { test: "Globulin", unit: "g/L", ref: "20-35" },
      { test: "Globulin", unit: "g/dL", ref: "2,0-3,5" },
      { test: "Sắt", unit: "µmol/L", ref: "8,1-28,6" },
      { test: "Sắt", unit: "µg/dL", ref: "45-160" },
      { test: "Ferritin", unit: "ng/mL", ref: "Nam: 30-400\nNữ: 13-150" },
      { test: "Transferrin", unit: "mg/dL", ref: "200-400" },
      { test: "TIBC", unit: "µmol/L", ref: "45-72" },
      { test: "TIBC", unit: "µg/dL", ref: "251-402" },
      { test: "Độ bão hòa transferrin", unit: "%", ref: "20-50" },
      { test: "Tỷ số A/G", unit: "Tỷ số", ref: "1,0-2,2" },
    ],
  },
  {
    title: "Sinh hóa: Nội tiết",
    rows: [
      { test: "Cortisol", unit: "nmol/L", ref: "Trước 10 giờ: 101,2-535,7\nSau 17 giờ: 79,0-477,8" },
      { test: "Cortisol", unit: "µg/dL", ref: "Trước 10 giờ: 3,7-19,4\nSau 17 giờ: 2,9-17,3" },
      {
        test: "FSH",
        unit: "IU/L",
        ref:
          "Nam: 1,5-12,4\n" +
          "Nữ - pha nang: 3,5-12,5; rụng trứng: 4,7-21,5; hoàng thể: 1,7-7,7; mãn kinh: 25,8-134,8",
      },
      {
        test: "LH",
        unit: "IU/L",
        ref:
          "Nam: 1,7-8,6\n" +
          "Nữ - pha nang: 3,4-12,6; rụng trứng: 14,0-95,6; hoàng thể: 1,0-11,4; mãn kinh: 7,7-58,5",
      },
      { test: "Prolactin", unit: "ng/mL", ref: "Nam: 4,6-21,4\nNữ: 6,0-29,9" },
      { test: "PTH", unit: "pmol/L", ref: "1,6-6,9" },
      { test: "TSH", unit: "mIU/L", ref: "0,27-4,2" },
      { test: "FT3", unit: "pmol/L", ref: "3,95-6,8" },
      { test: "FT3", unit: "pg/mL", ref: "2,57-4,43" },
      { test: "FT4", unit: "pmol/L", ref: "12-22" },
      { test: "FT4", unit: "ng/dL", ref: "0,93-1,71" },
      { test: "T3", unit: "nmol/L", ref: "1,3-3,1" },
      { test: "T3", unit: "ng/dL", ref: "85-202" },
      { test: "T4", unit: "nmol/L", ref: "66-181" },
      { test: "T4", unit: "µg/dL", ref: "5,1-14,1" },
      { test: "T-uptake", unit: "Tỷ số", ref: "0,8-1,3" },
      { test: "GH", unit: "ng/mL", ref: "Người lớn sau nhịn đói qua đêm: ≤7" },
    ],
  },
  {
    title: "Sinh hóa: Miễn dịch",
    rows: [
      { test: "IgA", unit: "mg/dL", ref: "70-400" },
      { test: "IgE", unit: "U/L", ref: "<100" },
      { test: "IgG", unit: "mg/dL", ref: "700-1.600" },
      { test: "IgM", unit: "mg/dL", ref: "40-230" },
    ],
  },
  {
    title: "Sinh hóa: Dấu ấn viêm",
    rows: [{ test: "CRP", unit: "mg/L", ref: "<5" }],
  },
  {
    title: "Khí máu động mạch",
    rows: [
      { test: "pH", unit: "-", ref: "7,35-7,45" },
      { test: "pCO₂", unit: "mmHg", ref: "35-45" },
      { test: "pO₂", unit: "mmHg", ref: "80-100" },
      { test: "HCO₃⁻", unit: "mEq/L", ref: "22-28" },
      { test: "SaO₂", unit: "%", ref: "94-100" },
      { test: "BE", unit: "mmol/L", ref: "-2 đến +2" },
      { test: "Lactate", unit: "mmol/L", ref: "0,5-2,0" },
    ],
  },
  {
    title: "Nước tiểu – 10 thông số (máy)",
    rows: [
      { test: "COLOR", unit: "-", ref: "Vàng nhạt" },
      { test: "CLARITY", unit: "-", ref: "Trong" },
      { test: "GLU", unit: "Định tính", ref: "Âm tính (bình thường: <1,7 mmol/L)" },
      { test: "BIL", unit: "Định tính", ref: "Âm tính (<3,4 µmol/L)" },
      { test: "KET", unit: "Định tính", ref: "Âm tính (<0,5 mmol/L)" },
      { test: "SG", unit: "-", ref: "1,01-1,025" },
      { test: "pH", unit: "-", ref: "4,8-7,5" },
      { test: "Alb/Cre (bán định lượng)", unit: "mg/mmol", ref: "<3,4 mg/mmol" },
      { test: "PRO", unit: "Định tính", ref: "Âm tính (<0,1 g/L)" },
      { test: "URO", unit: "Định tính", ref: "Bình thường: <17 µmol/L" },
      { test: "NIT", unit: "Định tính", ref: "Âm tính" },
      { test: "LEU", unit: "Định tính", ref: "Âm tính (<10/µL)" },
      { test: "BLOOD", unit: "Định tính", ref: "Âm tính (<5 Ery/µL)" },
    ],
  },
  {
    title: "Soi cặn nước tiểu",
    rows: [
      { test: "Hồng cầu", unit: "/HPF", ref: "0-2" },
      { test: "Bạch cầu", unit: "/HPF", ref: "0-5" },
      { test: "Tế bào biểu mô lát", unit: "/HPF", ref: "0-5" },
      { test: "Trụ hyalin", unit: "/LPF", ref: "0-2" },
      { test: "Trụ bệnh lý", unit: "Định tính", ref: "Không có" },
      { test: "Tinh thể", unit: "Định tính", ref: "Không có" },
      { test: "Vi khuẩn", unit: "Định tính", ref: "Không có" },
      { test: "Nấm men", unit: "Định tính", ref: "Không có" },
    ],
  },
  {
    title: "Dịch não tủy",
    rows: [
      { test: "Màu sắc", unit: "-", ref: "Không màu" },
      { test: "Độ trong", unit: "-", ref: "Trong" },
      { test: "Bạch cầu", unit: "tế bào/µL", ref: "0-5" },
      { test: "Hồng cầu", unit: "tế bào/µL", ref: "0" },
      { test: "Cl⁻", unit: "mmol/L", ref: "120-130" },
      { test: "Glucose", unit: "mmol/L", ref: "2,2-3,9" },
      { test: "Glucose", unit: "mg/dL", ref: "40-70" },
      { test: "Tỷ số glucose DNT/máu", unit: "Tỷ số", ref: "0,5-0,8" },
      { test: "Lactate", unit: "mmol/L", ref: "1,1-2,4" },
      { test: "Pandy", unit: "Định tính", ref: "Âm tính" },
      { test: "Protein", unit: "g/L", ref: "<0,45" },
      { test: "Protein", unit: "mg/dL", ref: "<45" },
    ],
  },
];

/** Chuẩn hoá chuỗi để tìm kiếm: bỏ dấu tiếng Việt + về chữ thường. */
export function normalizeSearch(s: string): string {
  return s
    .toLowerCase()
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .replace(/đ/g, "d");
}

/** Lọc các nhóm theo từ khoá (khớp tên xét nghiệm hoặc đơn vị). Trả về nhóm rỗng bị loại. */
export function filterGroups(groups: LabGroup[], query: string): LabGroup[] {
  const q = normalizeSearch(query.trim());
  if (!q) return groups;
  return groups
    .map((g) => ({
      ...g,
      rows: g.rows.filter(
        (r) => normalizeSearch(r.test).includes(q) || normalizeSearch(r.unit).includes(q),
      ),
    }))
    .filter((g) => g.rows.length > 0);
}
