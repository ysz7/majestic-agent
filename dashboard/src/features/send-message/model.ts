import { useCallback, useRef, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { apiChatSSE } from '@/shared/api/client'
import type { StreamMessage } from '@/widgets/chat-window'
import type { ToolCallEvent } from '@/entities/message/model'

interface UseSendMessageOptions {
  sessionId: string | null
  onSessionCreated?: (id: string) => void
}

export function useSendMessage({ sessionId, onSessionCreated }: UseSendMessageOptions) {
  const qc = useQueryClient()
  const [streaming, setStreaming] = useState(false)
  const [streamMsgs, setStreamMsgs] = useState<StreamMessage[]>([])
  const stopRef = useRef<(() => void) | null>(null)
  const activeSessionRef = useRef<string | null>(sessionId)

  // Keep ref in sync so the SSE callback always has the latest session id
  activeSessionRef.current = sessionId

  const send = useCallback(
    (text: string) => {
      if (!text.trim() || streaming) return

      setStreaming(true)
      const toolCalls: ToolCallEvent[] = []

      const userMsg: StreamMessage = {
        id: `__user_${Date.now()}`,
        role: 'user',
        content: text,
      }

      const assistantMsg: StreamMessage = {
        id: '__stream__',
        role: 'assistant',
        content: '',
        toolCalls: [],
        streaming: true,
      }

      // Show user message immediately; assistant placeholder will be added on first event
      setStreamMsgs([userMsg])

      stopRef.current = apiChatSSE(
        { message: text, session_id: sessionId },
        (event) => {
          if (event.type === 'session_id') {
            activeSessionRef.current = event.data
            onSessionCreated?.(event.data)
          } else if (event.type === 'tool_call') {
            toolCalls.push(event.data)
            setStreamMsgs((prev) => {
              const user = prev.find((m) => m.id !== '__stream__') ?? userMsg
              return [user, { ...assistantMsg, toolCalls: [...toolCalls] }]
            })
          } else if (event.type === 'text') {
            setStreamMsgs((prev) => {
              const user = prev.find((m) => m.id !== '__stream__') ?? userMsg
              const cur = prev.find((m) => m.id === '__stream__') ?? assistantMsg
              return [
                user,
                {
                  ...cur,
                  content: cur.content + event.data,
                  toolCalls: [...toolCalls],
                  streaming: true,
                },
              ]
            })
          } else if (event.type === 'done') {
            setStreaming(false)
            setStreamMsgs((prev) => {
              const errMsg = prev.find((m) => m.id === '__error__')
              return errMsg ? [errMsg] : []
            })
            qc.invalidateQueries({ queryKey: ['messages', activeSessionRef.current] })
            qc.invalidateQueries({ queryKey: ['sessions'] })
          } else if (event.type === 'error') {
            setStreamMsgs((prev) => {
              const user = prev.find((m) => m.id !== '__stream__' && m.id !== '__error__')
              const errMsg: StreamMessage = {
                id: '__error__',
                role: 'assistant',
                content: `Error: ${event.data}`,
              }
              return user ? [user, errMsg] : [errMsg]
            })
            setStreaming(false)
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
  }, [])

  return { streaming, streamMsgs, send, stop }
}
