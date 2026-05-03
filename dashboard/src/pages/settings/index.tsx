import { useEffect, useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Badge } from '@/components/ui/badge'
import { Switch } from '@/components/ui/switch'
import { Save, CheckCircle2, AlertCircle, Plus, Trash2, Globe, GitBranch, Database, Mail, Play, Square, ChevronDown, ChevronUp } from 'lucide-react'
import { getSettings, saveSettings, getMcpStatus, addMcpServer, removeMcpServer, toggleMcpServer, getEmailStatus, testEmailConnection, saveEmailConfig, startEmailGateway, stopEmailGateway } from '@/shared/api/settings'
import type { Settings, McpServer, EmailConfig } from '@/shared/api/settings'
import { LlmKeysManager } from '@/widgets/llm-keys-manager'

const SEARCH_MODES = ['all', 'docs', 'intel']

function Field({ label, hint, children }: { label: string; hint?: string; children: React.ReactNode }) {
  return (
    <div className="space-y-1.5">
      <Label className="text-sm">{label}</Label>
      {children}
      {hint && <p className="text-xs text-muted-foreground">{hint}</p>}
    </div>
  )
}

export function SettingsPage() {
  const qc = useQueryClient()
  const { data, isLoading } = useQuery({ queryKey: ['settings'], queryFn: getSettings })
  const [form, setForm] = useState<Settings>({})
  const [dirty, setDirty] = useState(false)

  useEffect(() => {
    if (data) { setForm(data); setDirty(false) }
  }, [data])

  const save = useMutation({
    mutationFn: () => saveSettings(form),
    onSuccess: () => {
      setDirty(false)
      qc.invalidateQueries({ queryKey: ['settings'] })
    },
  })

  const set = (key: keyof Settings, val: unknown) => {
    setForm((f) => ({ ...f, [key]: val }))
    setDirty(true)
  }

  const setNested = (section: keyof Settings, key: string, val: unknown) => {
    setForm((f) => ({ ...f, [section]: { ...(f[section] as object ?? {}), [key]: val } }))
    setDirty(true)
  }

  if (isLoading) return <p className="text-sm text-muted-foreground p-4">Loading…</p>

  const agent = form.agent ?? {}
  const api = form.api ?? {}
  const dashboard = form.dashboard ?? {}
  const telegram = form.telegram ?? {}
  const research = form.research ?? {}

  return (
    <div className="space-y-4 max-w-2xl">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold">Settings</h2>
          <p className="text-sm text-muted-foreground">Changes take effect immediately without restart</p>
        </div>
        <div className="flex items-center gap-2">
          {dirty && <Badge variant="secondary" className="text-xs">Unsaved changes</Badge>}
          {save.isSuccess && !dirty && (
            <span className="flex items-center gap-1 text-xs text-green-500">
              <CheckCircle2 className="h-3.5 w-3.5" /> Saved
            </span>
          )}
          {save.isError && (
            <span className="flex items-center gap-1 text-xs text-destructive">
              <AlertCircle className="h-3.5 w-3.5" /> Error
            </span>
          )}
          <Button size="sm" onClick={() => save.mutate()} disabled={!dirty || save.isPending}>
            <Save className="h-3.5 w-3.5 mr-1.5" />
            {save.isPending ? 'Saving…' : 'Save'}
          </Button>
        </div>
      </div>

      <Tabs defaultValue="general">
        <TabsList className="w-full justify-start flex-wrap h-auto gap-1 p-1">
          {['general', 'llm', 'agent', 'research', 'gateways', 'api', 'mcp', 'email'].map((t) => (
            <TabsTrigger key={t} value={t} className="text-xs capitalize">{t}</TabsTrigger>
          ))}
        </TabsList>

        {/* ── General ── */}
        <TabsContent value="general" className="space-y-4 mt-4">
          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-sm">General</CardTitle>
              <CardDescription className="text-xs">Language, currency and search preferences</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <Field label="Language" hint="Response language code (en, uk, de, fr, es…)">
                <Input value={form.language ?? ''} onChange={(e) => set('language', e.target.value)} />
              </Field>
              <Field label="Currency" hint="Used for market data and price display">
                <Input value={form.currency ?? ''} onChange={(e) => set('currency', e.target.value)} />
              </Field>
              <Field label="Search Mode">
                <Select value={form.search_mode ?? undefined} onValueChange={(v) => set('search_mode', v)}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {SEARCH_MODES.map((m) => <SelectItem key={m} value={m}>{m}</SelectItem>)}
                  </SelectContent>
                </Select>
              </Field>
            </CardContent>
          </Card>
        </TabsContent>

        {/* ── LLM ── */}
        <TabsContent value="llm" className="space-y-4 mt-4">
          <Card>
            <CardContent className="pt-4">
              <LlmKeysManager />
            </CardContent>
          </Card>
        </TabsContent>

        {/* ── Agent ── */}
        <TabsContent value="agent" className="space-y-4 mt-4">
          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-sm">Agent Role</CardTitle>
              <CardDescription className="text-xs">Injected into system prompt as custom persona</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <Field label="Role / Persona">
                <Textarea
                  rows={5}
                  placeholder="e.g. You are a financial analyst specializing in crypto markets…"
                  value={agent.role ?? ''}
                  onChange={(e) => setNested('agent', 'role', e.target.value)}
                />
              </Field>
              <Field label="Tools disabled" hint="Comma-separated tool names to disable">
                <Input
                  placeholder="e.g. run_code, send_telegram"
                  value={(agent.tools_disabled ?? []).join(', ')}
                  onChange={(e) => setNested('agent', 'tools_disabled', e.target.value.split(',').map((s) => s.trim()).filter(Boolean))}
                />
              </Field>
              <div className="flex items-center justify-between">
                <div>
                  <Label className="text-sm">Allow scripts</Label>
                  <p className="text-xs text-muted-foreground mt-0.5">Let the agent save and run Python scripts from workspace/scripts/</p>
                </div>
                <Switch
                  checked={agent.allow_scripts !== false}
                  onCheckedChange={(v) => setNested('agent', 'allow_scripts', v)}
                />
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        {/* ── Research ── */}
        <TabsContent value="research" className="space-y-4 mt-4">
          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-sm">Research & Data</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <Field label="Crypto coins" hint="Comma-separated CoinGecko IDs">
                <Input
                  value={(research.crypto_coins ?? []).join(', ')}
                  onChange={(e) => setNested('research', 'crypto_coins', e.target.value.split(',').map((s) => s.trim()).filter(Boolean))}
                />
              </Field>
              <Field label="Stock symbols">
                <Input
                  value={(research.stock_symbols ?? []).join(', ')}
                  onChange={(e) => setNested('research', 'stock_symbols', e.target.value.split(',').map((s) => s.trim()).filter(Boolean))}
                />
              </Field>
              <Field label="Forex pairs">
                <Input
                  value={(research.forex_pairs ?? []).join(', ')}
                  onChange={(e) => setNested('research', 'forex_pairs', e.target.value.split(',').map((s) => s.trim()).filter(Boolean))}
                />
              </Field>
              <Field label="Reddit subreddits" hint="Without r/ prefix">
                <Input
                  value={(research.reddit_subs ?? []).join(', ')}
                  onChange={(e) => setNested('research', 'reddit_subs', e.target.value.split(',').map((s) => s.trim()).filter(Boolean))}
                />
              </Field>
              <Field label="Auto-collect interval (minutes)" hint="0 = disabled">
                <Input
                  type="number"
                  min={0}
                  value={research.auto_interval_minutes ?? 0}
                  onChange={(e) => setNested('research', 'auto_interval_minutes', Number(e.target.value))}
                />
              </Field>
            </CardContent>
          </Card>
        </TabsContent>

        {/* ── Gateways ── */}
        <TabsContent value="gateways" className="space-y-4 mt-4">
          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-sm">Telegram</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <Field label="Morning briefing hour" hint="0 = disabled, 1–23 = send at this UTC hour">
                <Input
                  type="number"
                  min={0}
                  max={23}
                  value={telegram.morning_briefing_hour ?? 0}
                  onChange={(e) => setNested('telegram', 'morning_briefing_hour', Number(e.target.value))}
                />
              </Field>
              <Field label="Allowed user IDs" hint="Comma-separated Telegram user IDs (empty = any)">
                <Input
                  value={(telegram.allowed_user_ids ?? []).join(', ')}
                  onChange={(e) => setNested('telegram', 'allowed_user_ids', e.target.value.split(',').map((s) => Number(s.trim())).filter(Boolean))}
                />
              </Field>
            </CardContent>
          </Card>
        </TabsContent>

        {/* ── API ── */}
        <TabsContent value="api" className="space-y-4 mt-4">
          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-sm">REST API</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <Field label="API port">
                <Input
                  type="number"
                  value={api.port ?? 8080}
                  onChange={(e) => setNested('api', 'port', Number(e.target.value))}
                />
              </Field>
              <Field label="API key" hint="Leave blank to allow localhost-only without auth">
                <Input
                  type="password"
                  placeholder="secret key…"
                  value={api.key ?? ''}
                  onChange={(e) => setNested('api', 'key', e.target.value)}
                />
              </Field>
            </CardContent>
          </Card>
          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-sm">Dashboard</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <Field label="Dashboard port">
                <Input
                  type="number"
                  value={dashboard.port ?? 8090}
                  onChange={(e) => setNested('dashboard', 'port', Number(e.target.value))}
                />
              </Field>
              <Field label="Dashboard password" hint="Leave blank for localhost-only access">
                <Input
                  type="password"
                  placeholder="password…"
                  value={dashboard.password ?? ''}
                  onChange={(e) => setNested('dashboard', 'password', e.target.value)}
                />
              </Field>
            </CardContent>
          </Card>
        </TabsContent>
        {/* ── MCP ── */}
        <TabsContent value="mcp" className="space-y-4 mt-4">
          <McpTab />
        </TabsContent>

        {/* ── Email ── */}
        <TabsContent value="email" className="space-y-4 mt-4">
          <EmailTab />
        </TabsContent>

      </Tabs>
    </div>
  )
}

