import { useEffect, useState } from "react";

export interface Viewport {
  width: number;
  /** enough room for the three docked zones (sessions · graph · transcript) */
  isWide: boolean;
  /** the sessions rail can stay docked */
  isMedium: boolean;
}

/** Responsive shell breakpoints. The graph is the stage: below `isWide` the
 *  transcript becomes an overlay drawer instead of squeezing the canvas. */
export function useViewport(): Viewport {
  const [width, setWidth] = useState(() =>
    typeof window === "undefined" ? 1440 : window.innerWidth,
  );

  useEffect(() => {
    let frame = 0;
    const onResize = () => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(() => setWidth(window.innerWidth));
    };
    window.addEventListener("resize", onResize);
    return () => {
      window.removeEventListener("resize", onResize);
      cancelAnimationFrame(frame);
    };
  }, []);

  return {
    width,
    isWide: width >= 1500,
    isMedium: width >= 980,
  };
}
