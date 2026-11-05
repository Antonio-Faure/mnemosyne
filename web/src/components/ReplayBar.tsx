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
  live: boolean;
  following: boolean;
  onSeek: (index: number) => void;
  onToggle: () => void;
  onLive: () => void;
  onReplay: () => void;
}

const BUTTON =
  "grid h-7 w-7 place-items-center rounded-md border border-ink-600 bg-ink-800 text-slate-300 transition hover:border-sky-500/50 hover:text-sky-300 disabled:opacity-40";

function formatSpeed(value: number): string {
  return `${new Intl.NumberFormat("fr-FR", { maximumFractionDigits: 2 }).format(value)}×`;
}

export function ReplayBar({
  total,
  cursor,
  playing,
  speed,
  live,
  following,
  onSeek,
  onToggle,
  onLive,
  onReplay,
}: Props) {
  const hasEvents = total > 0;
  return (
    <div className="flex items-center gap-3 border-t border-ink-700 bg-ink-850 px-4 py-2.5">
      <button
        onClick={onReplay}
        disabled={!hasEvents}
        className={BUTTON}
        title="Rejouer depuis le début"
      >
        <RotateCcw size={13} />
      </button>

      <div className="flex items-center gap-1">
        <button
          onClick={() => onSeek(Math.max(0, cursor - 1))}
          disabled={!hasEvents}
          className={BUTTON}
          title="Événement précédent"
        >
          <SkipBack size={14} />
        </button>
        <button
          onClick={onToggle}
          disabled={!hasEvents}
          className={`${BUTTON} h-8 w-8 border-sky-500/40 text-sky-300`}
          title={playing ? "Pause" : "Lecture"}
        >
          {playing ? <Pause size={15} /> : <Play size={15} />}
        </button>
        <button
          onClick={() => onSeek(Math.min(total - 1, cursor + 1))}
          disabled={!hasEvents}
          className={BUTTON}
          title="Événement suivant"
        >
          <SkipForward size={14} />
        </button>
      </div>

      <span
        title="Molette : régler la vitesse — 1× = temps réel (délais des horodatages)"
        className="flex h-7 items-center gap-1 rounded-md border border-ink-600 bg-ink-800 px-2 font-mono text-[11px] text-slate-300"
      >
        <Mouse size={12} className="text-slate-500" />
        {formatSpeed(speed)}
      </span>

      <input
        type="range"
        min={0}
        max={Math.max(total - 1, 0)}
        value={hasEvents ? cursor : 0}
        onChange={(event) => onSeek(Number(event.target.value))}
        className="h-1 flex-1 cursor-pointer rounded-full bg-ink-600 accent-sky-500"
        title="Position dans la timeline"
      />

      <span className="w-16 text-right font-mono text-[11px] text-slate-400">
        {hasEvents ? cursor + 1 : 0}/{total}
      </span>

      {live && (
        <button
          onClick={onLive}
          className={`flex items-center gap-1 rounded-md px-2 py-1 text-[10px] font-semibold uppercase tracking-wider transition ${
            following
              ? "bg-emerald-500/15 text-emerald-300 ring-1 ring-emerald-500/40"
              : "bg-ink-800 text-slate-400 ring-1 ring-ink-600 hover:text-emerald-300"
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
