import { useState, useEffect, useCallback, useRef } from 'react'
import { useQuery } from '@tanstack/react-query'
import { getSessions, getMessages } from '@/shared/api/sessions'
import { SessionList } from '@/widgets/session-list'
import { ChatWindow } from '@/widgets/chat-window'
import { AgentGraph } from '@/widgets/agent-graph'
import { useSendMessage } from '@/features/send-message/model'

export function ChatPage() {
  const [activeSession, setActiveSession] = useState<string | null>(null)
  const [input, setInput] = useState('')
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

  useEffect(() => {
    if (sessions.length > 0 && activeSession === null && !wantNewChatRef.current) {
      setActiveSession(sessions[0].id)
    }
  }, [sessions, activeSession])

  const handleSessionCreated = useCallback((id: string) => {
    wantNewChatRef.current = false
    setActiveSession(id)
  }, [])

  const { streaming, streamMsgs, streamSessionId, toolEvents, send, resetToolEvents } = useSendMessage({
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
    resetToolEvents()
  }

  const handleSelect = (id: string) => {
    wantNewChatRef.current = false
    setActiveSession(id)
    resetToolEvents()
  }

  return (
    <div className="flex flex-1 overflow-hidden">
      {/* Sessions panel */}
      <aside className="w-52 border-r shrink-0 flex flex-col overflow-hidden">
        <SessionList
          sessions={sessions}
          activeId={activeSession}
          onSelect={handleSelect}
          onNew={handleNew}
        />
      </aside>

      {/* Agent Graph panel — relative so AgentGraph can absolute inset-0 */}
      <div className="flex-1 border-r relative min-w-0">
        <AgentGraph toolEvents={toolEvents} streaming={streaming} />
      </div>

      {/* Chat panel */}
      <div className="w-[600px] shrink-0 flex flex-col overflow-hidden border-l">
        <ChatWindow
          messages={activeSession ? messages : []}
          streamMsgs={activeSession === streamSessionId ? streamMsgs : []}
          input={input}
          onInputChange={setInput}
          onSend={handleSend}
          streaming={streaming}
        />
      </div>
    </div>
  )
}
