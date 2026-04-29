import { apiFetch } from './client'
import type { Session } from '@/entities/session/model'
import type { Message } from '@/entities/message/model'

export type { Session, Message }

export const getSessions = () => apiFetch<Session[]>('/api/sessions')

export const getMessages = (sessionId: string) =>
  apiFetch<Message[]>(`/api/sessions/${sessionId}/messages`)

export const createSession = (name?: string) =>
  apiFetch<Session>('/api/sessions', { method: 'POST', body: JSON.stringify({ name }) })

export const deleteSession = (sessionId: string) =>
  apiFetch<{ ok: boolean }>(`/api/sessions/${sessionId}`, { method: 'DELETE' })
