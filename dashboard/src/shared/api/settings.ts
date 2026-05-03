import { apiFetch } from './client'
import type { Skill } from '@/entities/skill/model'

export type { Skill }

// ── Settings ──────────────────────────────────────────────────────────────────

export interface Settings {
  llm?: { provider?: string; model?: string; ollama_url?: string; num_ctx?: number }
  agent?: { role?: string; tools_enabled?: string[]; tools_disabled?: string[]; allow_scripts?: boolean }
  language?: string
  currency?: string
  search_mode?: string
  api?: { port?: number; key?: string }
  dashboard?: { port?: number; password?: string }
  telegram?: { morning_briefing_hour?: number; allowed_user_ids?: number[] }
  research?: {
    auto_interval_minutes?: number
    reddit_subs?: string[]
    crypto_coins?: string[]
    stock_symbols?: string[]
    forex_pairs?: string[]
  }
  _api_key_set?: boolean
  _api_key_preview?: string
  api_key?: string
}

export const getSettings = () => apiFetch<Settings>('/api/settings')
export const saveSettings = (s: Settings) =>
  apiFetch<{ ok: boolean }>('/api/settings', { method: 'POST', body: JSON.stringify(s) })
export const getOllamaModels = () => apiFetch<string[]>('/api/ollama/models')

// ── LLM Configs ───────────────────────────────────────────────────────────────

export interface LlmConfig {
  name: string
  provider: string
  model: string
  key_preview: string
  ollama_url: string
  active: boolean
}

export const getLlmConfigs = () => apiFetch<LlmConfig[]>('/api/llm/configs')
export const createLlmConfig = (cfg: {
  name: string
  provider: string
  model: string
  api_key?: string
  ollama_url?: string
}) => apiFetch<{ ok: boolean }>('/api/llm/configs', { method: 'POST', body: JSON.stringify(cfg) })
export const deleteLlmConfig = (name: string) =>
  apiFetch<{ ok: boolean }>(`/api/llm/configs/${encodeURIComponent(name)}`, { method: 'DELETE' })
export const activateLlmConfig = (name: string) =>
  apiFetch<{ ok: boolean }>(`/api/llm/configs/${encodeURIComponent(name)}/activate`, {
    method: 'POST',
    body: '{}',
  })

// ── Memory ────────────────────────────────────────────────────────────────────

export interface MemoryMd {
  agent: string
  user: string
}

export const getMemoryMd = () => apiFetch<MemoryMd>('/api/memory')
export const saveMemoryMd = (m: Partial<MemoryMd>) =>
  apiFetch<{ ok: boolean }>('/api/memory', { method: 'POST', body: JSON.stringify(m) })

// ── Skills ────────────────────────────────────────────────────────────────────

export const getSkills = () => apiFetch<Skill[]>('/api/skills')
export const getSkillDetail = (name: string) =>
  apiFetch<Skill & { body: string }>(`/api/skills/${encodeURIComponent(name)}`)
export const createSkill = (s: { name: string; description: string; body: string; tags: string[] }) =>
  apiFetch<{ ok: boolean }>('/api/skills', { method: 'POST', body: JSON.stringify(s) })
export const deleteSkill = (name: string) =>
  apiFetch<{ ok: boolean }>(`/api/skills/${encodeURIComponent(name)}`, { method: 'DELETE' })

// ── MCP ───────────────────────────────────────────────────────────────────────

export interface McpServer {
  name: string
  command: string[]
  env?: Record<string, string>
  disabled?: boolean
}

export const getMcpStatus = () =>
  apiFetch<{ servers: McpServer[] }>('/api/mcp/status')

export const addMcpServer = (s: McpServer) =>
  apiFetch<{ ok: boolean }>('/api/mcp/servers', { method: 'POST', body: JSON.stringify(s) })

export const removeMcpServer = (name: string) =>
  apiFetch<{ ok: boolean }>(`/api/mcp/servers/${encodeURIComponent(name)}`, { method: 'DELETE' })

export const toggleMcpServer = (name: string) =>
  apiFetch<{ ok: boolean }>(`/api/mcp/servers/${encodeURIComponent(name)}/toggle`, {
    method: 'POST',
    body: '{}',
  })

// ── Email ─────────────────────────────────────────────────────────────────────

export interface EmailStatus {
  configured: boolean
  running: boolean
  last_poll: number | null
  error: string | null
  username: string
}

export interface EmailConfig {
  imap_host?: string
  imap_port?: number
  smtp_host?: string
  smtp_port?: number
  username?: string
  password?: string
  poll_interval?: number
  allowed_senders?: string[]
}

export const getEmailStatus = () => apiFetch<EmailStatus>('/api/email/status')

export const testEmailConnection = (cfg: EmailConfig) =>
  apiFetch<{ ok: boolean; error?: string }>('/api/email/test', {
    method: 'POST',
    body: JSON.stringify(cfg),
  })

export const saveEmailConfig = (cfg: EmailConfig) =>
  apiFetch<{ ok: boolean }>('/api/email/save', {
    method: 'POST',
    body: JSON.stringify(cfg),
  })

export const startEmailGateway = (cfg?: EmailConfig) =>
  apiFetch<{ ok: boolean; message?: string; error?: string }>('/api/email/start', {
    method: 'POST',
    body: JSON.stringify(cfg ?? {}),
  })

export const stopEmailGateway = () =>
  apiFetch<{ ok: boolean }>('/api/email/stop', { method: 'POST', body: '{}' })
