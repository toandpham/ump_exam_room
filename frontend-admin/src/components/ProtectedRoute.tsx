import { Navigate, Outlet } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { authApi } from "../api/auth";
import { useAuthStore } from "../stores/auth";

export default function ProtectedRoute() {
  const token = useAuthStore((s) => s.token);
  const setAdmin = useAuthStore((s) => s.setAdmin);

  const { isLoading, isError } = useQuery({
    queryKey: ["me"],
    enabled: !!token,
    queryFn: async () => {
      const data = await authApi.me();
      setAdmin(data);
      return data;
    },
  });

  if (!token) return <Navigate to="/login" replace />;
  if (isLoading) {
    return <div className="min-h-screen flex items-center justify-center text-slate-500">Đang tải…</div>;
  }
  if (isError) return <Navigate to="/login" replace />;
  return <Outlet />;
}
