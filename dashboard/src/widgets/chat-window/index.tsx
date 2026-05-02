import { useRef, useEffect, useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import { Avatar, AvatarFallback } from '@/components/ui/avatar'
import {
  ArrowUp, Square, Plus, Loader2, User, X, Paperclip,
  Globe, Database, FileText, Search, TrendingUp,
  Newspaper, Brain, Lightbulb, GitBranch, Wrench,
} from 'lucide-react'
import { ModelSelector } from './model-selector'
import { uploadWorkspaceFile } from '@/shared/api/workspace'
import type { Message } from '@/entities/message/model'
import type { StreamMessage, ToolEvent } from '@/entities/message/model'
import { cn } from '@/lib/utils'

export type { StreamMessage }

// ── Tool metadata ─────────────────────────────────────────────────────────────

type IconComponent = React.ComponentType<{ className?: string }>

const TOOL_META: Record<string, { Icon: IconComponent; label: string }> = {
  search_web:        { Icon: Globe,       label: 'Searching the web' },
  search_knowledge:  { Icon: Database,    label: 'Searching knowledge' },
  write_file:        { Icon: FileText,    label: 'Writing file' },
  read_file:         { Icon: FileText,    label: 'Reading file' },
  get_market_data:   { Icon: TrendingUp,  label: 'Fetching market data' },
  get_news:          { Icon: Newspaper,   label: 'Getting news' },
  get_briefing:      { Icon: Brain,       label: 'Getting briefing' },
  get_report:        { Icon: FileText,    label: 'Getting report' },
  generate_ideas:    { Icon: Lightbulb,   label: 'Generating ideas' },
  run_research:      { Icon: Search,      label: 'Running research' },
  delegate_task:     { Icon: GitBranch,   label: 'Delegating task' },
  delegate_parallel: { Icon: GitBranch,   label: 'Running parallel tasks' },
}

function argHint(args: Record<string, unknown>): string | null {
  const val = args.query ?? args.q ?? args.prompt ?? args.text ?? args.path ?? args.file_path ?? args.task
  if (typeof val === 'string' && val.trim()) return val.trim().slice(0, 80)
  return null
}

function ToolStatus({ event }: { event: ToolEvent }) {
  const meta = TOOL_META[event.name]
  const Icon = meta?.Icon ?? Wrench
  const label = meta?.label ?? event.name.replace(/_/g, ' ')
  const hint = argHint(event.args)
  return (
    <div className="flex items-center gap-2 text-sm text-muted-foreground py-0.5 min-w-0">
      <Icon
        className={cn(
          'h-3.5 w-3.5 shrink-0',
          event.status === 'running' && 'text-primary animate-pulse',
        )}
      />
      <span className="shrink-0">{label}</span>
      {hint && (
        <span className="text-muted-foreground/40 truncate text-xs">· {hint}</span>
      )}
    </div>
  )
}

// ── Message bubble ─────────────────────────────────────────────────────────────

const FILE_RE = /\[Attached workspace file: "([^"]+)", path: "[^"]+" — use read_file\("[^"]+"\) to read it\]/g

function parseUserContent(content: string): { text: string; files: string[] } {
  const files: string[] = []
  const text = content.replace(FILE_RE, (_, name: string) => { files.push(name); return '' }).trim()
  return { text, files }
}

function MessageBubble({ msg }: { msg: Message | StreamMessage }) {
  const isUser = msg.role === 'user'
  const isStreaming = 'streaming' in msg && msg.streaming
  const { text, files } = isUser ? parseUserContent(msg.content) : { text: msg.content, files: [] as string[] }

  return (
    <div className={cn('flex gap-2.5', isUser && 'flex-row-reverse')}>
      <Avatar className="h-6 w-6 shrink-0 mt-1">
        <AvatarFallback className="bg-muted">
          {isUser
            ? <User className="h-3.5 w-3.5" />
            : <img src="/majestic-icon.png" alt="" className="h-3.5 w-3.5" />}
        </AvatarFallback>
      </Avatar>
      <div className={cn('flex flex-col gap-1 max-w-[78%]', isUser && 'items-end')}>
        <div className={cn(
          'rounded-xl px-3 py-2 text-sm leading-relaxed break-words',
          isUser ? 'bg-primary text-primary-foreground' : 'bg-muted text-foreground',
        )}>
          {isUser ? (
            <div className="flex flex-col gap-1.5">
              {text && <span className="whitespace-pre-wrap">{text}</span>}
              {files.map(name => (
                <div key={name} className="flex items-center gap-1.5 bg-primary-foreground/15 rounded-full px-2.5 py-1 text-xs self-start">
                  <Paperclip className="h-3 w-3 shrink-0" />
                  <span className="truncate max-w-[180px]">{name}</span>
                </div>
              ))}
            </div>
          ) : (
            <div className="prose prose-sm dark:prose-invert max-w-none [&>*:first-child]:mt-0 [&>*:last-child]:mb-0">
              <ReactMarkdown remarkPlugins={[remarkGfm]}>{msg.content}</ReactMarkdown>
            </div>
          )}
          {isStreaming && (
            <span className="inline-block w-1.5 h-4 bg-current ml-0.5 align-[-3px] animate-pulse rounded-sm" />
          )}
        </div>
      </div>
    </div>
  )
}

// ── Main component ─────────────────────────────────────────────────────────────

interface AttachedFile { name: string; path: string }

interface Props {
  messages: Message[]
  streamMsgs: StreamMessage[]
  toolEvents: ToolEvent[]
  input: string
  onInputChange: (v: string) => void
  onSend: (extra?: string) => void
  onStop: () => void
  streaming: boolean
}

export function ChatWindow({
  messages, streamMsgs, toolEvents, input,
  onInputChange, onSend, onStop, streaming,
}: Props) {
  const bottomRef    = useRef<HTMLDivElement>(null)
  const fileRef      = useRef<HTMLInputElement>(null)
  const textareaRef  = useRef<HTMLTextAreaElement>(null)
  const scrollRef    = useRef<HTMLDivElement>(null)
  const inputWrapRef = useRef<HTMLDivElement>(null)
  const [attachedFiles, setAttachedFiles] = useState<AttachedFile[]>([])

  // Reset textarea height when input is cleared (after send)
  useEffect(() => {
    const el = textareaRef.current
    if (!input && el) { el.style.height = 'auto'; el.style.height = '60px' }
  }, [input])

  // Scroll to bottom on new messages/events
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, streamMsgs, toolEvents])

  // Keep messages padding-bottom = input height so last message is never hidden
  // Input is absolute-positioned, so it never affects the flex/scroll layout
  useEffect(() => {
    const wrap = inputWrapRef.current
    const scroll = scrollRef.current
    if (!wrap || !scroll) return
    const update = () => {
      scroll.style.paddingBottom = `${wrap.getBoundingClientRect().height}px`
    }
    update()
    const obs = new ResizeObserver(update)
    obs.observe(wrap)
    return () => obs.disconnect()
  }, [])

  const upload = useMutation({
    mutationFn: async (file: File) => {
      const buf = await file.arrayBuffer()
      const bytes = new Uint8Array(buf)
      let b64 = ''
      for (let i = 0; i < bytes.length; i++) b64 += String.fromCharCode(bytes[i])
      return uploadWorkspaceFile('', file.name, btoa(b64))
    },
    onSuccess: (data, file) => {
      const path = data.path ?? file.name
      setAttachedFiles(prev => [...prev, { name: file.name, path }])
    },
  })

  const handleSubmit = () => {
    if (!input.trim() && attachedFiles.length === 0) return
    const refs = attachedFiles.map(f =>
      `[Attached workspace file: "${f.name}", path: "${f.path}" — use read_file("${f.path}") to read it]`
    ).join('\n')
    setAttachedFiles([])
    onSend(refs || undefined)
  }

  const streamUser      = streamMsgs.find((m) => m.role === 'user')
  const streamAssistant = streamMsgs.find((m) => m.role === 'assistant')
  const activeTools     = toolEvents.filter((te) => !te.dim)
  const hasContent      = !!(streamAssistant?.content)

  return (
    <div className="flex-1 min-h-0 relative">
      {/* ── Messages — fills entire space, padding-bottom keeps last msg above input ── */}
      <div ref={scrollRef} className="absolute inset-0 overflow-y-auto">
        <div className="max-w-3xl mx-auto px-4 py-4 space-y-5">
          {messages.length === 0 && !streamMsgs.length && (
            <div className="flex flex-col items-center justify-center py-16 text-muted-foreground">
              <img src="/majestic-icon.png" alt="Majestic" className="h-12 w-12 mb-3 opacity-30" />
              <p className="text-sm">Start a conversation</p>
            </div>
          )}

          {messages.map((m) => <MessageBubble key={m.id} msg={m} />)}

          {streamUser && <MessageBubble msg={streamUser} />}

          {/* Inline tool statuses — shown while streaming */}
          {streaming && activeTools.length > 0 && (
            <div className="pl-9 space-y-1">
              {activeTools.map((te) => <ToolStatus key={te.id} event={te} />)}
            </div>
          )}

          {/* Assistant reply */}
          {streamAssistant && (
            hasContent ? (
              <MessageBubble msg={streamAssistant} />
            ) : !activeTools.length ? (
              <div className="flex gap-2.5">
                <div className="h-6 w-6 shrink-0" />
                <div className="bg-muted rounded-xl px-3 py-2">
                  <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
                </div>
              </div>
            ) : null
          )}

          <div ref={bottomRef} />
        </div>
      </div>

      {/* ── Input box — absolute at bottom, never affects scroll layout ─── */}
      <div ref={inputWrapRef} className="absolute bottom-0 left-0 right-0 pb-3" style={{ margin: '0 20px' }}>
        <div className="max-w-3xl mx-auto px-3">

          {/* Attached file badges */}
          {attachedFiles.length > 0 && (
            <div className="flex flex-wrap gap-1.5 mb-2 px-1">
              {attachedFiles.map((f) => (
                <div key={f.path} className="flex items-center gap-1 bg-muted rounded-full px-2.5 py-1 text-xs text-muted-foreground">
                  <Paperclip className="h-3 w-3 shrink-0" />
                  <span className="truncate max-w-[140px]">{f.name}</span>
                  <button
                    type="button"
                    className="ml-0.5 hover:text-foreground transition-colors"
                    onClick={() => setAttachedFiles(prev => prev.filter(a => a.path !== f.path))}
                  >
                    <X className="h-3 w-3" />
                  </button>
                </div>
              ))}
            </div>
          )}

          <div className="border rounded-xl bg-muted focus-within:ring-1 focus-within:ring-ring/30">
          <Textarea
            ref={textareaRef}
            className="border-0 shadow-none resize-none !bg-transparent dark:!bg-transparent text-sm px-4 pt-3 pb-1 focus-visible:ring-0 focus-visible:ring-offset-0 overflow-hidden"
            style={{ minHeight: '60px' }}
            placeholder="Write a message…"
            value={input}
            onChange={(e) => {
              onInputChange(e.target.value)
              const el = e.target
              el.style.height = 'auto'
              el.style.height = Math.min(el.scrollHeight, 200) + 'px'
            }}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSubmit() }
            }}
            disabled={streaming}
          />
          <div className="flex items-center gap-1 px-3 pb-2.5 pt-0.5">
            {/* Attach file */}
            <button
              type="button"
              className="h-7 w-7 flex items-center justify-center rounded-md text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
              onClick={() => fileRef.current?.click()}
              disabled={upload.isPending}
              title="Attach file"
            >
              {upload.isPending
                ? <Loader2 className="h-4 w-4 animate-spin" />
                : <Plus className="h-4 w-4" />}
            </button>

            <div className="flex-1" />

            {/* Model selector */}
            <ModelSelector />

            {/* Send / Stop */}
            <Button
              size="icon"
              className="h-7 w-7 rounded-lg"
              onClick={streaming ? onStop : handleSubmit}
              disabled={!streaming && !input.trim() && attachedFiles.length === 0}
            >
              {streaming
                ? <Square className="h-3.5 w-3.5" fill="currentColor" />
                : <ArrowUp className="h-4 w-4" />}
            </Button>
          </div>
        </div>

        <input
          ref={fileRef}
          type="file"
          className="hidden"
          onChange={(e) => {
            const file = e.target.files?.[0]
            if (file) upload.mutate(file)
            e.target.value = ''
          }}
        />
        </div>
      </div>
    </div>
  )
}
