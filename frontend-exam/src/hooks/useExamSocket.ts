import { useCallback, useEffect, useRef } from "react";
import { useStore } from "../store";

export interface WsEvent {
  scope: string;
  type: string;
  data: Record<string, unknown>;
}

/** Candidate WebSocket: receive control events, send tab-change reports. */
export function useExamSocket(sessionId: string | null, onEvent: (e: WsEvent) => void) {
  const wsRef = useRef<WebSocket | null>(null);
  const cbRef = useRef(onEvent);
  cbRef.current = onEvent;

  useEffect(() => {
    if (!sessionId) return;
    const token = useStore.getState().token;
    let retry: ReturnType<typeof setTimeout>;
    let closed = false;

    const connect = () => {
      const proto = window.location.protocol === "https:" ? "wss" : "ws";
      const ws = new WebSocket(`${proto}://${window.location.host}/ws/exam/${sessionId}?token=${token}`);
      wsRef.current = ws;
      ws.onmessage = (m) => { try { cbRef.current(JSON.parse(m.data)); } catch { /* ignore */ } };
      ws.onclose = () => { if (!closed) retry = setTimeout(connect, 2000); };
    };
    connect();
    return () => { closed = true; clearTimeout(retry); wsRef.current?.close(); };
  }, [sessionId]);

  const send = useCallback((obj: unknown) => {
    try {
      if (wsRef.current?.readyState === WebSocket.OPEN) wsRef.current.send(JSON.stringify(obj));
    } catch { /* ignore */ }
  }, []);
  return { send };
}
