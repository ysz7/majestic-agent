import { apiFetch } from './client'

export interface Session {
  id: string
  name: string
  created_at: string
  message_count: number
}

export interface Message {
  id: string
  role: 'user' | 'assistant'
  content: string
  created_at: string
}

export const getSessions = () => apiFetch<Session[]>('/api/sessions')
export const getMessages = (sessionId: string) =>
  apiFetch<Message[]>(`/api/sessions/${sessionId}/messages`)
export const createSession = (name?: string) =>
  apiFetch<Session>('/api/sessions', { method: 'POST', body: JSON.stringify({ name }) })
