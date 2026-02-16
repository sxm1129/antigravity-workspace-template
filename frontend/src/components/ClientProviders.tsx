"use client";

/** ClientProviders — wraps Toast, ConfirmDialog, and other client-only providers. */

import dynamic from "next/dynamic";

const ToastContainer = dynamic(() => import("@/components/Toast"), {
  ssr: false,
});

const ConfirmDialog = dynamic(() => import("@/components/ConfirmDialog"), {
  ssr: false,
});

export default function ClientProviders() {
  return (
    <>
      <ToastContainer />
      <ConfirmDialog />
    </>
  );
}
