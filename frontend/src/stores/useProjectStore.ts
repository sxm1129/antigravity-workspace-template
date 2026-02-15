/** Zustand store — global project state management. */

import { create } from "zustand";
import {
  type Project,
  type Scene,
  type Character,
  projectApi,
  sceneApi,
  characterApi,
  storyApi,
  assetApi,
} from "@/lib/api";

interface ProjectStore {
  // ── State ──
  projects: Project[];
  currentProject: Project | null;
  scenes: Scene[];
  characters: Character[];
  loading: boolean;
  error: string | null;

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

  // ── Story AI ──
  generateOutline: (projectId: string) => Promise<void>;
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

export const useProjectStore = create<ProjectStore>((set, get) => ({
  projects: [],
  currentProject: null,
  scenes: [],
  characters: [],
  loading: false,
  error: null,

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
    set({ loading: true, error: null, currentProject: null, scenes: [], characters: [] });
    try {
      const project = await projectApi.get(id);
      set({ currentProject: project, loading: false });
      // Also fetch scenes and characters
      const scenes = await sceneApi.list(id);
      const characters = await characterApi.list(id);
      set({ scenes, characters });
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
      // Refresh project to get updated outline + status
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
      const project = await projectApi.advanceStatus(projectId, "SCRIPT_REVIEW");
      const scenes = await sceneApi.list(projectId);
      set({ currentProject: project, scenes, loading: false });
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
    set({ currentProject: null, scenes: [], characters: [], error: null });
  },
}));
