import { useEffect, useMemo, useRef, useState } from "react";
import {
  Briefcase,
  ChevronDown,
  ChevronRight,
  Code2,
  Globe,
  Inbox,
  Network,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";

import type { ObsEvent, Session } from "../lib/types";
import {
  kindColor,
  matchesNode,
  summarize,
  type NodeId,
} from "../lib/events";
import { formatTime, fullTimestamp } from "../lib/format";

interface Props {
  session: Session | null;
  events: ObsEvent[];
  cursor: number;
  step: NodeId;
  pinned: boolean;
  loading?: boolean;
  onFollow: () => void;
  onSeek: (index: number) => void;
  onCollapse: () => void;
}

const STEPS: Record<NodeId, { label: string; color: string; icon: LucideIcon }> = {
  orchestrator: { label: "Orchestrateur", color: "#60a5fa", icon: Network },
  browser: { label: "Navigateur", color: "#38bdf8", icon: Globe },
  coder: { label: "Codeur", color: "#818cf8", icon: Code2 },
  mailbox: { label: "Mailbox", color: "#fbbf24", icon: Inbox },
  job: { label: "Système · job", color: "#34d399", icon: Briefcase },
};

export function ActivityPanel({
  session,
  events,
  cursor,
  step,
  pinned,
  loading = false,
  onFollow,
  onSeek,
  onCollapse,
}: Props) {
  const meta = STEPS[step];
  const Icon = meta.icon;

  const indices = useMemo(() => {
    const map = new Map<number, number>();
    events.forEach((event, index) => map.set(event.id, index));
    return map;
  }, [events]);

  const filtered = useMemo(
    () => events.filter((event) => matchesNode(event, step)),
    [events, step],
  );
  const currentId = events[cursor]?.id ?? null;
  const currentRef = useRef<HTMLDivElement>(null);
  const [expanded, setExpanded] = useState<Set<number>>(new Set());

  useEffect(() => {
    currentRef.current?.scrollIntoView({ block: "nearest" });
  }, [currentId, step]);

  const toggle = (id: number) => {
    setExpanded((previous) => {
      const next = new Set(previous);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  return (
    <aside className="absolute bottom-4 right-4 top-4 z-20 flex w-[388px] flex-col overflow-hidden rounded-xl border border-ink-600 bg-ink-850/95 shadow-2xl backdrop-blur">
      <div className="border-b border-ink-700 p-3">
        <div className="flex items-center gap-2">
          <span
            className="grid h-6 w-6 place-items-center rounded-md"
            style={{ background: `${meta.color}1f`, color: meta.color }}
          >
            <Icon size={13} />
          </span>
          <div className="min-w-0">
            <div className="text-[9px] uppercase tracking-[0.20em] text-slate-500">
              étape en cours
            </div>
            <div className="text-[12.5px] font-semibold text-slate-100">
              {meta.label}
            </div>
          </div>
          <div className="ml-auto flex items-center gap-1.5">
            <span className="font-mono text-[10px] text-slate-500">
              {loading ? "…" : `${filtered.length} ev.`}
            </span>
            {pinned ? (
              <button
                onClick={onFollow}
                className="rounded-md bg-sky-500/15 px-2 py-1 text-[10px] font-medium text-sky-300 ring-1 ring-sky-500/40 transition hover:bg-sky-500/25"
                title="Suivre l'étape de la timeline"
              >
                suivre
              </button>
            ) : (
              <span className="rounded-md bg-ink-700 px-2 py-1 text-[10px] text-slate-400">
                auto
              </span>
            )}
            <button
              onClick={onCollapse}
              className="rounded p-0.5 text-slate-500 transition hover:bg-ink-700 hover:text-slate-200"
              title="Replier le panneau"
            >
              <ChevronRight size={14} />
            </button>
          </div>
        </div>
        {session && (
          <div className="mt-2 truncate font-mono text-[9.5px] text-slate-500">
            {session.id} · {session.title}
          </div>
        )}
      </div>

      <div className="min-h-0 flex-1 space-y-1 overflow-y-auto p-2">
        {filtered.map((event) => {
          const index = indices.get(event.id) ?? 0;
          const summary = summarize(event);
          const isCurrent = event.id === currentId;
          const open = expanded.has(event.id);
          return (
            <div
              key={event.id}
              role="button"
              tabIndex={0}
              ref={isCurrent ? currentRef : undefined}
              onClick={() => onSeek(index)}
              onKeyDown={(keyEvent) => {
                if (keyEvent.key === "Enter" || keyEvent.key === " ") {
                  keyEvent.preventDefault();
                  onSeek(index);
                }
              }}
              className={`relative block w-full cursor-pointer overflow-hidden rounded-lg border px-2.5 py-1.5 text-left transition ${
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
                <span className="min-w-0 flex-1 truncate text-[11.5px] font-medium text-slate-200">
                  {summary.title}
                </span>
                <button
                  onClick={(clickEvent) => {
                    clickEvent.stopPropagation();
                    toggle(event.id);
                  }}
                  className="rounded p-0.5 text-slate-500 transition hover:bg-ink-700 hover:text-slate-200"
                  title={open ? "Masquer les détails" : "Voir les détails (JSON, horodatage complet)"}
                >
                  {open ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
                </button>
              </div>
              {summary.detail && (
                <p className="mt-0.5 line-clamp-3 whitespace-pre-wrap break-words text-[10.5px] leading-snug text-slate-400">
                  {summary.detail}
                </p>
              )}
              {open && (
                <div className="mt-1.5 rounded-md border border-ink-600 bg-ink-900/80 p-2">
                  <div className="mb-1 font-mono text-[9.5px] text-slate-500">
                    {fullTimestamp(event.ts)} · {event.kind} · #{event.id}
                  </div>
                  <pre className="max-h-64 overflow-auto whitespace-pre-wrap break-words font-mono text-[10px] leading-relaxed text-slate-300">
                    {JSON.stringify(
                      {
                        kind: event.kind,
                        actor: event.actor,
                        ts: event.ts,
                        payload: event.payload,
                      },
                      null,
                      2,
                    )}
                  </pre>
                </div>
              )}
            </div>
          );
        })}
        {!filtered.length && (
          <div className="p-3 text-[12px] text-slate-500">
            {loading
              ? "chargement de la session…"
              : "Aucun événement pour cette étape."}
          </div>
        )}
      </div>
    </aside>
  );
}
