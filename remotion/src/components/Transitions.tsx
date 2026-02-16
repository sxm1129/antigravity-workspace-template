import type { TransitionPresentation } from "@remotion/transitions";
import { fade } from "@remotion/transitions/fade";
import { slide } from "@remotion/transitions/slide";
import { wipe } from "@remotion/transitions/wipe";

/**
 * Map transition name to Remotion presentation.
 */
export function getTransitionPresentation(
  name: string
): TransitionPresentation<Record<string, unknown>> {
  switch (name) {
    case "slide":
      return slide();
    case "wipe":
      return wipe();
    case "dissolve":
      // dissolve ≈ fade with longer duration
      return fade();
    case "fade":
    default:
      return fade();
  }
}
