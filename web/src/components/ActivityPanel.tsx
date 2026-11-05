import { useEffect, useMemo, useRef } from "react";
import { Activity } from "lucide-react";

import type { ObsEvent, Session } from "../lib/types";
import {
  kindColor,
  matchesNode,
  summarize,
  type NodeId,
} from "../lib/events";
import { formatTime } from "../lib/format";

interface Props {
  session: Session | null;
  events: ObsEvent[];
  cursor: number;
  focus: NodeId | "all";
  loading?: boolean;
  onFocus: (focus: NodeId | "all") => void;
  onSeek: (index: number) => void;
}

const BASE_FOCUS: { id: NodeId | "all"; label: string }[] = [
  { id: "all", label: "Tout" },
  { id: "orchestrator", label: "Orchestrateur" },
  { id: "browser", label: "Browser" },
  { id: "coder", label: "Codeur" },
  { id: "mailbox", label: "Mailbox" },
  { id: "llm", label: "LLM" },
];

export function ActivityPanel({
  session,
  events,
  cursor,
  focus,
  loading = false,
  onFocus,
  onSeek,
}: Props) {
  const focusOptions = useMemo(
    () =>
      session?.family === "job"
        ? [...BASE_FOCUS, { id: "job" as NodeId, label: "Job" }]
        : BASE_FOCUS,
    [session?.family],
  );

  const indices = useMemo(() => {
    const map = new Map<number, number>();
    events.forEach((event, index) => map.set(event.id, index));
    return map;
  }, [events]);

  const filtered = useMemo(
    () => events.filter((event) => matchesNode(event, focus)),
    [events, focus],
  );
  const currentId = events[cursor]?.id ?? null;
  const currentRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    currentRef.current?.scrollIntoView({ block: "nearest" });
  }, [currentId, focus]);

  return (
    <aside className="flex min-h-0 w-[400px] shrink-0 flex-col border-l border-ink-700 bg-ink-850">
      <div className="space-y-2 border-b border-ink-700 p-3">
        <div className="flex items-center gap-2">
          <Activity size={14} className="text-sky-400" />
          <span className="text-[11px] font-semibold uppercase tracking-[0.18em] text-slate-400">
            Activité
          </span>
          <span className="ml-auto font-mono text-[10px] text-slate-500">
            {loading
              ? "…"
              : `${filtered.length} événement${filtered.length > 1 ? "s" : ""}`}
          </span>
        </div>
        <div className="flex flex-wrap gap-1">
          {focusOptions.map((option) => (
            <button
              key={option.id}
              onClick={() => onFocus(option.id)}
              className={`rounded-md px-2 py-1 text-[10.5px] transition ${
                focus === option.id
                  ? "bg-sky-500/15 text-sky-300 ring-1 ring-sky-500/40"
                  : "text-slate-400 hover:bg-ink-700 hover:text-slate-200"
              }`}
            >
              {option.label}
            </button>
          ))}
        </div>
      </div>

      <div className="min-h-0 flex-1 space-y-1 overflow-y-auto p-2">
        {filtered.map((event) => {
          const index = indices.get(event.id) ?? 0;
          const summary = summarize(event);
          const isCurrent = event.id === currentId;
          return (
            <button
              key={event.id}
              ref={isCurrent ? currentRef : undefined}
              onClick={() => onSeek(index)}
              className={`relative block w-full overflow-hidden rounded-lg border px-2.5 py-1.5 text-left transition ${
                isCurrent
                  ? "border-sky-500/50 bg-sky-500/[0.07]"
                  : "border-transparent hover:border-ink-600 hover:bg-ink-800"
              }`}
            >
              <span
                className="absolute left-0 top-0 h-full w-[2px]"
                style={{ background: kindColor(event.kind) }}
              />
              <div className="flex items-center gap-1.5">
                <span className="font-mono text-[9.5px] text-slate-500">
                  {formatTime(event.ts)}
                </span>
                <span className="rounded bg-ink-700 px-1.5 py-[1px] text-[9.5px] uppercase tracking-wide text-slate-400">
                  {event.actor ?? "système"}
                </span>
                <span className="truncate text-[11.5px] font-medium text-slate-200">
                  {summary.title}
                </span>
              </div>
              {summary.detail && (
                <p className="mt-0.5 line-clamp-3 text-[10.5px] leading-snug text-slate-400">
                  {summary.detail}
                </p>
              )}
            </button>
          );
        })}
        {!filtered.length && (
          <div className="p-3 text-[12px] text-slate-500">
            {loading
              ? "chargement de la session…"
              : "Aucun événement pour ce filtre."}
          </div>
        )}
      </div>
    </aside>
  );
}
