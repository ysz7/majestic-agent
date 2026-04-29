import { apiFetch } from './client'

export interface SetupStatus {
  configured: boolean
  has_api_key: boolean
  has_model: boolean
}

export interface SetupPayload {
  api_key: string
  model: string
  language: string
  currency: string
}

export const getSetupStatus = () => apiFetch<SetupStatus>('/api/setup/status')
export const submitSetup = (payload: SetupPayload) =>
  apiFetch<{ ok: boolean }>('/api/setup', { method: 'POST', body: JSON.stringify(payload) })
