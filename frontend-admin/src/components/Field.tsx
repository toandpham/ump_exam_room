import type { ReactNode } from "react";

/** Label + control wrapper used across the admin forms. */
export default function Field({ label, children, className }: {
  label: string;
  children: ReactNode;
  className?: string;
}) {
  return (
    <div className={className}>
      <label className="block text-xs font-semibold text-slate-600 mb-1">{label}</label>
      {children}
    </div>
  );
}
