import { apiFetch } from './client'

export interface WorkspaceItem {
  name: string
  path: string
  type: 'dir' | 'text' | 'image' | 'binary'
  size: number
  modified_at: string
}

export interface WorkspaceListResult {
  items: WorkspaceItem[]
  path: string
}

export interface WorkspaceFileResult {
  type: 'text' | 'image' | 'binary'
  content?: string
  content_b64?: string
  mime?: string
  ext?: string
  size: number
  name?: string
  error?: string
}

export const listWorkspace = (path = '') =>
  apiFetch<WorkspaceListResult>(`/api/workspace/list?path=${encodeURIComponent(path)}`)

export const readWorkspaceFile = (path: string) =>
  apiFetch<WorkspaceFileResult>(`/api/workspace/file?path=${encodeURIComponent(path)}`)

export const saveWorkspaceFile = (path: string, content: string) =>
  apiFetch<{ ok: boolean }>('/api/workspace/file', {
    method: 'POST',
    body: JSON.stringify({ path, content }),
  })

export const deleteWorkspaceFile = (path: string) =>
  apiFetch<{ ok: boolean }>(`/api/workspace/file?path=${encodeURIComponent(path)}`, {
    method: 'DELETE',
  })

export const uploadWorkspaceFile = (path: string, filename: string, contentB64: string) =>
  apiFetch<{ ok: boolean; path?: string }>('/api/workspace/upload', {
    method: 'POST',
    body: JSON.stringify({ path, filename, content_b64: contentB64 }),
  })

export const mkdirWorkspace = (path: string) =>
  apiFetch<{ ok: boolean }>('/api/workspace/mkdir', {
    method: 'POST',
    body: JSON.stringify({ path }),
  })
