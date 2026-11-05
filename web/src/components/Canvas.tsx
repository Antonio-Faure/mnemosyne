import { useMemo } from "react";
import {
  Background,
  Controls,
  ReactFlow,
  type Edge,
  type NodeTypes,
} from "@xyflow/react";
import { motion } from "framer-motion";
import {
  Briefcase,
  Code2,
  Globe,
  Inbox,
  Network,
  Sparkles,
} from "lucide-react";

import type { ObsEvent, Session } from "../lib/types";
import { computeState, type NodeId } from "../lib/events";
import { formatNumber } from "../lib/format";
import { AgentNode, type AgentNodeType } from "./AgentNode";

const nodeTypes: NodeTypes = { agent: AgentNode };

interface Props {
  session: Session | null;
  visible: ObsEvent[];
  onFocus: (node: NodeId | null) => void;
}

const COLORS = {
  orchestrator: "#60a5fa",
  browser: "#38bdf8",
  coder: "#818cf8",
  mailbox: "#fbbf24",
  job: "#34d399",
};

export function Canvas({ session, visible, onFocus }: Props) {
  const state = useMemo(() => computeState(visible), [visible]);
  const isJob = session?.family === "job";

  const lastLlm = useMemo(
    () => [...visible].reverse().find((event) => event.kind === "llm.call") ?? null,
    [visible],
  );
  const recentTools = useMemo(() => {
    const names: string[] = [];
    for (const event of [...visible].reverse()) {
      if (event.kind !== "tool.call") continue;
      const name = String(event.payload?.name ?? "outil");
      if (!names.includes(name)) names.push(name);
      if (names.length === 3) break;
    }
    return names;
  }, [visible]);

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
        position: { x: 80, y: 190 },
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
        position: { x: 400, y: 200 },
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
        position: { x: 720, y: 190 },
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
    ];
    if (isJob) {
      list.push({
        id: "job",
        type: "agent",
        position: { x: 80, y: 400 },
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
    const orchestrationPulse = last === "orchestrator";

    const list = [
      make("o-b", "orchestrator", "browser", "b", "t", COLORS.browser, orchestrationPulse, isJob),
      make("o-c", "orchestrator", "coder", "b", "t", COLORS.coder, orchestrationPulse, isJob),
      make("b-m", "browser", "mailbox", "sr", "l", COLORS.mailbox, mailboxPulse, isJob),
      make("m-c", "mailbox", "coder", "sr", "l", COLORS.mailbox, mailboxPulse, isJob),
      make("c-m", "coder", "mailbox", "sl", "r", COLORS.mailbox, mailboxPulse, isJob),
      make("m-b", "mailbox", "browser", "sl", "r", COLORS.mailbox, mailboxPulse, isJob),
    ];
    if (isJob) {
      list.push(
        make(
          "o-j",
          "orchestrator",
          "job",
          "b",
          "t",
          COLORS.job,
          orchestrationPulse || state.jobActive,
          false,
        ),
      );
    }
    return list;
  }, [isJob, state.lastNode, state.jobActive]);

  return (
    <div className="relative h-full w-full">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
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
        onNodeClick={(_, node) => onFocus(node.id as NodeId)}
        onPaneClick={() => onFocus(null)}
        className="bg-ink-900"
      >
        <Background color="#1b2534" gap={24} size={1} />
        <Controls
          showInteractive={false}
          className="!rounded-lg !border !border-ink-600 !bg-ink-800 [&_button]:!border-ink-600 [&_button]:!bg-ink-800 [&_button]:!text-slate-300"
        />
      </ReactFlow>

      {/* The LLM is not a step: its activity floats over the Make canvas and
          belongs to the browser/coder step currently running. */}
      <motion.div
        key={lastLlm?.id ?? "idle"}
        initial={{ opacity: 0.65, y: -4 }}
        animate={{ opacity: 1, y: 0 }}
        className="pointer-events-none absolute right-4 top-4 w-[270px] rounded-xl border border-ink-600 bg-ink-850/90 p-3 shadow-xl backdrop-blur"
      >
        <div className="flex items-center gap-1.5 text-[10px] uppercase tracking-[0.18em] text-slate-400">
          <Sparkles size={12} className="text-violet-300" />
          LLM
          <span className="ml-auto truncate font-mono text-[10px] normal-case tracking-normal text-violet-200">
            {String(lastLlm?.payload?.model ?? "—")}
          </span>
        </div>
        <div className="mt-2 grid grid-cols-3 gap-1 text-center">
          <div>
            <div className="font-mono text-[13px] text-slate-200">
              {formatNumber(lastLlm?.payload?.prompt_tokens)}
            </div>
            <div className="text-[9px] uppercase tracking-wider text-slate-500">prompt</div>
          </div>
          <div>
            <div className="font-mono text-[13px] text-slate-200">
              {formatNumber(lastLlm?.payload?.completion_tokens)}
            </div>
            <div className="text-[9px] uppercase tracking-wider text-slate-500">sortie</div>
          </div>
          <div>
            <div className="font-mono text-[13px] text-slate-200">
              {formatNumber(lastLlm?.payload?.cached_tokens)}
            </div>
            <div className="text-[9px] uppercase tracking-wider text-slate-500">cache</div>
          </div>
        </div>
        <div className="mt-2 flex flex-wrap items-center gap-1">
          {recentTools.length ? (
            recentTools.map((name) => (
              <span
                key={name}
                className="rounded bg-violet-500/10 px-1.5 py-[1px] text-[10px] text-violet-200"
              >
                {name}
              </span>
            ))
          ) : (
            <span className="text-[10px] text-slate-500">aucun appel pour l'instant</span>
          )}
          {lastLlm?.payload?.messages_count ? (
            <span className="ml-auto font-mono text-[9px] text-slate-500">
              {lastLlm.payload.messages_count} msg
            </span>
          ) : null}
        </div>
      </motion.div>
    </div>
  );
}
