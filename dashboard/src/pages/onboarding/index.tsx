import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useMutation } from '@tanstack/react-query'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Progress } from '@/components/ui/progress'
import { Crown, Key, Bot, Globe, CheckCircle } from 'lucide-react'
import { submitSetup } from '@/shared/api/setup'
import type { SetupPayload } from '@/shared/api/setup'

const STEPS = ['Welcome', 'API Key', 'Preferences', 'Done']

const MODELS = [
  { value: 'claude-sonnet-4-6', label: 'Claude Sonnet 4.6 (recommended)' },
  { value: 'claude-opus-4-7', label: 'Claude Opus 4.7' },
  { value: 'claude-haiku-4-5-20251001', label: 'Claude Haiku 4.5' },
]

const LANGUAGES = [
  { value: 'en', label: 'English' },
  { value: 'uk', label: 'Ukrainian' },
  { value: 'de', label: 'German' },
  { value: 'fr', label: 'French' },
  { value: 'es', label: 'Spanish' },
]

const CURRENCIES = ['USD', 'EUR', 'GBP', 'UAH', 'BTC']

export function OnboardingPage() {
  const navigate = useNavigate()
  const [step, setStep] = useState(0)
  const [form, setForm] = useState<SetupPayload>({
    api_key: '',
    model: 'claude-sonnet-4-6',
    language: 'en',
    currency: 'USD',
  })

  const mutation = useMutation({
    mutationFn: submitSetup,
    onSuccess: () => {
      setStep(3)
    },
  })

  const set = (key: keyof SetupPayload, value: string | null) =>
    setForm((f) => ({ ...f, [key]: value ?? f[key] }))

  return (
    <div className="min-h-screen flex items-center justify-center bg-background p-4">
      <div className="w-full max-w-md space-y-6">
        <div className="text-center space-y-1">
          <div className="flex justify-center mb-3">
            <Crown className="h-8 w-8" />
          </div>
          <h1 className="text-2xl font-semibold">Majestic</h1>
          <p className="text-sm text-muted-foreground">Setup Wizard — Step {step + 1} of {STEPS.length}</p>
        </div>

        <Progress value={((step + 1) / STEPS.length) * 100} className="h-1" />

        {step === 0 && (
          <Card>
            <CardHeader>
              <CardTitle>Welcome to Majestic</CardTitle>
              <CardDescription>
                Your personal AI agent. Let&apos;s get you set up in a few steps.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <ul className="text-sm text-muted-foreground space-y-2">
                <li className="flex gap-2"><Key className="h-4 w-4 mt-0.5 shrink-0" /> Connect your Anthropic API key</li>
                <li className="flex gap-2"><Bot className="h-4 w-4 mt-0.5 shrink-0" /> Choose your preferred model</li>
                <li className="flex gap-2"><Globe className="h-4 w-4 mt-0.5 shrink-0" /> Set language &amp; currency</li>
              </ul>
              <Button className="w-full" onClick={() => setStep(1)}>Get Started</Button>
            </CardContent>
          </Card>
        )}

        {step === 1 && (
          <Card>
            <CardHeader>
              <CardTitle>API Key</CardTitle>
              <CardDescription>Your key is stored locally in ~/.majestic-agent/.env and never sent anywhere.</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <Input
                type="password"
                placeholder="sk-ant-..."
                value={form.api_key}
                onChange={(e) => set('api_key', e.target.value)}
              />
              <div className="flex gap-2">
                <Button variant="outline" className="flex-1" onClick={() => setStep(0)}>Back</Button>
                <Button className="flex-1" disabled={!form.api_key.startsWith('sk-')} onClick={() => setStep(2)}>
                  Continue
                </Button>
              </div>
            </CardContent>
          </Card>
        )}

        {step === 2 && (
          <Card>
            <CardHeader>
              <CardTitle>Preferences</CardTitle>
              <CardDescription>These can be changed later in Settings.</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="space-y-1.5">
                <label className="text-sm font-medium">Model</label>
                <Select value={form.model} onValueChange={(v) => set('model', v)}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {MODELS.map((m) => <SelectItem key={m.value} value={m.value}>{m.label}</SelectItem>)}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-1.5">
                <label className="text-sm font-medium">Language</label>
                <Select value={form.language} onValueChange={(v) => set('language', v)}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {LANGUAGES.map((l) => <SelectItem key={l.value} value={l.value}>{l.label}</SelectItem>)}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-1.5">
                <label className="text-sm font-medium">Currency</label>
                <Select value={form.currency} onValueChange={(v) => set('currency', v)}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {CURRENCIES.map((c) => <SelectItem key={c} value={c}>{c}</SelectItem>)}
                  </SelectContent>
                </Select>
              </div>
              {mutation.isError && (
                <p className="text-sm text-destructive">{(mutation.error as Error).message}</p>
              )}
              <div className="flex gap-2">
                <Button variant="outline" className="flex-1" onClick={() => setStep(1)}>Back</Button>
                <Button className="flex-1" onClick={() => mutation.mutate(form)} disabled={mutation.isPending}>
                  {mutation.isPending ? 'Saving…' : 'Finish Setup'}
                </Button>
              </div>
            </CardContent>
          </Card>
        )}

        {step === 3 && (
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <CheckCircle className="h-5 w-5 text-green-500" />
                You&apos;re all set
              </CardTitle>
              <CardDescription>Majestic is configured and ready to use.</CardDescription>
            </CardHeader>
            <CardContent>
              <Button className="w-full" onClick={() => navigate('/chat')}>Open Dashboard</Button>
            </CardContent>
          </Card>
        )}
      </div>
    </div>
  )
}
