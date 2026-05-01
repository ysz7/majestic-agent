import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  getLlmConfigs,
  createLlmConfig,
  deleteLlmConfig,
  activateLlmConfig,
  getOllamaModels,
} from '@/shared/api/settings'
import type { LlmConfig } from '@/shared/api/settings'
import { Card, CardContent } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from '@/components/ui/dialog'
import { Trash2, Plus, Check } from 'lucide-react'

const PROVIDERS = ['anthropic', 'ollama', 'openrouter']
const ANTHROPIC_MODELS = ['claude-sonnet-4-6', 'claude-opus-4-7', 'claude-haiku-4-5-20251001']
const OPENROUTER_MODELS = [
  'openai/gpt-4o',
  'openai/gpt-4o-mini',
  'google/gemini-2.0-flash',
  'meta-llama/llama-3.3-70b-instruct',
  'anthropic/claude-sonnet-4-6',
]

const EMPTY_FORM = { name: '', provider: 'anthropic', model: '', api_key: '', ollama_url: '' }

function ConfigCard({
  cfg,
  onActivate,
  onDelete,
}: {
  cfg: LlmConfig
  onActivate: () => void
  onDelete: () => void
}) {
  return (
    <Card
      className={`cursor-pointer transition-colors hover:bg-accent/50 ${cfg.active ? 'border-primary/60 bg-primary/5' : ''}`}
      onClick={onActivate}
    >
      <CardContent className="flex items-center gap-3 py-3 px-4">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <span className="text-sm font-medium">{cfg.name}</span>
            {cfg.active && (
              <Badge className="text-[10px] h-4 px-1.5 py-0">Active</Badge>
            )}
          </div>
          <p className="text-xs text-muted-foreground mt-0.5 truncate">
            {cfg.provider}
            {cfg.model ? ` · ${cfg.model}` : ''}
            {cfg.key_preview ? ` · ${cfg.key_preview}` : ''}
            {cfg.ollama_url ? ` · ${cfg.ollama_url}` : ''}
          </p>
        </div>
        {cfg.active && <Check className="h-4 w-4 text-primary shrink-0" />}
        <Button
          size="icon"
          variant="ghost"
          className="h-7 w-7 shrink-0"
          onClick={(e) => {
            e.stopPropagation()
            onDelete()
          }}
        >
          <Trash2 className="h-3.5 w-3.5" />
        </Button>
      </CardContent>
    </Card>
  )
}

