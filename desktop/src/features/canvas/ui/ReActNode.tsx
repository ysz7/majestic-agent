import type { Node, NodeProps } from "@xyflow/react";
import { Handle, Position } from "@xyflow/react";
import { Brain, Wrench, Eye } from "lucide-react";

export type ReActStepType = "REASON" | "TOOL_CALL" | "OBSERVE";

export type ReActNodeData = {
  stepType: ReActStepType;
  content:  string;
  active:   boolean;   // latest node → pulse border
  fading:   boolean;   // removal animation
};

export type ReActNodeType = Node<ReActNodeData, "reactNode">;

const STEP_META: Record<ReActStepType, { icon: React.ElementType; color: string; label: string }> = {
  REASON:    { icon: Brain,   color: "#a78bfa", label: "Reason"  },
  TOOL_CALL: { icon: Wrench,  color: "#fbbf24", label: "Tool"    },
  OBSERVE:   { icon: Eye,     color: "#64748b", label: "Observe" },
};

export function ReActNode({ data }: NodeProps<ReActNodeType>) {
  const meta = STEP_META[data.stepType] ?? STEP_META.REASON;
  const Icon = meta.icon;

  return (
    <div
      style={{
        width: 175,
        opacity: data.fading ? 0 : 1,
        transition: "opacity 0.5s ease",
        boxShadow: data.active
          ? `0 0 0 1.5px ${meta.color}55, 0 0 12px ${meta.color}22`
          : undefined,
      }}
      className="rounded-node border border-border bg-node-gradient flex flex-col gap-[6px] px-[10px] py-[8px]"
    >
      <Handle type="target" position={Position.Left}  style={{ opacity: 0 }} />
      <Handle type="source" position={Position.Bottom} style={{ opacity: 0 }} />

      {/* Badge row */}
      <div className="flex items-center gap-[5px]">
        <Icon size={10} style={{ color: meta.color }} className="flex-shrink-0" />
        <span
          className="text-[10px] font-semibold uppercase tracking-[0.8px]"
          style={{ color: meta.color }}
        >
          {meta.label}
        </span>
        {data.active && (
          <span
            className="ml-auto w-[5px] h-[5px] rounded-full animate-pulse"
            style={{ background: meta.color }}
          />
        )}
      </div>

      {/* Content preview */}
      {data.content && (
        <div className="text-[11px] text-text-muted-2 leading-[1.45] line-clamp-2 break-words">
          {data.content}
        </div>
      )}
    </div>
  );
}
