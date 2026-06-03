import { Handle, Position } from "@xyflow/react";
import type { Node, NodeProps } from "@xyflow/react";
import { Bot, Search, Globe, Code } from "lucide-react";
import { cn } from "@shared/lib/cn";

type ActionSubtype = "research" | "prompt" | "http" | "python";

type ActionNodeData = {
  subtype: ActionSubtype;
  label?:  string;
  query?:  string;
  prompt?: string;
  url?:    string;
};

type ActionNodeType = Node<ActionNodeData, "actionNode">;

const ACTION_COLOR = "#60a5fa";

const ICONS: Record<ActionSubtype, React.ElementType> = {
  research: Search,
  prompt:   Bot,
  http:     Globe,
  python:   Code,
};

const LABELS: Record<ActionSubtype, string> = {
  research: "Research",
  prompt:   "Prompt",
  http:     "HTTP",
  python:   "Python",
};

const HANDLE_STYLE = {
  background: "#0c0c0c",
  border:     "1.4px solid rgba(255,255,255,0.5)",
  width:      8,
  height:     8,
};

export function ActionNode({ data, selected }: NodeProps<ActionNodeType>) {
  const Icon    = ICONS[data.subtype]  ?? Bot;
  const heading = LABELS[data.subtype] ?? data.subtype;
  const preview = data.query ?? data.prompt ?? data.url ?? "";

  return (
    <div
      className={cn(
        "rounded-node border bg-node-gradient",
        selected ? "border-border-strong" : "border-border",
      )}
      style={{ width: 170, minHeight: 78 }}
    >
      <Handle type="target" position={Position.Left}  style={HANDLE_STYLE} />
      <Handle type="source" position={Position.Right} style={HANDLE_STYLE} />

      {/* Header */}
      <div className="flex items-center gap-[7px] px-[11px] py-[9px] border-b border-border">
        <Icon size={11} style={{ color: ACTION_COLOR }} className="flex-shrink-0" />
        <span className="flex-1 truncate text-base text-text-sub">{heading}</span>
      </div>

      {/* Body */}
      <div className="px-[11px] py-[9px]">
        <div className="text-xs text-text-muted-2 truncate">
          {preview ? `"${preview}"` : "No query set"}
        </div>
      </div>
    </div>
  );
}
