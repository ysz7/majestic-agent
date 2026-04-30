import { useRef, useEffect } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import { Avatar, AvatarFallback } from '@/components/ui/avatar'
import { Send, Crown, User, Wrench, Loader2 } from 'lucide-react'
import type { Message, ToolCallEvent } from '@/entities/message/model'
import { cn } from '@/lib/utils'

export interface StreamMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
  toolCalls?: ToolCallEvent[]
  streaming?: boolean
}

interface Props {
  messages: Message[]
  streamMsgs: StreamMessage[]
  input: string
  onInputChange: (v: string) => void
  onSend: () => void
  streaming: boolean
}

function ToolCallCard({ call }: { call: ToolCallEvent }) {
  const summary = Object.entries(call.args)
    .map(([k, v]) => `${k}: ${String(v).slice(0, 120)}`)
    .join(' · ')

  return (
    <div className="flex items-start gap-2 rounded-md border bg-muted/50 px-3 py-2 text-xs w-full">
      <Wrench className="h-3.5 w-3.5 mt-0.5 shrink-0 text-muted-foreground" />
      <div className="min-w-0 flex-1">
        <span className="font-medium font-mono">{call.name}</span>
        {summary && <p className="text-muted-foreground mt-0.5 break-words">{summary}</p>}
      </div>
    </div>
  )
}

function MessageBubble({ msg }: { msg: Message | StreamMessage }) {
  const isUser = msg.role === 'user'
  const isStreaming = 'streaming' in msg && msg.streaming
  const toolCalls = 'toolCalls' in msg ? msg.toolCalls : undefined

  return (
    <div className={cn('flex gap-2.5', isUser && 'flex-row-reverse')}>
      <Avatar className="h-6 w-6 shrink-0 mt-1">
        <AvatarFallback className="bg-muted">
          {isUser ? <User className="h-3 w-3" /> : <Crown className="h-3 w-3" />}
        </AvatarFallback>
      </Avatar>
      <div className={cn('flex flex-col gap-1.5 max-w-[78%]', isUser && 'items-end')}>
        {toolCalls && toolCalls.length > 0 && (
          <div className="space-y-1 w-full">
            {toolCalls.map((tc, i) => <ToolCallCard key={i} call={tc} />)}
          </div>
        )}
        {msg.content && (
          <div
            className={cn(
              'rounded-xl px-3 py-2 text-sm leading-relaxed break-words',
              isUser
                ? 'bg-primary text-primary-foreground'
                : 'bg-muted text-foreground',
            )}
          >
            {isUser ? (
              <span className="whitespace-pre-wrap">{msg.content}</span>
            ) : (
              <ReactMarkdown
                remarkPlugins={[remarkGfm]}
                className="prose prose-sm dark:prose-invert max-w-none [&>*:first-child]:mt-0 [&>*:last-child]:mb-0"
              >
                {msg.content}
              </ReactMarkdown>
            )}
            {isStreaming && (
              <span className="inline-block w-1.5 h-4 bg-current ml-0.5 align-[-3px] animate-pulse rounded-sm" />
            )}
          </div>
        )}
        {isStreaming && !msg.content && (
          <div className="bg-muted rounded-xl px-3 py-2">
            <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
          </div>
        )}
      </div>
    </div>
  )
}

export function ChatWindow({ messages, streamMsgs, input, onInputChange, onSend, streaming }: Props) {
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, streamMsgs])

  const allMessages: (Message | StreamMessage)[] = [...messages, ...streamMsgs]

  return (
    <div className="flex flex-col flex-1 min-h-0">
      <div className="flex-1 overflow-y-auto min-h-0">
        <div className="px-4 py-4 space-y-5 max-w-2xl mx-auto">
          {allMessages.length === 0 && (
            <div className="flex flex-col items-center justify-center py-16 text-muted-foreground">
              <Crown className="h-8 w-8 mb-3 opacity-20" />
              <p className="text-sm">Start a conversation</p>
            </div>
          )}
          {allMessages.map((m) => <MessageBubble key={m.id} msg={m} />)}
          <div ref={bottomRef} />
        </div>
      </div>

      <div className="border-t p-3">
        <div className="flex gap-2 max-w-2xl mx-auto items-end">
          <Textarea
            className="flex-1 min-h-[40px] max-h-32 resize-none text-sm"
            placeholder="Message Majestic… (Enter to send, Shift+Enter for newline)"
            value={input}
            rows={1}
            onChange={(e) => onInputChange(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault()
                onSend()
              }
            }}
            disabled={streaming}
          />
          <Button
            size="icon"
            className="h-10 w-10 shrink-0"
            onClick={onSend}
            disabled={streaming || !input.trim()}
          >
            {streaming ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
          </Button>
        </div>
        {streaming && (
          <p className="text-[11px] text-muted-foreground max-w-2xl mx-auto mt-1.5">
            Agent is thinking…
          </p>
        )}
      </div>
    </div>
  )
}
