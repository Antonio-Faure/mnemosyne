import { useMemo } from "react";
import {
  Background,
  Controls,
  ReactFlow,
  type Edge,
  type NodeTypes,
} from "@xyflow/react";
import {
  BrainCircuit,
  Briefcase,
  Code2,
  Globe,
  Inbox,
  Network,
} from "lucide-react";

import type { ObsEvent, Session } from "../lib/types";
import { computeState, type NodeId } from "../lib/events";
import { AgentNode, type AgentNodeType } from "./AgentNode";

const nodeTypes: NodeTypes = { agent: AgentNode };

interface Props {
  session: Session | null;
  visible: ObsEvent[];
  focus: NodeId | "all";
  onFocus: (node: NodeId | "all") => void;
}

const COLORS = {
  orchestrator: "#60a5fa",
  browser: "#38bdf8",
  coder: "#818cf8",
  mailbox: "#fbbf24",
  llm: "#a78bfa",
  job: "#34d399",
};

export function Canvas({ session, visible, focus, onFocus }: Props) {
  const state = useMemo(() => computeState(visible), [visible]);
  const isJob = session?.family === "job";

  const nodes = useMemo<AgentNodeType[]>(() => {
    const last = state.lastNode;
    const browserActive = state.openAgents.has("browser");
    const coderActive = state.openAgents.has("coder");
    const list: AgentNodeType[] = [
      {
        id: "orchestrator",
        type: "agent",
        position: { x: 400, y: 0 },
        data: {
          label: "Orchestrateur",
          subtitle: isJob ? `job ${session?.type ?? ""}` : "file · superviseur",
          color: COLORS.orchestrator,
          icon: Network,
          active: browserActive || coderActive || state.jobActive,
          pulse: last === "orchestrator",
          badge: `${visible.length}`,
        },
      },
      {
        id: "browser",
        type: "agent",
        position: { x: 80, y: 180 },
        data: {
          label: "Navigateur",
          subtitle: browserActive
            ? "activation en cours"
            : `${state.eventsByAgent.browser ?? 0} événements`,
          color: COLORS.browser,
          icon: Globe,
          active: browserActive,
          pulse: last === "browser",
          muted: isJob,
        },
      },
      {
        id: "mailbox",
        type: "agent",
        position: { x: 400, y: 190 },
        data: {
          label: "Mailbox",
          subtitle: "messages entre agents",
          color: COLORS.mailbox,
          icon: Inbox,
          pulse: last === "mailbox",
          badge: `${state.mailboxMessages}`,
          muted: isJob,
        },
      },
      {
        id: "coder",
        type: "agent",
        position: { x: 720, y: 180 },
        data: {
          label: "Codeur",
          subtitle: coderActive
            ? "activation en cours"
            : `${state.eventsByAgent.coder ?? 0} événements`,
          color: COLORS.coder,
          icon: Code2,
          active: coderActive,
          pulse: last === "coder",
          muted: isJob,
        },
      },
      {
        id: "llm",
        type: "agent",
        position: { x: 400, y: 380 },
        data: {
          label: "LLM",
          subtitle: `${state.llmCalls} appels · ${state.toolCalls} outils`,
          color: COLORS.llm,
          icon: BrainCircuit,
          pulse: last === "llm",
          badge: `${state.llmCalls}`,
          muted: isJob,
        },
      },
    ];
    if (isJob) {
      list.push({
        id: "job",
        type: "agent",
        position: { x: 80, y: 380 },
        data: {
          label: `Job · ${session?.type ?? ""}`,
          subtitle: state.jobActive ? "en cours" : session?.status ?? "terminé",
          color: COLORS.job,
          icon: Briefcase,
          active: state.jobActive,
          pulse: last === "job",
          badge: `${visible.length}`,
        },
      });
    }
    return list;
  }, [session, isJob, state, visible.length]);

  const edges = useMemo<Edge[]>(() => {
    const last = state.lastNode;
    const make = (
      id: string,
      source: string,
      target: string,
      sourceHandle: string,
      targetHandle: string,
      color: string,
      pulsing: boolean,
      muted: boolean,
    ): Edge => ({
      id,
      source,
      target,
      sourceHandle,
      targetHandle,
      type: "smoothstep",
      animated: pulsing && !muted,
      style: {
        stroke: color,
        strokeWidth: pulsing ? 2.1 : 1.2,
        opacity: muted ? 0.14 : pulsing ? 0.95 : 0.4,
      },
    });

    const mailboxPulse = last === "mailbox";
    const llmPulse = last === "llm";
    const orchestrationPulse = last === "orchestrator";

    const list = [
      make("o-b", "orchestrator", "browser", "b", "t", COLORS.browser, orchestrationPulse, isJob),
      make("o-c", "orchestrator", "coder", "b", "t", COLORS.coder, orchestrationPulse, isJob),
      make("b-m", "browser", "mailbox", "sr", "l", COLORS.mailbox, mailboxPulse, isJob),
      make("m-c", "mailbox", "coder", "sr", "l", COLORS.mailbox, mailboxPulse, isJob),
      make("c-m", "coder", "mailbox", "sl", "r", COLORS.mailbox, mailboxPulse, isJob),
      make("m-b", "mailbox", "browser", "sl", "r", COLORS.mailbox, mailboxPulse, isJob),
      make("b-l", "browser", "llm", "b", "t", COLORS.llm, llmPulse, isJob),
      make("c-l", "coder", "llm", "b", "t", COLORS.llm, llmPulse, isJob),
    ];
    if (isJob) {
      list.push(
        make("o-j", "orchestrator", "job", "b", "t", COLORS.job, orchestrationPulse || state.jobActive, false),
      );
    }
    return list;
  }, [isJob, state.lastNode, state.jobActive]);

  return (
    <div className="h-full w-full">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        fitView
        fitViewOptions={{ padding: 0.22 }}
        nodesDraggable={false}
        nodesConnectable={false}
        elementsSelectable={false}
        panOnScroll
        zoomOnScroll
        minZoom={0.45}
        maxZoom={1.5}
        proOptions={{ hideAttribution: true }}
        onNodeClick={(_, node) => onFocus(node.id as NodeId)}
        onPaneClick={() => onFocus("all")}
        className="bg-ink-900"
      >
        <Background color="#1b2534" gap={24} size={1} />
        <Controls
          showInteractive={false}
          className="!rounded-lg !border !border-ink-600 !bg-ink-800 [&_button]:!border-ink-600 [&_button]:!bg-ink-800 [&_button]:!text-slate-300"
        />
      </ReactFlow>
      {focus !== "all" && (
        <div className="pointer-events-none absolute bottom-3 left-1/2 -translate-x-1/2 rounded-full border border-ink-600 bg-ink-850/90 px-3 py-1 text-[11px] text-slate-400">
          nœud « {focus} » sélectionné — cliquez le fond pour revenir au flux global
        </div>
      )}
    </div>
  );
}
