import "@xyflow/react/dist/style.css";

import { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  AlertTriangle,
  Boxes,
  MessagesSquare,
  PanelRight,
  ScanSearch,
  X,
} from "lucide-react";

import { ActivityPanel } from "./ActivityPanel";
import { Canvas } from "./Canvas";
import { ReplayBar } from "./ReplayBar";
import { useSessionStream } from "../hooks/useSessionStream";
import { useViewport } from "../hooks/useViewport";
import {
  fetchSession,
  fetchSessionEvents,
  orderEvents,
  sessionIsLive,
} from "../lib/api";
import {
  agentLabel,
  outcomeClass,
  waitingClass,
  type BoardCard as BoardCardModel,
} from "../lib/board";
import { eventNode, isRenderable, type NodeId } from "../lib/events";
import { formatTime } from "../lib/format";
import type { ObsEvent, Session } from "../lib/types";

const SPEEDS = [0.25, 0.5, 1, 2, 4, 8, 16, 32] as const;
const MIN_STEP_MS = 1000;

function stepSpeed(current: number, faster: boolean): number {
  const index = SPEEDS.findIndex((value) => value >= current - 1e-6);
  const base = index === -1 ? SPEEDS.length - 1 : index;
  const next = Math.max(0, Math.min(SPEEDS.length - 1, base + (faster ? 1 : -1)));
  return SPEEDS[next];
}

function fallbackSession(card: BoardCardModel): Session {
  const terminal = ["done", "failed", "cancelled"].includes(card.status);
  return {
    id: card.links.session,
    family: "task",
    type: card.agent ?? "resolver",
    title: card.title,
    agent: card.current_agent,
    status: card.status,
    notable: true,
    started_at: card.created_at,
    ended_at: terminal ? card.updated_at : null,
    updated_at: card.updated_at,
    meta: null,
    event_count: 0,
  };
}

function CardBadges({ card }: { card: BoardCardModel }) {
  return (
    <div className="flex flex-wrap items-center gap-1">
      {card.waiting.map((item) => (
        <span
          key={item.type}
          className={`rounded-full border px-1.5 py-0.5 text-[9.5px] font-medium ${waitingClass(item.type)}`}
          title={item.detail || undefined}
        >
          {item.label}
        </span>
      ))}
      {card.outcome_label ? (
        <span
          className={`rounded-full border px-1.5 py-0.5 text-[9.5px] font-medium ${outcomeClass(card.outcome)}`}
        >
          {card.outcome_label}
        </span>
      ) : null}
      {card.kind === "resolution" && (card.source_count ?? 0) > 0 ? (
        <span className="rounded-full border border-pink-500/25 bg-pink-500/10 px-1.5 py-0.5 text-[9.5px] font-medium text-pink-300">
          {card.source_count} source{(card.source_count ?? 0) > 1 ? "s" : ""}
        </span>
      ) : null}
      {card.kind === "mission" && (card.request_count ?? 0) > 0 ? (
        <span className="rounded-full border border-sky-500/25 bg-sky-500/10 px-1.5 py-0.5 text-[9.5px] font-medium text-sky-300">
          {card.request_count} résolution{(card.request_count ?? 0) > 1 ? "s" : ""}
        </span>
      ) : null}
    </div>
  );
}

