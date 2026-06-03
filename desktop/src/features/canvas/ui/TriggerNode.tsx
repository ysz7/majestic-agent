import { Handle, Position } from "@xyflow/react";
import type { Node, NodeProps } from "@xyflow/react";
import { Clock, MousePointer, Play } from "lucide-react";
import { cn } from "@shared/lib/cn";

type TriggerNodeData = {
  subtype:  "manual" | "cron";
  label?:   string;
  schedule?: string;
};

type TriggerNodeType = Node<TriggerNodeData, "triggerNode">;

const TRIGGER_COLOR = "#4ade80";

const HANDLE_STYLE = {
  background:  "#0c0c0c",
  border:      "1.4px solid rgba(255,255,255,0.5)",
  width:       8,
  height:      8,
};

export function TriggerNode({ data, selected }: NodeProps<TriggerNodeType>) {
  const isCron = data.subtype === "cron";

  return (
    <div
      className={cn(
        "rounded-node border bg-node-gradient",
        selected ? "border-border-strong" : "border-border",
      )}
      style={{ width: 160, minHeight: 72 }}
    >
      <Handle type="source" position={Position.Right} style={HANDLE_STYLE} />

      {/* Header */}
      <div className="flex items-center gap-[7px] px-[11px] py-[9px] border-b border-border">
        {isCron
          ? <Clock       size={11} style={{ color: TRIGGER_COLOR }} className="flex-shrink-0" />
          : <MousePointer size={11} style={{ color: TRIGGER_COLOR }} className="flex-shrink-0" />
        }
        <span className="flex-1 truncate text-base text-text-sub">
          {isCron ? "Schedule" : "Manual"}
        </span>
        <span
          className="w-[5px] h-[5px] rounded-dot flex-shrink-0"
          style={{ background: TRIGGER_COLOR }}
        />
      </div>

      {/* Body */}
      <div className="px-[11px] py-[9px]">
        {isCron ? (
          <div className="font-mono text-xs text-text-dim">
            {data.schedule ?? "0 9 * * *"}
          </div>
        ) : (
          <button
            className="flex items-center gap-[5px] text-xs text-text-muted-2 hover:text-text-sub transition-colors"
            onClick={(e) => e.stopPropagation()}
          >
            <Play size={9} style={{ color: TRIGGER_COLOR }} />
            Run now
          </button>
        )}
      </div>
    </div>
  );
}
