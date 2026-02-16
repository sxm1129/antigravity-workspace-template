"use client";

import { useParams } from "next/navigation";
import VideoEditor from "@/components/VideoEditor";

/**
 * Video Editor page — full-screen composition editor.
 * Route: /project/[id]/video-editor
 */
export default function VideoEditorPage() {
  const params = useParams();
  const projectId = params?.id as string;

  if (!projectId) {
    return (
      <div style={{ padding: 40, color: "#fff", textAlign: "center" }}>
        无效的项目 ID
      </div>
    );
  }

  return <VideoEditor projectId={projectId} />;
}
