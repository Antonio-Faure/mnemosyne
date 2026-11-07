import { useCallback, useEffect, useMemo, useRef } from "react";
import {
  Background,
  Controls,
  Position,
  ReactFlow,
  getViewportForBounds,
  type Edge,
  type NodeHandle,
  type NodeTypes,
  type ReactFlowInstance,
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
  /** triggers a re-fit when the floating panel opens/closes */
  panelOpen: boolean;
  /** triggers a re-fit when the docked sessions rail opens/closes */
  sidebarOpen: boolean;
}

const COLORS = {
  agency: "#f59e0b",
  orchestrator: "#60a5fa",
  browser: "#38bdf8",
  coder: "#818cf8",
  mailbox: "#fbbf24",
  job: "#34d399",
};

/** Give React Flow a size before its ResizeObserver fires: otherwise nodes
 *  (and their edges) stay `visibility:hidden` until measured — or forever when
 *  the observer misses them (background tab, panel resize). */
const NODE_WIDTH = 204;
const NODE_HEIGHT = 72;

/** Bounding box of the fixed graph layout (used to frame it without waiting
 *  for React Flow's DOM measurements). */
const GRAPH_BOUNDS = {
  x: 80,
  y: -120,
  width: 720 + NODE_WIDTH - 80,
  height: 400 + NODE_HEIGHT + 120,
};

/** Handle fallback so edges exist before (or without) DOM measurement. */
const NODE_HANDLES: NodeHandle[] = [
  { id: "t", type: "target", position: Position.Top, x: NODE_WIDTH / 2, y: 0 },
  { id: "l", type: "target", position: Position.Left, x: 0, y: NODE_HEIGHT / 2 },
  { id: "r", type: "target", position: Position.Right, x: NODE_WIDTH, y: NODE_HEIGHT / 2 },
  { id: "b", type: "source", position: Position.Bottom, x: NODE_WIDTH / 2, y: NODE_HEIGHT },
  { id: "sl", type: "source", position: Position.Left, x: 0, y: NODE_HEIGHT / 2 },
  { id: "sr", type: "source", position: Position.Right, x: NODE_WIDTH, y: NODE_HEIGHT / 2 },
];

export function Canvas({ session, visible, onFocus, panelOpen, sidebarOpen }: Props) {
  const state = useMemo(() => computeState(visible), [visible]);
  const isJob = session?.family === "job";
  const isAgency = session?.type === "agency";
  const wrapperRef = useRef<HTMLDivElement>(null);
  const flowRef = useRef<ReactFlowInstance<AgentNodeType, Edge> | null>(null);

  const fitGraph = useCallback(() => {
    const instance = flowRef.current;
    const rect = wrapperRef.current?.getBoundingClientRect();
    if (!instance || !rect) return;
    // The wrapper is already narrowed by the step panel (pr-[452px]).
    instance.setViewport(
      getViewportForBounds(
        GRAPH_BOUNDS,
        Math.max(160, rect.width),
        Math.max(160, rect.height),
        0.3,
        1.5,
        0.2,
      ),
    );
  }, []);

  useEffect(() => {
    const element = wrapperRef.current;
    if (!element) return;
    const observer = new ResizeObserver(() => {
      fitGraph();
    });
    observer.observe(element);
    const timer = window.setTimeout(fitGraph, 50);
    return () => {
      observer.disconnect();
      window.clearTimeout(timer);
    };
  }, [fitGraph]);

  // Panel toggle / window resize: do not rely on ResizeObserver alone (it is
  // throttled in background tabs and sometimes misses the change).
  useEffect(() => {
    const timer = window.setTimeout(fitGraph, 80);
    return () => window.clearTimeout(timer);
  }, [fitGraph, panelOpen, sidebarOpen]);

  useEffect(() => {
    const onResize = () => {
      window.setTimeout(fitGraph, 80);
    };
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, [fitGraph]);

  const nodes = useMemo<AgentNodeType[]>(() => {
    const last = state.lastNode;
    const browserActive = state.openAgents.has("browser");
    const coderActive = state.openAgents.has("coder");
    const list: AgentNodeType[] = [
      {
        id: "agency",
        type: "agent",
        initialWidth: NODE_WIDTH,
        initialHeight: NODE_HEIGHT,
        handles: NODE_HANDLES,
        position: { x: 400, y: -120 },
        data: {
          label: "Agency",
          subtitle: isAgency
            ? `moteur de la file · ${session?.status ?? ""}`
            : last === "agency"
              ? "mission en file"
              : "moteur de la file · ~2 min",
          color: COLORS.agency,
          icon: Cog,
          active:
            last === "agency" ||
            (isAgency && (state.jobActive || last === "job")),
        },
      },
      {
        id: "orchestrator",
        type: "agent",
        initialWidth: NODE_WIDTH,
        initialHeight: NODE_HEIGHT,
        handles: NODE_HANDLES,
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
        initialWidth: NODE_WIDTH,
        initialHeight: NODE_HEIGHT,
        handles: NODE_HANDLES,
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
        initialWidth: NODE_WIDTH,
        initialHeight: NODE_HEIGHT,
        handles: NODE_HANDLES,
        position: { x: 400, y: 200 },
        data: {
          label: "Mailbox",
          subtitle: "messages",
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
        initialWidth: NODE_WIDTH,
        initialHeight: NODE_HEIGHT,
        handles: NODE_HANDLES,
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
        initialWidth: NODE_WIDTH,
        initialHeight: NODE_HEIGHT,
        handles: NODE_HANDLES,
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
        state.lastNode === "agency" || (isAgency && state.jobActive),
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
    <div ref={wrapperRef} className="relative h-full w-full">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        edgeTypes={edgeTypes}
        onInit={(instance) => {
          flowRef.current = instance;
          fitGraph();
        }}
        nodesDraggable={false}
        nodesConnectable={false}
        elementsSelectable={false}
        panOnScroll
        zoomOnScroll
        minZoom={0.3}
        maxZoom={1.5}
        proOptions={{ hideAttribution: true }}
        onNodeClick={(_, node) => {
          if (node.id === "agency") {
            onFocus(session?.family === "job" ? "job" : "agency");
            return;
          }
          onFocus(node.id as NodeId);
        }}
        onPaneClick={() => onFocus(null)}
        className="bg-[#080c11]"
      >
        <Background color="#16202d" gap={26} size={1} />
        <Controls
          showInteractive={false}
          className="!rounded-lg !border !border-ink-600 !bg-ink-800 [&_button]:!border-ink-600 [&_button]:!bg-ink-800 [&_button]:!text-slate-300"
        />
      </ReactFlow>
    </div>
  );
}
