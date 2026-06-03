export interface Profile {
  profile: string;      // directory name (slug)
  name: string;         // display name from persona.yaml
  role: string;
  running: boolean;
  port: number | null;
  pid: number | null;
  started_at: string | null;
}

export interface PersonaYaml {
  name: string;
  role: string;
  tone: string;
  language: string;
  port: number;
  limits: {
    max_tokens_per_task: number;
    max_cost_per_task: number;
  };
  model_routing?: {
    reason?: string;
    simple?: string;
    code?: string;
    reflection?: string;
  };
  context?: string;
}
