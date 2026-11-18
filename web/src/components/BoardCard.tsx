import {
  ArrowRight,
  Bot,
  Boxes,
  KeyRound,
  Layers,
  Mail,
  ScanSearch,
  UserRound,
} from "lucide-react";

import {
  agentLabel,
  outcomeClass,
  relativeTime,
  waitingClass,
  type BoardCard as BoardCardModel,
  type BoardMission,
  type BoardResolution,
  type WaitingType,
} from "../lib/board";

function WaitingIcon({ type }: { type: WaitingType }) {
  if (type === "operator") return <UserRound size={11} />;
  if (type === "sources") return <Layers size={11} />;
  if (type === "email") return <Mail size={11} />;
  return <KeyRound size={11} />;
}

function Badge({
  children,
  className,
  title,
}: {
  children: React.ReactNode;
  className: string;
  title?: string;
}) {
  return (
    <span
      title={title}
      className={`inline-flex items-center gap-1 rounded-full border px-1.5 py-0.5 text-[10px] font-medium leading-none ${className}`}
    >
      {children}
    </span>
  );
}

function AgentTrail({ card }: { card: BoardCardModel }) {
  const agents = card.agents.length ? card.agents : [card.agent ?? "—"];
  return (
    <div className="mt-2 flex flex-wrap items-center gap-1 text-[10.5px] text-slate-500">
      <Bot size={11} className="text-slate-500" />
      {agents.map((agent, index) => (
        <span key={`${agent}-${index}`} className="inline-flex items-center gap-1">
          {index > 0 ? <ArrowRight size={9} className="text-slate-600" /> : null}
          <span
            className={
              agent === card.current_agent
                ? "rounded bg-sky-500/10 px-1 py-0.5 text-sky-300"
                : ""
            }
          >
            {agentLabel(agent)}
          </span>
        </span>
      ))}
    </div>
  );
}

const STATUS_LABELS: Record<string, string> = {
  pending: "En file",
  running: "En cours",
  done: "Terminé",
  failed: "Échec",
  cancelled: "Annulé",
  waiting: "En attente",
};

function MissionRow({ mission }: { mission: BoardMission }) {
  const tone =
    mission.outcome !== null && mission.outcome !== undefined
      ? outcomeClass(mission.outcome)
      : mission.waiting_on
        ? waitingClass(mission.waiting_on)
        : "border-ink-600 bg-ink-700/40 text-slate-400";
  const label =
    mission.outcome_label ??
    (mission.waiting_on
      ? mission.waiting_on === "email"
        ? "E-mail"
        : mission.waiting_on === "access"
          ? "Accès"
          : mission.waiting_on === "operator"
            ? "Opérateur"
            : "Sources"
      : STATUS_LABELS[mission.status ?? ""] ?? mission.status ?? "—");
  return (
    <li className="flex items-start justify-between gap-2 rounded-md bg-ink-900/70 px-2 py-1.5">
      <span className="min-w-0 truncate text-[11px] text-slate-400">
        <span className="text-slate-300">Mission #{mission.task_id ?? "?"}</span>
        {mission.source_id ? ` · ${mission.source_id}` : ""}
      </span>
      <Badge className={tone}>{label}</Badge>
    </li>
  );
}

function ResolutionRow({ resolution }: { resolution: BoardResolution }) {
  const tone =
    resolution.outcome !== null && resolution.outcome !== undefined
      ? outcomeClass(resolution.outcome)
      : resolution.status === "waiting"
        ? waitingClass("operator")
        : "border-ink-600 bg-ink-700/40 text-slate-400";
  return (
    <li className="flex items-start justify-between gap-2 rounded-md bg-ink-900/70 px-2 py-1.5">
      <span className="min-w-0">
        <span className="block truncate text-[11px] text-slate-300" title={resolution.title}>
          #{resolution.task_id} · {resolution.title}
        </span>
        <span className="block truncate text-[10.5px] text-slate-500">
          {resolution.segment_id}
        </span>
      </span>
      <Badge className={tone}>
        {resolution.outcome_label ?? STATUS_LABELS[resolution.status] ?? resolution.status}
      </Badge>
    </li>
  );
}

