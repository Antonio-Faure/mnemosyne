import { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";

import { ActivityPanel } from "./components/ActivityPanel";
import { Canvas } from "./components/Canvas";
import { Header } from "./components/Header";
import { ReplayBar } from "./components/ReplayBar";
import { Sidebar } from "./components/Sidebar";import { useSessionStream } from "./hooks/useSessionStream";
import { fetchSessionEvents, fetchSessions, sessionIsLive } from "./lib/api";
import { eventNode, isRenderable, type NodeId } from "./lib/events";
import type { ObsEvent, Session } from "./lib/types";

export default function App() {
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
  const [sessionsOpen, setSessionsOpen] = useState(
    () => localStorage.getItem("obs.sessionsOpen") !== "0",
  );
  const [stepOpen, setStepOpen] = useState(
    () => localStorage.getItem("obs.stepOpen") !== "0",
  );

  useEffect(() => {
    localStorage.setItem("obs.sessionsOpen", sessionsOpen ? "1" : "0");
  }, [sessionsOpen]);
  useEffect(() => {
    localStorage.setItem("obs.stepOpen", stepOpen ? "1" : "0");
  }, [stepOpen]);

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
        : [...previous, event],
    );
    if (
      ["task.status", "job.start", "job.end", "session.created"].includes(
        event.kind,
      )
    ) {
      void sessionsQuery.refetch();
    }
  });

  useEffect(() => {
    if (following && events.length) setCursor(events.length - 1);
  }, [events.length, following]);

  useEffect(() => {
    if (!playing || !events.length) return;
    if (cursor >= events.length - 1) {
      setPlaying(false);
      return;
    }
    const timer = window.setTimeout(
      () => setCursor((current) => Math.min(current + 1, events.length - 1)),
      420 / speed,
    );
    return () => window.clearTimeout(timer);
  }, [playing, cursor, events.length, speed]);

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

  return (
    <div className="flex h-screen flex-col overflow-hidden bg-ink-900 text-slate-200">
      <Header
        session={selected}
        live={live}
        canPrev={Boolean(older)}
        canNext={Boolean(newer)}
        sessionsOpen={sessionsOpen}
        stepOpen={stepOpen}
        onToggleSessions={() => setSessionsOpen((value) => !value)}
        onToggleStep={() => setStepOpen((value) => !value)}
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
      />
      <div className="flex min-h-0 flex-1">
        {sessionsOpen && (
          <Sidebar
            sessions={sessions}
            selectedId={selectedId}
            onSelect={(id) => {
              setSelectedId(id);
              setPlaying(false);
            }}
            includeSilent={includeSilent}
            onIncludeSilent={setIncludeSilent}
            family={family}
            onFamily={setFamily}
            hiddenCount={sessionsQuery.data?.silent_count ?? 0}
          />
        )}
        <main className="relative flex min-w-0 flex-1 flex-col">
          <div className="relative min-h-0 flex-1">
            <div className={`absolute inset-0 ${stepOpen ? "pr-[404px]" : ""}`}>
              <Canvas
                session={selected}
                visible={visible}
                onFocus={setPinnedNode}
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
            live={live}
            following={following}
            onSeek={seek}
            onToggle={() => {
              setFollowing(false);
              setPlaying((value) => !value);
            }}
            onSpeed={setSpeed}
            onLive={goLive}
            onReplay={replay}
          />
        </main>
      </div>
    </div>
  );
}
