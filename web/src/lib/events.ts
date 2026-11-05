import { formatNumber } from "./format";
import type { ObsEvent } from "./types";

/** Canvas nodes. The LLM has no node: it lives inside the browser/coder step
 * (its calls are shown in that step's panel). */
export type NodeId =
  | "agency"
  | "orchestrator"
  | "browser"
  | "coder"
  | "mailbox"
  | "job";

export const KIND_COLORS: Record<string, string> = {
  "session.created": "#f59e0b",
  "task.status": "#60a5fa",
  "activation.start": "#22d3ee",
  "activation.end": "#38bdf8",
  "mailbox.message": "#fbbf24",
  "llm.call": "#a78bfa",
  "tool.call": "#c084fc",
  "tool.result": "#f0abfc",
  "job.start": "#34d399",
  "job.end": "#10b981",
};

export function kindColor(kind: string): string {
  return KIND_COLORS[kind] ?? "#94a3b8";
}

const ORCHESTRATOR_KINDS = new Set([
  "task.status",
  "activation.returned",
  "job.start",
  "job.end",
]);

/** The canvas step an event belongs to. */
export function eventNode(event: ObsEvent): NodeId | null {
  if (event.kind === "mailbox.message") return "mailbox";
  // the queue (Agency) opens the session / enqueues the mission
  if (event.kind === "session.created") return "agency";
  if (ORCHESTRATOR_KINDS.has(event.kind)) {
    return event.kind.startsWith("job.") ? "job" : "orchestrator";
  }
  // LLM/tool activity belongs to the agent that is running it
  if (
    event.kind === "llm.call" ||
    event.kind === "tool.call" ||
    event.kind === "tool.result"
  ) {
    return event.actor === "browser" || event.actor === "coder"
      ? (event.actor as NodeId)
      : "orchestrator";
  }
  if (event.actor === "browser" || event.actor === "coder") {
    return event.actor as NodeId;
  }
  return null;
}

/** Does an event belong to the given step? */
export function matchesNode(event: ObsEvent, node: NodeId): boolean {
  if (node === "mailbox") return event.kind === "mailbox.message";
  if (node === "agency") return event.kind === "session.created";
  if (node === "orchestrator") {
    return (
      event.kind === "task.status" ||
      event.kind === "activation.returned"
    );
  }
  if (node === "job") return event.kind.startsWith("job.");
  return event.actor === node;
}

export interface Summary {
  title: string;
  detail: string | null;
}

function payloadSummary(payload: Record<string, unknown>): string {
  const bits: string[] = [];
  const source = payload.source_id;
  if (source) bits.push(`source ${source}`);
  if (payload.seed_index !== undefined) bits.push(`seed ${payload.seed_index}`);
  if (payload.interval_s) bits.push(`intervalle ${payload.interval_s}s`);
  if (payload.limit) bits.push(`limite ${payload.limit}`);
  return bits.join(" · ");
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
    case "activation.returned":
      return {
        title: "retour à l'orchestrateur",
        detail: `${payload.status ?? "?"} · retour ${payload.agent ?? "?"}`,
      };
    case "activation.start": {
      const bits = [`${payload.messages ?? 0} message(s)`];
      if (payload.turn_cap) bits.push(`cap ${payload.turn_cap} tours`);
      if (payload.objective) bits.push(String(payload.objective));
      return { title: `activation ${event.actor ?? "agent"}`, detail: bits.join(" · ") };
    }
    case "activation.end": {
      const bits = [`${payload.turns ?? "?"} tour(s)`];
      if (payload.duration_s !== undefined) bits.push(`${payload.duration_s}s`);
      if (payload.branch) bits.push(`branche ${payload.branch}`);
      if (payload.error) bits.push(`erreur : ${payload.error}`);
      if (payload.finish) bits.push(String(payload.finish));
      return {
        title: `fin d'activation ${event.actor ?? "agent"}`,
        detail: bits.join(" · "),
      };
    }
    case "mailbox.message":
      return {
        title: `${payload.from ?? "?"} → ${payload.to ?? "?"}`,
        detail: payload.body || payload.preview || null,
      };
    case "llm.call": {
      const tools =
        Array.isArray(payload.tools) && payload.tools.length
          ? ` · outils : ${payload.tools.join(", ")}`
          : "";
      const tokens = `${formatNumber(payload.prompt_tokens)} prompt · ${formatNumber(
        payload.completion_tokens,
      )} sortie · ${formatNumber(payload.cached_tokens)} cache`;
      const context = payload.messages_count
        ? `${payload.messages_count} messages · `
        : "";
      return {
        title: `appel LLM ${payload.model ?? ""}`.trim(),
        detail: `${context}${tokens}${tools}${payload.text ? ` — ${payload.text}` : ""}`,
      };
    }
    case "tool.call":
      return { title: `outil ${payload.name ?? "?"}`, detail: payload.args || null };
    case "tool.result":
      return {
        title: `résultat ${payload.name ?? "outil"}`,
        detail: payload.preview || null,
      };
    case "job.start": {
      const summary = payloadSummary(payload.payload ?? {});
      return {
        title: `job ${payload.kind ?? ""} démarré`.trim(),
        detail: summary || null,
      };
    }
    case "job.end": {
      const bits: string[] = [];
      if (payload.duration_s !== undefined) bits.push(`${payload.duration_s}s`);
      if (payload.activity) bits.push(String(payload.activity));
      if (payload.error) bits.push(`erreur : ${payload.error}`);
      const updates = payload.updates;
      if (updates && typeof updates === "object") {
        const keys = Object.keys(updates as Record<string, unknown>);
        if (keys.length) bits.push(`maj ${keys.join(", ")}`);
      }
      return {
        title: `job terminé (${payload.status ?? "done"})`.trim(),
        detail: bits.join(" · ") || null,
      };
    }
    default:
      return { title: event.kind, detail: null };
  }
}

