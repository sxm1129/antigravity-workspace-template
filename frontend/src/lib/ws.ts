/** WebSocket client for real-time task progress. */

const WS_BASE = (() => {
  // Priority: explicit WS URL > API URL > derive from window (same-origin, for Docker/prod)
  const explicit = process.env.NEXT_PUBLIC_WS_URL || process.env.NEXT_PUBLIC_API_URL;
  if (explicit) {
    return explicit.replace("http://", "ws://").replace("https://", "wss://");
  }
  // In dev mode, Next.js proxy does NOT support WebSocket upgrades,
  // so we must connect directly to the backend on port 9001.
  if (typeof window !== "undefined") {
    const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
    // If running via Next.js dev on a different port, connect to backend directly
    const host = window.location.hostname;
    const port = window.location.port;
    // In production Docker (same port), use same host; in dev (port 9000), target 9001
    const backendPort = port === "9000" ? "9001" : port;
    return `${proto}//${host}:${backendPort}`;
  }
  return "ws://localhost:9001";
})();

export interface WSMessage {
  type: "scene_update" | "project_update" | "compose_progress" | "task_progress" | "pong";
  scene_id?: string;
  status?: string;
  rendered?: number;
  total?: number;
  percent?: number;
  data?: Record<string, unknown>;
}

const MAX_RECONNECT_DELAY = 30000; // 30s cap

export function connectProjectWS(
  projectId: string,
  onMessage: (msg: WSMessage) => void
): { close: () => void } {
  const url = `${WS_BASE}/ws/${projectId}`;
  let ws: WebSocket | null = null;
  let reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  let attempt = 0;
  let closed = false;

  function connect() {
    if (closed) return;

    try {
      ws = new WebSocket(url);
    } catch {
      // WebSocket constructor can throw if URL is invalid
      scheduleReconnect();
      return;
    }

    ws.onopen = () => {
      attempt = 0; // reset backoff on successful connect
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
      if (closed) return;
      scheduleReconnect();
    };

    ws.onerror = () => {
      // Silently handle — onclose will fire right after and trigger reconnect
      ws?.close();
    };
  }

  function scheduleReconnect() {
    if (closed) return;
    attempt++;
    const delay = Math.min(1000 * Math.pow(2, attempt), MAX_RECONNECT_DELAY);
    if (attempt <= 3) {
      console.log(`[WS] Reconnecting in ${delay / 1000}s (attempt ${attempt})...`);
    }
    // After 3 failed attempts, go silent to avoid console spam
    reconnectTimer = setTimeout(connect, delay);
  }

  connect();

  return {
    close: () => {
      closed = true;
      if (reconnectTimer) clearTimeout(reconnectTimer);
      ws?.close();
    },
  };
}
