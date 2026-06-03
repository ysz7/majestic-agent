import { Handle, Position } from "@xyflow/react";
import type { Node, NodeProps } from "@xyflow/react";
import { FileText } from "lucide-react";
import { cn } from "@shared/lib/cn";

type FileNodeData = { name: string; path: string; size: number; type: string };
type FileNodeType = Node<FileNodeData, "fileNode">;

function fmtSize(b: number): string {
  if (b < 1024) return `${b}B`;
  if (b < 1024 * 1024) return `${(b / 1024).toFixed(1)}KB`;
  return `${(b / (1024 * 1024)).toFixed(1)}MB`;
}

export function FileNode({ data, selected }: NodeProps<FileNodeType>) {
  return (
    <div
      className={cn(
        "rounded-node border bg-node-gradient",
        selected ? "border-border-strong" : "border-border",
      )}
      style={{ width: 140 }}
    >
      <Handle
        type="target"
        position={Position.Left}
        style={{ background: "#0c0c0c", border: "1.4px solid rgba(255,255,255,0.5)", width: 8, height: 8 }}
      />

      <div className="flex items-center gap-[7px] px-[11px] py-[9px] border-b border-border">
        <FileText size={11} className="text-text-dim flex-shrink-0" />
        <span className="flex-1 truncate text-base text-text-sub">{data.name}</span>
      </div>

      <div className="px-[11px] py-[9px] flex flex-col gap-[4px]">
        <div className="text-xs text-text-muted-2 truncate">{data.type}</div>
        <div className="text-xs text-text-muted-3">{fmtSize(data.size)}</div>
      </div>
    </div>
  );
}
