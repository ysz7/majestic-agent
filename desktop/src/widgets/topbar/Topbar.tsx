import { Moon } from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { agentsApi } from "@shared/api/client";
import { Badge } from "@shared/ui-kit";

export function Topbar() {
  const { data } = useQuery({
    queryKey: ["agents-running"],
    queryFn:  () => agentsApi.running(),
    refetchInterval: 5000,
  });

  const count = data?.agents.length ?? 0;

  return (
    <div className="absolute top-[14px] right-[14px] flex items-center gap-[10px] z-[7]">
      {/* Theme toggle (placeholder) */}
      <button
        className="w-[38px] h-[30px] rounded-control border border-border bg-bg-topbar
                   flex items-center justify-center text-text-faint hover:text-text-sub"
      >
        <Moon size={14} />
      </button>

      {/* Running agents */}
      <div
        className="flex items-center gap-2 border border-border rounded-control
                   bg-bg-topbar px-[9px] h-[30px]"
      >
        <span className="w-[5px] h-[5px] rounded-full bg-text-bright" />
        <span className="text-xs text-text-sub">
          {count} agent{count !== 1 ? "s" : ""} running
        </span>
      </div>

      {/* Share / export CTA */}
      <button
        className="h-[30px] px-4 rounded-control border-0
                   bg-cta-bg text-cta-text text-md font-semibold
                   hover:opacity-90"
      >
        Share
      </button>
    </div>
  );
}
