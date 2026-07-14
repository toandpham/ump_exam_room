import { create } from "zustand";
import type { Role } from "../lib/roles";

export interface Admin {
  id: string;
  username: string;
  full_name: string | null;
  role: Role;
}

interface AuthState {
  token: string | null;
  admin: Admin | null;
  setToken: (token: string) => void;
  setAdmin: (admin: Admin) => void;
  clear: () => void;
}

export const useAuthStore = create<AuthState>((set) => ({
  token: localStorage.getItem("admin_token"),
  admin: null,
  setToken: (token) => {
    localStorage.setItem("admin_token", token);
    set({ token });
  },
  setAdmin: (admin) => set({ admin }),
  clear: () => {
    localStorage.removeItem("admin_token");
    set({ token: null, admin: null });
  },
}));
