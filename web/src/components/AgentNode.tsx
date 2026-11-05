import { Handle, Position, type Node, type NodeProps } from "@xyflow/react";
import { motion } from "framer-motion";
import type { LucideIcon } from "lucide-react";

export type AgentNodeData = {
  label: string;
  subtitle?: string;
  color: string;
  icon: LucideIcon;
  active?: boolean;
  pulse?: boolean;
  badge?: string;
  muted?: boolean;
};

export type AgentNodeType = Node<AgentNodeData, "agent">;

const HANDLE = "!h-1.5 !w-1.5 !border-0 !bg-transparent";

export function AgentNode({ data }: NodeProps<AgentNodeType>) {
  const Icon = data.icon;
  const lit = data.active || data.pulse;
  return (
    <motion.div
      animate={data.pulse ? { scale: [1, 1.03, 1] } : { scale: 1 }}
      transition={{ duration: 0.45 }}
      className={`w-[196px] rounded-xl border px-3 py-2.5 ${
        data.muted ? "opacity-45" : "opacity-100"
      }`}
      style={{
        borderColor: lit ? data.color : "#243045",
        background: "rgba(14, 20, 27, 0.94)",
        boxShadow: lit
          ? `0 0 0 1px ${data.color}55, 0 0 26px ${data.color}2e`
          : "0 8px 24px rgba(0, 0, 0, 0.25)",
      }}
    >
      <Handle id="t" type="target" position={Position.Top} className={HANDLE} />
      <Handle id="l" type="target" position={Position.Left} className={HANDLE} />
      <Handle id="r" type="target" position={Position.Right} className={HANDLE} />
      <Handle id="b" type="source" position={Position.Bottom} className={HANDLE} />
      <Handle id="sl" type="source" position={Position.Left} className={HANDLE} />
      <Handle id="sr" type="source" position={Position.Right} className={HANDLE} />

      <div className="flex items-center gap-2">
        <span
          className="grid h-7 w-7 shrink-0 place-items-center rounded-lg"
          style={{ background: `${data.color}20`, color: data.color }}
        >
          <Icon size={15} />
        </span>
        <div className="min-w-0">
          <div className="truncate text-[13px] font-semibold text-slate-100">
            {data.label}
          </div>
          {data.subtitle && (
            <div className="truncate text-[10.5px] text-slate-400">{data.subtitle}</div>
          )}
        </div>
        {data.badge && (
          <span className="ml-auto rounded-md bg-ink-700 px-1.5 py-0.5 font-mono text-[10px] text-slate-300">
            {data.badge}
          </span>
        )}
      </div>

      {lit && (
        <motion.div
          className="mt-2 h-[3px] rounded-full"
          style={{ background: data.color }}
          initial={{ opacity: 0.35 }}
          animate={{ opacity: [0.35, 1, 0.35] }}
          transition={{ repeat: Infinity, duration: 1.5 }}
        />
      )}
    </motion.div>
  );
}
