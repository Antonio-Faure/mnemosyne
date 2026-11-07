import { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";

import { ActivityPanel } from "./components/ActivityPanel";
import { Canvas } from "./components/Canvas";
import { Header } from "./components/Header";
import { ReplayBar } from "./components/ReplayBar";
import { Sidebar } from "./components/Sidebar";
import { useSessionStream } from "./hooks/useSessionStream";
import { useViewport } from "./hooks/useViewport";
import {
  fetchSessionEvents,
  fetchSessions,
  orderEvents,
  sessionIsLive,
} from "./lib/api";
import { eventNode, isRenderable, type NodeId } from "./lib/events";
import { formatTime } from "./lib/format";
import type { ObsEvent, Session } from "./lib/types";

const SPEEDS = [0.25, 0.5, 1, 2, 4, 8, 16, 32] as const;
/** Every step stays readable for at least 1 s, even at 32× or when the real
 *  timestamp gap is shorter. The floor overrides the multiplier. */
const MIN_STEP_MS = 1000;

function stepSpeed(current: number, faster: boolean): number {
  const index = SPEEDS.findIndex((value) => value >= current - 1e-6);
  const base = index === -1 ? SPEEDS.length - 1 : index;
  const next = Math.max(
    0,
    Math.min(SPEEDS.length - 1, base + (faster ? 1 : -1)),
  );
  return SPEEDS[next];
}

export default function App() {
  const { isWide, isMedium } = useViewport();
  const [includeSilent, setIncludeSilent] = useState(false);
  const [family, setFamily] = useState<"all" | "task" | "job">("all");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [events, setEvents] = useState<ObsEvent[]>([]);
  const [cursor, setCursor] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [following, setFollowing] = useState(true);
  const [speed, setSpeed] = useState(1);
  const [pinnedNode, setPinnedNode] = useState<NodeId | null>(null);
  const [streamAfter, setStreamAfter] = useState(0);
  const [sessionsOpen, setSessionsOpen] = useState(() => {
    const stored = localStorage.getItem("obs.v2.sessionsOpen");
    return stored === null ? window.innerWidth >= 980 : stored === "1";
  });
  const [stepOpen, setStepOpen] = useState(() => {
    const stored = localStorage.getItem("obs.v2.stepOpen");
    return stored === null ? window.innerWidth >= 1500 : stored === "1";
  });

  useEffect(() => {
    localStorage.setItem("obs.v2.sessionsOpen", sessionsOpen ? "1" : "0");
  }, [sessionsOpen]);
  useEffect(() => {
    localStorage.setItem("obs.v2.stepOpen", stepOpen ? "1" : "0");
  }, [stepOpen]);

  // Crossing a breakpoint folds the zone that no longer fits; it never
  // re-opens by itself (the header buttons do that).
  useEffect(() => {
    if (!isWide) setStepOpen(false);
    if (!isMedium) setSessionsOpen(false);
  }, [isWide, isMedium]);

  const sessionsQuery = useQuery({
    queryKey: ["sessions", includeSilent, family],
    queryFn: () => fetchSessions(includeSilent, family),
    refetchInterval: 8000,
    staleTime: 3000,
  });
  const sessions = useMemo<Session[]>(
    () => sessionsQuery.data?.sessions ?? [],
    [sessionsQuery.data],
  );

  useEffect(() => {
    if (!sessions.length) return;
    if (!selectedId || !sessions.some((session) => session.id === selectedId)) {
      // open on the actual work (the newest task) rather than on the agency
      // job run that merely executed it
      const newestTask = sessions.find((session) => session.family === "task");
      setSelectedId((newestTask ?? sessions[0]).id);
    }
  }, [sessions, selectedId]);

  const selected = useMemo(
    () => sessions.find((session) => session.id === selectedId) ?? null,
    [sessions, selectedId],
  );

  const eventsQuery = useQuery({
    queryKey: ["events", selectedId],
    queryFn: () => fetchSessionEvents(selectedId as string),
    enabled: Boolean(selectedId),
    staleTime: Infinity,
  });

  useEffect(() => {
    const data = eventsQuery.data;
    if (!data) {
      setEvents([]);
      setCursor(0);
      return;
    }
    // One step = one visible block: invisible turns never become a step.
    const shown = data.filter(isRenderable);
    setEvents(shown);
    setCursor(Math.max(0, shown.length - 1));
    setFollowing(true);
    setPlaying(false);
    setPinnedNode(null);
  }, [eventsQuery.data, selectedId]);

  useEffect(() => {
    if (!eventsQuery.data) return;
    const last = eventsQuery.data[eventsQuery.data.length - 1];
    setStreamAfter(last ? last.id : 0);
  }, [eventsQuery.data]);

  useSessionStream(selectedId, streamAfter, (event) => {
    if (!isRenderable(event)) return;
    setEvents((previous) =>
      previous.some((item) => item.id === event.id)
        ? previous
        : orderEvents([...previous, event]),
    );
    if (
      ["task.status", "job.start", "job.end", "session.created"].includes(
        event.kind,
      )
    ) {
      void sessionsQuery.refetch();
    }
  });

  // The mouse wheel is the speed control: 1× = real time. It is scoped to the
  // speed badge so scrolling the transcript/sessions and the canvas zoom keep
  // their native behavior.
  useEffect(() => {
    if (following && events.length) setCursor(events.length - 1);
  }, [events.length, following]);

  useEffect(() => {
    if (!playing || !events.length) return;
    if (cursor >= events.length - 1) {
      setPlaying(false);
      return;
    }
    const current = events[cursor];
    const next = events[cursor + 1];
    const from = current ? Date.parse(current.ts) : Number.NaN;
    const to = next ? Date.parse(next.ts) : Number.NaN;
    const delta = Number.isFinite(from) && Number.isFinite(to)
      ? Math.max(0, to - from)
      : 1000;
    // 1× replays the real gap between two events; the wheel scales it. The
    // initial enqueue wait is compressed: it is queue latency, not work.
    // In all cases, a step gets at least MIN_STEP_MS on screen.
    const delay =
      current?.kind === "session.created"
        ? MIN_STEP_MS
        : Math.max(MIN_STEP_MS, delta / speed);
    const timer = window.setTimeout(
      () => setCursor((current) => Math.min(current + 1, events.length - 1)),
      delay,
    );
    return () => window.clearTimeout(timer);
  }, [playing, cursor, events, speed]);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      const target = event.target;
      if (
        target instanceof HTMLInputElement ||
        target instanceof HTMLSelectElement ||
        target instanceof HTMLTextAreaElement
      ) {
        return;
      }
      if (event.code === "Space") {
        event.preventDefault();
        setFollowing(false);
        setPlaying((value) => !value);
      } else if (event.code === "ArrowRight") {
        setFollowing(false);
        setCursor((current) =>
          Math.min(current + 1, Math.max(0, events.length - 1)),
        );
      } else if (event.code === "ArrowLeft") {
        setFollowing(false);
        setCursor((current) => Math.max(0, current - 1));
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [events.length]);

  const index = sessions.findIndex((session) => session.id === selectedId);
  const older = index >= 0 ? sessions[index + 1] : undefined;
  const newer = index > 0 ? sessions[index - 1] : undefined;
  const live = sessionIsLive(selected);

  const seek = (value: number) => {
    setFollowing(false);
    setPlaying(false);
    setCursor(Math.max(0, Math.min(value, Math.max(0, events.length - 1))));
  };
  const replay = () => {
    if (!events.length) return;
    setFollowing(false);
    setCursor(0);
    setPlaying(true);
  };
  const goLive = () => {
    setFollowing(true);
    setPlaying(false);
    setCursor(Math.max(0, events.length - 1));
  };

  const visible = useMemo(
    () => events.slice(0, Math.min(cursor + 1, events.length)),
    [events, cursor],
  );
  const currentEvent = events[cursor] ?? null;
  const step: NodeId =
    pinnedNode ??
    (currentEvent ? eventNode(currentEvent) ?? "orchestrator" : "orchestrator");
  const timeLabel = currentEvent ? formatTime(currentEvent.ts) : null;

  const toggleSessions = () => {
    setSessionsOpen((open) => {
      const next = !open;
      if (next && !isMedium) setStepOpen(false);
      return next;
    });
  };
  const toggleStep = () => {
    setStepOpen((open) => {
      const next = !open;
      if (next && !isMedium) setSessionsOpen(false);
      return next;
    });
  };
  const closeOverlays = () => {
    if (!isMedium) setSessionsOpen(false);
    if (!isWide) setStepOpen(false);
  };
  const showBackdrop =
    (!isMedium && sessionsOpen) || (!isWide && stepOpen);

  return (
    <div className="flex h-screen flex-col overflow-hidden bg-ink-900 text-slate-200">
      <Header
        session={selected}
        live={live}
        canPrev={Boolean(older)}
        canNext={Boolean(newer)}
        sessionsOpen={sessionsOpen}
        stepOpen={stepOpen}
        onToggleSessions={toggleSessions}
        onToggleStep={toggleStep}
        onPrev={() => {
          if (older) {
            setSelectedId(older.id);
            setPlaying(false);
          }
        }}
        onNext={() => {
          if (newer) {
            setSelectedId(newer.id);
            setPlaying(false);
          }
        }}
        onReplay={replay}
        loading={sessionsQuery.isPending}
      />
      <div className="relative flex min-h-0 flex-1">
        {showBackdrop && (
          <button
            type="button"
            aria-label="Fermer le panneau"
            onClick={closeOverlays}
            className="fixed inset-x-0 bottom-0 top-14 z-30 bg-ink-950/50 backdrop-blur-[1px]"
          />
        )}
        {sessionsOpen && (
          <Sidebar
            sessions={sessions}
            selectedId={selectedId}
            onSelect={(id) => {
              setSelectedId(id);
              setPlaying(false);
              if (!isMedium) setSessionsOpen(false);
            }}
            includeSilent={includeSilent}
            onIncludeSilent={setIncludeSilent}
            family={family}
            onFamily={setFamily}
            hiddenCount={sessionsQuery.data?.silent_count ?? 0}
            loading={sessionsQuery.isPending}
            error={sessionsQuery.isError}
            onRetry={() => void sessionsQuery.refetch()}
            overlay={!isMedium}
            onClose={() => setSessionsOpen(false)}
          />
        )}
        <main className="relative flex min-w-0 flex-1 flex-col">
          <div className="relative min-h-0 flex-1">
            <div
              className={`absolute inset-0 ${
                stepOpen && isWide ? "pr-[472px]" : ""
              }`}
            >
              <Canvas
                session={selected}
                visible={visible}
                onFocus={setPinnedNode}
                panelOpen={stepOpen && isWide}
                sidebarOpen={sessionsOpen && isMedium}
              />
            </div>
            {stepOpen && (
              <ActivityPanel
                session={selected}
                events={events}
                cursor={cursor}
                step={step}
                pinned={pinnedNode !== null}
                loading={Boolean(selectedId) && eventsQuery.isPending}
                error={eventsQuery.isError}
                onRetry={() => void eventsQuery.refetch()}
                overlay={!isWide}
                onClose={() => setStepOpen(false)}
                onFollow={() => setPinnedNode(null)}
                onSeek={seek}
              />
            )}
          </div>
          <ReplayBar
            total={events.length}
            cursor={cursor}
            playing={playing}
            speed={speed}
            timeLabel={timeLabel}
            live={live}
            following={following}
            onSeek={seek}
            onToggle={() => {
              setFollowing(false);
              setPlaying((value) => !value);
            }}
            onSpeed={(faster) =>
              setSpeed((current) => stepSpeed(current, faster))
            }
            onLive={goLive}
            onReplay={replay}
          />
        </main>
      </div>
    </div>
  );
}
