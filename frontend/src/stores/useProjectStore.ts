/** Zustand store — global project state management. */

import { create } from "zustand";
import {
  type Project,
  type Scene,
  type Character,
  type Episode,
  type PipelineEvent,
  projectApi,
  sceneApi,
  characterApi,
  storyApi,
  assetApi,
  episodeApi,
  generateOutlineStream as apiGenerateOutlineStream,
  continuePipeline as apiContinuePipeline,
} from "@/lib/api";

interface ProjectStore {
  // ── State ──
  projects: Project[];
  currentProject: Project | null;
  scenes: Scene[];
  characters: Character[];
  episodes: Episode[];
  loading: boolean;
  error: string | null;

  // ── Pipeline state ──
  pipelineActive: boolean;
  pipelineCurrentStep: number;  // -1 = not started, 0-3 = running
  pipelineSteps: { key: string; label: string; status: "pending" | "running" | "done" }[];
  pipelineResults: Record<string, Record<string, unknown>>;  // step key -> result JSON

  // ── Projects ──
  fetchProjects: () => Promise<void>;
  createProject: (title: string, logline?: string) => Promise<Project>;
  fetchProject: (id: string) => Promise<void>;
  deleteProject: (id: string) => Promise<void>;

  // ── Scenes ──
  fetchScenes: (projectId: string) => Promise<void>;
  reorderScenes: (projectId: string, sceneIds: string[]) => Promise<void>;

  // ── Characters ──
  fetchCharacters: (projectId: string) => Promise<void>;
  createCharacter: (projectId: string, name: string, prompt?: string) => Promise<void>;

  // ── Episodes ──
  fetchEpisodes: (projectId: string) => Promise<void>;
  extractAndGenerate: (projectId: string) => Promise<void>;
  parseEpisodeScenes: (episodeId: string) => Promise<void>;

  // ── Story AI ──
  generateOutline: (projectId: string) => Promise<void>;
  generateOutlineStream: (projectId: string) => Promise<void>;
  continuePipelineFrom: (projectId: string, startFrom: number) => Promise<void>;
  resetPipeline: () => void;
  updatePipelineResult: (step: string, result: Record<string, unknown>) => void;
  regenerateOutline: (projectId: string, customPrompt?: string) => Promise<void>;
  generateScript: (projectId: string) => Promise<void>;
  parseScenes: (projectId: string) => Promise<void>;

  // ── Assets ──
  generateAllImages: (projectId: string) => Promise<void>;
  approveScene: (sceneId: string) => Promise<void>;
  regenerateImage: (sceneId: string) => Promise<void>;
  composeFinal: (projectId: string) => Promise<void>;

  // ── Content ──
  saveProjectContent: (projectId: string, data: { world_outline?: string; full_script?: string }) => Promise<void>;
  rollbackToWriter: (projectId: string) => Promise<void>;

  // ── Helpers ──
  setError: (err: string | null) => void;
  updateSceneLocally: (sceneId: string, patch: Partial<Scene>) => void;
  refreshCurrentProject: () => Promise<void>;
  clearCurrentProject: () => void;
}

/** Shared SSE event handler — used by both generateOutlineStream and continuePipelineFrom */
function _handlePipelineEvent(
  event: PipelineEvent,
  get: () => ProjectStore,
  set: (partial: Partial<ProjectStore> | ((state: ProjectStore) => Partial<ProjectStore>)) => void,
) {
  const state = get();
  if (event.event_type === "step_start" && event.step) {
    const steps = state.pipelineSteps.map((s) =>
      s.key === event.step ? { ...s, status: "running" as const } : s
    );
    set({ pipelineSteps: steps, pipelineCurrentStep: event.index ?? -1 });
  } else if (event.event_type === "step_complete" && event.step && event.result) {
    const steps = state.pipelineSteps.map((s) =>
      s.key === event.step ? { ...s, status: "done" as const } : s
    );
    set({
      pipelineSteps: steps,
      pipelineResults: { ...state.pipelineResults, [event.step]: event.result },
    });
  } else if (event.event_type === "pipeline_complete") {
    set({ pipelineActive: false, pipelineCurrentStep: 4 });
  } else if (event.event_type === "error") {
    set({ error: event.error || "Pipeline error", pipelineActive: false });
  }
}

