import { Handle, Position } from "@xyflow/react";
import type { Node, NodeProps } from "@xyflow/react";
import { Bell, FileText, Bot } from "lucide-react";
import { cn } from "@shared/lib/cn";

type OutputSubtype = "notify" | "savefile" | "agent";

type OutputNodeData = {
  subtype:  OutputSubtype;
  label?:   string;
  title?:   string;
  filename?: string;
  target?:  string;
};

type OutputNodeType = Node<OutputNodeData, "outputNode">;

const OUTPUT_COLOR = "#c084fc";

const ICONS: Record<OutputSubtype, React.ElementType> = {
  notify:   Bell,
  savefile: FileText,
  agent:    Bot,
};

const LABELS: Record<OutputSubtype, string> = {
  notify:   "Notify",
  savefile: "Save File",
  agent:    "Agent",
};

const HANDLE_STYLE = {
  background: "#0c0c0c",
  border:     "1.4px solid rgba(255,255,255,0.5)",
  width:      8,
  height:     8,
};

export function OutputNode({ data, selected }: NodeProps<OutputNodeType>) {
  const Icon    = ICONS[data.subtype]  ?? Bell;
  const heading = LABELS[data.subtype] ?? data.subtype;
  const preview = data.title ?? data.filename ?? data.target ?? "";

  return (
    <div
      className={cn(
        "rounded-node border bg-node-gradient",
        selected ? "border-border-strong" : "border-border",
      )}
      style={{ width: 152, minHeight: 72 }}
    >
      <Handle type="target" position={Position.Left} style={HANDLE_STYLE} />

      {/* Header */}
      <div className="flex items-center gap-[7px] px-[11px] py-[9px] border-b border-border">
        <Icon size={11} style={{ color: OUTPUT_COLOR }} className="flex-shrink-0" />
        <span className="flex-1 truncate text-base text-text-sub">{heading}</span>
      </div>

      {/* Body */}
      <div className="px-[11px] py-[9px]">
        <div className="text-xs text-text-muted-2 truncate">
          {preview || "Output node"}
        </div>
      </div>
    </div>
  );
}
