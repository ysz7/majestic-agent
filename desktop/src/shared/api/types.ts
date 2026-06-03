// API response shapes for all /api/* endpoints

export interface Profile {
  profile: string;
  name: string;
  role: string;
  running: boolean;
  port: number | null;
  pid: number | null;
  started_at: string | null;
}

export interface AgentEntry {
  profile: string;
  agent_name: string;
  pid: number;
  port: number;
  started_at: string;
  status: string;
}

export interface EpisodicEntry {
  id: number;
  timestamp: string;
  task: string;
  result: string;
  reflection: string;
  tokens_used: number;
  cost: number;
  duration_s: number;
}

export interface LessonEntry {
  id: number;
  task_type: string;
  lesson: string;
  usage_count: number;
  created_at: string;
}

export interface Skill {
  _filename: string;
  name: string;
  description?: string;
  triggers?: string[];
  steps?: string[];
  [key: string]: unknown;
}

export interface WorkspaceFile {
  path: string;
  name: string;
  size: number;
  modified: number;
  type: string;
}

export interface Budget {
  profile: string;
  limits: {
    max_tokens_per_task: number;
    max_cost_per_task: number;
  };
  recent_10_tasks: {
    total_tokens: number;
    total_cost_usd: number;
    task_count: number;
  };
}

export interface EnvEntry {
  key:    string;
  value:  string;
  masked: boolean;
}

export interface AuditEntry {
  task_id:       string;
  created_at:    string;
  tool:          string;
  args_preview:  string;
  result_preview: string;
}

export interface CronJob {
  id:         string;
  schedule:   string;
  task:       string;
  active:     boolean;
  agent:      string;
  created_at: string;
  last_run:   string | null;
}

// WebSocket event union
export type WsEvent =
  | { type: "connected"; agent: string }
  | { type: "pong" }
  | { type: "token"; content: string }
  | { type: "step"; step: "REASON" | "TOOL_CALL" | "OBSERVE"; content: string }
  | { type: "hitl"; task_id: string; tool: string; args: Record<string, unknown> }
  | { type: "done"; task_id: string; tokens: number; cost: number }
  | { type: "error"; message: string };
