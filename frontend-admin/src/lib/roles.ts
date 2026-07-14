export type Role = "super_admin" | "proctor" | "room_proctor";

const ROLE_LABELS: Record<string, string> = {
  super_admin: "Quản trị",
  proctor: "Chủ tịch hội đồng thi",
  room_proctor: "Giám thị",
};

/** Vietnamese label for an admin role (AD-47). */
export function roleLabel(role: string | null | undefined): string {
  if (!role) return "";
  return ROLE_LABELS[role] ?? role;
}