export const useProjectStore = create<ProjectStore>((set, get) => ({
  projects: [],
  currentProject: null,
  scenes: [],
  characters: [],
  episodes: [],
  loading: false,
  error: null,

  pipelineActive: false,
  pipelineCurrentStep: -1,
  pipelineSteps: [
    { key: "intent", label: "意图识别", status: "pending" },
    { key: "world", label: "世界观 & 角色构建", status: "pending" },
    { key: "plot", label: "剧情架构", status: "pending" },
    { key: "assemble", label: "组装大纲", status: "pending" },
  ],
  pipelineResults: {},

  setError: (err) => set({ error: err }),

  // ── Projects ──

  fetchProjects: async () => {
    set({ loading: true, error: null });
    try {
      const projects = await projectApi.list();
      set({ projects, loading: false });
    } catch (e: unknown) {
      set({ error: (e as Error).message, loading: false });
    }
  },

  createProject: async (title, logline) => {
    set({ loading: true, error: null });
    try {
      const project = await projectApi.create({ title, logline });
      set((s) => ({ projects: [project, ...s.projects], loading: false }));
      return project;
    } catch (e: unknown) {
      set({ error: (e as Error).message, loading: false });
      throw e;
    }
  },

  fetchProject: async (id) => {
    set({ loading: true, error: null, currentProject: null, scenes: [], characters: [], episodes: [] });
    try {
      const project = await projectApi.get(id);
      set({ currentProject: project, loading: false });
      // Also fetch scenes, characters, and episodes
      const scenes = await sceneApi.list(id);
      const characters = await characterApi.list(id);
      const episodes = await episodeApi.list(id);
      set({ scenes, characters, episodes });
    } catch (e: unknown) {
      set({ error: (e as Error).message, loading: false });
    }
  },

  deleteProject: async (id) => {
    try {
      await projectApi.delete(id);
      set((s) => ({ projects: s.projects.filter((p) => p.id !== id) }));
    } catch (e: unknown) {
      set({ error: (e as Error).message });
    }
  },

  // ── Scenes ──

  fetchScenes: async (projectId) => {
    try {
      const scenes = await sceneApi.list(projectId);
      set({ scenes });
    } catch (e: unknown) {
      set({ error: (e as Error).message });
    }
  },

  reorderScenes: async (projectId, sceneIds) => {
    try {
      const scenes = await sceneApi.reorder(projectId, sceneIds);
      set({ scenes });
    } catch (e: unknown) {
      set({ error: (e as Error).message });
    }
  },

  // ── Characters ──

  fetchCharacters: async (projectId) => {
    try {
      const characters = await characterApi.list(projectId);
      set({ characters });
    } catch (e: unknown) {
      set({ error: (e as Error).message });
    }
  },

  createCharacter: async (projectId, name, prompt) => {
    try {
      const char = await characterApi.create(projectId, {
        name,
        appearance_prompt: prompt,
      });
      set((s) => ({ characters: [...s.characters, char] }));
    } catch (e: unknown) {
      set({ error: (e as Error).message });
    }
  },

  // ── Story AI ──

  generateOutline: async (projectId) => {
    set({ loading: true, error: null });
    try {
      const res = await storyApi.generateOutline(projectId);
      const project = await projectApi.get(projectId);
      set({ currentProject: project, loading: false });
    } catch (e: unknown) {
      set({ error: (e as Error).message, loading: false });
    }
  },

  generateOutlineStream: async (projectId) => {
    const freshSteps = [
      { key: "intent", label: "意图识别", status: "pending" as const },
      { key: "world", label: "世界观 & 角色构建", status: "pending" as const },
      { key: "plot", label: "剧情架构", status: "pending" as const },
      { key: "assemble", label: "组装大纲", status: "pending" as const },
    ];
    set({ loading: true, error: null, pipelineActive: true, pipelineCurrentStep: -1, pipelineSteps: freshSteps, pipelineResults: {} });
    try {
      await apiGenerateOutlineStream(projectId, (event: PipelineEvent) => _handlePipelineEvent(event, get, set));
      // Refresh project from DB
      const project = await projectApi.get(projectId);
      set({ currentProject: project, loading: false });
    } catch (e: unknown) {
      set({ error: (e as Error).message, loading: false, pipelineActive: false });
    }
  },

  continuePipelineFrom: async (projectId, startFrom) => {
    const state = get();
    // Reset steps from startFrom onwards to pending
    const steps = state.pipelineSteps.map((s, i) =>
      i >= startFrom ? { ...s, status: "pending" as const } : s
    );
    set({ loading: true, error: null, pipelineActive: true, pipelineSteps: steps });
    try {
      await apiContinuePipeline(
        projectId, startFrom,
        state.pipelineResults.intent as Record<string, unknown> | undefined,
        state.pipelineResults.world as Record<string, unknown> | undefined,
        state.pipelineResults.plot as Record<string, unknown> | undefined,
        (event: PipelineEvent) => _handlePipelineEvent(event, get, set),
      );
      const project = await projectApi.get(projectId);
      set({ currentProject: project, loading: false });
    } catch (e: unknown) {
      set({ error: (e as Error).message, loading: false, pipelineActive: false });
    }
  },

  resetPipeline: () => {
    set({
      pipelineActive: false,
      pipelineCurrentStep: -1,
      pipelineSteps: [
        { key: "intent", label: "意图识别", status: "pending" },
        { key: "world", label: "世界观 & 角色构建", status: "pending" },
        { key: "plot", label: "剧情架构", status: "pending" },
        { key: "assemble", label: "组装大纲", status: "pending" },
      ],
      pipelineResults: {},
    });
  },

  updatePipelineResult: (step, result) => {
    const state = get();
    set({ pipelineResults: { ...state.pipelineResults, [step]: result } });
  },

  regenerateOutline: async (projectId, customPrompt) => {
    set({ loading: true, error: null });
    try {
      await storyApi.regenerateOutline(projectId, customPrompt);
      const project = await projectApi.get(projectId);
      set({ currentProject: project, loading: false });
    } catch (e: unknown) {
      set({ error: (e as Error).message, loading: false });
    }
  },

  generateScript: async (projectId) => {
    set({ loading: true, error: null });
    try {
      await storyApi.generateScript(projectId);
      const project = await projectApi.get(projectId);
      set({ currentProject: project, loading: false });
    } catch (e: unknown) {
      set({ error: (e as Error).message, loading: false });
    }
  },

  parseScenes: async (projectId) => {
    set({ loading: true, error: null });
    try {
      await storyApi.parseScenes(projectId);
      const project = await projectApi.get(projectId);
      const scenes = await sceneApi.list(projectId);
      set({ currentProject: project, scenes, loading: false });
    } catch (e: unknown) {
      set({ error: (e as Error).message, loading: false });
    }
  },

  // ── Episodes ──

  fetchEpisodes: async (projectId) => {
    try {
      const episodes = await episodeApi.list(projectId);
      set({ episodes });
    } catch (e: unknown) {
      set({ error: (e as Error).message });
    }
  },

  extractAndGenerate: async (projectId) => {
    set({ loading: true, error: null });
    try {
      await storyApi.extractAndGenerate(projectId);
      const project = await projectApi.get(projectId);
      const episodes = await episodeApi.list(projectId);
      set({ currentProject: project, episodes, loading: false });
    } catch (e: unknown) {
      set({ error: (e as Error).message, loading: false });
    }
  },

  parseEpisodeScenes: async (episodeId) => {
    set({ loading: true, error: null });
    try {
      await storyApi.parseEpisodeScenes(episodeId);
      // Refresh episode
      const episode = await episodeApi.get(episodeId);
      set((s) => ({
        episodes: s.episodes.map((ep) => (ep.id === episodeId ? episode : ep)),
        loading: false,
      }));
    } catch (e: unknown) {
      set({ error: (e as Error).message, loading: false });
    }
  },

  // ── Assets ──

  generateAllImages: async (projectId) => {
    set({ loading: true, error: null });
    try {
      await assetApi.generateAllImages(projectId);
      const project = await projectApi.get(projectId);
      set({ currentProject: project, loading: false });
    } catch (e: unknown) {
      set({ error: (e as Error).message, loading: false });
    }
  },

  approveScene: async (sceneId) => {
    try {
      await assetApi.approveScene(sceneId);
      // Refresh scenes
      const project = get().currentProject;
      if (project) {
        const scenes = await sceneApi.list(project.id);
        set({ scenes });
      }
    } catch (e: unknown) {
      set({ error: (e as Error).message });
    }
  },

  composeFinal: async (projectId) => {
    set({ loading: true, error: null });
    try {
      await assetApi.composeFinal(projectId);
      // Poll until project status becomes COMPLETED (or timeout)
      const maxAttempts = 150; // 5 minutes (2s intervals)
      for (let i = 0; i < maxAttempts; i++) {
        await new Promise((r) => setTimeout(r, 2000));
        const project = await projectApi.get(projectId);
        set({ currentProject: project });
        if (project.status === "COMPLETED") {
          set({ loading: false });
          return;
        }
        if (project.status !== "COMPOSING") {
          // Unexpected status change
          set({ loading: false });
          return;
        }
      }
      set({ loading: false, error: "合成超时，请检查后台日志" });
    } catch (e: unknown) {
      set({ error: (e as Error).message, loading: false });
    }
  },

  // ── Content ──

  saveProjectContent: async (projectId, data) => {
    try {
      await projectApi.update(projectId, data);
    } catch (e: unknown) {
      set({ error: (e as Error).message });
    }
  },

  rollbackToWriter: async (projectId) => {
    set({ loading: true, error: null });
    try {
      const project = await projectApi.advanceStatus(projectId, "OUTLINE_REVIEW");
      const episodes = await episodeApi.list(projectId);
      set({ currentProject: project, episodes, loading: false });
    } catch (e: unknown) {
      set({ error: (e as Error).message, loading: false });
    }
  },

  regenerateImage: async (sceneId) => {
    try {
      await assetApi.regenerateImage(sceneId);
      // Update scene status locally to show spinner
      set((s) => ({
        scenes: s.scenes.map((sc) =>
          sc.id === sceneId ? { ...sc, status: "GENERATING" } : sc
        ),
      }));
    } catch (e: unknown) {
      set({ error: (e as Error).message });
    }
  },

  // ── Helpers ──

  updateSceneLocally: (sceneId, patch) => {
    set((s) => ({
      scenes: s.scenes.map((sc) =>
        sc.id === sceneId ? { ...sc, ...patch } : sc
      ),
    }));
  },

  refreshCurrentProject: async () => {
    const project = get().currentProject;
    if (!project) return;
    try {
      const updated = await projectApi.get(project.id);
      const scenes = await sceneApi.list(project.id);
      set({ currentProject: updated, scenes });
    } catch (e: unknown) {
      set({ error: (e as Error).message });
    }
  },

  clearCurrentProject: () => {
    set({ currentProject: null, scenes: [], characters: [], episodes: [], error: null });
  },
}));
