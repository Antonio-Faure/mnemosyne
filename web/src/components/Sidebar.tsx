import { useMemo } from "react";
import {
  CheckCircle2,
  CircleDashed,
  Loader2,
  PauseCircle,
  XCircle,
} from "lucide-react";

import type { Session } from "../lib/types";
import { dayLabel, durationLabel, formatTime, typeColor } from "../lib/format";

interface Props {
  sessions: Session[];
  selectedId: string | null;
  onSelect: (id: string) => void;
  includeSilent: boolean;
  onIncludeSilent: (value: boolean) => void;
  family: "all" | "task" | "job";
  onFamily: (family: "all" | "task" | "job") => void;
}

function StatusIcon({ status }: { status: string }) {
  if (status === "running") {
    return <Loader2 size={12} className="animate-spin text-sky-400" />;
  }
  if (status === "failed" || status === "cancelled") {
    return <XCircle size={12} className="text-rose-400" />;
  }
  if (status === "done" || status === "connected") {
    return <CheckCircle2 size={12} className="text-emerald-400" />;
  }
  if (status === "review" || status === "blocked") {
    return <PauseCircle size={12} className="text-amber-400" />;
  }
  return <CircleDashed size={12} className="text-slate-500" />;
}

const FAMILIES: { id: "all" | "task" | "job"; label: string }[] = [
  { id: "all", label: "Tout" },
  { id: "task", label: "Tâches" },
  { id: "job", label: "Système" },
];

export function Sidebar({
  sessions,
  selectedId,
  onSelect,
  includeSilent,
  onIncludeSilent,
  family,
  onFamily,
}: Props) {
  const groups = useMemo(() => {
    const map = new Map<string, Session[]>();
    for (const session of sessions) {
      const key = dayLabel(session.started_at);
      const bucket = map.get(key);
      if (bucket) bucket.push(session);
      else map.set(key, [session]);
    }
    return [...map.entries()];
  }, [sessions]);

  return (
    <aside className="flex min-h-0 w-[330px] shrink-0 flex-col border-r border-ink-700 bg-ink-850">
      <div className="space-y-2 border-b border-ink-700 p-3">
        <div className="flex items-center gap-2">
          <span className="text-[11px] font-semibold uppercase tracking-[0.18em] text-slate-400">
            Sessions
          </span>
          <span className="ml-auto font-mono text-[10px] text-slate-500">
            {sessions.length}
          </span>
        </div>
        <div className="flex gap-1">
          {FAMILIES.map((item) => (
            <button
              key={item.id}
              onClick={() => onFamily(item.id)}
              className={`rounded-md px-2 py-1 text-[11px] transition ${
                family === item.id
                  ? "bg-sky-500/15 text-sky-300 ring-1 ring-sky-500/40"
                  : "text-slate-400 hover:bg-ink-700 hover:text-slate-200"
              }`}
            >
              {item.label}
            </button>
          ))}
        </div>
        <label className="flex cursor-pointer items-center gap-2 text-[10.5px] text-slate-500">
          <input
            type="checkbox"
            checked={includeSilent}
            onChange={(event) => onIncludeSilent(event.target.checked)}
            className="h-3 w-3 accent-sky-500"
          />
          inclure les runs silencieux
        </label>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto">
        {groups.map(([label, items]) => (
          <section key={label}>
            <div className="sticky top-0 z-10 border-b border-ink-800 bg-ink-850/95 px-3 py-1.5 text-[10px] uppercase tracking-[0.16em] text-slate-500 backdrop-blur">
              {label}
            </div>
            {items.map((session) => {
              const selected = session.id === selectedId;
              const color = typeColor(session.type);
              return (
                <button
                  key={session.id}
                  onClick={() => onSelect(session.id)}
                  className={`group relative w-full border-b border-ink-800/70 px-3 py-2 text-left transition ${
                    selected ? "bg-ink-750" : "hover:bg-ink-800/70"
                  }`}
                >
                  <span
                    className="absolute left-0 top-0 h-full w-[2px]"
                    style={{ background: selected ? color : "transparent" }}
                  />
                  <div className="flex items-center gap-2">
                    <span
                      className="h-2 w-2 shrink-0 rounded-full"
                      style={{ background: color, boxShadow: `0 0 8px ${color}66` }}
                    />
                    <span className="min-w-0 flex-1 truncate text-[12px] font-medium text-slate-200">
                      {session.title}
                    </span>
                    <StatusIcon status={session.status} />
                  </div>
                  <div className="mt-1 flex items-center gap-1.5 pl-4 font-mono text-[10px] text-slate-500">
                    <span
                      className="rounded bg-ink-700/80 px-1 py-[1px] text-[9px] uppercase tracking-wider text-slate-300"
                      title={
                        session.family === "task"
                          ? "tâche de la queue — session d'agent (coût LLM)"
                          : "run de job système — déclencheur (aucun LLM)"
                      }
                    >
                      {session.family === "task" ? "tâche" : "job"}
                    </span>
                    <span>{formatTime(session.started_at)}</span>
                    <span>·</span>
                    <span>{durationLabel(session)}</span>
                    <span>·</span>
                    <span>{session.event_count} ev.</span>
                    <span className="ml-auto uppercase tracking-wider text-slate-600">
                      {session.type}
                    </span>
                  </div>
                </button>
              );
            })}
          </section>
        ))}
        {!sessions.length && (
          <div className="p-4 text-[12px] text-slate-500">Aucune session.</div>
        )}
      </div>
    </aside>
  );
}
