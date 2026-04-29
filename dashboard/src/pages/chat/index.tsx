import { useState, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Button } from '@/components/ui/button'
import { Crown } from 'lucide-react'
import { getSessions, createSession, getMessages } from '@/shared/api/sessions'
import { SessionList } from '@/widgets/session-list'
import { ChatWindow } from '@/widgets/chat-window'
import { useSendMessage } from '@/features/send-message/model'

export function ChatPage() {
  const qc = useQueryClient()
  const [activeSession, setActiveSession] = useState<string | null>(null)
  const [input, setInput] = useState('')

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

  const newSession = useMutation({
    mutationFn: () => createSession(),
    onSuccess: (s) => {
      qc.invalidateQueries({ queryKey: ['sessions'] })
      setActiveSession(s.id)
    },
  })

  // Auto-select the most recent session on first load
  useEffect(() => {
    if (sessions.length > 0 && activeSession === null) {
      setActiveSession(sessions[0].id)
    }
  }, [sessions, activeSession])

  const { streaming, streamMsg, send } = useSendMessage({ sessionId: activeSession })

  const handleSend = () => {
    if (!input.trim()) return
    send(input.trim())
    setInput('')
  }

  return (
    <div className="flex flex-1 overflow-hidden">
      {/* Session sidebar */}
      <aside className="w-52 border-r shrink-0 flex flex-col overflow-hidden">
        <SessionList
          sessions={sessions}
          activeId={activeSession}
          onSelect={setActiveSession}
          onNew={() => newSession.mutate()}
        />
      </aside>

      {/* Main area */}
      {activeSession ? (
        <ChatWindow
          messages={messages}
          streamMsg={streamMsg}
          input={input}
          onInputChange={setInput}
          onSend={handleSend}
          streaming={streaming}
        />
      ) : (
        <div className="flex flex-1 items-center justify-center text-muted-foreground">
          <div className="text-center space-y-3">
            <Crown className="h-10 w-10 mx-auto opacity-15" />
            <p className="text-sm">Select a session or start a new chat</p>
            <Button size="sm" variant="outline" onClick={() => newSession.mutate()}>
              New Chat
            </Button>
          </div>
        </div>
      )}
    </div>
  )
}
