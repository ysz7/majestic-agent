export interface Agent {
  profile: string;
  agent_name: string;
  pid: number;
  port: number;
  started_at: string;
  status: "running" | "idle" | "stopped";
}

export type AgentStatus = "running" | "idle" | "stopped";