export function BoardCard({ card }: { card: BoardCardModel }) {
  const waiting = card.waiting ?? [];
  const dependencyCount =
    card.kind === "resolution" ? card.missions.length : card.resolutions.length;

  return (
    <article className="group rounded-lg border border-ink-700/80 bg-ink-850/95 p-2.5 shadow-sm transition hover:border-ink-600 hover:bg-ink-800">
      <div className="flex items-start gap-2">
        <span className="mt-0.5 grid h-6 w-6 shrink-0 place-items-center rounded-md bg-ink-800 text-slate-400 ring-1 ring-inset ring-ink-700">
          {card.kind === "resolution" ? (
            <ScanSearch size={12} strokeWidth={1.8} />
          ) : (
            <Boxes size={12} strokeWidth={1.8} />
          )}
        </span>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-1">
            {waiting.map((item) => (
              <Badge
                key={item.type}
                className={waitingClass(item.type)}
                title={item.detail || undefined}
              >
                <WaitingIcon type={item.type} />
                {item.label}
              </Badge>
            ))}
            {card.outcome_label ? (
              <Badge className={outcomeClass(card.outcome)}>{card.outcome_label}</Badge>
            ) : null}
            {card.kind === "resolution" && (card.source_count ?? 0) > 0 ? (
              <Badge className="border-pink-500/25 bg-pink-500/10 text-pink-300">
                <Layers size={10} />
                {card.source_count} source{(card.source_count ?? 0) > 1 ? "s" : ""}
              </Badge>
            ) : null}
            {card.kind === "mission" && (card.request_count ?? 0) > 0 ? (
              <Badge className="border-sky-500/25 bg-sky-500/10 text-sky-300">
                <Layers size={10} />
                {card.request_count} résolution{(card.request_count ?? 0) > 1 ? "s" : ""}
              </Badge>
            ) : null}
          </div>
          <h3
            className="mt-1.5 line-clamp-3 text-[12.5px] font-medium leading-snug text-slate-100"
            title={card.title}
          >
            {card.title}
          </h3>
          {card.subtitle ? (
            <p className="mt-0.5 truncate text-[10.5px] text-slate-500" title={card.subtitle}>
              {card.subtitle}
            </p>
          ) : null}
        </div>
      </div>

      <AgentTrail card={card} />

      {dependencyCount > 0 ? (
        <div className="mt-2 border-t border-ink-700/70 pt-2">
          <div className="mb-1 flex items-center justify-between text-[9.5px] uppercase tracking-[0.14em] text-slate-500">
            <span>{card.kind === "resolution" ? "Sources demandées" : "Résolutions liées"}</span>
            <span>{dependencyCount}</span>
          </div>
          <ul className="max-h-36 space-y-1 overflow-y-auto pr-0.5">
            {card.kind === "resolution"
              ? card.missions.map((mission, index) => (
                  <MissionRow key={`${mission.task_id}-${index}`} mission={mission} />
                ))
              : card.resolutions.map((resolution) => (
                  <ResolutionRow key={resolution.task_id} resolution={resolution} />
                ))}
          </ul>
          {card.kind === "resolution" && waiting.length > 0 ? (
            <p className="mt-1 text-[10px] leading-snug text-pink-300/80">
              {waiting
                .filter((item) => item.type === "sources" && item.detail)
                .map((item) => item.detail)
                .join(" · ")}
            </p>
          ) : null}
        </div>
      ) : null}

      <footer className="mt-2 flex items-center justify-between border-t border-ink-700/60 pt-1.5 text-[9.5px] text-slate-500">
        <span>tâche #{card.task_id}</span>
        <span title={card.updated_at}>{relativeTime(card.updated_at)}</span>
      </footer>
    </article>
  );
}
