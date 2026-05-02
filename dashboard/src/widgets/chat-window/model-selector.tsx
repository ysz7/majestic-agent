import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { getSettings, saveSettings, getOllamaModels } from '@/shared/api/settings'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { ChevronDown, Check } from 'lucide-react'

const ANTHROPIC_MODELS = [
  'claude-opus-4-7',
  'claude-sonnet-4-6',
  'claude-haiku-4-5-20251001',
]

function shortName(id: string): string {
  const cleaned = id.replace(/^claude-/, '')
  const parts = cleaned.split('-')
  if (parts.length >= 3) {
    const name = parts[0].charAt(0).toUpperCase() + parts[0].slice(1)
    return `${name} ${parts[1]}.${parts[2]}`
  }
  // Ollama: "gemma3:latest" → "gemma3"
  return id.split(':')[0]
}

export function ModelSelector() {
  const qc = useQueryClient()
  const { data: settings } = useQuery({ queryKey: ['settings'], queryFn: getSettings })
  const provider = settings?.llm?.provider ?? 'anthropic'
  const currentModel = settings?.llm?.model ?? ''

  const { data: ollamaModels = [] } = useQuery({
    queryKey: ['ollama-models'],
    queryFn: getOllamaModels,
    enabled: provider === 'ollama',
    staleTime: 60_000,
  })

  const models = provider === 'ollama' ? ollamaModels : ANTHROPIC_MODELS

  const save = useMutation({
    mutationFn: (model: string) =>
      saveSettings({ ...(settings ?? {}), llm: { ...(settings?.llm ?? {}), model } }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['settings'] }),
  })

  if (!currentModel) return null

  return (
    <DropdownMenu>
      <DropdownMenuTrigger className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground transition-colors px-2 py-1 rounded-md hover:bg-muted cursor-pointer">
        <span>{shortName(currentModel)}</span>
        <ChevronDown className="h-3 w-3" />
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="min-w-[180px]">
        {models.map((m) => (
          <DropdownMenuItem
            key={m}
            onClick={() => save.mutate(m)}
            className="flex items-center justify-between"
          >
            <span>{shortName(m)}</span>
            {m === currentModel && <Check className="h-3.5 w-3.5 text-primary" />}
          </DropdownMenuItem>
        ))}
        {models.length === 0 && (
          <DropdownMenuItem disabled>No models found</DropdownMenuItem>
        )}
      </DropdownMenuContent>
    </DropdownMenu>
  )
}
