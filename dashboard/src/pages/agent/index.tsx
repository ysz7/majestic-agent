import { useState, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs'
import { Activity, BookOpen, Code2, X } from 'lucide-react'
import { apiFetch } from '@/shared/api/client'

interface Job {
  id: string
  type: string
  name: string
  status: 'running' | 'done' | 'failed' | 'cancelled'
  started_at: number
  finished_at: number | null
  result: string | null
  error: string | null
}

interface Reflection {
  id: string
  name: string
  modified_at: number
}

interface ScriptStat {
  runs: number
  failures: number
  success_rate: number
  last_used: number | null
}

function fmtTime(epoch: number | null): string {
  if (!epoch) return '—'
  return new Date(epoch * 1000).toLocaleTimeString()
}

function fmtDur(job: Job): string {
  if (!job.finished_at) return '…'
  const s = job.finished_at - job.started_at
  return s < 60 ? `${s}s` : `${Math.floor(s / 60)}m ${s % 60}s`
}

const STATUS_VARIANT: Record<string, 'default' | 'secondary' | 'destructive' | 'outline'> = {
  running: 'default',
  done: 'secondary',
  failed: 'destructive',
  cancelled: 'outline',
}

// ── Jobs ──────────────────────────────────────────────────────────────────────

function JobsTab() {
  const qc = useQueryClient()
  const [liveJobs, setLiveJobs] = useState<Job[]>([])

  const { data, isLoading } = useQuery<{ jobs: Job[] }>({
    queryKey: ['agent-jobs'],
    queryFn: () => apiFetch('/api/jobs'),
    refetchInterval: 8_000,
  })

  useEffect(() => {
    const es = new EventSource('/api/jobs/stream')
    es.onmessage = (e) => {
      try {
        const d = JSON.parse(e.data as string)
        if (d.type === 'job_update') setLiveJobs(d.jobs as Job[])
      } catch {}
    }
    return () => es.close()
  }, [])

  const cancel = useMutation({
    mutationFn: (id: string) =>
      apiFetch(`/api/jobs/${id}/cancel`, { method: 'POST', body: '{}' }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['agent-jobs'] }),
  })

  const jobs = liveJobs.length > 0 ? liveJobs : (data?.jobs ?? [])

  if (isLoading && jobs.length === 0)
    return <p className="text-sm text-muted-foreground p-4">Loading…</p>

  if (jobs.length === 0)
    return <p className="text-sm text-muted-foreground p-4 text-center">No background jobs yet.</p>

  return (
    <div className="space-y-0.5">
      <div className="grid grid-cols-[10rem_6rem_8rem_1fr_6rem_5rem_2.5rem] gap-2 px-3 py-1.5 text-[11px] uppercase text-muted-foreground font-medium border-b">
        <span>ID</span><span>Type</span><span>Status</span><span>Name</span>
        <span>Started</span><span>Dur</span><span />
      </div>
      {jobs.map((j) => (
        <div key={j.id}>
          <div className="grid grid-cols-[10rem_6rem_8rem_1fr_6rem_5rem_2.5rem] gap-2 items-center px-3 py-2 text-sm hover:bg-muted/30 rounded-md">
            <span className="font-mono text-[11px] text-muted-foreground truncate">{j.id}</span>
            <Badge variant="outline" className="text-[10px] w-fit px-1.5">{j.type}</Badge>
            <Badge variant={STATUS_VARIANT[j.status] ?? 'secondary'} className="text-[10px] w-fit px-1.5">
              {j.status}
            </Badge>
            <span className="truncate text-xs">{j.name}</span>
            <span className="text-xs text-muted-foreground">{fmtTime(j.started_at)}</span>
            <span className="text-xs text-muted-foreground">{fmtDur(j)}</span>
            {j.status === 'running' ? (
              <Button
                size="icon" variant="ghost"
                className="h-5 w-5 text-muted-foreground hover:text-destructive"
                onClick={() => cancel.mutate(j.id)}
              >
                <X className="h-3 w-3" />
              </Button>
            ) : <span />}
          </div>
          {j.error && (
            <p className="px-3 pb-1.5 text-[11px] text-destructive truncate">{j.error}</p>
          )}
        </div>
      ))}
    </div>
  )
}

// ── Reflections ───────────────────────────────────────────────────────────────

