import { API_BASE } from "@shared/config";
import type {
  AgentEntry,
  AuditEntry,
  Budget,
  CronJob,
  EnvEntry,
  EpisodicEntry,
  LessonEntry,
  ProductReport,
  ProductReportSummary,
  Profile,
  Skill,
  Workflow,
  WorkflowEdgeDef,
  WorkflowNodeDef,
  WorkspaceFile,
} from "./types";

// Read agent token from localStorage (set during first connect or from data/agent_token)
function getToken(): string {
  return localStorage.getItem("agent_token") ?? "";
}

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

async function request<T>(
  method: string,
  path: string,
  body?: unknown,
): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    method,
    headers: {
      "Content-Type": "application/json",
      "X-Agent-Token": getToken(),
    },
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new ApiError(res.status, err.detail ?? `HTTP ${res.status}`);
  }

  return res.json() as Promise<T>;
}

const get  = <T>(path: string)              => request<T>("GET",    path);
const post = <T>(path: string, body?: unknown) => request<T>("POST",   path, body);
const put  = <T>(path: string, body: unknown)  => request<T>("PUT",    path, body);
const del  = <T>(path: string)              => request<T>("DELETE", path);

// ── Profiles ──────────────────────────────────────────────────────────────────
export const profilesApi = {
  list:          ()           => get<{ profiles: Profile[] }>("/api/profiles"),
  create:        (body: object) => post<{ status: string; profile: string }>("/api/profiles/new", body),
  remove:        (name: string) => del<{ status: string }>(`/api/profiles/${name}`),
  getPersona:    (name: string) => get<Record<string, unknown>>(`/api/profiles/${name}/persona`),
  updatePersona: (name: string, body: object) => put<{ status: string }>(`/api/profiles/${name}/persona`, body),
  getEnv:        (name: string)                => get<{ entries: EnvEntry[] }>(`/api/profiles/${name}/env`),
  updateEnv:     (name: string, entries: EnvEntry[]) =>
    put<{ status: string }>(`/api/profiles/${name}/env`, { entries }),
};

// ── Agents ────────────────────────────────────────────────────────────────────
export const agentsApi = {
  running: ()           => get<{ agents: AgentEntry[] }>("/api/agents/running"),
  start:   (name: string) => post<{ status: string; pid?: number }>(`/api/agents/${name}/start`),
  stop:    (name: string) => post<{ status: string }>(`/api/agents/${name}/stop`),
};

// ── Memory ────────────────────────────────────────────────────────────────────
export const memoryApi = {
  episodic:    (profile: string, q?: string, limit = 20) =>
    get<{ entries: EpisodicEntry[] }>(
      `/api/memory/${profile}/episodic${q ? `?q=${encodeURIComponent(q)}&limit=${limit}` : `?limit=${limit}`}`,
    ),
  deleteEpisodic: (profile: string, id: number) =>
    del<{ status: string }>(`/api/memory/${profile}/episodic/${id}`),

  lessons:     (profile: string, q?: string, limit = 30) =>
    get<{ entries: LessonEntry[] }>(
      `/api/memory/${profile}/lessons${q ? `?q=${encodeURIComponent(q)}&limit=${limit}` : `?limit=${limit}`}`,
    ),
  deleteLesson: (profile: string, id: number) =>
    del<{ status: string }>(`/api/memory/${profile}/lessons/${id}`),

  userProfile:  (profile: string) =>
    get<{ profile: Record<string, string> }>(`/api/memory/${profile}/profile`),
  deleteProfileKey: (profile: string, key: string) =>
    del<{ status: string }>(`/api/memory/${profile}/profile/${encodeURIComponent(key)}`),

  clear: (profile: string, type: "episodic" | "lessons" | "profile") =>
    post<{ status: string }>(`/api/memory/${profile}/clear`, { type }),
};

// ── Skills ────────────────────────────────────────────────────────────────────
export const skillsApi = {
  list:   (profile: string)                    => get<{ skills: Skill[] }>(`/api/skills/${profile}`),
  create: (profile: string, body: object)      => post<{ status: string }>(`/api/skills/${profile}`, body),
  update: (profile: string, name: string, body: object) =>
    put<{ status: string }>(`/api/skills/${profile}/${name}`, body),
  remove: (profile: string, name: string)      => del<{ status: string }>(`/api/skills/${profile}/${name}`),
};

// ── Workspace ─────────────────────────────────────────────────────────────────
export const workspaceApi = {
  files:  (profile: string) => get<{ files: WorkspaceFile[] }>(`/api/workspace/${profile}/files`),
  read:   (profile: string, path: string) =>
    get<{ path: string; content: string; binary: boolean }>(
      `/api/workspace/${profile}/file?path=${encodeURIComponent(path)}`,
    ),
  remove: (profile: string, path: string) =>
    del<{ status: string }>(`/api/workspace/${profile}/file?path=${encodeURIComponent(path)}`),
};

// ── Budget ────────────────────────────────────────────────────────────────────
export const budgetApi = {
  get: (profile: string) => get<Budget>(`/api/budget/${profile}`),
};

// ── Audit ─────────────────────────────────────────────────────────────────────
export const auditApi = {
  list: (profile: string, limit = 50, tool?: string) =>
    get<{ entries: AuditEntry[] }>(
      `/api/audit/${profile}?limit=${limit}${tool ? `&tool=${encodeURIComponent(tool)}` : ""}`,
    ),
};

// ── Tasks (direct agent endpoints — not under /api) ───────────────────────────
export const tasksApi = {
  submit: (text: string) =>
    post<{ status: string; task_id: string }>("/task", { text }),
};

// ── Workflows ─────────────────────────────────────────────────────────────────
export const workflowsApi = {
  list:   (profile: string) =>
    get<{ workflows: Workflow[] }>(`/api/workflows/${profile}`),
  create: (profile: string, body: { name: string; nodes: WorkflowNodeDef[]; edges: WorkflowEdgeDef[] }) =>
    post<{ status: string; workflow: Workflow }>(`/api/workflows/${profile}`, body),
  update: (profile: string, id: string, body: { name: string; nodes: WorkflowNodeDef[]; edges: WorkflowEdgeDef[] }) =>
    put<{ status: string; workflow: Workflow }>(`/api/workflows/${profile}/${id}`, body),
  remove: (profile: string, id: string) =>
    del<{ status: string }>(`/api/workflows/${profile}/${id}`),
  run:    (profile: string, id: string) =>
    post<{ status: string }>(`/api/workflows/${profile}/${id}/run`),
};

// ── Products (Solo Product Forge) ───────────────────────────────────────────
export const productsApi = {
  list: (profile: string) =>
    get<{ reports: ProductReportSummary[] }>(`/api/products/${profile}`),
  get:  (profile: string, date: string) =>
    get<ProductReport>(`/api/products/${profile}/${date}`),
  run:  (profile: string, days = 30) =>
    post<ProductReport>(`/api/products/${profile}/run`, { days }),
};

// ── Cron ──────────────────────────────────────────────────────────────────────
export const cronApi = {
  list:   (profile: string)                                => get<{ jobs: CronJob[] }>(`/api/cron/${profile}`),
  create: (profile: string, body: Partial<CronJob>)        => post<{ status: string; job: CronJob }>(`/api/cron/${profile}`, body),
  update: (profile: string, id: string, body: Partial<CronJob>) =>
    put<{ status: string; job: CronJob }>(`/api/cron/${profile}/${id}`, body),
  remove: (profile: string, id: string)                    => del<{ status: string }>(`/api/cron/${profile}/${id}`),
};
