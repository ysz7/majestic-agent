import { useRef, useState, useEffect } from 'react'
import { Loader2, Check, X, Wrench } from 'lucide-react'
import { cn } from '@/lib/utils'
import type { ToolEvent } from '@/features/send-message/model'

interface Props {
  toolEvents: ToolEvent[]
  streaming: boolean
}

const MAIN_R = 40
const RING_R = 50
const MAIN_CY = 72
const RING_BOTTOM = MAIN_CY + RING_R + 2
const TOOL_W = 132
const TOOL_COLS = 3
const COL_STEP = 152
const ROW_STEP = 74
const NODES_TOP = 190

type Status = 'idle' | 'thinking' | 'running_tool'

function agentStatus(streaming: boolean, events: ToolEvent[]): Status {
  if (!streaming) return 'idle'
  return events.some(e => e.status === 'running' && !e.dim) ? 'running_tool' : 'thinking'
}

function nodePositions(events: ToolEvent[], w: number) {
  if (!events.length) return []
  const cols = Math.min(TOOL_COLS, events.length)
  const totalW = cols * TOOL_W + (cols - 1) * (COL_STEP - TOOL_W)
  const startX = w / 2 - totalW / 2
  return events.map((_, i) => ({
    x: startX + (i % TOOL_COLS) * COL_STEP,
    y: NODES_TOP + Math.floor(i / TOOL_COLS) * ROW_STEP,
  }))
}

function argPreview(args: Record<string, unknown>) {
  const entries = Object.entries(args)
  if (!entries.length) return ''
  const [k, v] = entries[0]
  const str = String(v).slice(0, 36)
  return entries.length > 1 ? `${k}: ${str} +${entries.length - 1}` : `${k}: ${str}`
}

export function AgentGraph({ toolEvents, streaming }: Props) {
  const containerRef = useRef<HTMLDivElement>(null)
  const [w, setW] = useState(640)

  useEffect(() => {
    const el = containerRef.current
    if (!el) return
    // measure immediately, then observe changes
    setW(el.getBoundingClientRect().width || 640)
    const ro = new ResizeObserver(([entry]) => {
      if (entry.contentRect.width > 0) setW(entry.contentRect.width)
    })
    ro.observe(el)
    return () => ro.disconnect()
  }, [])

  const status = agentStatus(streaming, toolEvents)
  const positions = nodePositions(toolEvents, w)
  const cx = w / 2

  return (
    // absolute inset-0: fills the relative parent without relying on h-full
    <div ref={containerRef} className="absolute inset-0 select-none overflow-hidden">
      {/* SVG: ring + edges — pure CSS sizing, no inline height override */}
      <svg className="absolute inset-0 w-full h-full pointer-events-none">
        {status === 'idle' && (
          <circle cx={cx} cy={MAIN_CY} r={RING_R} fill="none" stroke="#6b7280" strokeWidth="2" strokeOpacity="0.25" />
        )}
        {status === 'thinking' && (
          <circle cx={cx} cy={MAIN_CY} r={RING_R} fill="none" stroke="#22c55e" strokeWidth="2.5">
            <animate attributeName="stroke-opacity" values="0.9;0.2;0.9" dur="1.5s" repeatCount="indefinite" />
          </circle>
        )}
        {status === 'running_tool' && (
          <circle cx={cx} cy={MAIN_CY} r={RING_R} fill="none" stroke="#3b82f6" strokeWidth="2.5" strokeDasharray="18 8">
            <animateTransform attributeName="transform" type="rotate"
              from={`0 ${cx} ${MAIN_CY}`} to={`360 ${cx} ${MAIN_CY}`}
              dur="2s" repeatCount="indefinite" />
          </circle>
        )}
        {positions.map((pos, i) => {
          const ex = pos.x + TOOL_W / 2
          const midY = (RING_BOTTOM + pos.y) / 2
          const ev = toolEvents[i]
          const color = ev.dim ? '#4b5563'
            : ev.status === 'done' ? '#22c55e'
            : ev.status === 'error' ? '#ef4444'
            : '#3b82f6'
          return (
            <path key={ev.id}
              d={`M ${cx} ${RING_BOTTOM} C ${cx} ${midY}, ${ex} ${midY}, ${ex} ${pos.y}`}
              fill="none" stroke={color} strokeWidth="1.5"
              strokeOpacity={ev.dim ? 0.25 : 0.7}
            />
          )
        })}
      </svg>

      {/* Main node */}
      <div className="absolute flex flex-col items-center gap-1.5"
        style={{ left: cx - MAIN_R, top: MAIN_CY - MAIN_R, width: MAIN_R * 2 }}>
        <div className="rounded-full bg-muted flex items-center justify-center border border-border/50"
          style={{ width: MAIN_R * 2, height: MAIN_R * 2 }}>
          <img src="/majestic-icon.png" alt="Majestic" className="w-10 h-10 object-contain" />
        </div>
      </div>
      <div className="absolute text-center" style={{ left: cx - 56, top: MAIN_CY + MAIN_R + 8, width: 112 }}>
        <p className="text-xs font-semibold">Majestic</p>
        <p className="text-[10px] text-muted-foreground">
          {status === 'idle' ? 'idle' : status === 'thinking' ? 'thinking…' : 'running tool…'}
        </p>
      </div>

      {/* Tool nodes */}
      {toolEvents.map((ev, i) => {
        const pos = positions[i]
        if (!pos) return null
        return (
          <div key={ev.id}
            className={cn(
              'absolute rounded-lg border bg-card px-2.5 py-2',
              'animate-in fade-in zoom-in-95 duration-200',
              ev.dim && 'opacity-25',
              !ev.dim && ev.status === 'done' && 'border-green-500/40',
              !ev.dim && ev.status === 'error' && 'border-red-500/40',
              !ev.dim && ev.status === 'running' && 'border-blue-500/40',
            )}
            style={{ width: TOOL_W, left: pos.x, top: pos.y }}
          >
            <div className="flex items-center gap-1.5 min-w-0">
              <Wrench className="h-3 w-3 text-muted-foreground shrink-0" />
              <span className="text-[11px] font-medium font-mono truncate flex-1">{ev.name}</span>
              {!ev.dim && ev.status === 'running' && <Loader2 className="h-3 w-3 animate-spin text-blue-500 shrink-0" />}
              {!ev.dim && ev.status === 'done' && <Check className="h-3 w-3 text-green-500 shrink-0" />}
              {!ev.dim && ev.status === 'error' && <X className="h-3 w-3 text-red-500 shrink-0" />}
            </div>
            {Object.keys(ev.args).length > 0 && (
              <p className="text-[10px] text-muted-foreground mt-0.5 truncate">{argPreview(ev.args)}</p>
            )}
          </div>
        )
      })}

      {toolEvents.length === 0 && (
        <p className="absolute text-[11px] text-muted-foreground/50 text-center"
          style={{ left: 0, right: 0, top: NODES_TOP }}>
          Tool calls will appear here
        </p>
      )}
    </div>
  )
}
