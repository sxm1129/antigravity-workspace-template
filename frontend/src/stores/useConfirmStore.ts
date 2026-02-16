/** Confirm dialog store — replaces native confirm() / alert() with custom UI. */

import { create } from "zustand";

export interface ConfirmState {
  open: boolean;
  title: string;
  message: string;
  confirmText: string;
  cancelText: string;
  variant: "danger" | "info" | "warning";
  onConfirm: (() => void) | null;
  onCancel: (() => void) | null;
}

interface ConfirmStore extends ConfirmState {
  /** Show a confirm dialog. Returns void — use onConfirm callback for action. */
  showConfirm: (options: {
    title?: string;
    message: string;
    confirmText?: string;
    cancelText?: string;
    variant?: ConfirmState["variant"];
    onConfirm: () => void;
    onCancel?: () => void;
  }) => void;
  /** Show a simple alert (no cancel button). */
  showAlert: (message: string, options?: { title?: string; variant?: ConfirmState["variant"] }) => void;
  close: () => void;
}

const INITIAL: ConfirmState = {
  open: false,
  title: "",
  message: "",
  confirmText: "确认",
  cancelText: "取消",
  variant: "info",
  onConfirm: null,
  onCancel: null,
};

export const useConfirmStore = create<ConfirmStore>((set) => ({
  ...INITIAL,

  showConfirm: (opts) =>
    set({
      open: true,
      title: opts.title ?? "确认操作",
      message: opts.message,
      confirmText: opts.confirmText ?? "确认",
      cancelText: opts.cancelText ?? "取消",
      variant: opts.variant ?? "info",
      onConfirm: opts.onConfirm,
      onCancel: opts.onCancel ?? null,
    }),

  showAlert: (message, opts) =>
    set({
      open: true,
      title: opts?.title ?? "提示",
      message,
      confirmText: "知道了",
      cancelText: "",
      variant: opts?.variant ?? "warning",
      onConfirm: null,
      onCancel: null,
    }),

  close: () => set(INITIAL),
}));
