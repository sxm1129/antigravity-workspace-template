/** MotionWeaver API Client — typed fetch wrapper for all backend endpoints. */

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "";

// ──────── Types ────────

export interface Project {
  id: string;
  title: string;
  logline: string | null;
  world_outline: string | null;
  full_script: string | null;
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

export interface StoryResponse {
  project_id: string;
  status: string;
  content?: string | null;
  scenes_count?: number | null;
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
};

// ──────── Asset API ────────

export const assetApi = {
  generateAllImages: (projectId: string) =>
    fetcher<TaskDispatchResult>("/api/assets/generate-all-images", {
      method: "POST",
      body: JSON.stringify({ project_id: projectId }),
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

  composeFinal: (projectId: string) =>
    fetcher<TaskDispatchResult>("/api/assets/compose-final", {
      method: "POST",
      body: JSON.stringify({ project_id: projectId }),
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
};

// ──────── Media URL helper ────────

export function mediaUrl(relativePath: string | null): string | null {
  if (!relativePath) return null;
  return `${API_BASE}/media/${relativePath}`;
}

