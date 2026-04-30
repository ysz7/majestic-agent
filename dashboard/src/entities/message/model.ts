export interface Message {
  id: string
  role: 'user' | 'assistant'
  content: string
  created_at: string
}

export interface ToolCallEvent {
  name: string
  args: Record<string, unknown>
}

export type ChatEvent =
  | { type: 'text'; data: string }
  | { type: 'tool_call'; data: ToolCallEvent }
  | { type: 'session_id'; data: string }
  | { type: 'done' }
  | { type: 'error'; data: string }
