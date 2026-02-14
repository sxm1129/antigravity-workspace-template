/** WebSocket client for real-time task progress. */

const WS_BASE =
  (process.env.NEXT_PUBLIC_WS_URL ||
  (typeof window !== "undefined"
    ? `${window.location.protocol === "https:" ? "wss:" : "ws:"}//${window.location.host}`
    : "ws://localhost:8000"))
  .replace("http://", "ws://")
  .replace("https://", "wss://");

export interface WSMessage {
  type: "scene_update" | "project_update" | "task_progress" | "pong";
  scene_id?: string;
  status?: string;
  data?: Record<string, unknown>;
}

export function connectProjectWS(
  projectId: string,
  onMessage: (msg: WSMessage) => void
): { close: () => void } {
  const url = `${WS_BASE}/ws/${projectId}`;
  let ws: WebSocket | null = null;
  let reconnectTimer: ReturnType<typeof setTimeout> | null = null;

  function connect() {
    ws = new WebSocket(url);

    ws.onopen = () => {
      console.log("[WS] Connected:", projectId);
    };

    ws.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data) as WSMessage;
        onMessage(msg);
      } catch {
        console.warn("[WS] Invalid message:", event.data);
      }
    };

    ws.onclose = () => {
      console.log("[WS] Disconnected, reconnecting in 3s...");
      reconnectTimer = setTimeout(connect, 3000);
    };

    ws.onerror = (err) => {
      console.error("[WS] Error:", err);
      ws?.close();
    };
  }

  connect();

  return {
    close: () => {
      if (reconnectTimer) clearTimeout(reconnectTimer);
      ws?.close();
    },
  };
}
