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

const PROVIDERS = ['anthropic', 'openai', 'openrouter', 'ollama']

const MODEL_LISTS: Record<string, string[]> = {
  anthropic: ['claude-sonnet-4-6', 'claude-opus-4-7', 'claude-haiku-4-5-20251001'],
  openai: ['gpt-4o', 'gpt-4o-mini', 'o3-mini', 'o1'],
  openrouter: [
    'anthropic/claude-sonnet-4-6',
    'anthropic/claude-opus-4-7',
    'openai/gpt-4o',
    'openai/gpt-4o-mini',
    'openai/o3-mini',
    'google/gemini-2.5-pro',
    'google/gemini-2.5-flash',
    'meta-llama/llama-3.3-70b-instruct',
    'mistralai/mistral-large',
    'deepseek/deepseek-r1',
    'qwen/qwen-2.5-72b-instruct',
  ],
}

const CUSTOM_SENTINEL = '__custom__'

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
  const [customModel, setCustomModel] = useState(false)

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

  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ['llm-configs'] })
    qc.invalidateQueries({ queryKey: ['settings'] })
  }

  const create = useMutation({
    mutationFn: () => createLlmConfig(form),
    onSuccess: () => {
      invalidate()
      setOpen(false)
      setForm(EMPTY_FORM)
      setCustomModel(false)
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

  const changeProvider = (v: string | null) => {
    if (!v) return
    setForm((f) => ({ ...f, provider: v, model: '' }))
    setCustomModel(false)
  }

  const changeModel = (v: string | null) => {
    if (!v) return
    if (v === CUSTOM_SENTINEL) {
      setCustomModel(true)
      setField('model', '')
    } else {
      setCustomModel(false)
      setField('model', v)
    }
  }

  const openAdd = () => {
    setForm(EMPTY_FORM)
    setCustomModel(false)
    setOpen(true)
  }

  const selectValue = customModel ? CUSTOM_SENTINEL : (form.model || undefined)
  const customPlaceholder =
    form.provider === 'openrouter'
      ? 'e.g. mistralai/mixtral-8x22b-instruct'
      : form.provider === 'openai'
      ? 'e.g. gpt-4-turbo'
      : 'e.g. claude-3-5-sonnet-20241022'

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
              <Select value={form.provider} onValueChange={changeProvider}>
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
                <Select key="anthropic" value={selectValue} onValueChange={changeModel}>
                  <SelectTrigger>
                    <SelectValue placeholder="Select model" />
                  </SelectTrigger>
                  <SelectContent>
                    {MODEL_LISTS.anthropic.map((m) => (
                      <SelectItem key={m} value={m}>{m}</SelectItem>
                    ))}
                    <SelectItem value={CUSTOM_SENTINEL}>
                      <span className="text-muted-foreground">Custom model…</span>
                    </SelectItem>
                  </SelectContent>
                </Select>
              )}

              {form.provider === 'openai' && (
                <Select key="openai" value={selectValue} onValueChange={changeModel}>
                  <SelectTrigger>
                    <SelectValue placeholder="Select model" />
                  </SelectTrigger>
                  <SelectContent>
                    {MODEL_LISTS.openai.map((m) => (
                      <SelectItem key={m} value={m}>{m}</SelectItem>
                    ))}
                    <SelectItem value={CUSTOM_SENTINEL}>
                      <span className="text-muted-foreground">Custom model…</span>
                    </SelectItem>
                  </SelectContent>
                </Select>
              )}

              {form.provider === 'openrouter' && (
                <Select key="openrouter" value={selectValue} onValueChange={changeModel}>
                  <SelectTrigger>
                    <SelectValue placeholder="Select model" />
                  </SelectTrigger>
                  <SelectContent>
                    {MODEL_LISTS.openrouter.map((m) => (
                      <SelectItem key={m} value={m}>{m}</SelectItem>
                    ))}
                    <SelectItem value={CUSTOM_SENTINEL}>
                      <span className="text-muted-foreground">Custom model…</span>
                    </SelectItem>
                  </SelectContent>
                </Select>
              )}

              {/* Custom model input — shown when "Custom model…" selected */}
              {customModel && (
                <Input
                  autoFocus
                  placeholder={customPlaceholder}
                  value={form.model}
                  onChange={(e) => setField('model', e.target.value)}
                />
              )}

              {/* Ollama — list from server or free-form input */}
              {form.provider === 'ollama' &&
                (ollamaModels.length > 0 ? (
                  <Select key="ollama" value={form.model || undefined} onValueChange={(v) => setField('model', v ?? '')}>
                    <SelectTrigger>
                      <SelectValue placeholder="Select installed model" />
                    </SelectTrigger>
                    <SelectContent>
                      {ollamaModels.map((m) => (
                        <SelectItem key={m} value={m}>{m}</SelectItem>
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
              disabled={!form.name || !form.provider || !form.model || create.isPending}
            >
              {create.isPending ? 'Saving…' : 'Save'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  )
}
