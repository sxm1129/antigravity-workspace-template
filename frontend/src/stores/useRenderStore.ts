"use client";
/**
 * useRenderStore — Zustand store for video render state.
 *
 * Manages: provider info, preview props, render status.
 */

import { create } from "zustand";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "";

interface ProviderInfo {
  provider: string;
  supports_preview: boolean;
}

interface RenderState {
  // Provider
  providerInfo: ProviderInfo | null;
  providerLoading: boolean;

  // Preview props
  previewProps: Record<string, unknown> | null;
  propsLoading: boolean;

  // Render
  renderStatus: "idle" | "rendering" | "done" | "error";
  renderResult: { output_path: string; provider: string } | null;
  renderError: string | null;

  // Actions
  fetchProvider: () => Promise<void>;
  fetchPreviewProps: (projectId: string) => Promise<void>;
  updatePreviewProps: (props: Record<string, unknown>) => void;
  startRender: (projectId: string, opts?: { title?: string; style?: string }) => Promise<void>;
}

export const useRenderStore = create<RenderState>((set, get) => ({
  providerInfo: null,
  providerLoading: false,
  previewProps: null,
  propsLoading: false,
  renderStatus: "idle",
  renderResult: null,
  renderError: null,

  fetchProvider: async () => {
    set({ providerLoading: true });
    try {
      const res = await fetch(`${API_BASE}/api/render/provider`);
      const data: ProviderInfo = await res.json();
      set({ providerInfo: data, providerLoading: false });
    } catch (e) {
      console.error("Failed to fetch provider:", e);
      set({ providerLoading: false });
    }
  },

  fetchPreviewProps: async (projectId: string) => {
    set({ propsLoading: true });
    try {
      const res = await fetch(`${API_BASE}/api/render/preview-props/${projectId}`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      set({ previewProps: data.props, propsLoading: false });
    } catch (e) {
      console.error("Failed to fetch preview props:", e);
      set({ propsLoading: false });
    }
  },

  updatePreviewProps: (props: Record<string, unknown>) => {
    set({ previewProps: props });
  },

  startRender: async (projectId: string, opts = {}) => {
    set({ renderStatus: "rendering", renderError: null });
    try {
      const res = await fetch(`${API_BASE}/api/render/start/${projectId}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          title: opts.title || "",
          style: opts.style || "default",
        }),
      });
      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || "Render failed");
      }
      const data = await res.json();
      set({
        renderStatus: "done",
        renderResult: { output_path: data.output_path, provider: data.provider },
      });
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : "Unknown error";
      set({ renderStatus: "error", renderError: msg });
    }
  },
}));
