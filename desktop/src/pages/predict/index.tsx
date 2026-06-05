import { useState, useEffect } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { TrendingUp, Loader2, ArrowUp, ArrowDown, ArrowRight, Anchor } from "lucide-react";
import { predictApi } from "@shared/api/client";
import { useAgentStore } from "@store/agentStore";
import type { PredictionItem } from "@shared/api/types";
import { cn } from "@shared/lib/cn";

function dirIcon(dir: string) {
  if (dir === "up")   return <ArrowUp   size={12} className="text-green-400" />;
  if (dir === "down") return <ArrowDown size={12} className="text-red-400" />;
  return <ArrowRight size={12} className="text-text-muted-2" />;
}

function probColor(p: number): string {
  if (p >= 70) return "#4ade80";
  if (p >= 50) return "#fbbf24";
  return "#f87171";
}

function PredictionCard({ item }: { item: PredictionItem }) {
  const cs = item.cross_sector;
  return (
    <div className="rounded-[12px] border border-border bg-node-gradient px-[13px] py-[11px] flex flex-col gap-[7px]">
      {/* Header */}
      <div className="flex items-start gap-[9px]">
        <div className="flex items-center gap-[5px] mt-[1px] flex-shrink-0">
          {dirIcon(item.direction)}
        </div>
        <div className="flex-1 min-w-0">
          <div className="text-md text-text-sub leading-[1.35]">{item.prediction}</div>
          <div className="flex items-center gap-[6px] mt-[3px]">
            <span className="text-xs text-text-muted-2">{item.niche}</span>
            {item.anchor && (
              <span className="flex items-center gap-[2px] text-[8px] text-text-muted-3 uppercase tracking-[0.5px] border border-border rounded-[4px] px-[4px] py-[1px]">
                <Anchor size={7} /> anchor
              </span>
            )}
            {item.horizon && (
              <span className="text-[8px] text-text-muted-3 border border-border rounded-[4px] px-[4px] py-[1px]">
                {item.horizon}
              </span>
            )}
          </div>
        </div>
        <span className="text-md font-semibold flex-shrink-0" style={{ color: probColor(item.probability) }}>
          {item.probability}%
        </span>
      </div>

      {/* Reason */}
      <p className="text-xs text-text-dim leading-[1.5]">{item.reason}</p>

      {/* Evidence */}
      {item.evidence?.length ? (
        <ul className="flex flex-col gap-[2px]">
          {item.evidence.map((e, i) => (
            <li key={i} className="text-[9px] text-text-muted-2 leading-[1.4] pl-[8px] border-l border-border">
              {e}
            </li>
          ))}
        </ul>
      ) : null}

      {/* Cross-sector + trend */}
      <div className="flex flex-wrap items-center gap-x-[12px] gap-y-[3px] pt-[2px]">
        {cs?.niche && (
          <span className="flex items-center gap-[4px] text-[9px] text-text-muted-2">
            <span className="text-text-muted-3 uppercase tracking-[0.5px]">cross-sector</span>
            {dirIcon(cs.direction ?? "flat")}
            {cs.niche} ({cs.probability ?? "?"}%)
            {cs.note ? <span className="text-text-muted-3">— {cs.note}</span> : null}
          </span>
        )}
        {item.trend && (
          <span className="text-[9px] text-text-muted-2">
            <span className="text-text-muted-3 uppercase tracking-[0.5px]">trend </span>
            {item.trend}
          </span>
        )}
      </div>
    </div>
  );
}

export function PredictPage() {
  const activeProfile = useAgentStore((s) => s.activeProfile);
  const qc = useQueryClient();
  const [selectedDate, setSelectedDate] = useState<string | null>(null);

  const reports = useQuery({
    queryKey: ["predict", activeProfile],
    queryFn:  () => predictApi.list(activeProfile!),
    enabled:  !!activeProfile,
  });

  useEffect(() => {
    const list = reports.data?.reports ?? [];
    if (!selectedDate && list.length) setSelectedDate(list[0].date);
  }, [reports.data, selectedDate]);

  const report = useQuery({
    queryKey: ["predict-report", activeProfile, selectedDate],
    queryFn:  () => predictApi.get(activeProfile!, selectedDate!),
    enabled:  !!activeProfile && !!selectedDate,
  });

  const run = useMutation({
    mutationFn: () => predictApi.run(activeProfile!, 30),
    onSuccess:  (data) => {
      qc.invalidateQueries({ queryKey: ["predict", activeProfile] });
      setSelectedDate(data.date);
      qc.setQueryData(["predict-report", activeProfile, data.date], data);
    },
  });

  const items = report.data?.items ?? [];
  const reportList = reports.data?.reports ?? [];

  return (
    <div className="w-full h-full flex flex-col">
      <div className="flex items-center justify-between px-[14px] py-[11px] flex-shrink-0">
        <div className="flex items-center gap-[8px]">
          <TrendingUp size={14} className="text-text-sub" />
          <span className="text-md text-text-sub">Predictions</span>
          {reportList.length > 0 && (
            <select
              value={selectedDate ?? ""}
              onChange={(e) => setSelectedDate(e.target.value)}
              className="ml-[6px] bg-bg-elevated border border-border rounded-[7px] px-[8px] py-[4px] text-xs text-text-dim outline-none focus:border-border-strong"
            >
              {reportList.map((r) => (
                <option key={r.date} value={r.date}>{r.date} ({r.count})</option>
              ))}
            </select>
          )}
        </div>
        <button
          onClick={() => run.mutate()}
          disabled={run.isPending || !activeProfile}
          className={cn(
            "flex items-center gap-[6px] px-[11px] py-[6px] rounded-[8px] border text-xs transition-colors",
            "border-border text-text-dim hover:text-text-sub hover:border-border-strong disabled:opacity-40",
          )}
        >
          {run.isPending ? <Loader2 size={12} className="animate-spin" /> : <TrendingUp size={12} />}
          {run.isPending ? "Forecasting…" : "Generate"}
        </button>
      </div>

      <div className="flex-1 overflow-y-auto px-[14px] pb-[14px]">
        {run.isError && (
          <div className="text-xs text-red-300 mb-[10px]">
            {(run.error as Error)?.message ?? "Generation failed"}
          </div>
        )}

        {run.isPending ? (
          <div className="h-full flex flex-col items-center justify-center gap-[10px] text-text-muted-2">
            <Loader2 size={22} className="animate-spin" />
            <span className="text-xs">Synthesizing signals & cross-sector links…</span>
          </div>
        ) : !activeProfile ? (
          <Empty text="No active profile." />
        ) : report.isLoading && selectedDate ? (
          <div className="text-xs text-text-muted-2">Loading…</div>
        ) : items.length === 0 ? (
          <Empty text="No predictions yet. Click Generate to forecast from your intelligence corpus." />
        ) : (
          <div className="flex flex-col gap-[8px] max-w-[760px]">
            {items.map((it, i) => <PredictionCard key={i} item={it} />)}
          </div>
        )}
      </div>
    </div>
  );
}

function Empty({ text }: { text: string }) {
  return (
    <div className="h-full flex items-center justify-center">
      <span className="text-xs text-text-muted-2 text-center max-w-[280px] leading-[1.6]">{text}</span>
    </div>
  );
}
