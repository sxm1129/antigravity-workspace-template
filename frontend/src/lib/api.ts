/** MotionWeaver API Client — typed fetch wrapper for all backend endpoints. */

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "";

// ──────── Types ────────

export interface Project {
  id: string;
  title: string;
  logline: string | null;
  world_outline: string | null;
  full_script: string | null;
  final_video_path: string | null;
  style_preset: string | null;
  status: string;
  created_at: string;
  updated_at: string;
}

export interface Character {
  id: string;
  project_id: string;
  name: string;
  appearance_prompt: string | null;
  nano_identity_refs: string[];
}

export interface Scene {
  id: string;
  project_id: string;
  episode_id: string | null;
  sequence_order: number;
  dialogue_text: string | null;
  prompt_visual: string | null;
  prompt_motion: string | null;
  sfx_text: string | null;
  local_audio_path: string | null;
  local_image_path: string | null;
  local_video_path: string | null;
  status: string;
}

export interface Episode {
  id: string;
  project_id: string;
  episode_number: number;
  title: string;
  synopsis: string | null;
  full_script: string | null;
  final_video_path: string | null;
  status: string;
  scenes_count: number | null;
  created_at: string;
  updated_at: string;
}

export interface StoryResponse {
  project_id: string;
  status: string;
  content?: string | null;
  scenes_count?: number | null;
  episodes_count?: number | null;
}

export interface TaskDispatchResult {
  dispatched?: number;
  tasks?: { scene_id: string; task: string; task_id: string }[];
  scene_id?: string;
  task_id?: string;
  status?: string;
  project_id?: string;
}

// ──────── Helpers ────────

async function fetcher<T>(path: string, init?: RequestInit): Promise<T> {
  const url = `${API_BASE}${path}`;
  const res = await fetch(url, {
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || `API Error ${res.status}`);
  }
  if (res.status === 204) return undefined as T;
  return res.json();
}

// ──────── Project API ────────

export const projectApi = {
  list: () => fetcher<Project[]>("/api/projects/"),

  create: (data: { title: string; logline?: string }) =>
    fetcher<Project>("/api/projects/", { method: "POST", body: JSON.stringify(data) }),

  get: (id: string) => fetcher<Project>(`/api/projects/${id}`),

  update: (id: string, data: Partial<Project>) =>
    fetcher<Project>(`/api/projects/${id}`, {
      method: "PATCH",
      body: JSON.stringify(data),
    }),

  advanceStatus: (id: string, targetStatus: string) =>
    fetcher<Project>(`/api/projects/${id}/advance-status`, {
      method: "POST",
      body: JSON.stringify({ target_status: targetStatus }),
    }),

  delete: (id: string) =>
    fetcher<void>(`/api/projects/${id}`, { method: "DELETE" }),
};

// ──────── Character API ────────

export const characterApi = {
  list: (projectId: string) =>
    fetcher<Character[]>(`/api/projects/${projectId}/characters/`),

  create: (projectId: string, data: { name: string; appearance_prompt?: string }) =>
    fetcher<Character>(`/api/projects/${projectId}/characters/`, {
      method: "POST",
      body: JSON.stringify(data),
    }),

  update: (projectId: string, id: string, data: Partial<Character>) =>
    fetcher<Character>(`/api/projects/${projectId}/characters/${id}`, {
      method: "PATCH",
      body: JSON.stringify(data),
    }),

  delete: (projectId: string, id: string) =>
    fetcher<void>(`/api/projects/${projectId}/characters/${id}`, { method: "DELETE" }),
};

// ──────── Scene API ────────

export const sceneApi = {
  list: (projectId: string) =>
    fetcher<Scene[]>(`/api/projects/${projectId}/scenes/`),

  create: (projectId: string, data: Partial<Scene>) =>
    fetcher<Scene>(`/api/projects/${projectId}/scenes/`, {
      method: "POST",
      body: JSON.stringify(data),
    }),

  update: (projectId: string, id: string, data: Partial<Scene>) =>
    fetcher<Scene>(`/api/projects/${projectId}/scenes/${id}`, {
      method: "PATCH",
      body: JSON.stringify(data),
    }),

  reorder: (projectId: string, sceneIds: string[]) =>
    fetcher<Scene[]>(`/api/projects/${projectId}/scenes/reorder`, {
      method: "POST",
      body: JSON.stringify(sceneIds),
    }),

  delete: (projectId: string, id: string) =>
    fetcher<void>(`/api/projects/${projectId}/scenes/${id}`, { method: "DELETE" }),
};

