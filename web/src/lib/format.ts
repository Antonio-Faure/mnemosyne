import type { Session } from "./types";

export const TYPE_COLORS: Record<string, string> = {
  warmup: "#2dd4bf",
  connexion: "#f59e0b",
  connect: "#a78bfa",
  browser: "#38bdf8",
  coder: "#818cf8",
  harvest: "#34d399",
  verify: "#22d3ee",
  discover: "#f472b6",
  agency: "#60a5fa",
  journal: "#94a3b8",
  watchdog: "#fb923c",
};

export function typeColor(type: string): string {
  return TYPE_COLORS[type] ?? "#94a3b8";
}

/** Session color: the system warmup (planner) is deliberately distinct from
 * the browser warmup (Gmail/navigation account). */
export function sessionColor(session: Session): string {
  if (session.type === "warmup" && session.family === "job") return "#64748b";
  return typeColor(session.type);
}

export function sessionTypeLabel(session: Session): string {
  if (session.type === "warmup") {
    return session.family === "job" ? "warmup système" : "warmup navigateur";
  }
  return session.type;
}

export function sessionFamilyLabel(session: Session): string {
  if (session.family === "job") return "système";
  if (session.agent === "browser") return "navigateur";
  if (session.agent === "coder") return "codeur";
  return "tâche";
}

export function formatTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "—";
  return date.toLocaleTimeString("fr-FR", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

export function fullTimestamp(iso: string | null | undefined): string {
  if (!iso) return "—";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return date.toLocaleString("fr-FR", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

const DAY_FORMAT = new Intl.DateTimeFormat("fr-FR", {
  weekday: "long",
  day: "numeric",
  month: "long",
});

export function dayLabel(iso: string): string {
  const date = new Date(iso);
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const yesterday = new Date(today);
  yesterday.setDate(today.getDate() - 1);
  const day = new Date(date);
  day.setHours(0, 0, 0, 0);
  if (day.getTime() === today.getTime()) return "Aujourd'hui";
  if (day.getTime() === yesterday.getTime()) return "Hier";
  return DAY_FORMAT.format(date);
}

export function durationLabel(session: Session): string {
  const start = Date.parse(session.started_at);
  if (Number.isNaN(start)) return "—";
  const end = session.ended_at ? Date.parse(session.ended_at) : Date.now();
  const seconds = Math.max(0, Math.round((end - start) / 1000));
  if (seconds < 60) return `${seconds}s`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ${String(seconds % 60).padStart(2, "0")}s`;
  const hours = Math.floor(minutes / 60);
  return `${hours}h ${String(minutes % 60).padStart(2, "0")}m`;
}

export function formatNumber(value: number | null | undefined): string {
  if (value === null || value === undefined) return "—";
  return value.toLocaleString("fr-FR");
}
