import { apiFetch } from './client'
import type { UserTable, TableRows } from '@/entities/user-table/model'

export type { UserTable, TableRows }

export const getTables = () => apiFetch<UserTable[]>('/api/tables')

export const createTable = (name: string, columns: string[]) =>
  apiFetch<{ ok: boolean }>('/api/tables', { method: 'POST', body: JSON.stringify({ name, columns }) })

export const deleteTable = (name: string) =>
  apiFetch<{ ok: boolean }>(`/api/tables/${encodeURIComponent(name)}`, { method: 'DELETE' })

export const getRows = (name: string) =>
  apiFetch<TableRows>(`/api/tables/${encodeURIComponent(name)}/rows`)

export const addRow = (name: string, row: Record<string, string>) =>
  apiFetch<{ ok: boolean; id: number }>(`/api/tables/${encodeURIComponent(name)}/rows`, {
    method: 'POST',
    body: JSON.stringify(row),
  })

export const updateRow = (name: string, id: number, row: Record<string, string>) =>
  apiFetch<{ ok: boolean }>(`/api/tables/${encodeURIComponent(name)}/rows/${id}`, {
    method: 'PUT',
    body: JSON.stringify(row),
  })

export const deleteRow = (name: string, id: number) =>
  apiFetch<{ ok: boolean }>(`/api/tables/${encodeURIComponent(name)}/rows/${id}`, { method: 'DELETE' })
