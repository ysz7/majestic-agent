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
import { Separator } from '@/components/ui/separator'
import { Save, CheckCircle2, AlertCircle } from 'lucide-react'
import { getSettings, saveSettings } from '@/shared/api/settings'
import type { Settings } from '@/shared/api/settings'

const PROVIDERS = ['anthropic', 'ollama', 'openrouter']
const MODELS = ['claude-sonnet-4-6', 'claude-opus-4-7', 'claude-haiku-4-5-20251001']
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
  const [newApiKey, setNewApiKey] = useState('')

  useEffect(() => {
    if (data) { setForm(data); setDirty(false) }
  }, [data])

  const save = useMutation({
    mutationFn: () => saveSettings({ ...form, ...(newApiKey ? { api_key: newApiKey } : {}) }),
    onSuccess: () => {
      setDirty(false)
      setNewApiKey('')
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

  const llm = form.llm ?? {}
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
          {['general', 'llm', 'agent', 'research', 'gateways', 'api'].map((t) => (
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
            <CardHeader className="pb-3">
              <CardTitle className="text-sm">LLM Provider</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <Field label="Provider">
                <Select value={llm.provider ?? 'anthropic'} onValueChange={(v) => setNested('llm', 'provider', v)}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {PROVIDERS.map((p) => <SelectItem key={p} value={p}>{p}</SelectItem>)}
                  </SelectContent>
                </Select>
              </Field>
              <Field label="Model">
                <Select value={llm.model ?? undefined} onValueChange={(v) => setNested('llm', 'model', v)}>
                  <SelectTrigger><SelectValue placeholder="Select model" /></SelectTrigger>
                  <SelectContent>
                    {MODELS.map((m) => <SelectItem key={m} value={m}>{m}</SelectItem>)}
                  </SelectContent>
                </Select>
              </Field>
              <Separator />
              <Field
                label="Anthropic API Key"
                hint={
                  form._api_key_set
                    ? `Current key: ${form._api_key_preview} — leave blank to keep unchanged`
                    : 'No API key set'
                }
              >
                <Input
                  type="password"
                  placeholder={form._api_key_set ? '••••••••' : 'sk-ant-…'}
                  value={newApiKey}
                  onChange={(e) => { setNewApiKey(e.target.value); setDirty(true) }}
                />
              </Field>
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
      </Tabs>
    </div>
  )
}