export function SessionDrawer({
  card,
  onClose,
}: {
  card: BoardCardModel;
  onClose: () => void;
}) {
  const { width } = useViewport();
  const canDock = width >= 1100;
  const [panelOpen, setPanelOpen] = useState(canDock);
  const [events, setEvents] = useState<ObsEvent[]>([]);
  const [cursor, setCursor] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [following, setFollowing] = useState(true);
  const [speed, setSpeed] = useState(1);
  const [pinnedNode, setPinnedNode] = useState<NodeId | null>(null);
  const [streamAfter, setStreamAfter] = useState(0);

  const sessionId = card.links.session;
  const sessionQuery = useQuery({
    queryKey: ["session", sessionId],
    queryFn: () => fetchSession(sessionId),
    refetchInterval: 5000,
    staleTime: 2000,
  });
  const session = sessionQuery.data ?? fallbackSession(card);

  const eventsQuery = useQuery({
    queryKey: ["events", sessionId],
    queryFn: () => fetchSessionEvents(sessionId),
    staleTime: 5000,
  });

  useEffect(() => {
    const data = eventsQuery.data;
    if (!data) {
      setEvents([]);
      setCursor(0);
      return;
    }
    const shown = data.filter(isRenderable);
    setEvents(shown);
    setCursor(Math.max(0, shown.length - 1));
    setFollowing(true);
    setPlaying(false);
    setPinnedNode(null);
  }, [eventsQuery.data, sessionId]);

  useEffect(() => {
    if (!eventsQuery.data) return;
    const last = eventsQuery.data[eventsQuery.data.length - 1];
    setStreamAfter(last ? last.id : 0);
  }, [eventsQuery.data]);

  useSessionStream(sessionId, streamAfter, (event) => {
    if (!isRenderable(event)) return;
    setEvents((previous) =>
      previous.some((item) => item.id === event.id)
        ? previous
        : orderEvents([...previous, event]),
    );
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
    const current = events[cursor];
    const next = events[cursor + 1];
    const from = current ? Date.parse(current.ts) : Number.NaN;
    const to = next ? Date.parse(next.ts) : Number.NaN;
    const delta =
      Number.isFinite(from) && Number.isFinite(to) ? Math.max(0, to - from) : 1000;
    const delay =
      current?.kind === "session.created"
        ? MIN_STEP_MS
        : Math.max(MIN_STEP_MS, delta / speed);
    const timer = window.setTimeout(
      () => setCursor((value) => Math.min(value + 1, events.length - 1)),
      delay,
    );
    return () => window.clearTimeout(timer);
  }, [playing, cursor, events, speed]);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.code === "Escape") {
        onClose();
        return;
      }
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
        setCursor((value) => Math.min(value + 1, Math.max(0, events.length - 1)));
      } else if (event.code === "ArrowLeft") {
        setFollowing(false);
        setCursor((value) => Math.max(0, value - 1));
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [events.length, onClose]);

  const visible = useMemo(
    () => events.slice(0, Math.min(cursor + 1, events.length)),
    [events, cursor],
  );
  const currentEvent = events[cursor] ?? null;
  const step: NodeId =
    pinnedNode ??
    (currentEvent ? eventNode(currentEvent) ?? "orchestrator" : "orchestrator");
  const timeLabel = currentEvent ? formatTime(currentEvent.ts) : null;
  const live = sessionIsLive(session);

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

  return (
    <div
      className="fixed inset-0 z-[60] flex bg-ink-950/80 p-2 backdrop-blur-sm sm:p-3"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
      role="dialog"
      aria-modal="true"
      aria-label={`Session de ${card.title}`}
    >
      <div className="flex min-w-0 flex-1 flex-col overflow-hidden rounded-xl border border-ink-600/90 bg-ink-900 shadow-2xl">
        <header className="flex shrink-0 items-center gap-2 border-b border-ink-700/80 bg-ink-850 px-3 py-2">
          <span className="grid h-7 w-7 shrink-0 place-items-center rounded-md bg-ink-800 text-slate-400 ring-1 ring-inset ring-ink-700">
            {card.kind === "resolution" ? (
              <ScanSearch size={14} strokeWidth={1.8} />
            ) : (
              <Boxes size={14} strokeWidth={1.8} />
            )}
          </span>
          <div className="min-w-0 flex-1">
            <div className="flex min-w-0 items-center gap-2">
              <h2 className="truncate text-[13px] font-medium text-slate-100" title={card.title}>
                {card.title}
              </h2>
              <CardBadges card={card} />
            </div>
            <div className="mt-0.5 flex items-center gap-2 text-[10px] text-slate-500">
              <span>tâche #{card.task_id}</span>
              <span>·</span>
              <span>{agentLabel(card.current_agent ?? card.agent)}</span>
              {card.subtitle ? (
                <>
                  <span>·</span>
                  <span className="truncate">{card.subtitle}</span>
                </>
              ) : null}
            </div>
          </div>
          <button
            onClick={() => setPanelOpen((open) => !open)}
            className={`grid h-7 w-7 place-items-center rounded-md border transition ${
              panelOpen
                ? "border-sky-500/40 bg-sky-500/10 text-sky-300"
                : "border-ink-700 text-slate-400 hover:border-ink-600 hover:text-slate-200"
            }`}
            title={panelOpen ? "Masquer le détail" : "Afficher le détail"}
          >
            <PanelRight size={13} />
          </button>
          <button
            onClick={onClose}
            className="grid h-7 w-7 place-items-center rounded-md border border-ink-700 text-slate-400 transition hover:border-rose-500/40 hover:text-rose-300"
            title="Fermer la session"
            aria-label="Fermer la session"
          >
            <X size={14} />
          </button>
        </header>

        <div className="relative min-h-0 flex-1">
          <div className={`absolute inset-0 ${panelOpen && canDock ? "pr-[440px]" : ""}`}>
            <Canvas
              session={session}
              visible={visible}
              onFocus={setPinnedNode}
              panelOpen={panelOpen && canDock}
              sidebarOpen={false}
            />
          </div>
          {panelOpen ? (
            <ActivityPanel
              session={session}
              events={events}
              cursor={cursor}
              step={step}
              pinned={pinnedNode !== null}
              loading={eventsQuery.isPending}
              error={eventsQuery.isError}
              onRetry={() => void eventsQuery.refetch()}
              overlay={!canDock}
              onClose={() => setPanelOpen(false)}
              onFollow={() => setPinnedNode(null)}
              onSeek={seek}
            />
          ) : null}
          {eventsQuery.isError ? (
            <div className="absolute left-1/2 top-3 z-30 flex -translate-x-1/2 items-center gap-2 rounded-lg border border-rose-500/30 bg-rose-500/10 px-2.5 py-1.5 text-[10px] text-rose-200">
              <AlertTriangle size={12} />
              Impossible de charger les événements.
            </div>
          ) : null}
          {!events.length && !eventsQuery.isPending ? (
            <div className="pointer-events-none absolute inset-x-0 bottom-6 flex justify-center">
              <div className="flex items-center gap-1.5 rounded-full border border-ink-700 bg-ink-850/90 px-2.5 py-1 text-[10px] text-slate-500">
                <MessagesSquare size={11} />
                Aucun événement enregistré pour cette tâche.
              </div>
            </div>
          ) : null}
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
          onSpeed={(faster) => setSpeed((value) => stepSpeed(value, faster))}
          onLive={goLive}
          onReplay={replay}
        />
      </div>
    </div>
  );
}
