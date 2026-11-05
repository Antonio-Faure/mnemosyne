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

export async function fetchSessionEvents(sessionId: string): Promise<ObsEvent[]> {
  const response = await fetch(
    `/api/obs/sessions/${encodeURIComponent(sessionId)}/events?limit=20000`,
  );
  if (!response.ok) throw new Error(`events: HTTP ${response.status}`);
  const data = (await response.json()) as { events: ObsEvent[] };
  return data.events;
}

export function sessionIsLive(session: Session | null): boolean {
  return !!session && !session.ended_at;
}