// ── MCP Tab ───────────────────────────────────────────────────────────────────

const MCP_PRESETS = [
  {
    id: 'browser',
    label: 'Playwright Browser',
    description: 'Screenshots, JS-heavy pages, web automation',
    Icon: Globe,
    command: ['npx', '-y', '@playwright/mcp'],
  },
  {
    id: 'github',
    label: 'GitHub',
    description: 'Repos, issues, PRs, code search. Requires GITHUB_TOKEN env var.',
    Icon: GitBranch,
    command: ['npx', '-y', '@modelcontextprotocol/server-github'],
    env: { GITHUB_TOKEN: '${GITHUB_TOKEN}' },
  },
  {
    id: 'postgres',
    label: 'PostgreSQL',
    description: 'SQL queries, schema inspection. Requires DATABASE_URL env var.',
    Icon: Database,
    command: ['npx', '-y', '@modelcontextprotocol/server-postgres', '${DATABASE_URL}'],
  },
]

function McpTab() {
  const qc = useQueryClient()
  const { data, isLoading } = useQuery({ queryKey: ['mcp-status'], queryFn: getMcpStatus })
  const servers: McpServer[] = data?.servers ?? []

  const add = useMutation({
    mutationFn: addMcpServer,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['mcp-status'] }),
  })
  const remove = useMutation({
    mutationFn: removeMcpServer,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['mcp-status'] }),
  })
  const toggle = useMutation({
    mutationFn: toggleMcpServer,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['mcp-status'] }),
  })

  const configuredNames = new Set(servers.map((s) => s.name))

  if (isLoading) return <p className="text-sm text-muted-foreground p-2">Loading…</p>

  return (
    <div className="space-y-4">
      {/* Configured servers */}
      {servers.length > 0 && (
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-sm">Configured Servers</CardTitle>
            <CardDescription className="text-xs">Changes take effect on next agent restart</CardDescription>
          </CardHeader>
          <CardContent className="space-y-2">
            {servers.map((srv) => (
              <div key={srv.name} className="flex items-center gap-3 py-2 border-b last:border-0">
                <Switch
                  checked={!srv.disabled}
                  onCheckedChange={() => toggle.mutate(srv.name)}
                  disabled={toggle.isPending}
                />
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium">{srv.name}</p>
                  <p className="text-xs text-muted-foreground font-mono truncate">{srv.command.join(' ')}</p>
                </div>
                {srv.disabled && <Badge variant="secondary" className="text-[10px] h-4 shrink-0">disabled</Badge>}
                <Button
                  variant="ghost"
                  size="icon"
                  className="h-7 w-7 shrink-0 text-muted-foreground hover:text-destructive"
                  onClick={() => remove.mutate(srv.name)}
                  disabled={remove.isPending}
                >
                  <Trash2 className="h-3.5 w-3.5" />
                </Button>
              </div>
            ))}
          </CardContent>
        </Card>
      )}

      {/* Presets */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-sm">Add MCP Server</CardTitle>
          <CardDescription className="text-xs">Requires Node.js / npx to be installed</CardDescription>
        </CardHeader>
        <CardContent className="space-y-2">
          {MCP_PRESETS.map(({ id, label, description, Icon, command, env }) => {
            const installed = configuredNames.has(id)
            return (
              <div key={id} className="flex items-start gap-3 py-2 border-b last:border-0">
                <div className="mt-0.5 h-7 w-7 rounded-md bg-muted flex items-center justify-center shrink-0">
                  <Icon className="h-3.5 w-3.5 text-muted-foreground" />
                </div>
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium">{label}</p>
                  <p className="text-xs text-muted-foreground">{description}</p>
                </div>
                {installed ? (
                  <Badge variant="secondary" className="text-[10px] h-5 shrink-0 mt-0.5">Added</Badge>
                ) : (
                  <Button
                    size="sm"
                    variant="outline"
                    className="h-7 text-xs shrink-0"
                    onClick={() => add.mutate({ name: id, command, env })}
                    disabled={add.isPending}
                  >
                    <Plus className="h-3 w-3 mr-1" />Add
                  </Button>
                )}
              </div>
            )
          })}
        </CardContent>
      </Card>

      <p className="text-xs text-muted-foreground">
        Custom servers: use <code className="font-mono bg-muted px-1 rounded">majestic mcp add &lt;name&gt; &lt;command…&gt;</code> from the terminal.
      </p>
    </div>
  )
}

