import { Navigate, Route, Routes } from "react-router-dom";
import ProtectedRoute from "./components/ProtectedRoute";
import Layout from "./components/Layout";
import LoginPage from "./pages/LoginPage";
import ExamsPage from "./pages/ExamsPage";
import SectionDetailPage from "./pages/SectionDetailPage";
import OverviewTab from "./pages/sectionTabs/OverviewTab";
import RoomsTab from "./pages/sectionTabs/RoomsTab";
import SittingsTab from "./pages/sectionTabs/SittingsTab";
import SittingDetailPage from "./pages/SittingDetailPage";
import SectionExamTab from "./pages/sectionTabs/SectionExamTab";
import CandidatesPage from "./pages/CandidatesPage";
import MonitorPage from "./pages/MonitorPage";
import ReportsPage from "./pages/ReportsPage";
import MyRoomsPage from "./pages/MyRoomsPage";
import AdminsPage from "./pages/AdminsPage";
import AuditLogPage from "./pages/AuditLogPage";
import DashboardPage from "./pages/DashboardPage";
import LicensePage from "./pages/LicensePage";
import UpdatePage from "./pages/UpdatePage";
import { useAuthStore } from "./stores/auth";

function HomeRedirect() {
  const role = useAuthStore((s) => s.admin?.role);
  const to = role === "super_admin" ? "/dashboard"
    : role === "room_proctor" ? "/my-rooms"
    : "/exams";
  return <Navigate to={to} replace />;
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route element={<ProtectedRoute />}>
        <Route element={<Layout />}>
          <Route path="/" element={<HomeRedirect />} />
          <Route path="/dashboard" element={<DashboardPage />} />
          <Route path="/exams" element={<ExamsPage />} />
          <Route path="/my-rooms" element={<MyRoomsPage />} />
          <Route path="/admins" element={<AdminsPage />} />
          <Route path="/update" element={<UpdatePage />} />
          <Route path="/audit" element={<AuditLogPage />} />
          <Route path="/license" element={<LicensePage />} />
          {/* Sitting detail (buổi) — its own layout with Đề thi / Giám sát / Báo cáo */}
          <Route path="/exams/:examId/sittings/:sittingId" element={<SittingDetailPage />}>
            <Route index element={<Navigate to="exam" replace />} />
            <Route path="exam" element={<SectionExamTab />} />
            <Route path="monitor" element={<MonitorPage />} />
            <Route path="reports" element={<ReportsPage />} />
          </Route>
          {/* Exam (kỳ thi) container dashboard */}
          <Route path="/exams/:examId" element={<SectionDetailPage />}>
            <Route index element={<Navigate to="overview" replace />} />
            <Route path="overview" element={<OverviewTab />} />
            <Route path="rooms" element={<RoomsTab />} />
            <Route path="sittings" element={<SittingsTab />} />
            <Route path="candidates" element={<CandidatesPage />} />
          </Route>
        </Route>
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