// ──────── Story AI API ────────

export const storyApi = {
  generateOutline: (projectId: string) =>
    fetcher<StoryResponse>("/api/story/generate-outline", {
      method: "POST",
      body: JSON.stringify({ project_id: projectId }),
    }),

  generateScript: (projectId: string) =>
    fetcher<StoryResponse>("/api/story/generate-script", {
      method: "POST",
      body: JSON.stringify({ project_id: projectId }),
    }),

  parseScenes: (projectId: string) =>
    fetcher<StoryResponse>("/api/story/parse-scenes", {
      method: "POST",
      body: JSON.stringify({ project_id: projectId }),
    }),

  extractAndGenerate: (projectId: string) =>
    fetcher<StoryResponse>("/api/story/extract-and-generate", {
      method: "POST",
      body: JSON.stringify({ project_id: projectId }),
    }),

  parseEpisodeScenes: (episodeId: string) =>
    fetcher<StoryResponse>("/api/story/parse-episode-scenes", {
      method: "POST",
      body: JSON.stringify({ episode_id: episodeId }),
    }),

  regenerateOutline: (projectId: string, customPrompt?: string) =>
    fetcher<StoryResponse>("/api/story/regenerate-outline", {
      method: "POST",
      body: JSON.stringify({ project_id: projectId, custom_prompt: customPrompt || null }),
    }),
};

// ──────── Pipeline SSE Types ────────

export interface PipelineEvent {
  event_type: "step_start" | "step_complete" | "pipeline_complete" | "error";
  step?: string;       // intent | world | plot | assemble
  label?: string;      // 用户可读的步骤名
  index?: number;      // 0-3
  total?: number;      // 4
  result?: Record<string, unknown>;  // JSON result of a step
  outline?: string;    // final markdown
  error?: string;
}

/**
 * Stream pipeline events via SSE (POST-based fetch + ReadableStream).
 * Calls onEvent for each parsed event, returns when stream ends.
 */
