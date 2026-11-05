import { useMemo } from "react";
import {
  Background,
  Controls,
  ReactFlow,
  type Edge,
  type NodeTypes,
} from "@xyflow/react";
import {
  Briefcase,
  Code2,
  Cog,
  Globe,
  Inbox,
  Network,
} from "lucide-react";

import type { ObsEvent, Session } from "../lib/types";
import { computeState, type NodeId } from "../lib/events";
import { AgentNode, type AgentNodeType } from "./AgentNode";
import { BeadEdge } from "./BeadEdge";

const nodeTypes: NodeTypes = { agent: AgentNode };
const edgeTypes = { bead: BeadEdge };

interface Props {
  session: Session | null;
  visible: ObsEvent[];
  onFocus: (node: NodeId | null) => void;
}

const COLORS = {
  agency: "#f59e0b",
  orchestrator: "#60a5fa",
  browser: "#38bdf8",
  coder: "#818cf8",
  mailbox: "#fbbf24",
  job: "#34d399",
};

export function Canvas({ session, visible, onFocus }: Props) {
  const state = useMemo(() => computeState(visible), [visible]);
  const isJob = session?.family === "job";
  const isAgency = session?.type === "agency";

  const nodes = useMemo<AgentNodeType[]>(() => {
    const last = state.lastNode;
    const browserActive = state.openAgents.has("browser");
    const coderActive = state.openAgents.has("coder");
    const list: AgentNodeType[] = [
      {
        id: "agency",
        type: "agent",
        position: { x: 400, y: -120 },
        data: {
          label: "Agency",
          subtitle: isAgency
            ? `moteur de la file · ${session?.status ?? ""}`
            : "moteur de la file · ~2 min",
          color: COLORS.agency,
          icon: Cog,
          active: isAgency && (state.jobActive || last === "job"),
        },
      },
      {
        id: "orchestrator",
        type: "agent",
        position: { x: 400, y: 0 },
        data: {
          label: "Orchestrateur",
          subtitle: isJob ? `job ${session?.type ?? ""}` : "file · superviseur",
          color: COLORS.orchestrator,
          icon: Network,
          active: last === "orchestrator",
          badge: `${visible.length}`,
        },
      },
      {
        id: "browser",
        type: "agent",
        position: { x: 80, y: 190 },
        data: {
          label: "Navigateur",
          subtitle: browserActive
            ? "activation en cours"
            : `${state.eventsByAgent.browser ?? 0} événements`,
          color: COLORS.browser,
          icon: Globe,
          active: last === "browser",
          muted: isJob,
        },
      },
      {
        id: "mailbox",
        type: "agent",
        position: { x: 400, y: 200 },
        data: {
          label: "Mailbox",
          subtitle: "messages entre agents",
          color: COLORS.mailbox,
          icon: Inbox,
          active: last === "mailbox",
          badge: `${state.mailboxMessages}`,
          muted: isJob,
        },
      },
      {
        id: "coder",
        type: "agent",
        position: { x: 720, y: 190 },
        data: {
          label: "Codeur",
          subtitle: coderActive
            ? "activation en cours"
            : `${state.eventsByAgent.coder ?? 0} événements`,
          color: COLORS.coder,
          icon: Code2,
          active: last === "coder",
          muted: isJob,
        },
      },
    ];
    if (isJob && !isAgency) {
      list.push({
        id: "job",
        type: "agent",
        position: { x: 80, y: 400 },
        data: {
          label: `Job · ${session?.type ?? ""}`,
          subtitle: state.jobActive ? "en cours" : session?.status ?? "terminé",
          color: COLORS.job,
          icon: Briefcase,
          active: last === "job",
          badge: `${visible.length}`,
        },
      });
    }
    return list;
  }, [session, isJob, state, visible.length]);

  const edges = useMemo<Edge[]>(() => {
    const make = (
      id: string,
      source: string,
      target: string,
      sourceHandle: string,
      targetHandle: string,
      color: string,
      pulsing: boolean,
      muted: boolean,
      reverse = false,
    ): Edge => ({
      id,
      source,
      target,
      sourceHandle,
      targetHandle,
      type: "bead",
      animated: pulsing && !muted,
      data: { active: pulsing && !muted, color, reverse },
      style: {
        stroke: color,
        strokeWidth: pulsing ? 2.1 : 1.2,
        opacity: muted ? 0.14 : pulsing ? 0.95 : 0.4,
      },
    });

    // One link at a time: the handoff points to (or comes back from) a single
    // agent. Never light both o→browser and o→coder.
    const handoff = state.handoff;
    const toBrowser = handoff?.agent === "browser" && handoff.direction === "to";
    const fromBrowser = handoff?.agent === "browser" && handoff.direction === "from";
    const toCoder = handoff?.agent === "coder" && handoff.direction === "to";
    const fromCoder = handoff?.agent === "coder" && handoff.direction === "from";

    // Mailbox: only the segments the message actually crosses are lit.
    const mail = state.mailRoute;
    const mailFromBrowser = mail?.from === "browser";
    const mailToBrowser = mail?.to === "browser";
    const mailFromCoder = mail?.from === "coder";
    const mailToCoder = mail?.to === "coder";

    const list = [
      make(
        "a-o",
        "agency",
        "orchestrator",
        "b",
        "t",
        COLORS.agency,
        isAgency && state.jobActive,
        false,
      ),
      make(
        "o-b",
        "orchestrator",
        "browser",
        "b",
        "t",
        COLORS.browser,
        toBrowser || fromBrowser,
        isJob,
        fromBrowser,
      ),
      make(
        "o-c",
        "orchestrator",
        "coder",
        "b",
        "t",
        COLORS.coder,
        toCoder || fromCoder,
        isJob,
        fromCoder,
      ),
      make("b-m", "browser", "mailbox", "sr", "l", COLORS.mailbox, mailFromBrowser, isJob),
      make("m-c", "mailbox", "coder", "sr", "l", COLORS.mailbox, mailToCoder, isJob),
      make("c-m", "coder", "mailbox", "sl", "r", COLORS.mailbox, mailFromCoder, isJob),
      make("m-b", "mailbox", "browser", "sl", "r", COLORS.mailbox, mailToBrowser, isJob),
    ];
    if (isJob && !isAgency) {
      list.push(
        make(
          "o-j",
          "orchestrator",
          "job",
          "b",
          "t",
          COLORS.job,
          state.jobActive,
          false,
        ),
      );
    }
    return list;
  }, [
    isAgency,
    isJob,
    state.jobActive,
    state.handoff,
    state.mailRoute,
  ]);

  return (
    <div className="relative h-full w-full">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        edgeTypes={edgeTypes}
        fitView
        fitViewOptions={{ padding: 0.24 }}
        nodesDraggable={false}
        nodesConnectable={false}
        elementsSelectable={false}
        panOnScroll
        zoomOnScroll
        minZoom={0.45}
        maxZoom={1.5}
        proOptions={{ hideAttribution: true }}
        onNodeClick={(_, node) => {
          if (node.id === "agency") {
            if (session?.type === "agency") onFocus("job");
            return;
          }
          onFocus(node.id as NodeId);
        }}
        onPaneClick={() => onFocus(null)}
        className="bg-ink-900"
      >
        <Background color="#1b2534" gap={24} size={1} />
        <Controls
          showInteractive={false}
          className="!rounded-lg !border !border-ink-600 !bg-ink-800 [&_button]:!border-ink-600 [&_button]:!bg-ink-800 [&_button]:!text-slate-300"
        />
      </ReactFlow>
    </div>
  );
}
