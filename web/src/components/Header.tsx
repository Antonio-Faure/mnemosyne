import { ChevronLeft, ChevronRight, RotateCcw, Waypoints } from "lucide-react";

import type { Session } from "../lib/types";
import { durationLabel, typeColor } from "../lib/format";

interface Props {
  session: Session | null;
  live: boolean;
  canPrev: boolean;
  canNext: boolean;
  onPrev: () => void;
  onNext: () => void;
  onReplay: () => void;
}

const NAV =
  "flex items-center gap-1 rounded-md border border-ink-600 bg-ink-800 px-2 py-1 text-[11px] text-slate-300 transition hover:border-sky-500/50 hover:text-sky-300 disabled:cursor-default disabled:opacity-35";

export function Header({
  session,
  live,
  canPrev,
  canNext,
  onPrev,
  onNext,
  onReplay,
}: Props) {
  return (
    <header className="flex h-14 shrink-0 items-center gap-4 border-b border-ink-700 bg-ink-850 px-4">
      <div className="flex items-center gap-2">
        <span className="grid h-8 w-8 place-items-center rounded-lg bg-sky-500/10 text-sky-400">
          <Waypoints size={16} />
        </span>
        <div className="leading-tight">
          <div className="text-[13px] font-semibold tracking-wide text-slate-100">
            mnemosyne
          </div>
          <div className="text-[9px] uppercase tracking-[0.24em] text-slate-500">
            observatoire
          </div>
        </div>
      </div>

      <div className="h-6 w-px bg-ink-700" />

      {session ? (
        <div className="flex min-w-0 items-center gap-2.5">
          <span
            className="h-2.5 w-2.5 shrink-0 rounded-full"
            style={{
              background: typeColor(session.type),
              boxShadow: `0 0 10px ${typeColor(session.type)}77`,
            }}
          />
          <div className="min-w-0">
            <div className="truncate text-[13px] font-medium text-slate-100">
              {session.title}
            </div>
            <div className="flex items-center gap-1.5 text-[10px] text-slate-500">
              <span className="uppercase tracking-wider text-slate-400">
                {session.type}
              </span>
              <span>·</span>
              <span className="font-mono">{session.id}</span>
              <span>·</span>
              <span>{durationLabel(session)}</span>
              <span>·</span>
              <span
                className={
                  session.status === "failed"
                    ? "text-rose-400"
                    : session.status === "running"
                      ? "text-sky-400"
                      : "text-slate-400"
                }
              >
                {session.status}
              </span>
              {live && (
                <span className="ml-1 flex items-center gap-1 text-emerald-400">
                  <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-emerald-400" />
                  direct
                </span>
              )}
            </div>
          </div>
        </div>
      ) : (
        <div className="text-[12px] text-slate-500">
          Choisissez une session à gauche
        </div>
      )}

      <div className="ml-auto flex items-center gap-1.5">
        <button onClick={onPrev} disabled={!canPrev} className={NAV} title="Session précédente (plus ancienne)">
          <ChevronLeft size={12} /> Précédente
        </button>
        <button onClick={onNext} disabled={!canNext} className={NAV} title="Session suivante (plus récente)">
          Suivante <ChevronRight size={12} />
        </button>
        <button onClick={onReplay} disabled={!session} className={`${NAV} ml-1`}>
          <RotateCcw size={12} /> Rejouer
        </button>
      </div>
    </header>
  );
}
