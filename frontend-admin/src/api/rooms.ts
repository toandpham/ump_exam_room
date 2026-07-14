import { api } from "./client";
import { triggerDownload } from "./exams";
import type { MyRoom, Room } from "./types";

export interface RoomCreate {
  name: string;
  proctor_id?: string | null;
  capacity?: number;
  proctor_real_name?: string | null;
}
export interface RoomUpdate {
  name?: string;
  proctor_id?: string | null;
  capacity?: number;
  proctor_real_name?: string | null;
}

export interface RoomSeat {
  candidate_id: string;
  full_name: string;
  cccd: string;
  id_type?: string;     // 'cccd' | 'passport' (AD-58)
  unit?: string;
  birth_date?: string | null;
}

export const roomsApi = {
  listRooms: async (examId: string): Promise<Room[]> =>
    (await api.get(`/admin/exams/${examId}/rooms`)).data,
  createRoom: async (examId: string, body: RoomCreate): Promise<Room> =>
    (await api.post(`/admin/exams/${examId}/rooms`, body)).data,
  updateRoom: async (id: string, body: RoomUpdate): Promise<Room> =>
    (await api.patch(`/admin/rooms/${id}`, body)).data,
  removeRoom: async (id: string): Promise<void> => { await api.delete(`/admin/rooms/${id}`); },

  roomSeating: async (roomId: string): Promise<RoomSeat[]> =>
    (await api.get(`/admin/rooms/${roomId}/seating`)).data,
  // Giám thị (hoặc chủ tịch) thêm 1 thí sinh lẻ vào phòng (AD-54).
  addRoomCandidate: async (roomId: string, body: {
    cccd: string; full_name: string; birth_date: string; unit: string;
    category: string; attempt_number: number; graduation_year?: number | null; major?: string | null;
  }): Promise<RoomSeat> =>
    (await api.post(`/admin/rooms/${roomId}/candidates`, body)).data,
  seatingXlsx: async (examId: string) => {
    const res = await api.get(`/admin/exams/${examId}/seating.xlsx`, { responseType: "blob" });
    triggerDownload(res.data, `seating_${examId}.xlsx`);
  },
  seatingPdf: async (examId: string) => {
    const res = await api.get(`/admin/exams/${examId}/seating.pdf`, { responseType: "blob" });
    triggerDownload(res.data, `seating_${examId}.pdf`);
  },

  myRooms: async (): Promise<MyRoom[]> => (await api.get("/admin/my-rooms")).data,
};
