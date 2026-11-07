import { useEffect, useRef } from "react";
import {
  Mouse,
  Pause,
  Play,
  Radio,
  RotateCcw,
  SkipBack,
  SkipForward,
} from "lucide-react";

interface Props {
  total: number;
  cursor: number;
  playing: boolean;
  speed: number;
  timeLabel: string | null;
  live: boolean;
  following: boolean;
  onSeek: (index: number) => void;
  onToggle: () => void;
  onSpeed: (faster: boolean) => void;
  onLive: () => void;
  onReplay: () => void;
}

const GHOST =
  "grid h-8 w-8 place-items-center rounded-lg border border-ink-700/80 bg-ink-800/70 text-slate-400 transition hover:border-ink-600 hover:text-slate-100 disabled:cursor-default disabled:opacity-30";

function formatSpeed(value: number): string {
  return `${new Intl.NumberFormat("fr-FR", { maximumFractionDigits: 2 }).format(value)}×`;
}

export function ReplayBar({
  total,
  cursor,
  playing,
  speed,
  timeLabel,
  live,
  following,
  onSeek,
  onToggle,
  onSpeed,
  onLive,
  onReplay,
}: Props) {
  const hasEvents = total > 0;
  return (
    <div className="flex h-14 shrink-0 items-center gap-2 border-t border-ink-700/80 bg-ink-850 px-3 sm:gap-3 sm:px-4">
      <div className="flex shrink-0 items-center gap-1">
        <button
          onClick={onReplay}
          disabled={!hasEvents}
          className={GHOST}
          title="Rejouer depuis le début"
          aria-label="Rejouer depuis le début"
        >
          <RotateCcw size={13} />
        </button>
        <button
          onClick={() => onSeek(Math.max(0, cursor - 1))}
          disabled={!hasEvents}
          className={GHOST}
          title="Événement précédent"
          aria-label="Événement précédent"
        >
          <SkipBack size={14} />
        </button>
        <button
          onClick={onToggle}
          disabled={!hasEvents}
          className="grid h-8 w-8 place-items-center rounded-lg bg-sky-500 text-ink-950 shadow-sm transition hover:bg-sky-400 disabled:cursor-default disabled:opacity-30"
          title={playing ? "Pause" : "Lecture"}
          aria-label={playing ? "Mettre en pause" : "Lire"}
        >
          {playing ? <Pause size={14} /> : <Play size={14} className="translate-x-[1px]" />}
        </button>
        <button
          onClick={() => onSeek(Math.min(total - 1, cursor + 1))}
          disabled={!hasEvents}
          className={GHOST}
          title="Événement suivant"
          aria-label="Événement suivant"
        >
          <SkipForward size={14} />
        </button>
      </div>

      <span className="hidden h-5 w-px bg-ink-700/70 sm:block" />

      <SpeedBadge speed={speed} onSpeed={onSpeed} />

      <input
        type="range"
        min={0}
        max={Math.max(total - 1, 0)}
        value={hasEvents ? cursor : 0}
        onChange={(event) => onSeek(Number(event.target.value))}
        className="h-1 min-w-[60px] flex-1 cursor-pointer rounded-full bg-ink-700 accent-sky-400"
        title="Position dans la timeline"
        aria-label="Position dans la timeline"
      />

      <div className="hidden shrink-0 flex-col items-end leading-tight sm:flex">
        <span className="font-mono text-[11px] tabular-nums text-slate-300">
          {timeLabel ?? "—"}
        </span>
        <span className="font-mono text-[9.5px] tabular-nums text-slate-400">
          {hasEvents ? cursor + 1 : 0} / {total}
        </span>
      </div>

      {live && (
        <button
          onClick={onLive}
          className={`flex h-8 shrink-0 items-center gap-1.5 rounded-lg px-2.5 text-[10px] font-semibold uppercase tracking-[0.08em] transition ${
            following
              ? "bg-emerald-500/10 text-emerald-300 ring-1 ring-inset ring-emerald-500/25"
              : "bg-ink-800 text-slate-400 ring-1 ring-inset ring-ink-700 hover:text-emerald-300"
          }`}
          title="Suivre le direct"
        >
          <Radio size={11} />
          live
        </button>
      )}
    </div>
  );
}

function SpeedBadge({
  speed,
  onSpeed,
}: {
  speed: number;
  onSpeed: (faster: boolean) => void;
}) {
  const ref = useRef<HTMLSpanElement>(null);
  const callback = useRef(onSpeed);
  callback.current = onSpeed;

  useEffect(() => {
    const element = ref.current;
    if (!element) return;
    const handler = (event: WheelEvent) => {
      if (event.ctrlKey || event.metaKey || event.deltaY === 0) return;
      event.preventDefault();
      event.stopPropagation();
      callback.current(event.deltaY < 0);
    };
    element.addEventListener("wheel", handler, { passive: false });
    return () => element.removeEventListener("wheel", handler);
  }, []);

  return (
    <span
      ref={ref}
      title="Molette sur ce badge : régler la vitesse — 1× = temps réel, minimum 1 s par étape"
      className="flex h-8 shrink-0 cursor-ns-resize items-center gap-1.5 rounded-lg border border-ink-700/80 bg-ink-800/70 px-2 font-mono text-[11px] tabular-nums text-slate-300"
      aria-label={`Vitesse ${formatSpeed(speed)}`}
    >
      <Mouse size={12} className="text-slate-500" />
      {formatSpeed(speed)}
    </span>
  );
}
