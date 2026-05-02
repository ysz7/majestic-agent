import { useCallback, useRef, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { apiChatSSE } from '@/shared/api/client'
import type { StreamMessage } from '@/widgets/chat-window'

export interface ToolEvent {
  id: string
  name: string
  args: Record<string, unknown>
  status: 'running' | 'done' | 'error'
  dim: boolean
}

interface UseSendMessageOptions {
  sessionId: string | null
  onSessionCreated?: (id: string) => void
}

export function useSendMessage({ sessionId, onSessionCreated }: UseSendMessageOptions) {
  const qc = useQueryClient()
  const [streaming, setStreaming] = useState(false)
  const [streamMsgs, setStreamMsgs] = useState<StreamMessage[]>([])
  const [streamSessionId, setStreamSessionId] = useState<string | null>(null)
  const [toolEvents, setToolEvents] = useState<ToolEvent[]>([])
  const stopRef = useRef<(() => void) | null>(null)
  const activeSessionRef = useRef<string | null>(sessionId)
  const counterRef = useRef(0)

  activeSessionRef.current = sessionId

  const resetToolEvents = useCallback(() => setToolEvents([]), [])

  const send = useCallback(
    (text: string) => {
      if (!text.trim() || streaming) return

      setStreaming(true)
      // Dim existing tool events from previous turns
      setToolEvents(prev => prev.map(e => ({ ...e, dim: true })))

      const userMsg: StreamMessage = { id: `__user_${Date.now()}`, role: 'user', content: text }
      const assistantMsg: StreamMessage = { id: '__stream__', role: 'assistant', content: '', streaming: true }

      setStreamMsgs([userMsg])
      setStreamSessionId(sessionId)

      stopRef.current = apiChatSSE(
        { message: text, session_id: sessionId },
        (event) => {
          if (event.type === 'session_id') {
            activeSessionRef.current = event.data
            setStreamSessionId(event.data)
            onSessionCreated?.(event.data)
          } else if (event.type === 'tool_call') {
            const te: ToolEvent = {
              id: `${event.data.name}_${++counterRef.current}`,
              name: event.data.name,
              args: event.data.args,
              status: 'running',
              dim: false,
            }
            setToolEvents(prev => [...prev, te])
          } else if (event.type === 'text') {
            setStreamMsgs((prev) => {
              const user = prev.find((m) => m.id !== '__stream__') ?? userMsg
              const cur = prev.find((m) => m.id === '__stream__') ?? assistantMsg
              return [user, { ...cur, content: cur.content + event.data, streaming: true }]
            })
          } else if (event.type === 'done') {
            setStreaming(false)
            setToolEvents(prev => prev.map(e => e.status === 'running' && !e.dim ? { ...e, status: 'done' } : e))
            setStreamMsgs((prev) => {
              const errMsg = prev.find((m) => m.id === '__error__')
              if (!errMsg) setStreamSessionId(null)
              return errMsg ? [errMsg] : []
            })
            qc.invalidateQueries({ queryKey: ['messages', activeSessionRef.current] })
            qc.invalidateQueries({ queryKey: ['sessions'] })
          } else if (event.type === 'error') {
            setStreaming(false)
            setToolEvents(prev => prev.map(e => e.status === 'running' && !e.dim ? { ...e, status: 'error' } : e))
            setStreamMsgs((prev) => {
              const user = prev.find((m) => m.id !== '__stream__' && m.id !== '__error__')
              const errMsg: StreamMessage = { id: '__error__', role: 'assistant', content: `Error: ${event.data}` }
              return user ? [user, errMsg] : [errMsg]
            })
          }
        },
      )
    },
    [streaming, sessionId, onSessionCreated, qc],
  )

  const stop = useCallback(() => {
    stopRef.current?.()
    setStreaming(false)
    setStreamMsgs([])
    setStreamSessionId(null)
  }, [])

  return { streaming, streamMsgs, streamSessionId, toolEvents, send, stop, resetToolEvents }
}
