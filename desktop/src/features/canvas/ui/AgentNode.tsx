import { Handle, Position } from "@xyflow/react";
import type { Node, NodeProps } from "@xyflow/react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Bot } from "lucide-react";
import { cn } from "@shared/lib/cn";
import { agentsApi } from "@shared/api/client";

type AgentNodeData = {
  label: string;
  profile: string;
  status: "running" | "idle" | "stopped";
  port: number;
  pid?: number;
};

type AgentNodeType = Node<AgentNodeData, "agentNode">;

const STATUS_COLOR: Record<string, string> = {
  running: "#4ade80",
  idle:    "#fbbf24",
  stopped: "#565656",
};

const HANDLE_STYLE = {
  background: "#0c0c0c",
  border: "1.4px solid rgba(255,255,255,0.5)",
  width: 8,
  height: 8,
};

export function AgentNode({ data, selected }: NodeProps<AgentNodeType>) {
  const qc = useQueryClient();

  const stop = useMutation({
    mutationFn: () => agentsApi.stop(data.profile),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["agents-running"] }),
  });

  const start = useMutation({
    mutationFn: () => agentsApi.start(data.profile),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["agents-running"] }),
  });

  return (
    <div
      className={cn(
        "rounded-node border bg-node-gradient",
        selected ? "border-border-strong" : "border-border",
      )}
      style={{ width: 170, minHeight: 90 }}
    >
      <Handle type="target" position={Position.Left}  style={HANDLE_STYLE} />
      <Handle type="source" position={Position.Right} style={HANDLE_STYLE} />

      {/* header */}
      <div className="flex items-center gap-[7px] px-[11px] py-[9px] border-b border-border">
        <Bot size={11} className="text-text-dim flex-shrink-0" />
        <span className="flex-1 truncate text-base text-text-sub">{data.label}</span>
        <span
          className="w-[6px] h-[6px] rounded-dot flex-shrink-0"
          style={{ background: STATUS_COLOR[data.status] ?? "#565656" }}
        />
      </div>

      {/* body */}
      <div className="px-[11px] py-[9px] flex flex-col gap-[6px]">
        <div className="text-2xs text-text-muted-3 uppercase tracking-[1.2px] font-semibold">
          Profile
        </div>
        <div className="text-xs text-text-dim">{data.profile}</div>

        {data.status === "running" && (
          <div className="flex items-center justify-between mt-[2px]">
            <span className="text-xs text-text-muted-2">:{data.port}</span>
            <button
              onClick={() => stop.mutate()}
              disabled={stop.isPending}
              className="text-xs text-text-muted-2 hover:text-text-sub px-2 py-[2px] rounded-[5px] border border-border hover:border-border-strong transition-colors"
            >
              Stop
            </button>
          </div>
        )}

        {data.status === "stopped" && (
          <button
            onClick={() => start.mutate()}
            disabled={start.isPending}
            className="mt-[2px] text-xs text-text-dim bg-bg-elevated border border-border rounded-[7px] px-2 py-[5px] hover:border-border-strong transition-colors text-center"
          >
            Start
          </button>
        )}
      </div>
    </div>
  );
}
