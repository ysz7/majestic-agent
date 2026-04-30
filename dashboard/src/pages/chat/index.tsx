import { useState, useEffect, useCallback, useRef } from 'react'
import { useQuery } from '@tanstack/react-query'
import { getSessions, getMessages } from '@/shared/api/sessions'
import { SessionList } from '@/widgets/session-list'
import { ChatWindow } from '@/widgets/chat-window'
import { useSendMessage } from '@/features/send-message/model'

export function ChatPage() {
  const [activeSession, setActiveSession] = useState<string | null>(null)
  const [input, setInput] = useState('')
  // Tracks whether the user explicitly opened a new chat (suppresses auto-select)
  const wantNewChatRef = useRef(false)

  const { data: sessions = [] } = useQuery({
    queryKey: ['sessions'],
    queryFn: getSessions,
    refetchInterval: 10_000,
  })

  const { data: messages = [] } = useQuery({
    queryKey: ['messages', activeSession],
    queryFn: () => getMessages(activeSession!),
    enabled: !!activeSession,
  })

  // Auto-select the most recent session on first load only
  useEffect(() => {
    if (sessions.length > 0 && activeSession === null && !wantNewChatRef.current) {
      setActiveSession(sessions[0].id)
    }
  }, [sessions, activeSession])

  const handleSessionCreated = useCallback((id: string) => {
    wantNewChatRef.current = false
    setActiveSession(id)
  }, [])

  const { streaming, streamMsgs, streamSessionId, send } = useSendMessage({
    sessionId: activeSession,
    onSessionCreated: handleSessionCreated,
  })

  const handleSend = () => {
    if (!input.trim()) return
    send(input.trim())
    setInput('')
  }

  const handleNew = () => {
    wantNewChatRef.current = true
    setActiveSession(null)
    setInput('')
  }

  const handleSelect = (id: string) => {
    wantNewChatRef.current = false
    setActiveSession(id)
  }

  return (
    <div className="flex flex-1 overflow-hidden">
      <aside className="w-52 border-r shrink-0 flex flex-col overflow-hidden">
        <SessionList
          sessions={sessions}
          activeId={activeSession}
          onSelect={handleSelect}
          onNew={handleNew}
        />
      </aside>

      <ChatWindow
        messages={activeSession ? messages : []}
        streamMsgs={activeSession === streamSessionId ? streamMsgs : []}
        input={input}
        onInputChange={setInput}
        onSend={handleSend}
        streaming={streaming}
      />
    </div>
  )
}
