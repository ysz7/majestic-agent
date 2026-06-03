import { useMutation, useQueryClient } from "@tanstack/react-query";
import type { Node, NodeProps } from "@xyflow/react";
import { Handle, Position } from "@xyflow/react";
import { Clock, Pause, Play, Trash2 } from "lucide-react";
import { cronApi } from "@shared/api/client";

type CronNodeData = {
  id:       string;
  schedule: string;
  task:     string;
  active:   boolean;
  agent:    string;
  last_run: string | null;
  profile:  string;
};

export type CronNodeType = Node<CronNodeData, "cronNode">;

function fmtDate(iso: string | null): string {
  if (!iso) return "never";
  try {
    return new Date(iso).toLocaleDateString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
  } catch {
    return iso;
  }
}

export function CronNode({ data }: NodeProps<CronNodeType>) {
  const qc = useQueryClient();

  const toggle = useMutation({
    mutationFn: () =>
      cronApi.update(data.profile, data.id, { active: !data.active }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["cron", data.profile] }),
  });

  const remove = useMutation({
    mutationFn: () => cronApi.remove(data.profile, data.id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["cron", data.profile] }),
  });

  return (
    <div
      style={{ width: 200 }}
      className={`flex flex-col gap-[7px] rounded-node border bg-node-gradient px-[12px] py-[10px] text-xs transition-opacity ${
        data.active ? "border-border opacity-100" : "border-border opacity-50"
      }`}
    >
      <Handle type="target" position={Position.Left} style={{ opacity: 0 }} />

      {/* Header */}
      <div className="flex items-center gap-[6px]">
        <Clock size={11} className="text-text-muted-2 flex-shrink-0" />
        <span className="font-mono text-[11px] text-text-dim leading-none truncate flex-1">
          {data.schedule}
        </span>
        <span
          className={`w-[6px] h-[6px] rounded-full flex-shrink-0 ${
            data.active ? "bg-[#4ade80]" : "bg-[#565656]"
          }`}
        />
      </div>

      {/* Task text */}
      <div className="text-[11px] text-text-muted-2 leading-[1.5] line-clamp-2 min-h-[30px]">
        {data.task || <span className="italic text-text-muted-3">No task set</span>}
      </div>

      {/* Last run */}
      <div className="text-2xs text-text-muted-3">
        Last run: {fmtDate(data.last_run)}
      </div>

      {/* Actions */}
      <div className="flex items-center gap-[5px] pt-[2px] border-t border-border">
        <button
          onClick={() => toggle.mutate()}
          disabled={toggle.isPending}
          title={data.active ? "Pause" : "Resume"}
          className="flex items-center justify-center w-[22px] h-[22px] rounded-[5px] border border-border bg-bg-surface hover:bg-bg-elevated text-text-muted-2 hover:text-text-sub transition-colors"
        >
          {data.active ? <Pause size={10} /> : <Play size={10} />}
        </button>
        <button
          onClick={() => { if (confirm(`Delete cron "${data.schedule}"?`)) remove.mutate(); }}
          disabled={remove.isPending}
          title="Delete"
          className="flex items-center justify-center w-[22px] h-[22px] rounded-[5px] border border-border bg-bg-surface hover:bg-bg-elevated text-text-muted-3 hover:text-red-400 transition-colors ml-auto"
        >
          <Trash2 size={10} />
        </button>
      </div>

      <Handle type="source" position={Position.Right} style={{ opacity: 0 }} />
    </div>
  );
}
