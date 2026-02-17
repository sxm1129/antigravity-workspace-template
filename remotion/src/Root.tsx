import { Composition } from "remotion";
import { ComicDrama } from "./ComicDrama";
import { SingleScene } from "./components/SingleScene";
import { DEFAULTS } from "./types";
import type { ComicDramaProps, SingleSceneProps } from "./types";

/**
 * Root component — registers all Remotion compositions.
 *
 * Note: Remotion v4 Composition expects <ZodSchema, Props> generics.
 * We bypass ZodSchema with `as any` since props come from JSON --props file.
 */
export const RemotionRoot: React.FC = () => {
  const ComicDramaComposition = Composition as any;
  const SingleSceneComposition = Composition as any;

  return (
    <>
      <ComicDramaComposition
        id="ComicDrama"
        component={ComicDrama}
        fps={DEFAULTS.fps}
        width={DEFAULTS.width}
        height={DEFAULTS.height}
        durationInFrames={240}
        defaultProps={{
          title: "MotionWeaver Demo",
          fps: DEFAULTS.fps,
          width: DEFAULTS.width,
          height: DEFAULTS.height,
          scenes: [],
          style: "default",
        } satisfies ComicDramaProps}
        calculateMetadata={({ props }: { props: ComicDramaProps }) => {
          const sceneDuration = props.scenes.reduce(
            (sum: number, s: { durationInFrames: number }) =>
              sum + s.durationInFrames,
            0,
          );
          const titleDuration = 72;
          const creditsDuration = 72;
          const transitionOverlap =
            Math.max(0, props.scenes.length - 1) *
            DEFAULTS.transitionDurationInFrames;
          const totalDuration =
            titleDuration + sceneDuration + creditsDuration - transitionOverlap;

          return {
            durationInFrames: Math.max(totalDuration, 1),
            fps: props.fps || DEFAULTS.fps,
            width: props.width || DEFAULTS.width,
            height: props.height || DEFAULTS.height,
          };
        }}
      />

      {/* Single-scene image-to-video rendering (used as Seedance fallback) */}
      <SingleSceneComposition
        id="SingleSceneRender"
        component={SingleScene}
        fps={DEFAULTS.fps}
        width={DEFAULTS.width}
        height={DEFAULTS.height}
        durationInFrames={120}
        defaultProps={{
          imageSrc: "",
          durationInFrames: 120,
          motionPreset: "zoom-in",
        } satisfies SingleSceneProps}
        calculateMetadata={({ props }: { props: SingleSceneProps }) => ({
          durationInFrames: props.durationInFrames || 120,
          fps: DEFAULTS.fps,
          width: DEFAULTS.width,
          height: DEFAULTS.height,
        })}
      />
    </>
  );
};
