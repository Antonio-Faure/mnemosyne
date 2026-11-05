import { formatNumber } from "./format";
import type { ObsEvent } from "./types";

export type NodeId =
  | "orchestrator"
  | "browser"
  | "coder"
  | "mailbox"
  | "llm"
  | "job";

export const KIND_COLORS: Record<string, string> = {
  "session.created": "#94a3b8",
  "task.status": "#60a5fa",
  "activation.start": "#22d3ee",
  "activation.end": "#38bdf8",
  "mailbox.message": "#fbbf24",
  "llm.call": "#a78bfa",
  "tool.call": "#c084fc",
  "job.start": "#34d399",
  "job.end": "#10b981",
};

export function kindColor(kind: string): string {
  return KIND_COLORS[kind] ?? "#94a3b8";
}

const ORCHESTRATOR_KINDS = new Set([
  "session.created",
  "task.status",
  "job.start",
  "job.end",
]);

/** The canvas node an event belongs to (for highlighting and focus). */
export function eventNode(event: ObsEvent): NodeId | null {
  if (event.kind === "mailbox.message") return "mailbox";
  if (event.kind === "llm.call" || event.kind === "tool.call") return "llm";
  if (ORCHESTRATOR_KINDS.has(event.kind)) {
    return event.kind.startsWith("job.") ? "job" : "orchestrator";
  }
  if (event.actor === "browser" || event.actor === "coder") {
    return event.actor as NodeId;
  }
  return null;
}

/** Does an event belong to the focused node? */
export function matchesNode(event: ObsEvent, node: NodeId | "all"): boolean {
  if (node === "all") return true;
  if (node === "llm") return event.kind === "llm.call" || event.kind === "tool.call";
  if (node === "mailbox") return event.kind === "mailbox.message";
  if (node === "orchestrator") {
    return event.kind === "session.created" || event.kind === "task.status";
  }
  if (node === "job") return event.kind.startsWith("job.");
  return event.actor === node;
}

export interface Summary {
  title: string;
  detail: string | null;
}

export function summarize(event: ObsEvent): Summary {
  const payload = event.payload ?? {};
  switch (event.kind) {
    case "session.created":
      return {
        title: "session ouverte",
        detail: `${payload.type ?? "—"} · départ ${payload.agent ?? "—"}`,
      };
    case "task.status":
      return {
        title: `statut ${payload.from ?? "?"} → ${payload.to ?? "?"}`,
        detail: payload.note || null,
      };
    case "activation.start":
      return {
        title: `activation ${event.actor ?? "agent"}`,
        detail: `${payload.messages ?? 0} message(s) injecté(s)`,
      };
    case "activation.end": {
      const bits = [`${payload.turns ?? "?"} tour(s)`];
      if (payload.branch) bits.push(`branche ${payload.branch}`);
      if (payload.error) bits.push(`erreur : ${payload.error}`);
      if (payload.finish) bits.push(payload.finish);
      return { title: `fin d'activation ${event.actor ?? "agent"}`, detail: bits.join(" · ") };
    }
    case "mailbox.message":
      return {
        title: `${payload.from ?? "?"} → ${payload.to ?? "?"}`,
        detail: payload.preview || null,
      };
    case "llm.call": {
      const tools = Array.isArray(payload.tools) && payload.tools.length
        ? ` · outils : ${payload.tools.join(", ")}`
        : "";
      const tokens = `${formatNumber(payload.prompt_tokens)} prompt · ${formatNumber(
        payload.completion_tokens,
      )} sortie · ${formatNumber(payload.cached_tokens)} cache`;
      return {
        title: `appel LLM ${payload.model ?? ""}`.trim(),
        detail: `${tokens}${tools}${payload.text ? ` — ${payload.text}` : ""}`,
      };
    }
    case "tool.call":
      return { title: `outil ${payload.name ?? "?"}`, detail: payload.args || null };
    case "job.start":
      return { title: `job ${payload.kind ?? ""} démarré`.trim(), detail: null };
    case "job.end":
      return {
        title: `job terminé (${payload.status ?? "done"})`.trim(),
        detail: payload.activity || payload.error || null,
      };
    default:
      return { title: event.kind, detail: null };
  }
}

export interface TimelineState {
  /** agents with an activation open at the cursor */
  openAgents: Set<string>;
  jobActive: boolean;
  lastNode: NodeId | null;
  llmCalls: number;
  toolCalls: number;
  mailboxMessages: number;
  eventsByAgent: Record<string, number>;
}

/** Aggregate the visible timeline into per-node state (canvas highlighting). */
export function computeState(visible: ObsEvent[]): TimelineState {
  const openAgents = new Set<string>();
  const eventsByAgent: Record<string, number> = { browser: 0, coder: 0 };
  const state: TimelineState = {
    openAgents,
    jobActive: false,
    lastNode: null,
    llmCalls: 0,
    toolCalls: 0,
    mailboxMessages: 0,
    eventsByAgent,
  };
  for (const event of visible) {
    if (event.kind === "activation.start" && event.actor) openAgents.add(event.actor);
    if (event.kind === "activation.end" && event.actor) openAgents.delete(event.actor);
    if (event.kind === "job.start") state.jobActive = true;
    if (event.kind === "job.end") state.jobActive = false;
    if (event.kind === "llm.call") state.llmCalls += 1;
    if (event.kind === "tool.call") state.toolCalls += 1;
    if (event.kind === "mailbox.message") state.mailboxMessages += 1;
    if (event.actor) eventsByAgent[event.actor] = (eventsByAgent[event.actor] ?? 0) + 1;
    state.lastNode = eventNode(event);
  }
  return state;
}
