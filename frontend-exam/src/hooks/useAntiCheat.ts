import { useEffect, useState } from "react";

const BLOCKED_KEYS = (e: KeyboardEvent) =>
  e.key === "F12" ||
  (e.ctrlKey && e.shiftKey && ["I", "J", "C"].includes(e.key.toUpperCase())) ||
  (e.ctrlKey && ["U", "S"].includes(e.key.toUpperCase()));

/** Basic anti-cheat: block devtools/context/copy, count tab switches. */
export function useAntiCheat(onTabChange: (count: number) => void) {
  const [tabCount, setTabCount] = useState(0);

  useEffect(() => {
    let count = 0;
    const noop = (e: Event) => e.preventDefault();
    const onKey = (e: KeyboardEvent) => { if (BLOCKED_KEYS(e)) e.preventDefault(); };
    const onVisibility = () => {
      if (document.hidden) {
        count += 1;
        setTabCount(count);
        onTabChange(count);
      }
    };
    document.addEventListener("contextmenu", noop);
    document.addEventListener("copy", noop);
    document.addEventListener("cut", noop);
    document.addEventListener("paste", noop);
    document.addEventListener("keydown", onKey);
    document.addEventListener("visibilitychange", onVisibility);
    return () => {
      document.removeEventListener("contextmenu", noop);
      document.removeEventListener("copy", noop);
      document.removeEventListener("cut", noop);
      document.removeEventListener("paste", noop);
      document.removeEventListener("keydown", onKey);
      document.removeEventListener("visibilitychange", onVisibility);
    };
  }, [onTabChange]);

  return { tabCount };
}
