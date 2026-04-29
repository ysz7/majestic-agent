import { useState, useRef, useEffect, useCallback } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Avatar, AvatarFallback } from '@/components/ui/avatar'
import { Badge } from '@/components/ui/badge'
import { Send, Plus, Crown, User } from 'lucide-react'
import { getSessions, createSession, getMessages } from '@/shared/api/sessions'
import { apiSSE } from '@/shared/api/client'
import type { Message } from '@/shared/api/sessions'
import { cn } from '@/lib/utils'

export function ChatPage() {
  const qc = useQueryClient()
  const [activeSession, setActiveSession] = useState<string | null>(null)
  const [input, setInput] = useState('')
  const [streaming, setStreaming] = useState(false)
  const [streamBuf, setStreamBuf] = useState('')
  const bottomRef = useRef<HTMLDivElement>(null)
  const stopRef = useRef<(() => void) | null>(null)

  const { data: sessions = [] } = useQuery({ queryKey: ['sessions'], queryFn: getSessions })
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

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, streamBuf])

  const send = useCallback(() => {
    if (!input.trim() || streaming) return
    const text = input.trim()
    setInput('')
    setStreaming(true)
    setStreamBuf('')

    const sessionId = activeSession
    stopRef.current = apiSSE(
      '/api/chat',
      { message: text, session_id: sessionId },
      (chunk) => setStreamBuf((b) => b + chunk),
      () => {
        setStreaming(false)
        setStreamBuf('')
        qc.invalidateQueries({ queryKey: ['messages', sessionId] })
        qc.invalidateQueries({ queryKey: ['sessions'] })
      },
      (err) => {
        setStreaming(false)
        setStreamBuf(`Error: ${err.message}`)
      },
    )
  }, [input, streaming, activeSession, qc])

  const displayMessages: (Message | { id: string; role: 'assistant'; content: string; created_at: string })[] = [
    ...messages,
    ...(streamBuf ? [{ id: '__stream__', role: 'assistant' as const, content: streamBuf, created_at: '' }] : []),
  ]

  return (
    <div className="flex h-[calc(100vh-3rem)] overflow-hidden -m-4">
      {/* Session list */}
      <aside className="w-56 border-r flex flex-col shrink-0">
        <div className="p-3 border-b flex items-center justify-between">
          <span className="text-sm font-medium">Sessions</span>
          <Button size="icon" variant="ghost" className="h-7 w-7" onClick={() => newSession.mutate()}>
            <Plus className="h-4 w-4" />
          </Button>
        </div>
        <ScrollArea className="flex-1">
          <div className="p-2 space-y-1">
            {sessions.map((s) => (
              <button
                key={s.id}
                className={cn(
                  'w-full text-left rounded-md px-2 py-1.5 text-sm truncate transition-colors hover:bg-muted',
                  activeSession === s.id && 'bg-muted font-medium',
                )}
                onClick={() => setActiveSession(s.id)}
              >
                {s.name || `Session ${s.id.slice(0, 6)}`}
              </button>
            ))}
            {sessions.length === 0 && (
              <p className="text-xs text-muted-foreground px-2 py-1">No sessions yet</p>
            )}
          </div>
        </ScrollArea>
      </aside>

      {/* Chat area */}
      <div className="flex flex-col flex-1 overflow-hidden">
        {!activeSession ? (
          <div className="flex-1 flex items-center justify-center text-muted-foreground text-sm">
            <div className="text-center space-y-3">
              <Crown className="h-10 w-10 mx-auto opacity-20" />
              <p>Select a session or create a new one</p>
              <Button size="sm" onClick={() => newSession.mutate()}>New Session</Button>
            </div>
          </div>
        ) : (
          <>
            <ScrollArea className="flex-1 p-4">
              <div className="space-y-4 max-w-2xl mx-auto">
                {displayMessages.map((m) => (
                  <div key={m.id} className={cn('flex gap-3', m.role === 'user' && 'flex-row-reverse')}>
                    <Avatar className="h-7 w-7 shrink-0 mt-0.5">
                      <AvatarFallback className="text-xs">
                        {m.role === 'user' ? <User className="h-3.5 w-3.5" /> : <Crown className="h-3.5 w-3.5" />}
                      </AvatarFallback>
                    </Avatar>
                    <div
                      className={cn(
                        'rounded-lg px-3 py-2 text-sm max-w-[80%] whitespace-pre-wrap',
                        m.role === 'user'
                          ? 'bg-primary text-primary-foreground'
                          : 'bg-muted',
                      )}
                    >
                      {m.content}
                      {m.id === '__stream__' && (
                        <span className="inline-block w-1.5 h-3.5 bg-current ml-0.5 animate-pulse" />
                      )}
                    </div>
                  </div>
                ))}
                <div ref={bottomRef} />
              </div>
            </ScrollArea>

            <div className="border-t p-3">
              <div className="flex gap-2 max-w-2xl mx-auto">
                {streaming && (
                  <Badge variant="secondary" className="text-xs">Streaming…</Badge>
                )}
                <Input
                  className="flex-1"
                  placeholder="Message Majestic…"
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  onKeyDown={(e) => e.key === 'Enter' && !e.shiftKey && send()}
                  disabled={streaming}
                />
                <Button size="icon" onClick={send} disabled={streaming || !input.trim()}>
                  <Send className="h-4 w-4" />
                </Button>
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  )
}
