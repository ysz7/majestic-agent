import { useQuery, useMutation } from '@tanstack/react-query'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Separator } from '@/components/ui/separator'
import { apiFetch } from '@/shared/api/client'
import { useState, useEffect } from 'react'

interface Config {
  model: string
  language: string
  currency: string
  search_mode: string
}

const MODELS = [
  'claude-sonnet-4-6',
  'claude-opus-4-7',
  'claude-haiku-4-5-20251001',
]

export function SettingsPage() {
  const { data } = useQuery<Config>({ queryKey: ['config'], queryFn: () => apiFetch('/api/config') })
  const [form, setForm] = useState<Partial<Config>>({})

  useEffect(() => { if (data) setForm(data) }, [data])

  const save = useMutation({
    mutationFn: (cfg: Partial<Config>) => apiFetch('/api/config', { method: 'PATCH', body: JSON.stringify(cfg) }),
  })

  const set = (key: keyof Config, val: string | null) => setForm((f) => ({ ...f, [key]: val ?? f[key] ?? '' }))

  return (
    <div className="max-w-lg space-y-6">
      <div>
        <h2 className="text-lg font-semibold">Settings</h2>
        <p className="text-sm text-muted-foreground">Manage your agent configuration</p>
      </div>
      <Separator />
      <Card>
        <CardHeader>
          <CardTitle>Model</CardTitle>
          <CardDescription>The LLM used for all agent tasks</CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          <Select value={form.model ?? ''} onValueChange={(v) => set('model', v)}>
            <SelectTrigger><SelectValue placeholder="Select model" /></SelectTrigger>
            <SelectContent>
              {MODELS.map((m) => <SelectItem key={m} value={m}>{m}</SelectItem>)}
            </SelectContent>
          </Select>
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle>Language &amp; Currency</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <Input placeholder="Language (en, uk, de…)" value={form.language ?? ''} onChange={(e) => set('language', e.target.value)} />
          <Input placeholder="Currency (USD, EUR…)" value={form.currency ?? ''} onChange={(e) => set('currency', e.target.value)} />
        </CardContent>
      </Card>
      <Button onClick={() => save.mutate(form)} disabled={save.isPending}>
        {save.isPending ? 'Saving…' : 'Save Changes'}
      </Button>
    </div>
  )
}
