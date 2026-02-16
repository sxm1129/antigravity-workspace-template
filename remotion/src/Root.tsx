import { Composition } from "remotion";
import { ComicDrama } from "./ComicDrama";
import type { ComicDramaProps } from "./types";
import { DEFAULTS } from "./types";

/**
 * Root component — registers all Remotion compositions.
 */
export const RemotionRoot: React.FC = () => {
  return (
    <>
      <Composition<ComicDramaProps>
        id="ComicDrama"
        component={ComicDrama}
        fps={DEFAULTS.fps}
        width={DEFAULTS.width}
        height={DEFAULTS.height}
        durationInFrames={240} // placeholder, overridden by calculateMetadata
        defaultProps={{
          title: "MotionWeaver Demo",
          fps: DEFAULTS.fps,
          width: DEFAULTS.width,
          height: DEFAULTS.height,
          scenes: [],
          style: "default",
        }}
        calculateMetadata={({ props }) => {
          // Total duration = sum of scene durations + title + credits - transitions overlap
          const sceneDuration = props.scenes.reduce(
            (sum, s) => sum + s.durationInFrames,
            0
          );
          const titleDuration = 72; // 3 seconds at 24fps
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
    </>
  );
};
