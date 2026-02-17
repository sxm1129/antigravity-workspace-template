/**
 * InputProps types — shared contract between Python backend and Remotion.
 *
 * The backend generates a JSON file matching ComicDramaProps;
 * Remotion reads it via --props flag; @remotion/player uses it for preview.
 */

export interface ComicDramaProps {
  /** Project title (shown in title card) */
  title: string;
  /** Episode info (optional) */
  episode?: {
    title: string;
    number: number;
  };
  /** Frames per second */
  fps: number;
  /** Output width */
  width: number;
  /** Output height */
  height: number;
  /** Ordered scene list */
  scenes: SceneProps[];
  /** Background music path or URL (optional) */
  bgmSrc?: string;
  /** BGM volume 0-1 */
  bgmVolume?: number;
  /** Style preset */
  style: "default" | "manga_cn";
}

export interface SceneProps {
  /** Scene unique ID */
  id: string;
  /** Video clip source — absolute path or HTTP URL */
  videoSrc: string;
  /** TTS narration audio source (optional) */
  audioSrc?: string;
  /** Dialogue text to overlay */
  dialogue?: string;
  /** Dialogue bubble style */
  bubbleStyle?: "normal" | "think" | "shout" | "narration";
  /** Bubble position as 0-1 ratios */
  bubblePosition?: { x: number; y: number };
  /** Sound effect text overlay */
  sfx?: string;
  /** Duration in frames */
  durationInFrames: number;
  /** Transition to NEXT scene */
  transition?: "fade" | "dissolve" | "wipe" | "slide" | "none";
  /** Transition duration in frames */
  transitionDurationInFrames?: number;
}

/**
 * Props for single-scene image-to-video rendering (fallback mode).
 */
export interface SingleSceneProps {
  /** Image source — absolute path or HTTP URL */
  imageSrc: string;
  /** TTS audio source (optional) */
  audioSrc?: string;
  /** Duration in frames */
  durationInFrames: number;
  /** Motion preset for Ken Burns effect */
  motionPreset: "zoom-in" | "zoom-out" | "pan-left" | "pan-right" | "drift";
}

/**
 * Default values for missing optional fields.
 */
export const DEFAULTS = {
  fps: 24,
  width: 1920,
  height: 1080,
  bgmVolume: 0.3,
  transitionDurationInFrames: 15,
  bubbleStyle: "normal" as const,
  transition: "fade" as const,
} as const;
