import { useMemo } from "react";
import {
  CheckCircle2,
  CircleDashed,
  EyeOff,
  Loader2,
  PauseCircle,
  X,
  XCircle,
} from "lucide-react";

import type { Session } from "../lib/types";
import {
  dayLabel,
  durationLabel,
  formatClock,
  sessionColor,
} from "../lib/format";

interface Props {
  sessions: Session[];
  selectedId: string | null;
  onSelect: (id: string) => void;
  includeSilent: boolean;
  onIncludeSilent: (value: boolean) => void;
  family: "all" | "task" | "job";
  onFamily: (family: "all" | "task" | "job") => void;
  hiddenCount: number;
  loading?: boolean;
  error?: boolean;
  onRetry?: () => void;
  overlay?: boolean;
  onClose?: () => void;
}

function StatusIcon({ status }: { status: string }) {
  if (status === "running") {
    return <Loader2 size={13} className="animate-spin text-sky-400" aria-label="en cours" />;
  }
  if (status === "failed" || status === "cancelled") {
    return <XCircle size={13} className="text-rose-400" aria-label="échec" />;
  }
  if (status === "done" || status === "connected") {
    return <CheckCircle2 size={13} className="text-emerald-400/90" aria-label="terminé" />;
  }
  if (status === "review" || status === "blocked") {
    return <PauseCircle size={13} className="text-amber-400" aria-label="à revoir" />;
  }
  return <CircleDashed size={13} className="text-slate-600" aria-label="en attente" />;
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
  hiddenCount,
  loading = false,
  error = false,
  onRetry,
  overlay = false,
  onClose,
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
    <aside
      className={`${
        overlay
          ? "fixed bottom-0 left-0 top-14 z-40 w-[min(330px,90vw)] shadow-2xl"
          : "relative w-[304px] shrink-0"
      } flex min-h-0 flex-col border-r border-ink-700/80 bg-ink-850`}
      aria-label="Sessions observées"
    >
      <div className="shrink-0 px-3 pb-3 pt-3.5">
        <div className="flex items-center gap-2">
          <h2 className="text-[13px] font-semibold tracking-tight text-slate-100">
            Sessions
          </h2>
          <span className="font-mono text-[10px] tabular-nums text-slate-400">
            {sessions.length}
          </span>
          {overlay && (
            <button
              onClick={onClose}
              className="ml-auto grid h-7 w-7 place-items-center rounded-md text-slate-500 transition hover:bg-ink-800 hover:text-slate-200"
              title="Fermer"
              aria-label="Fermer les sessions"
            >
              <X size={14} />
            </button>
          )}
        </div>

        <div className="mt-3 grid grid-cols-3 gap-0.5 rounded-lg bg-ink-900/70 p-0.5 ring-1 ring-inset ring-ink-700/70">
          {FAMILIES.map((item) => (
            <button
              key={item.id}
              onClick={() => onFamily(item.id)}
              className={`rounded-md px-2 py-1.5 text-[11px] font-medium transition ${
                family === item.id
                  ? "bg-ink-750 text-slate-100 shadow-sm ring-1 ring-inset ring-ink-600"
                  : "text-slate-400 hover:text-slate-200"
              }`}
              aria-pressed={family === item.id}
            >
              {item.label}
            </button>
          ))}
        </div>

        <button
          onClick={() => onIncludeSilent(!includeSilent)}
          className="mt-3 flex w-full items-center gap-2 text-left text-[10.5px] text-slate-400 transition hover:text-slate-300"
          aria-pressed={includeSilent}
        >
          <span
            className={`relative h-4 w-7 shrink-0 rounded-full transition ${
              includeSilent ? "bg-sky-500/80" : "bg-ink-700"
            }`}
          >
            <span
              className={`absolute top-0.5 h-3 w-3 rounded-full bg-slate-200 transition-all ${
                includeSilent ? "left-3.5" : "left-0.5"
              }`}
            />
          </span>
          Inclure les runs silencieux
        </button>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto px-2 pb-3">
        {groups.map(([label, items]) => (
          <section key={label}>
            <div className="sticky top-0 z-10 flex items-center gap-2 bg-ink-850/95 px-2 py-2 backdrop-blur">
              <span className="text-[10px] font-medium uppercase tracking-[0.14em] text-slate-400">
                {label}
              </span>
              <span className="h-px flex-1 bg-ink-700/60" />
              <span className="font-mono text-[10px] tabular-nums text-slate-400">
                {items.length}
              </span>
            </div>
            <div className="space-y-0.5">
              {items.map((session) => {
                const selected = session.id === selectedId;
                const color = sessionColor(session);
                return (
                  <button
                    key={session.id}
                    onClick={() => onSelect(session.id)}
                    className={`group relative w-full rounded-lg px-2.5 py-2.5 text-left transition ${
                      selected
                        ? "bg-ink-750 ring-1 ring-inset ring-ink-600"
                        : "hover:bg-ink-800/70"
                    }`}
                  >
                    <div className="flex items-start gap-2.5">
                      <span
                        className="mt-[5px] h-2 w-2 shrink-0 rounded-full"
                        style={{
                          background: color,
                          boxShadow: selected ? `0 0 8px ${color}66` : undefined,
                        }}
                      />
                      <div className="min-w-0 flex-1">
                        <div
                          className={`line-clamp-2 text-[12.5px] leading-snug ${
                            selected
                              ? "font-medium text-slate-100"
                              : "font-normal text-slate-300"
                          }`}
                          title={session.title}
                        >
                          {session.title}
                        </div>
                        <div className="mt-1.5 flex items-center gap-1.5 font-mono text-[10px] tabular-nums text-slate-400">
                          <span>{formatClock(session.started_at)}</span>
                          <span className="text-slate-700">·</span>
                          <span>{durationLabel(session)}</span>
                          <span className="text-slate-700">·</span>
                          <span>{session.event_count} ev.</span>
                        </div>
                      </div>
                      <span className="mt-[3px] shrink-0">
                        <StatusIcon status={session.status} />
                      </span>
                    </div>
                  </button>
                );
              })}
            </div>
          </section>
        ))}
        {!sessions.length && (
          <div className="px-3 py-8 text-center">
            <p className="text-[12px] text-slate-300">
              {loading
                ? "Chargement des sessions…"
                : error
                  ? "Sessions indisponibles"
                  : "Aucune session"}
            </p>
            <p className="mt-1 text-[10.5px] leading-relaxed text-slate-400">
              {loading
                ? "Lecture de la file et des runs système."
                : error
                  ? "La lecture de la base a échoué."
                  : "Les runs vides et les wrappers restent masqués."}
            </p>
            {error && onRetry && (
              <button
                onClick={onRetry}
                className="mt-3 rounded-md border border-ink-600 bg-ink-800 px-2.5 py-1 text-[10.5px] text-slate-300 transition hover:border-sky-500/40 hover:text-sky-200"
              >
                Réessayer
              </button>
            )}
          </div>
        )}
      </div>

      {!includeSilent && hiddenCount > 0 && (
        <div className="shrink-0 border-t border-ink-700/60 px-3 py-2.5">
          <button
            onClick={() => onIncludeSilent(true)}
            className="flex w-full items-center gap-1.5 text-left text-[10px] text-slate-400 transition hover:text-slate-200"
            title="Les runs de jobs qui n'ont rien produit sont masqués par défaut"
          >
            <EyeOff size={11} />
            {hiddenCount.toLocaleString("fr-FR")} runs silencieux · afficher
          </button>
        </div>
      )}
    </aside>
  );
}