export async function generateOutlineStream(
  projectId: string,
  onEvent: (event: PipelineEvent) => void,
): Promise<void> {
  const res = await fetch(`${API_BASE}/api/story/generate-outline-stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ project_id: projectId }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || `HTTP ${res.status}`);
  }
  await _consumeSSE(res, onEvent);
}

/**
 * Continue pipeline from a specific step with modified results.
 */
export async function continuePipeline(
  projectId: string,
  startFrom: number,
  intentResult?: Record<string, unknown> | null,
  worldResult?: Record<string, unknown> | null,
  plotResult?: Record<string, unknown> | null,
  onEvent?: (event: PipelineEvent) => void,
): Promise<void> {
  const res = await fetch(`${API_BASE}/api/story/continue-pipeline`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      project_id: projectId,
      start_from: startFrom,
      intent_result: intentResult || null,
      world_result: worldResult || null,
      plot_result: plotResult || null,
    }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || `HTTP ${res.status}`);
  }
  if (onEvent) await _consumeSSE(res, onEvent);
}

/** Parse SSE text/event-stream from a fetch Response. */
async function _consumeSSE(
  res: Response,
  onEvent: (event: PipelineEvent) => void,
): Promise<void> {
  const reader = res.body?.getReader();
  if (!reader) return;

  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) {
      // Flush any remaining bytes held by the streaming decoder
      buffer += decoder.decode();
      break;
    }
    buffer += decoder.decode(value, { stream: true });

    // Parse SSE frames: "event: ...\ndata: ...\n\n"
    const frames = buffer.split("\n\n");
    buffer = frames.pop() || "";  // keep incomplete frame

    for (const frame of frames) {
      if (!frame.trim()) continue;
      const dataLine = frame.split("\n").find((l) => l.startsWith("data: "));
      if (dataLine) {
        try {
          const event = JSON.parse(dataLine.slice(6)) as PipelineEvent;
          onEvent(event);
        } catch {
          // skip malformed frames
        }
      }
    }
  }

  // Process any remaining complete frames after stream end
  if (buffer.trim()) {
    const dataLine = buffer.split("\n").find((l) => l.startsWith("data: "));
    if (dataLine) {
      try {
        const event = JSON.parse(dataLine.slice(6)) as PipelineEvent;
        onEvent(event);
      } catch {
        // skip malformed trailing data
      }
    }
  }
}


// ──────── Episode API ────────

export const episodeApi = {
  list: (projectId: string) =>
    fetcher<Episode[]>(`/api/projects/${projectId}/episodes`),

  get: (episodeId: string) =>
    fetcher<Episode>(`/api/episodes/${episodeId}`),

  update: (episodeId: string, data: Partial<Episode>) =>
    fetcher<Episode>(`/api/episodes/${episodeId}`, {
      method: "PATCH",
      body: JSON.stringify(data),
    }),

  advanceStatus: (episodeId: string, targetStatus: string) =>
    fetcher<Episode>(`/api/episodes/${episodeId}/advance-status`, {
      method: "POST",
      body: JSON.stringify({ target_status: targetStatus }),
    }),

  listScenes: (episodeId: string) =>
    fetcher<Scene[]>(`/api/episodes/${episodeId}/scenes`),

  resetStatus: (episodeId: string) =>
    fetcher<Episode>(`/api/episodes/${episodeId}/reset-status`, {
      method: "POST",
    }),
};

// ──────── Asset API ────────

export const assetApi = {
  generateAllImages: (projectId: string, episodeId?: string) =>
    fetcher<TaskDispatchResult>("/api/assets/generate-all-images", {
      method: "POST",
      body: JSON.stringify({ project_id: projectId, episode_id: episodeId || null }),
    }),

  regenerateImage: (sceneId: string) =>
    fetcher<TaskDispatchResult>("/api/assets/regenerate-image", {
      method: "POST",
      body: JSON.stringify({ scene_id: sceneId }),
    }),

  approveScene: (sceneId: string) =>
    fetcher<TaskDispatchResult>("/api/assets/approve-scene", {
      method: "POST",
      body: JSON.stringify({ scene_id: sceneId }),
    }),

  batchApprove: (sceneIds: string[]) =>
    fetcher<{ approved: number }>("/api/assets/batch-approve", {
      method: "POST",
      body: JSON.stringify({ scene_ids: sceneIds }),
    }),

  composeFinal: (projectId: string, episodeId?: string) =>
    fetcher<TaskDispatchResult>("/api/assets/compose-final", {
      method: "POST",
      body: JSON.stringify({ project_id: projectId, episode_id: episodeId || null }),
    }),

  retryVideoGen: (sceneIds: string[]) =>
    fetcher<{ retried: number }>("/api/assets/retry-video-gen", {
      method: "POST",
      body: JSON.stringify({ scene_ids: sceneIds }),
    }),
};

// ──────── Quick Draft API ────────

export interface DraftProgress {
  step: string;
  current: number;
  total: number;
  desc: string;
}

export const quickDraftApi = {
  start: (data: { title: string; logline: string; style?: string }) =>
    fetcher<{ project_id: string; task_id: string }>("/api/quick-draft/", {
      method: "POST",
      body: JSON.stringify(data),
    }),

  progress: (projectId: string) =>
    fetcher<{ project_id: string; status: string; progress: DraftProgress | null }>(
      `/api/quick-draft/${projectId}/progress`
    ),
};

// ──────── Styles API ────────

export interface StylePreset {
  id: string;
  name: string;
  description: string;
  templates: string[];
}

export const styleApi = {
  list: () => fetcher<{ styles: StylePreset[] }>("/api/styles/"),

  getPromptTemplate: (styleId: string, templateName: string) =>
    fetcher<{ style: string; template: string; content: string }>(
      `/api/styles/${styleId}/prompts/${templateName}`
    ),
};

// ──────── System API ────────

export interface CeleryStatus {
  status: "ok" | "offline" | "error";
  workers: { name: string; status: string }[];
  count: number;
  active_tasks?: number;
  reserved_tasks?: number;
  message?: string;
}

export interface CeleryStartResult {
  status: "started" | "already_running" | "error";
  message: string;
  pid?: number;
}

export const systemApi = {
  celeryStatus: () =>
    fetcher<unknown>("/api/system/status").then((r) => {
      const celery = (r as Record<string, unknown>).celery as CeleryStatus | undefined;
      return celery ?? { status: "error" as const, workers: [], count: 0 };
    }),

  celeryPing: () =>
    fetcher<{ online: boolean; worker_count: number }>("/api/system/celery/ping").then(
      (r) => r.online
    ),

  celeryStart: () =>
    fetcher<CeleryStartResult>("/api/system/celery/start", { method: "POST" }),
};

// ──────── Media URL helper ────────

export function mediaUrl(relativePath: string | null): string | null {
  if (!relativePath) return null;
  return `${API_BASE}/media/${relativePath}`;
}

