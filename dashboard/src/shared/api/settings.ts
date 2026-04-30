import { apiFetch } from './client'
import type { Skill } from '@/entities/skill/model'

export type { Skill }

// ── Settings ──────────────────────────────────────────────────────────────────

export interface Settings {
  llm?: { provider?: string; model?: string; ollama_url?: string }
  agent?: { role?: string; tools_enabled?: string[]; tools_disabled?: string[] }
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
