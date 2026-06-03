import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import type { Node, Edge } from "@xyflow/react";
import { agentsApi, cronApi, profilesApi, workspaceApi } from "@shared/api/client";

export function useCanvasData(activeProfile: string | null) {
  const agents = useQuery({
    queryKey: ["agents-running"],
    queryFn:  agentsApi.running,
    refetchInterval: 5000,
  });

  const profiles = useQuery({
    queryKey: ["profiles"],
    queryFn:  profilesApi.list,
    refetchInterval: 15000,
  });

  const files = useQuery({
    queryKey: ["workspace-files", activeProfile],
    queryFn:  () => workspaceApi.files(activeProfile!),
    enabled:  !!activeProfile,
    refetchInterval: 20000,
  });

  const cron = useQuery({
    queryKey: ["cron", activeProfile],
    queryFn:  () => cronApi.list(activeProfile!),
    enabled:  !!activeProfile,
    refetchInterval: 30000,
  });

  const result = useMemo(() => {
    const nodes: Node[] = [];
    const edges: Edge[] = [];

    const allProfiles = profiles.data?.profiles ?? [];
    const runningMap  = new Map((agents.data?.agents ?? []).map((a) => [a.profile, a]));

    allProfiles.forEach((p, i) => {
      const running = runningMap.get(p.profile);
      nodes.push({
        id:       `agent-${p.profile}`,
        type:     "agentNode",
        position: { x: 40, y: 40 + i * 140 },
        data: {
          label:   p.name,
          profile: p.profile,
          status:  running ? "running" : "stopped",
          port:    running?.port ?? p.port ?? 8000,
          pid:     running?.pid,
        },
      });
    });

    const fileList = (files.data?.files ?? []).slice(0, 8);
    fileList.forEach((f, i) => {
      const id = `file-${i}`;
      nodes.push({
        id,
        type:     "fileNode",
        position: { x: 300, y: 40 + i * 100 },
        data: { name: f.name, path: f.path, size: f.size, type: f.type },
      });

      if (activeProfile) {
        edges.push({
          id:     `e-${id}`,
          source: `agent-${activeProfile}`,
          target: id,
          style:  { stroke: "rgba(255,255,255,0.10)", strokeWidth: 1 },
        });
      }
    });

    const cronJobs = cron.data?.jobs ?? [];
    cronJobs.forEach((job, i) => {
      const id = `cron-${job.id}`;
      nodes.push({
        id,
        type:     "cronNode",
        position: { x: 560, y: 40 + i * 130 },
        data: {
          id:       job.id,
          schedule: job.schedule,
          task:     job.task,
          active:   job.active,
          agent:    job.agent,
          last_run: job.last_run,
          profile:  activeProfile ?? job.agent,
        },
      });

      edges.push({
        id:     `e-${id}`,
        source: `agent-${job.agent}`,
        target: id,
        style:  { stroke: "rgba(255,255,255,0.08)", strokeWidth: 1, strokeDasharray: "4 3" },
      });
    });

    return { nodes, edges };
  }, [profiles.data, agents.data, files.data, cron.data, activeProfile]);

  return {
    ...result,
    isLoading: profiles.isLoading || agents.isLoading,
  };
}
