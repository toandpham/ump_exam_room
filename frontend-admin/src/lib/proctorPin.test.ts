import { describe, it, expect, beforeEach } from "vitest";
import { loadPin, savePin, clearPin } from "./proctorPin";

const info = { pin: "482913", username: "giamthi3", full_name: "Giám thị 3" };

beforeEach(() => localStorage.clear());

describe("proctorPin", () => {
  it("giữ được mã PIN sau khi rời trang rồi quay lại", () => {
    // Lỗi hiện trường 30-07: PIN nằm trong state của component nên chuyển tab là
    // mất, chủ tịch phải đặt lại mã mới — giám thị đang cầm mã cũ thì hỏng.
    savePin("room-1", info);
    expect(loadPin("room-1")).toEqual(info);
  });

  it("mỗi phòng một mã riêng, không lẫn nhau", () => {
    savePin("room-1", info);
    savePin("room-2", { ...info, pin: "111222", username: "giamthi7" });
    expect(loadPin("room-1")?.pin).toBe("482913");
    expect(loadPin("room-2")?.pin).toBe("111222");
  });

  it("phòng chưa đặt mã thì trả null", () => {
    expect(loadPin("room-9")).toBeNull();
  });

  it("xoá được (đổi giám thị khác thì mã cũ không còn ý nghĩa)", () => {
    savePin("room-1", info);
    clearPin("room-1");
    expect(loadPin("room-1")).toBeNull();
  });

  it("dữ liệu hỏng trong localStorage KHÔNG làm vỡ trang", () => {
    localStorage.setItem("proctor_pin_room-1", "{{{ không phải JSON");
    expect(loadPin("room-1")).toBeNull();
  });
});
