import { useEffect, useRef } from "react";

import type { ObsEvent } from "../lib/types";

/**
 * Tail the selected session over SSE, starting after the last event loaded
 * over REST. The callback is stored in a ref so re-renders never reconnect.
 */
export function useSessionStream(
  sessionId: string | null,
  initialAfter: number,
  onEvent: (event: ObsEvent) => void,
): void {
  const handler = useRef(onEvent);
  handler.current = onEvent;

  useEffect(() => {
    if (!sessionId) return;
    const url = `/api/obs/stream?session=${encodeURIComponent(
      sessionId,
    )}&after=${initialAfter}`;
    const source = new EventSource(url);
    source.onmessage = (message) => {
      try {
        handler.current(JSON.parse(message.data) as ObsEvent);
      } catch {
        // malformed frame: ignore
      }
    };
    return () => source.close();
  }, [sessionId, initialAfter]);
}
