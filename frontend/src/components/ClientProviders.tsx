"use client";

/** ClientProviders — wraps Toast and other client-only providers. */

import dynamic from "next/dynamic";

const ToastContainer = dynamic(() => import("@/components/Toast"), {
  ssr: false,
});

export default function ClientProviders() {
  return <ToastContainer />;
}
