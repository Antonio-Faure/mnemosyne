import type { ObsEvent, Session, SessionsResponse } from "./types";

export async function fetchSessions(
  includeSilent: boolean,
  family: "all" | "task" | "job",
): Promise<SessionsResponse> {
  const params = new URLSearchParams({ limit: "200" });
  if (includeSilent) params.set("include_silent", "true");
  if (family !== "all") params.set("family", family);
  const response = await fetch(`/api/obs/sessions?${params.toString()}`);
  if (!response.ok) throw new Error(`sessions: HTTP ${response.status}`);
  return (await response.json()) as SessionsResponse;
}

const TERMINAL_STATUSES = new Set(["done", "failed", "review", "cancelled"]);

/** The agent stops before the orchestrator closes the task. Events emitted in
 *  the same second are ordered by meaning, not by insertion (legacy sessions
 *  recorded the status before activation.end). */
function eventRank(event: ObsEvent): number {
  if (event.kind === "activation.end") return 1;
  if (
    event.kind === "task.status" &&
    TERMINAL_STATUSES.has(String(event.payload?.to ?? ""))
  ) {
    return 2;
  }
  if (event.kind === "activation.returned") return 3;
  return 0;
}

export function orderEvents(events: ObsEvent[]): ObsEvent[] {
  return [...events].sort(
    (a, b) =>
      a.ts.localeCompare(b.ts) ||
      eventRank(a) - eventRank(b) ||
      a.id - b.id,
  );
}

export async function fetchSessionEvents(sessionId: string): Promise<ObsEvent[]> {
  const response = await fetch(
    `/api/obs/sessions/${encodeURIComponent(sessionId)}/events?limit=20000`,
  );
  if (!response.ok) throw new Error(`events: HTTP ${response.status}`);
  const data = (await response.json()) as { events: ObsEvent[] };
  return orderEvents(data.events);
}

export function sessionIsLive(session: Session | null): boolean {
  return !!session && !session.ended_at;
}
