"use client";

/** StylePicker — card-based style preset selector. */

import { useState, useEffect } from "react";
import { styleApi, type StylePreset } from "@/lib/api";

interface StylePickerProps {
  selected: string;
  onSelect: (styleId: string) => void;
}

const STYLE_EMOJIS: Record<string, string> = {
  default: "🎨",
  manga_jp: "🇯🇵",
  manga_cn: "🇨🇳",
  comic_us: "🇺🇸",
};

export default function StylePicker({ selected, onSelect }: StylePickerProps) {
  const [styles, setStyles] = useState<StylePreset[]>([]);

  useEffect(() => {
    styleApi.list().then((res) => setStyles(res.styles)).catch(() => {
      // Fallback if API not available
      setStyles([
        { id: "default", name: "默认", description: "通用漫剧风格", templates: [] },
        { id: "manga_jp", name: "日漫", description: "日本漫画风格", templates: [] },
        { id: "manga_cn", name: "国漫", description: "中国漫画风格", templates: [] },
        { id: "comic_us", name: "美漫", description: "美式漫画风格", templates: [] },
      ]);
    });
  }, []);

  return (
    <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(140px, 1fr))", gap: "0.75rem" }}>
      {styles.map((style) => (
        <button
          key={style.id}
          onClick={() => onSelect(style.id)}
          style={{
            padding: "1rem",
            borderRadius: "0.75rem",
            border: selected === style.id ? "2px solid #8b5cf6" : "2px solid transparent",
            background: selected === style.id
              ? "linear-gradient(135deg, rgba(99,102,241,0.2), rgba(139,92,246,0.2))"
              : "rgba(255,255,255,0.05)",
            color: "#fff",
            cursor: "pointer",
            textAlign: "center",
            transition: "all 0.2s ease",
          }}
        >
          <div style={{ fontSize: "1.5rem", marginBottom: "0.25rem" }}>
            {STYLE_EMOJIS[style.id] || "🖌️"}
          </div>
          <div style={{ fontWeight: 600, fontSize: "0.875rem" }}>{style.name}</div>
          <div style={{ fontSize: "0.75rem", color: "#888", marginTop: "0.25rem" }}>
            {style.description}
          </div>
        </button>
      ))}
    </div>
  );
}