function ReflectionsTab() {
  const [expanded, setExpanded] = useState<string | null>(null)
  const [content, setContent] = useState<Record<string, string>>({})

  const { data, isLoading } = useQuery<{ reflections: Reflection[] }>({
    queryKey: ['reflections'],
    queryFn: () => apiFetch('/api/reflections'),
  })

  const toggle = async (id: string) => {
    if (expanded === id) { setExpanded(null); return }
    setExpanded(id)
    if (!content[id]) {
      const d = await apiFetch<{ id: string; content?: string }>(`/api/reflections/${id}`)
      setContent((prev) => ({ ...prev, [id]: d.content ?? '' }))
    }
  }

  if (isLoading) return <p className="text-sm text-muted-foreground p-4">Loading…</p>

  const reflections = data?.reflections ?? []
  if (reflections.length === 0)
    return (
      <p className="text-sm text-muted-foreground p-4 text-center">
        No reflections yet. They appear after sessions with 3+ tool calls.
      </p>
    )

  return (
    <div className="space-y-2">
      {reflections.map((r) => (
        <Card key={r.id} className="cursor-pointer" onClick={() => toggle(r.id)}>
          <CardHeader className="pb-1 pt-3 px-4">
            <CardTitle className="text-sm">{r.name.replace('.md', '')}</CardTitle>
            <p className="text-xs text-muted-foreground">
              {new Date(r.modified_at * 1000).toLocaleString()}
            </p>
          </CardHeader>
          {expanded === r.id && (
            <CardContent className="px-4 pb-3">
              <pre className="text-xs leading-relaxed whitespace-pre-wrap font-sans">
                {content[r.id] ?? 'Loading…'}
              </pre>
            </CardContent>
          )}
        </Card>
      ))}
    </div>
  )
}

// ── Script Stats ──────────────────────────────────────────────────────────────

function ScriptStatsTab() {
  const { data, isLoading } = useQuery<{ stats: Record<string, ScriptStat> }>({
    queryKey: ['script-stats'],
    queryFn: () => apiFetch('/api/script-stats'),
  })

  if (isLoading) return <p className="text-sm text-muted-foreground p-4">Loading…</p>

  const entries = Object.entries(data?.stats ?? {}).sort(
    ([, a], [, b]) => (b.runs || 0) - (a.runs || 0),
  )

  if (entries.length === 0)
    return <p className="text-sm text-muted-foreground p-4 text-center">No script stats yet.</p>

  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
      {entries.map(([name, s]) => (
        <Card key={name}>
          <CardHeader className="pb-1 pt-3 px-4">
            <CardTitle className="text-sm truncate" title={name}>{name}</CardTitle>
          </CardHeader>
          <CardContent className="px-4 pb-3 space-y-1">
            {(
              [
                ['Runs', String(s.runs || 0)],
                ['Success', `${Math.round((s.success_rate || 0) * 100)}%`],
                ['Failures', String(s.failures || 0)],
                ['Last used', s.last_used ? new Date(s.last_used * 1000).toLocaleDateString() : '—'],
              ] as [string, string][]
            ).map(([label, val]) => (
              <div key={label} className="flex justify-between text-xs">
                <span className="text-muted-foreground">{label}</span>
                <span>{val}</span>
              </div>
            ))}
          </CardContent>
        </Card>
      ))}
    </div>
  )
}

// ── Page ──────────────────────────────────────────────────────────────────────

export function AgentPage() {
  return (
    <div className="space-y-5 max-w-5xl">
      <div>
        <h2 className="text-lg font-semibold">Agent Activity</h2>
        <p className="text-sm text-muted-foreground">Background jobs, reflections, and script stats</p>
      </div>

      <Tabs defaultValue="jobs">
        <TabsList variant="line">
          <TabsTrigger value="jobs">
            <Activity className="h-3.5 w-3.5" />
            Jobs
          </TabsTrigger>
          <TabsTrigger value="reflections">
            <BookOpen className="h-3.5 w-3.5" />
            Reflections
          </TabsTrigger>
          <TabsTrigger value="stats">
            <Code2 className="h-3.5 w-3.5" />
            Script Stats
          </TabsTrigger>
        </TabsList>

        <TabsContent value="jobs" className="mt-4">
          <JobsTab />
        </TabsContent>
        <TabsContent value="reflections" className="mt-4">
          <ReflectionsTab />
        </TabsContent>
        <TabsContent value="stats" className="mt-4">
          <ScriptStatsTab />
        </TabsContent>
      </Tabs>
    </div>
  )
}
