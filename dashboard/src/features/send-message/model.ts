import { useCallback, useRef, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { apiChatSSE } from '@/shared/api/client'
import type { StreamMessage } from '@/widgets/chat-window'
import type { ToolCallEvent } from '@/entities/message/model'

interface UseSendMessageOptions {
  sessionId: string | null
}

export function useSendMessage({ sessionId }: UseSendMessageOptions) {
  const qc = useQueryClient()
  const [streaming, setStreaming] = useState(false)
  const [streamMsg, setStreamMsg] = useState<StreamMessage | null>(null)
  const stopRef = useRef<(() => void) | null>(null)

  const send = useCallback(
    (text: string) => {
      if (!text.trim() || streaming) return

      setStreaming(true)
      const toolCalls: ToolCallEvent[] = []

      // Optimistic user message (will be replaced by real data after refetch)
      const userMsg: StreamMessage = {
        id: `__user_${Date.now()}`,
        role: 'user',
        content: text,
      }

      // Set initial streaming assistant placeholder
      const assistantMsg: StreamMessage = {
        id: '__stream__',
        role: 'assistant',
        content: '',
        toolCalls: [],
        streaming: true,
      }

      setStreamMsg(userMsg)

      stopRef.current = apiChatSSE(
        { message: text, session_id: sessionId },
        (event) => {
          if (event.type === 'tool_call') {
            toolCalls.push(event.data)
            setStreamMsg({ ...assistantMsg, toolCalls: [...toolCalls] })
          } else if (event.type === 'text') {
            setStreamMsg((prev) => ({
              ...(prev?.id === '__stream__' ? prev : assistantMsg),
              content: (prev?.id === '__stream__' ? prev.content : '') + event.data,
              toolCalls: [...toolCalls],
              streaming: true,
            }))
          } else if (event.type === 'done') {
            setStreaming(false)
            setStreamMsg(null)
            qc.invalidateQueries({ queryKey: ['messages', sessionId] })
            qc.invalidateQueries({ queryKey: ['sessions'] })
          } else if (event.type === 'error') {
            setStreamMsg({
              id: '__error__',
              role: 'assistant',
              content: `Error: ${event.data}`,
            })
            setStreaming(false)
          }
        },
      )
    },
    [streaming, sessionId, qc],
  )

  const stop = useCallback(() => {
    stopRef.current?.()
    setStreaming(false)
    setStreamMsg(null)
  }, [])

  return { streaming, streamMsg, send, stop }
}
