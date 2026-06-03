import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { agentsApi, profilesApi } from "@shared/api/client";
import { Button } from "@shared/ui-kit";
import { Play, Square, Trash2, Edit } from "lucide-react";
import { cn } from "@shared/lib/cn";

interface Props {
  onEdit:   (profile: string) => void;
  onCreate: () => void;
}

export function ProfileList({ onEdit, onCreate }: Props) {
  const qc = useQueryClient();

  const { data, isLoading } = useQuery({
    queryKey: ["profiles"],
    queryFn:  profilesApi.list,
    refetchInterval: 5000,
  });

  const start = useMutation({
    mutationFn: (name: string) => agentsApi.start(name),
    onSuccess:  () => qc.invalidateQueries({ queryKey: ["profiles"] }),
  });

  const stop = useMutation({
    mutationFn: (name: string) => agentsApi.stop(name),
    onSuccess:  () => qc.invalidateQueries({ queryKey: ["profiles"] }),
  });

  const remove = useMutation({
    mutationFn: (name: string) => profilesApi.remove(name),
    onSuccess:  () => qc.invalidateQueries({ queryKey: ["profiles"] }),
  });

  const profiles = data?.profiles ?? [];

  return (
    <div className="flex flex-col gap-[7px]">
      <div className="flex items-center justify-between mb-[4px]">
        <span className="text-2xs text-text-muted-3 uppercase tracking-[1.2px] font-semibold">
          Profiles
        </span>
        <Button size="sm" variant="cta" onClick={onCreate}>+ New</Button>
      </div>

      {isLoading ? (
        <div className="text-xs text-text-muted-2">Loading…</div>
      ) : profiles.length === 0 ? (
        <div className="text-xs text-text-muted-2">No profiles. Create one.</div>
      ) : (
        profiles.map((p) => (
          <div
            key={p.profile}
            className={cn(
              "flex items-center gap-[8px] rounded-node border px-[11px] py-[9px]",
              p.running
                ? "border-border-strong bg-node-gradient"
                : "border-border bg-bg-elevated",
            )}
          >
            <span
              className="w-[6px] h-[6px] rounded-dot flex-shrink-0"
              style={{ background: p.running ? "#4ade80" : "#565656" }}
            />

            <div className="flex-1 min-w-0">
              <div className="text-base text-text-sub truncate">{p.name}</div>
              <div className="text-xs text-text-muted-2 truncate">
                {p.profile}{p.port ? ` :${p.port}` : ""}
              </div>
            </div>

            <div className="flex items-center gap-[4px]">
              <button
                onClick={() => onEdit(p.profile)}
                className="p-[4px] text-text-muted-3 hover:text-text-sub"
              >
                <Edit size={11} />
              </button>

              {p.running ? (
                <button
                  onClick={() => stop.mutate(p.profile)}
                  disabled={stop.isPending}
                  className="p-[4px] text-text-muted-3 hover:text-text-sub disabled:opacity-40"
                >
                  <Square size={11} />
                </button>
              ) : (
                <button
                  onClick={() => start.mutate(p.profile)}
                  disabled={start.isPending}
                  className="p-[4px] text-text-muted-3 hover:text-text-sub disabled:opacity-40"
                >
                  <Play size={11} />
                </button>
              )}

              <button
                onClick={() => {
                  if (window.confirm(`Delete "${p.name}"?`)) remove.mutate(p.profile);
                }}
                disabled={p.running || remove.isPending}
                className="p-[4px] text-text-muted-3 hover:text-red-400 disabled:opacity-30"
              >
                <Trash2 size={11} />
              </button>
            </div>
          </div>
        ))
      )}
    </div>
  );
}
