/** Toast notification store for global feedback messages. */

import { create } from "zustand";

export interface Toast {
  id: string;
  type: "success" | "error" | "info" | "warning";
  message: string;
  duration: number;
}

interface ToastStore {
  toasts: Toast[];
  addToast: (type: Toast["type"], message: string, duration?: number) => void;
  removeToast: (id: string) => void;
}

let _id = 0;

export const useToastStore = create<ToastStore>((set) => ({
  toasts: [],

  addToast: (type, message, duration = 3000) => {
    const id = `toast-${++_id}`;
    set((s) => ({ toasts: [...s.toasts, { id, type, message, duration }] }));
    // Auto-remove after duration
    setTimeout(() => {
      set((s) => ({ toasts: s.toasts.filter((t) => t.id !== id) }));
    }, duration);
  },

  removeToast: (id) => {
    set((s) => ({ toasts: s.toasts.filter((t) => t.id !== id) }));
  },
}));