// ── Email Tab ─────────────────────────────────────────────────────────────────

const GMAIL_DEFAULTS: EmailConfig = {
  imap_host: 'imap.gmail.com', imap_port: 993,
  smtp_host: 'smtp.gmail.com', smtp_port: 587,
}

function EmailTab() {
  const qc = useQueryClient()
  const { data: status, isLoading } = useQuery({
    queryKey: ['email-status'],
    queryFn: getEmailStatus,
    refetchInterval: 5000,
  })

  const [form, setForm] = useState<EmailConfig>({
    imap_host: 'imap.gmail.com', imap_port: 993,
    smtp_host: 'smtp.gmail.com', smtp_port: 587,
    poll_interval: 60, allowed_senders: [],
  })
  const [senderInput, setSenderInput] = useState('')
  const [testResult, setTestResult] = useState<{ ok: boolean; error?: string } | null>(null)
  const [gmailGuide, setGmailGuide] = useState(false)
  const [dirty, setDirty] = useState(false)

  const set = (key: keyof EmailConfig, val: unknown) => {
    setForm((f) => ({ ...f, [key]: val }))
    setDirty(true)
    setTestResult(null)
  }

  const testMut = useMutation({
    mutationFn: () => testEmailConnection(form),
    onSuccess: (r) => setTestResult(r),
  })

  const saveMut = useMutation({
    mutationFn: () => saveEmailConfig(form),
    onSuccess: () => { setDirty(false); qc.invalidateQueries({ queryKey: ['email-status'] }) },
  })

  const startMut = useMutation({
    mutationFn: () => startEmailGateway(dirty ? form : undefined),
    onSuccess: () => { setDirty(false); qc.invalidateQueries({ queryKey: ['email-status'] }) },
  })

  const stopMut = useMutation({
    mutationFn: stopEmailGateway,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['email-status'] }),
  })

  const addSender = () => {
    const s = senderInput.trim().toLowerCase()
    if (!s) return
    const current = form.allowed_senders ?? []
    if (!current.includes(s)) set('allowed_senders', [...current, s])
    setSenderInput('')
  }

  const removeSender = (s: string) =>
    set('allowed_senders', (form.allowed_senders ?? []).filter((x) => x !== s))

  if (isLoading) return <p className="text-sm text-muted-foreground p-2">Loading…</p>

  return (
    <div className="space-y-4">
      {/* Status bar */}
      <Card>
        <CardContent className="pt-4 flex items-center justify-between gap-4">
          <div className="flex items-center gap-2">
            <Mail className="h-4 w-4 text-muted-foreground" />
            <div>
              <p className="text-sm font-medium">
                {status?.running ? 'Gateway running' : 'Gateway stopped'}
                {status?.username && <span className="text-muted-foreground font-normal"> · {status.username}</span>}
              </p>
              {status?.error && <p className="text-xs text-destructive">{status.error}</p>}
              {status?.last_poll && (
                <p className="text-xs text-muted-foreground">
                  Last poll: {new Date(status.last_poll * 1000).toLocaleTimeString()}
                </p>
              )}
            </div>
          </div>
          <div className="flex gap-2">
            {status?.running ? (
              <Button size="sm" variant="outline" onClick={() => stopMut.mutate()} disabled={stopMut.isPending}>
                <Square className="h-3.5 w-3.5 mr-1.5" fill="currentColor" />Stop
              </Button>
            ) : (
              <Button size="sm" onClick={() => startMut.mutate()} disabled={startMut.isPending || !status?.configured}>
                <Play className="h-3.5 w-3.5 mr-1.5" fill="currentColor" />
                {startMut.isPending ? 'Starting…' : 'Start'}
              </Button>
            )}
            {startMut.isError && <span className="text-xs text-destructive">Failed to start</span>}
            {(startMut.data as any)?.error && (
              <span className="text-xs text-destructive">{(startMut.data as any).error}</span>
            )}
          </div>
        </CardContent>
      </Card>

      {/* Connection form */}
      <Card>
        <CardHeader className="pb-3">
          <div className="flex items-center justify-between">
            <div>
              <CardTitle className="text-sm">Connection Settings</CardTitle>
              <CardDescription className="text-xs">IMAP for receiving, SMTP for sending</CardDescription>
            </div>
            <Button
              size="sm"
              variant="ghost"
              className="text-xs h-7 text-muted-foreground"
              onClick={() => { setForm((f) => ({ ...f, ...GMAIL_DEFAULTS })); setDirty(true) }}
            >
              Auto-fill Gmail
            </Button>
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid grid-cols-2 gap-3">
            <Field label="IMAP Host">
              <Input value={form.imap_host ?? ''} onChange={(e) => set('imap_host', e.target.value)} />
            </Field>
            <Field label="IMAP Port">
              <Input type="number" value={form.imap_port ?? 993} onChange={(e) => set('imap_port', Number(e.target.value))} />
            </Field>
            <Field label="SMTP Host">
              <Input value={form.smtp_host ?? ''} onChange={(e) => set('smtp_host', e.target.value)} />
            </Field>
            <Field label="SMTP Port">
              <Input type="number" value={form.smtp_port ?? 587} onChange={(e) => set('smtp_port', Number(e.target.value))} />
            </Field>
          </div>
          <Field label="Username (email address)">
            <Input type="email" value={form.username ?? ''} onChange={(e) => set('username', e.target.value)} />
          </Field>
          <Field label="Password" hint="For Gmail: use App Password, not your account password">
            <Input type="password" value={form.password ?? ''} onChange={(e) => set('password', e.target.value)} />
          </Field>
          <Field label="Poll interval (seconds)">
            <Input type="number" min={10} value={form.poll_interval ?? 60} onChange={(e) => set('poll_interval', Number(e.target.value))} />
          </Field>

          {/* Test + Save */}
          <div className="flex items-center gap-2 pt-1">
            <Button variant="outline" size="sm" onClick={() => testMut.mutate()} disabled={testMut.isPending}>
              {testMut.isPending ? 'Testing…' : 'Test connection'}
            </Button>
            {testResult?.ok && (
              <span className="flex items-center gap-1 text-xs text-green-500">
                <CheckCircle2 className="h-3.5 w-3.5" />Connected
              </span>
            )}
            {testResult && !testResult.ok && (
              <span className="flex items-center gap-1 text-xs text-destructive">
                <AlertCircle className="h-3.5 w-3.5" />{testResult.error}
              </span>
            )}
            <div className="flex-1" />
            <Button size="sm" onClick={() => saveMut.mutate()} disabled={!dirty || saveMut.isPending}>
              <Save className="h-3.5 w-3.5 mr-1.5" />
              {saveMut.isPending ? 'Saving…' : 'Save'}
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* Allowed senders */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-sm">Allowed Senders</CardTitle>
          <CardDescription className="text-xs">
            Only these addresses can send commands. Empty = accept from anyone.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          {(form.allowed_senders ?? []).length === 0 && (
            <p className="text-xs text-amber-500 flex items-center gap-1">
              <AlertCircle className="h-3 w-3" />No restriction — agent will respond to anyone
            </p>
          )}
          <div className="flex flex-wrap gap-1.5">
            {(form.allowed_senders ?? []).map((s) => (
              <div key={s} className="flex items-center gap-1 bg-muted rounded-full px-2.5 py-1 text-xs">
                <span>{s}</span>
                <button type="button" onClick={() => removeSender(s)} className="text-muted-foreground hover:text-foreground ml-0.5">
                  <Trash2 className="h-3 w-3" />
                </button>
              </div>
            ))}
          </div>
          <div className="flex gap-2">
            <Input
              placeholder="email@example.com"
              value={senderInput}
              className="h-8 text-xs"
              onChange={(e) => setSenderInput(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && addSender()}
            />
            <Button size="sm" variant="outline" className="h-8" onClick={addSender}>
              <Plus className="h-3.5 w-3.5" />
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* Gmail guide */}
      <div className="border rounded-lg overflow-hidden">
        <button
          type="button"
          className="w-full flex items-center justify-between px-4 py-3 text-sm font-medium hover:bg-muted/50 transition-colors"
          onClick={() => setGmailGuide((v) => !v)}
        >
          <span>Gmail App Password setup guide</span>
          {gmailGuide ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
        </button>
        {gmailGuide && (
          <div className="px-4 pb-4 text-xs space-y-2 text-muted-foreground border-t pt-3">
            <p>Gmail requires an App Password — your regular password will not work.</p>
            <ol className="list-decimal list-inside space-y-1.5">
              <li>Go to <span className="font-medium text-foreground">myaccount.google.com</span></li>
              <li>Security → 2-Step Verification → turn it <span className="font-medium text-foreground">On</span></li>
              <li>Security → <span className="font-medium text-foreground">App passwords</span></li>
              <li>Select app: <span className="font-medium text-foreground">Mail</span> → Generate</li>
              <li>Copy the 16-character code → paste it as Password above</li>
            </ol>
            <p>Also enable IMAP: Gmail Settings → See all settings → Forwarding and POP/IMAP → Enable IMAP.</p>
          </div>
        )}
      </div>
    </div>
  )
}
