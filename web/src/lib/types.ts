export type SessionFamily = "task" | "job";

export interface Session {
  id: string;
  family: SessionFamily;
  type: string;
  title: string;
  agent: string | null;
  status: string;
  notable: boolean;
  started_at: string;
  ended_at: string | null;
  updated_at: string;
  meta: Record<string, unknown> | null;
  event_count: number;
}

export interface ObsEvent {
  id: number;
  session_id: string;
  ts: string;
  kind: string;
  actor: string | null;
  payload: Record<string, any> | null;
}

export interface SessionsResponse {
  sessions: Session[];
  latest_event_id: number;
}
