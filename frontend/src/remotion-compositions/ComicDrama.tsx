import React from "react";
import { Audio } from "remotion";
import {
  TransitionSeries,
  linearTiming,
} from "@remotion/transitions";
import { fade } from "@remotion/transitions/fade";
import { slide } from "@remotion/transitions/slide";
import { wipe } from "@remotion/transitions/wipe";
import type { ComicDramaProps, SceneProps } from "./types";
import { DEFAULTS } from "./types";
import { TitleCard } from "./components/TitleCard";
import { SceneClip } from "./components/SceneClip";
import { Credits } from "./components/Credits";
import { getTransitionPresentation } from "./components/Transitions";

const TITLE_DURATION = 72; // 3s at 24fps
const CREDITS_DURATION = 72;

/**
 * Main composition — assembles title card, scenes with transitions, and credits.
 */
export const ComicDrama: React.FC<ComicDramaProps> = (props) => {
  const {
    title,
    episode,
    scenes,
    bgmSrc,
    bgmVolume = DEFAULTS.bgmVolume,
    style,
  } = props;

  return (
    <div
      style={{
        width: "100%",
        height: "100%",
        background: "#0a0a1a",
        position: "relative",
      }}
    >
      <TransitionSeries>
        {/* Title Card */}
        <TransitionSeries.Sequence durationInFrames={TITLE_DURATION}>
          <TitleCard title={title} episode={episode} style={style} />
        </TransitionSeries.Sequence>

        {/* Scene clips with transitions */}
        {scenes.map((scene, i) => {
          const transition = scene.transition || DEFAULTS.transition;
          const transitionDuration =
            scene.transitionDurationInFrames ||
            DEFAULTS.transitionDurationInFrames;

          return (
            <React.Fragment key={scene.id}>
              {/* Transition before this scene (skip for first scene) */}
              {i === 0 ? (
                <TransitionSeries.Transition
                  timing={linearTiming({
                    durationInFrames: transitionDuration,
                  })}
                  presentation={fade()}
                />
              ) : (
                <TransitionSeries.Transition
                  timing={linearTiming({
                    durationInFrames: transitionDuration,
                  })}
                  presentation={getTransitionPresentation(transition)}
                />
              )}

              <TransitionSeries.Sequence
                durationInFrames={scene.durationInFrames}
              >
                <SceneClip scene={scene} style={style} />
              </TransitionSeries.Sequence>
            </React.Fragment>
          );
        })}

        {/* Transition to credits */}
        <TransitionSeries.Transition
          timing={linearTiming({
            durationInFrames: DEFAULTS.transitionDurationInFrames,
          })}
          presentation={fade()}
        />

        {/* Credits */}
        <TransitionSeries.Sequence durationInFrames={CREDITS_DURATION}>
          <Credits title={title} style={style} />
        </TransitionSeries.Sequence>
      </TransitionSeries>

      {/* Background music (spans entire composition) */}
      {bgmSrc && <Audio src={bgmSrc} volume={bgmVolume} />}
    </div>
  );
};
