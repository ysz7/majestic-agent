import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Separator } from '@/components/ui/separator'
import { Trash2, Clock, Calendar, Activity } from 'lucide-react'
import { apiFetch } from '@/shared/api/client'

interface DayStats {
  date: string
  tokens_in: number
  tokens_out: number
  cost: number
  requests: number
}

interface MonitoringData {
  tokens: {
    total_in: number
    total_out: number
    total_cost_usd: number
    requests: number
    by_day: DayStats[]
  }
  schedules: {
    id: number; name: string; cron: string; prompt: string
    enabled: boolean; last_ran?: string; delivery_target?: string
  }[]
  reminders: {
    id: string; text: string; dt: string; done: boolean
  }[]
}

function TokenBarChart({ days }: { days: DayStats[] }) {
  if (days.length === 0) return <p className="text-xs text-muted-foreground py-4 text-center">No usage data yet</p>

  const maxCost = Math.max(...days.map((d) => d.cost), 0.0001)

  return (
    <div className="space-y-1.5">
      {days.slice(-14).map((day) => (
        <div key={day.date} className="flex items-center gap-2 text-xs">
          <span className="text-muted-foreground w-20 shrink-0 font-mono">
            {day.date.slice(5)}
          </span>
          <div className="flex-1 h-5 bg-muted/40 rounded-sm overflow-hidden relative">
            <div
              className="h-full bg-primary/70 rounded-sm transition-all"
              style={{ width: `${Math.max((day.cost / maxCost) * 100, 1)}%` }}
            />
          </div>
          <span className="w-14 text-right text-muted-foreground shrink-0">
            ${day.cost.toFixed(4)}
          </span>
          <span className="w-16 text-right text-muted-foreground shrink-0 hidden sm:block">
            {(day.tokens_in + day.tokens_out).toLocaleString()} tok
          </span>
        </div>
      ))}
    </div>
  )
}

function formatDt(iso: string) {
  if (!iso) return '—'
  return new Date(iso).toLocaleString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
}

export function MonitoringPage() {
  const qc = useQueryClient()
  const { data, isLoading } = useQuery<MonitoringData>({
    queryKey: ['monitoring'],
    queryFn: () => apiFetch('/api/monitoring'),
    refetchInterval: 15_000,
  })

  const delSchedule = useMutation({
    mutationFn: (id: number) => apiFetch(`/api/schedules/${id}`, { method: 'DELETE' }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['monitoring'] }),
  })

  if (isLoading) return <p className="text-sm text-muted-foreground p-4">Loading…</p>

  const tok = data?.tokens
  const schedules = data?.schedules ?? []
  const reminders = data?.reminders ?? []

  return (
    <div className="space-y-5 max-w-2xl">
      <div>
        <h2 className="text-lg font-semibold">Monitoring</h2>
        <p className="text-sm text-muted-foreground">Token usage, schedules and reminders</p>
      </div>

      {/* Summary cards */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        {[
          { label: 'Total cost', value: tok ? `$${tok.total_cost_usd.toFixed(4)}` : '—' },
          { label: 'Requests', value: tok?.requests?.toLocaleString() ?? '—' },
          { label: 'Tokens in', value: tok?.total_in?.toLocaleString() ?? '—' },
          { label: 'Tokens out', value: tok?.total_out?.toLocaleString() ?? '—' },
        ].map((s) => (
          <Card key={s.label}>
            <CardHeader className="pb-1 pt-3 px-4">
              <CardTitle className="text-[11px] font-medium text-muted-foreground uppercase tracking-wide">
                {s.label}
              </CardTitle>
            </CardHeader>
            <CardContent className="pb-3 px-4">
              <p className="text-sm font-semibold tabular-nums">{s.value}</p>
            </CardContent>
          </Card>
        ))}
      </div>

      {/* Token chart */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm flex items-center gap-2">
            <Activity className="h-4 w-4 text-muted-foreground" />
            Cost by day (last 14 days)
          </CardTitle>
        </CardHeader>
        <CardContent>
          <TokenBarChart days={tok?.by_day ?? []} />
        </CardContent>
      </Card>

      {/* Schedules */}
      <div className="space-y-2">
        <div className="flex items-center gap-2">
          <Calendar className="h-4 w-4 text-muted-foreground" />
          <span className="text-sm font-medium">Schedules</span>
          <Badge variant="secondary" className="text-xs">{schedules.length}</Badge>
        </div>
        {schedules.length === 0 && (
          <p className="text-xs text-muted-foreground">No schedules. Use /schedule add &lt;text&gt; in chat.</p>
        )}
        {schedules.map((s) => (
          <Card key={s.id}>
            <CardHeader className="pb-1 pt-3 px-4 flex-row items-start justify-between gap-2">
              <div className="space-y-0.5 min-w-0">
                <p className="text-sm font-medium flex items-center gap-2">
                  {s.name}
                  <Badge variant={s.enabled ? 'default' : 'secondary'} className="text-[10px]">
                    {s.enabled ? 'active' : 'paused'}
                  </Badge>
                </p>
                <p className="text-xs text-muted-foreground font-mono">{s.cron}</p>
              </div>
              <Button
                size="icon" variant="ghost"
                className="h-6 w-6 shrink-0 text-muted-foreground hover:text-destructive"
                onClick={() => delSchedule.mutate(s.id)}
              >
                <Trash2 className="h-3 w-3" />
              </Button>
            </CardHeader>
            <CardContent className="pb-3 px-4">
              <p className="text-xs text-muted-foreground truncate">{s.prompt}</p>
              {s.last_ran && (
                <p className="text-[10px] text-muted-foreground mt-1">Last ran: {formatDt(s.last_ran)}</p>
              )}
            </CardContent>
          </Card>
        ))}
      </div>

      <Separator />

      {/* Reminders */}
      <div className="space-y-2">
        <div className="flex items-center gap-2">
          <Clock className="h-4 w-4 text-muted-foreground" />
          <span className="text-sm font-medium">Reminders</span>
          <Badge variant="secondary" className="text-xs">{reminders.length}</Badge>
        </div>
        {reminders.length === 0 && (
          <p className="text-xs text-muted-foreground">No reminders. Use /remind &lt;text&gt; in chat.</p>
        )}
        {reminders.map((r) => (
          <div key={r.id} className="flex items-center gap-3 rounded-md border px-3 py-2.5">
            <Clock className="h-3.5 w-3.5 text-muted-foreground shrink-0" />
            <div className="flex-1 min-w-0">
              <p className="text-sm truncate">{r.text}</p>
              <p className="text-xs text-muted-foreground">{formatDt(r.dt)}</p>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
