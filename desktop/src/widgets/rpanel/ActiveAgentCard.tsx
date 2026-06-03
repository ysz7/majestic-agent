import { useQuery } from "@tanstack/react-query";
import { agentsApi } from "@shared/api/client";
import { Card, CardLabel } from "@shared/ui-kit";

export function ActiveAgentCard() {
  const { data, isLoading } = useQuery({
    queryKey: ["agents-running"],
    queryFn:  agentsApi.running,
    refetchInterval: 5000,
  });

  const agents = data?.agents ?? [];

  return (
    <Card>
      <div className="flex items-center justify-between mb-[6px]">
        <CardLabel>Active Session</CardLabel>
        <div className="flex items-center gap-[5px] text-xs text-text-sub">
          <span className="w-[5px] h-[5px] rounded-full bg-text-bright" />
          Live
        </div>
      </div>

      {isLoading ? (
        <div className="text-xs text-text-muted-2 mt-2">Loading…</div>
      ) : agents.length === 0 ? (
        <div className="text-xs text-text-muted-2 mt-2">No agents running</div>
      ) : (
        <div className="mt-2 flex flex-col gap-[5px]">
          {agents.slice(0, 3).map((a) => (
            <div key={a.profile} className="text-base text-text-sub">
              {a.agent_name}
              <span className="ml-1 text-xs text-text-muted-2">:{a.port}</span>
            </div>
          ))}
        </div>
      )}

    </Card>
  );
}
