import { useQuery } from "@tanstack/react-query";
import { budgetApi } from "@shared/api/client";

interface Props {
  profile: string;
}

export function BudgetPanel({ profile }: Props) {
  const { data, isLoading } = useQuery({
    queryKey:        ["budget", profile],
    queryFn:         () => budgetApi.get(profile),
    refetchInterval: 30000,
  });

  if (isLoading) return <div className="text-xs text-text-muted-2">Loading…</div>;
  if (!data) return null;

  const { limits, recent_10_tasks: r } = data;

  const usageStats = [
    { v: String(r.task_count),              k: "Tasks"      },
    { v: r.total_tokens.toLocaleString(),   k: "Tokens"     },
    { v: `$${r.total_cost_usd.toFixed(4)}`, k: "Cost"       },
    {
      v: r.task_count
        ? `$${(r.total_cost_usd / r.task_count).toFixed(4)}`
        : "—",
      k: "Avg / Task",
    },
  ];

  const limitRows = [
    {
      label: "Max Tokens / Task",
      value: limits.max_tokens_per_task === 0
        ? "Unlimited"
        : limits.max_tokens_per_task.toLocaleString(),
    },
    {
      label: "Max Cost / Task",
      value: limits.max_cost_per_task === 0
        ? "Unlimited"
        : `$${limits.max_cost_per_task}`,
    },
  ];

  return (
    <div className="flex flex-col gap-[14px]">
      <div>
        <div className="text-2xs text-text-muted-3 uppercase tracking-[1.2px] font-semibold mb-[8px]">
          Usage (Last 10 Tasks)
        </div>
        <div className="grid grid-cols-2 gap-[9px]">
          {usageStats.map(({ v, k }) => (
            <div key={k} className="border border-border rounded-node bg-bg-elevated px-[11px] py-[9px]">
              <div className="text-stat font-semibold text-text-bright">{v}</div>
              <div className="text-xs text-text-muted-2 mt-[2px]">{k}</div>
            </div>
          ))}
        </div>
      </div>

      <div>
        <div className="text-2xs text-text-muted-3 uppercase tracking-[1.2px] font-semibold mb-[8px]">
          Limits
        </div>
        <div className="flex flex-col gap-[5px]">
          {limitRows.map(({ label, value }) => (
            <div
              key={label}
              className="flex items-center justify-between border border-border rounded-node bg-bg-elevated px-[11px] py-[9px]"
            >
              <span className="text-xs text-text-dim">{label}</span>
              <span className="text-xs text-text-sub font-medium">{value}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