export function LlmKeysManager() {
  const qc = useQueryClient()
  const [open, setOpen] = useState(false)
  const [form, setForm] = useState(EMPTY_FORM)

  const { data: configs = [], isLoading } = useQuery({
    queryKey: ['llm-configs'],
    queryFn: getLlmConfigs,
  })

  const { data: ollamaModels = [] } = useQuery({
    queryKey: ['ollama-models'],
    queryFn: getOllamaModels,
    enabled: form.provider === 'ollama' && open,
    staleTime: 30_000,
  })

  const invalidate = () => qc.invalidateQueries({ queryKey: ['llm-configs'] })

  const create = useMutation({
    mutationFn: () => createLlmConfig(form),
    onSuccess: () => {
      invalidate()
      setOpen(false)
      setForm(EMPTY_FORM)
    },
  })

  const remove = useMutation({
    mutationFn: (name: string) => deleteLlmConfig(name),
    onSuccess: invalidate,
  })

  const activate = useMutation({
    mutationFn: (name: string) => activateLlmConfig(name),
    onSuccess: invalidate,
  })

  const setField = (key: keyof typeof EMPTY_FORM, val: string) =>
    setForm((f) => ({ ...f, [key]: val }))

  const openAdd = () => {
    setForm(EMPTY_FORM)
    setOpen(true)
  }

  return (
    <>
      <div className="flex items-center justify-between mb-3">
        <div>
          <p className="text-sm font-medium">LLM Configurations</p>
          <p className="text-xs text-muted-foreground">Click a config to activate it</p>
        </div>
        <Button size="sm" variant="outline" onClick={openAdd}>
          <Plus className="h-3.5 w-3.5 mr-1.5" />
          Add
        </Button>
      </div>

      <div className="space-y-2">
        {isLoading && <p className="text-sm text-muted-foreground py-2">Loading…</p>}
        {configs.map((cfg) => (
          <ConfigCard
            key={cfg.name}
            cfg={cfg}
            onActivate={() => activate.mutate(cfg.name)}
            onDelete={() => remove.mutate(cfg.name)}
          />
        ))}
        {!isLoading && configs.length === 0 && (
          <p className="text-sm text-muted-foreground py-6 text-center">
            No configurations yet — add one to get started
          </p>
        )}
      </div>

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Add LLM Configuration</DialogTitle>
          </DialogHeader>

          <div className="space-y-4 py-2">
            <div className="space-y-1.5">
              <Label>Name</Label>
              <Input
                placeholder="e.g. My Anthropic"
                value={form.name}
                onChange={(e) => setField('name', e.target.value)}
              />
            </div>

            <div className="space-y-1.5">
              <Label>Provider</Label>
              <Select
                value={form.provider}
                onValueChange={(v) => setForm((f) => ({ ...f, provider: v as string, model: '' }))}
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {PROVIDERS.map((p) => (
                    <SelectItem key={p} value={p}>
                      {p}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-1.5">
              <Label>Model</Label>
              {form.provider === 'anthropic' && (
                <Select
                  value={form.model || undefined}
                  onValueChange={(v) => setField('model', v as string)}
                >
                  <SelectTrigger>
                    <SelectValue placeholder="Select model" />
                  </SelectTrigger>
                  <SelectContent>
                    {ANTHROPIC_MODELS.map((m) => (
                      <SelectItem key={m} value={m}>
                        {m}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              )}
              {form.provider === 'openrouter' && (
                <Select
                  value={form.model || undefined}
                  onValueChange={(v) => setField('model', v as string)}
                >
                  <SelectTrigger>
                    <SelectValue placeholder="Select model" />
                  </SelectTrigger>
                  <SelectContent>
                    {OPENROUTER_MODELS.map((m) => (
                      <SelectItem key={m} value={m}>
                        {m}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              )}
              {form.provider === 'ollama' &&
                (ollamaModels.length > 0 ? (
                  <Select
                    value={form.model || undefined}
                    onValueChange={(v) => setField('model', v as string)}
                  >
                    <SelectTrigger>
                      <SelectValue placeholder="Select installed model" />
                    </SelectTrigger>
                    <SelectContent>
                      {ollamaModels.map((m) => (
                        <SelectItem key={m} value={m}>
                          {m}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                ) : (
                  <Input
                    placeholder="e.g. llama3.2, mistral, gemma3"
                    value={form.model}
                    onChange={(e) => setField('model', e.target.value)}
                  />
                ))}
            </div>

            {form.provider !== 'ollama' && (
              <div className="space-y-1.5">
                <Label>API Key</Label>
                <Input
                  type="password"
                  placeholder={form.provider === 'anthropic' ? 'sk-ant-…' : 'sk-or-…'}
                  value={form.api_key}
                  onChange={(e) => setField('api_key', e.target.value)}
                />
              </div>
            )}

            {form.provider === 'ollama' && (
              <div className="space-y-1.5">
                <Label>Ollama URL</Label>
                <Input
                  placeholder="http://localhost:11434"
                  value={form.ollama_url}
                  onChange={(e) => setField('ollama_url', e.target.value)}
                />
              </div>
            )}
          </div>

          <DialogFooter>
            <Button variant="outline" onClick={() => setOpen(false)}>
              Cancel
            </Button>
            <Button
              onClick={() => create.mutate()}
              disabled={!form.name || !form.provider || create.isPending}
            >
              {create.isPending ? 'Saving…' : 'Save'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  )
}
