import { useRef, type ReactNode } from "react";
import { X } from "lucide-react";

interface ModalProps {
  open: boolean;
  title: string;
  onClose: () => void;
  children: ReactNode;
  width?: string;
}

export default function Modal({ open, title, onClose, children, width = "max-w-lg" }: ModalProps) {
  // Only close on a genuine backdrop click — i.e. the press STARTED and ENDED on
  // the backdrop itself. Without this, drag-selecting text inside an input and
  // releasing past the edge fires a click on the backdrop and closes the modal.
  const downOnBackdrop = useRef(false);
  if (!open) return null;
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
      onMouseDown={(e) => { downOnBackdrop.current = e.target === e.currentTarget; }}
      onClick={(e) => { if (downOnBackdrop.current && e.target === e.currentTarget) onClose(); }}
    >
      <div className={`bg-white rounded-xl shadow-xl w-full ${width} max-h-[90vh] overflow-auto`}>
        <div className="flex items-center justify-between px-5 py-3 border-b border-slate-200 sticky top-0 bg-white">
          <h2 className="font-semibold text-slate-800">{title}</h2>
          <button onClick={onClose} className="text-slate-400 hover:text-slate-600">
            <X size={20} />
          </button>
        </div>
        <div className="p-5">{children}</div>
      </div>
    </div>
  );
}
