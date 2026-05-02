import { useState, useEffect, useCallback, useRef } from 'react'
import { useSearchParams, useLocation } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { getSessions, getMessages } from '@/shared/api/sessions'
import { ChatWindow } from '@/widgets/chat-window'
import { useSendMessage } from '@/features/send-message/model'

export function ChatPage() {
  const [searchParams, setSearchParams] = useSearchParams()
  const location = useLocation()
  const urlSessionId = searchParams.get('session')

  const [input, setInput] = useState('')
  const wantNewChatRef = useRef(false)

  const { data: sessions = [] } = useQuery({
    queryKey: ['sessions'],
    queryFn: getSessions,
    refetchInterval: 10_000,
  })

  const { data: messages = [] } = useQuery({
    queryKey: ['messages', urlSessionId],
    queryFn: () => getMessages(urlSessionId!),
    enabled: !!urlSessionId,
  })

  const handleSessionCreated = useCallback((id: string) => {
    wantNewChatRef.current = false
    setSearchParams({ session: id })
  }, [setSearchParams])

  const { streaming, streamMsgs, streamSessionId, toolEvents, send, stop, resetToolEvents } =
    useSendMessage({ sessionId: urlSessionId, onSessionCreated: handleSessionCreated })

  // Handle "New chat" from sidebar + auto-select on first load
  useEffect(() => {
    if (location.state?.newChat) {
      wantNewChatRef.current = true
      setSearchParams({}, { replace: true })
      setInput('')
      resetToolEvents()
      window.history.replaceState({}, document.title)
      return
    }
    if (!urlSessionId && !wantNewChatRef.current && sessions.length > 0) {
      setSearchParams({ session: sessions[0].id }, { replace: true })
    }
  }, [location.state?.newChat, sessions.length, urlSessionId])

  // Reset tool events when switching sessions
  const prevSession = useRef(urlSessionId)
  useEffect(() => {
    if (urlSessionId !== prevSession.current) {
      prevSession.current = urlSessionId
      if (urlSessionId) resetToolEvents()
    }
  }, [urlSessionId, resetToolEvents])

  const handleSend = () => {
    if (!input.trim()) return
    send(input.trim())
    setInput('')
  }

  return (
    <ChatWindow
      messages={urlSessionId ? messages : []}
      streamMsgs={urlSessionId === streamSessionId ? streamMsgs : []}
      toolEvents={toolEvents}
      input={input}
      onInputChange={setInput}
      onSend={handleSend}
      onStop={stop}
      streaming={streaming}
    />
  )
}
