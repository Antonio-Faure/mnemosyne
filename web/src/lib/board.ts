export type BoardId = "resolver" | "atelier";
export type ColumnId = "queued" | "running" | "waiting" | "done" | "failed";
export type WaitingType = "operator" | "sources" | "email" | "access";

export interface BoardWaiting {
  type: WaitingType;
  label: string;
  detail?: string;
}

export interface BoardMission {
  task_id: number | null;
  source_id?: string | null;
  status: string | null;
  column?: ColumnId | null;
  waiting_on?: WaitingType | null;
  outcome?: string | null;
  outcome_label?: string | null;
  agent?: string | null;
}

export interface BoardResolution {
  task_id: number;
  title: string;
  segment_id: string;
  status: string;
  outcome?: string | null;
  outcome_label?: string | null;
}

export interface BoardCard {
  id: string;
  kind: "resolution" | "mission";
  task_id: number;
  title: string;
  subtitle: string;
  source_id?: string | null;
  agent: string | null;
  current_agent: string | null;
  agents: string[];
  status: string;
  column: ColumnId;
  waiting_on: WaitingType | null;
  waiting: BoardWaiting[];
  outcome: string | null;
  outcome_label: string | null;
  created_at: string;
  updated_at: string;
  request_count: number | null;
  source_count: number | null;
  missions: BoardMission[];
  resolutions: BoardResolution[];
  links: {
    session: string;
    resolver_requests: number[];
    missions?: number[];
    resolutions?: number[];
  };
}

export interface BoardSummaryItem {
  key: string;
  label: string;
  count: number;
}

export interface BoardColumn {
  id: ColumnId;
  label: string;
  count: number;
  summary: BoardSummaryItem[];
  cards: BoardCard[];
}

export interface BoardResponse {
  board: BoardId;
  generated_at: string;
  columns: BoardColumn[];
  cards: BoardCard[];
}

export async function fetchBoard(board: BoardId): Promise<BoardResponse> {
  const response = await fetch(`/api/obs/tasks?board=${board}`);
  if (!response.ok) throw new Error(`board: HTTP ${response.status}`);
  return (await response.json()) as BoardResponse;
}

export const BOARD_LABELS: Record<BoardId, string> = {
  resolver: "Le Résolveur",
  atelier: "L’Atelier",
};

export const COLUMN_HINTS: Record<BoardId, Record<ColumnId, string>> = {
  resolver: {
    queued: "résolutions importées",
    running: "session résolveur active",
    waiting: "opérateur ou sources",
    done: "verdicts rendus",
    failed: "technique, budget, annulation",
  },
  atelier: {
    queued: "missions de source créées",
    running: "session codeur ou navigateur active",
    waiting: "opérateur, e-mail ou accès",
    done: "sources traitées",
    failed: "accès, technique, abandon",
  },
};

export const WAITING_LABELS: Record<WaitingType, string> = {
  operator: "Opérateur",
  sources: "Sources",
  email: "E-mail",
  access: "Accès",
};

export const WAITING_CLASSES: Record<WaitingType, string> = {
  operator: "border-amber-500/30 bg-amber-500/10 text-amber-300",
  sources: "border-pink-500/30 bg-pink-500/10 text-pink-300",
  email: "border-sky-500/30 bg-sky-500/10 text-sky-300",
  access: "border-violet-500/30 bg-violet-500/10 text-violet-300",
};

export const OUTCOME_CLASSES: Record<string, string> = {
  match: "border-emerald-500/30 bg-emerald-500/10 text-emerald-300",
  partial: "border-teal-500/30 bg-teal-500/10 text-teal-300",
  no_match: "border-slate-600 bg-slate-600/10 text-slate-400",
  ambiguous: "border-orange-500/30 bg-orange-500/10 text-orange-300",
  source_added: "border-emerald-500/30 bg-emerald-500/10 text-emerald-300",
  already_covered: "border-teal-500/30 bg-teal-500/10 text-teal-300",
  refused: "border-slate-600 bg-slate-600/10 text-slate-400",
  no_source: "border-slate-600 bg-slate-600/10 text-slate-400",
  technique: "border-rose-500/30 bg-rose-500/10 text-rose-300",
  access_denied: "border-rose-500/30 bg-rose-500/10 text-rose-300",
  budget: "border-red-800/50 bg-red-900/20 text-red-300",
  abandon: "border-orange-500/30 bg-orange-500/10 text-orange-300",
  cancelled: "border-slate-600 bg-slate-600/10 text-slate-400",
};

export function outcomeClass(outcome: string | null | undefined): string {
  return OUTCOME_CLASSES[outcome ?? ""] ?? "border-ink-600 bg-ink-700/40 text-slate-400";
}

export function waitingClass(type: WaitingType | null | undefined): string {
  return type ? WAITING_CLASSES[type] : "border-ink-600 bg-ink-700/40 text-slate-400";
}

export function agentLabel(agent: string | null | undefined): string {
  if (agent === "resolver") return "Résolveur";
  if (agent === "coder") return "Codeur";
  if (agent === "browser") return "Navigateur";
  return agent ?? "—";
}

export function relativeTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "—";
  const seconds = Math.max(0, Math.round((Date.now() - date.getTime()) / 1000));
  if (seconds < 45) return "à l’instant";
  if (seconds < 90) return "il y a 1 min";
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `il y a ${minutes} min`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `il y a ${hours} h`;
  const days = Math.round(hours / 24);
  return `il y a ${days} j`;
}
