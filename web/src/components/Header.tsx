import {
  ChevronLeft,
  ChevronRight,
  PanelLeft,
  PanelRight,
  RotateCcw,
  Waypoints,
} from "lucide-react";

import type { Session } from "../lib/types";
import {
  durationLabel,
  sessionTypeLabel,
} from "../lib/format";

interface Props {
  session: Session | null;
  live: boolean;
  canPrev: boolean;
  canNext: boolean;
  sessionsOpen: boolean;
  stepOpen: boolean;
  onToggleSessions: () => void;
  onToggleStep: () => void;
  onPrev: () => void;
  onNext: () => void;
  onReplay: () => void;
  loading?: boolean;
}

const TOGGLE =
  "grid h-8 w-8 place-items-center rounded-lg border transition";
const TOGGLE_ON =
  "border-sky-500/40 bg-sky-500/10 text-sky-300";
const TOGGLE_OFF =
  "border-transparent text-slate-500 hover:border-ink-600 hover:bg-ink-800 hover:text-slate-200";
const NAV =
  "flex h-8 items-center gap-1.5 rounded-lg border border-ink-700/80 bg-ink-800/80 px-2.5 text-[11px] font-medium text-slate-300 transition hover:border-sky-500/40 hover:text-sky-200 disabled:cursor-default disabled:opacity-30";

function statusLabel(status: string): string {
  switch (status) {
    case "running":
      return "en cours";
    case "done":
    case "connected":
      return "terminé";
    case "failed":
      return "échec";
    case "cancelled":
      return "annulé";
    case "review":
      return "à revoir";
    case "blocked":
      return "bloqué";
    case "pending":
      return "en file";
    default:
      return status;
  }
}

function statusTone(status: string): string {
  if (status === "running") return "bg-sky-500/10 text-sky-300 ring-sky-500/25";
  if (status === "failed" || status === "cancelled") {
    return "bg-rose-500/10 text-rose-300 ring-rose-500/25";
  }
  if (status === "review" || status === "blocked") {
    return "bg-amber-500/10 text-amber-300 ring-amber-500/25";
  }
  if (status === "done" || status === "connected") {
    return "bg-emerald-500/10 text-emerald-300 ring-emerald-500/25";
  }
  return "bg-ink-700/60 text-slate-400 ring-ink-600";
}

export function Header({
  session,
  live,
  canPrev,
  canNext,
  sessionsOpen,
  stepOpen,
  onToggleSessions,
  onToggleStep,
  onPrev,
  onNext,
  onReplay,
  loading = false,
}: Props) {
  return (
    <header className="relative z-50 flex h-14 shrink-0 items-center gap-3 border-b border-ink-700/80 bg-ink-850 px-3 sm:px-4">
      <div className="flex items-center gap-1">
        <button
          onClick={onToggleSessions}
          className={`${TOGGLE} ${sessionsOpen ? TOGGLE_ON : TOGGLE_OFF}`}
          title={sessionsOpen ? "Replier les sessions" : "Afficher les sessions"}
          aria-expanded={sessionsOpen}
        >
          <PanelLeft size={15} strokeWidth={1.8} />
        </button>
        <button
          onClick={onToggleStep}
          className={`${TOGGLE} ${stepOpen ? TOGGLE_ON : TOGGLE_OFF}`}
          title={stepOpen ? "Replier l'étape en cours" : "Afficher l'étape en cours"}
          aria-expanded={stepOpen}
        >
          <PanelRight size={15} strokeWidth={1.8} />
        </button>
      </div>

      <span className="h-5 w-px bg-ink-700/80" />

      <div className="flex min-w-0 items-center gap-2.5">
        <span className="grid h-8 w-8 shrink-0 place-items-center rounded-lg bg-sky-500/10 text-sky-400 ring-1 ring-inset ring-sky-500/20">
          <Waypoints size={16} strokeWidth={1.8} />
        </span>
        <div className="hidden leading-tight md:block">
          <div className="text-[13px] font-semibold tracking-tight text-slate-100">
            mnemosyne
          </div>
          <div className="text-[9px] uppercase tracking-[0.18em] text-slate-400">
            observatoire
          </div>
        </div>
      </div>

      <span className="hidden h-5 w-px bg-ink-700/80 md:block" />

      {session ? (
        <div className="flex min-w-0 flex-1 items-center gap-2.5">
          <div className="min-w-0">
            <div
              className="truncate text-[13.5px] font-medium leading-snug text-slate-100"
              title={session.title}
            >
              {session.title}
            </div>
            <div className="mt-0.5 flex items-center gap-1.5 text-[10.5px] text-slate-400">
              <span className="truncate uppercase tracking-[0.12em] text-slate-400">
                {sessionTypeLabel(session)}
              </span>
              <span className="text-slate-600">·</span>
              <span className="hidden font-mono text-slate-400 xl:inline">
                {session.id}
              </span>
              <span className="hidden text-slate-700 xl:inline">·</span>
              <span className="font-mono tabular-nums">
                {durationLabel(session)}
              </span>
              <span
                className={`ml-0.5 inline-flex items-center gap-1 rounded-full px-1.5 py-[1px] text-[10px] font-medium ring-1 ring-inset ${statusTone(session.status)}`}
              >
                <span className="h-1 w-1 rounded-full bg-current" />
                {statusLabel(session.status)}
              </span>
              {live && (
                <span className="inline-flex items-center gap-1 rounded-full bg-emerald-500/10 px-1.5 py-[1px] text-[10px] font-medium text-emerald-300 ring-1 ring-inset ring-emerald-500/25">
                  <span className="h-1 w-1 animate-pulse rounded-full bg-emerald-400" />
                  direct
                </span>
              )}
            </div>
          </div>
        </div>
      ) : (
        <div className="min-w-0 flex-1 text-[12px] text-slate-400">
          {loading ? "Chargement des sessions…" : "Choisissez une session à gauche"}
        </div>
      )}

      <div className="flex shrink-0 items-center gap-1.5">
        <button
          onClick={onPrev}
          disabled={!canPrev}
          className={NAV}
          title="Session précédente (plus ancienne)"
          aria-label="Session précédente"
        >
          <ChevronLeft size={13} />
          <span className="hidden lg:inline">Précédente</span>
        </button>
        <button
          onClick={onNext}
          disabled={!canNext}
          className={NAV}
          title="Session suivante (plus récente)"
          aria-label="Session suivante"
        >
          <span className="hidden lg:inline">Suivante</span>
          <ChevronRight size={13} />
        </button>
        <button
          onClick={onReplay}
          disabled={!session}
          className={`${NAV} border-sky-500/25 text-sky-200 hover:border-sky-400/50 hover:bg-sky-500/10`}
          title="Rejouer depuis le début"
        >
          <RotateCcw size={12} />
          <span className="hidden md:inline">Rejouer</span>
        </button>
      </div>
    </header>
  );
}
