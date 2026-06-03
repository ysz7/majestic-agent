import { Handle, Position } from "@xyflow/react";
import type { Node, NodeProps } from "@xyflow/react";
import { Zap } from "lucide-react";

type ZapNodeData = Record<string, never>;
type ZapNodeType = Node<ZapNodeData, "zapNode">;

const HANDLE_STYLE = {
  background: "#0c0c0c",
  border: "1.4px solid rgba(255,255,255,0.5)",
  width: 8,
  height: 8,
};

export function ZapNode({ selected }: NodeProps<ZapNodeType>) {
  return (
    <div
      className="w-[38px] h-[38px] rounded-[11px] border border-border-strong bg-zap-gradient flex items-center justify-center text-text-faint"
      style={{ boxShadow: selected ? "0 0 0 1.5px rgba(255,255,255,0.25)" : undefined }}
    >
      <Handle type="target" position={Position.Left}  style={HANDLE_STYLE} />
      <Zap size={14} />
      <Handle type="source" position={Position.Right} style={HANDLE_STYLE} />
    </div>
  );
}