export interface TimelineState {
  /** agents with an activation open at the cursor */
  openAgents: Set<string>;
  jobActive: boolean;
  lastNode: NodeId | null;
  /** orchestrator link lit by the current step (direction: to/from agent) */
  handoff: Handoff | null;
  /** mailbox message currently travelling (selects the lit segments) */
  mailRoute: MailRoute | null;
  llmCalls: number;
  toolCalls: number;
  mailboxMessages: number;
  eventsByAgent: Record<string, number>;
}

export interface Handoff {
  agent: "browser" | "coder";
  direction: "to" | "from";
}

export interface MailRoute {
  from: string;
  to: string;
}

function agentName(value: unknown): "browser" | "coder" | null {
  return value === "browser" || value === "coder" ? value : null;
}

/** Orchestrator link lit by an event — never both agents at once. Only real
 * handoffs produce a flow: mission (down), end of activation (up), status. */
export function eventHandoff(event: ObsEvent): Handoff | null {
  const payload = event.payload ?? {};
  switch (event.kind) {
    case "activation.start": {
      const agent = agentName(event.actor);
      return agent ? { agent, direction: "to" } : null;
    }
    case "activation.end": {
      const agent = agentName(event.actor);
      return agent ? { agent, direction: "from" } : null;
    }
    case "task.status": {
      const agent = agentName(payload.agent);
      if (!agent) return null; // status without a known target: no link
      return { agent, direction: payload.to === "running" ? "to" : "from" };
    }
    default:
      return null;
  }
}

/** Events the observatory does not show as steps: pure tool-call turns and the
 * redundant `finish` exchange. Filtering them out keeps one step = one block. */
export function isRenderable(event: ObsEvent): boolean {
  if (event.kind === "llm.call" && !String(event.payload?.text ?? "").trim()) {
    return false;
  }
  if (
    (event.kind === "tool.call" || event.kind === "tool.result") &&
    String(event.payload?.name ?? "").toLowerCase() === "finish"
  ) {
    return false;
  }
  return true;
}

/** Aggregate the visible timeline into per-step state (canvas highlighting). */
export function computeState(visible: ObsEvent[]): TimelineState {
  const openAgents = new Set<string>();
  const eventsByAgent: Record<string, number> = { browser: 0, coder: 0 };
  const state: TimelineState = {
    openAgents,
    jobActive: false,
    lastNode: null,
    handoff: null,
    mailRoute: null,
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
    state.handoff = eventHandoff(event);
    state.mailRoute =
      event.kind === "mailbox.message"
        ? {
            from: String(event.payload?.from ?? ""),
            to: String(event.payload?.to ?? ""),
          }
        : null;
  }
  return state;
}
