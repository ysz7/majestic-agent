import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { ScrollArea } from '@/components/ui/scroll-area'
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog'
import { Plus, Trash2, MessageSquare, Search } from 'lucide-react'
import { deleteSession } from '@/shared/api/sessions'
import type { Session } from '@/entities/session/model'
import { cn } from '@/lib/utils'

interface Props {
  sessions: Session[]
  activeId: string | null
  onSelect: (id: string) => void
  onNew: () => void
}

function formatTime(iso: string) {
  if (!iso) return ''
  const d = new Date(iso)
  const now = new Date()
  const diffMs = now.getTime() - d.getTime()
  const diffH = diffMs / 3_600_000
  if (diffH < 1) return `${Math.round(diffMs / 60000)}m ago`
  if (diffH < 24) return `${Math.round(diffH)}h ago`
  return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
}

export function SessionList({ sessions, activeId, onSelect, onNew }: Props) {
  const qc = useQueryClient()
  const [query, setQuery] = useState('')
  const [pendingDelete, setPendingDelete] = useState<string | null>(null)

  const remove = useMutation({
    mutationFn: (id: string) => deleteSession(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['sessions'] }),
  })

  const filtered = query.trim()
    ? sessions.filter((s) =>
        (s.title ?? s.source ?? '').toLowerCase().includes(query.toLowerCase()),
      )
    : sessions

  return (
    <>
      <div className="flex flex-col h-full">
        {/* Header */}
        <div className="p-2 border-b flex items-center gap-1.5">
          <div className="relative flex-1">
            <Search className="absolute left-2 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-muted-foreground pointer-events-none" />
            <Input
              className="pl-7 h-7 text-xs"
              placeholder="Search…"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
            />
          </div>
          <Button size="icon" variant="ghost" className="h-7 w-7 shrink-0" onClick={onNew} title="New chat">
            <Plus className="h-3.5 w-3.5" />
          </Button>
        </div>

        {/* List */}
        <ScrollArea className="flex-1 min-h-0">
          <div className="p-1.5 space-y-0.5">
            {filtered.length === 0 && (
              <p className="text-xs text-muted-foreground px-2 py-3 text-center">
                {query ? 'No results' : 'No sessions yet'}
              </p>
            )}
            {filtered.map((s) => (
              <div
                key={s.id}
                className={cn(
                  'group flex items-start gap-1.5 rounded-md px-2 py-1.5 cursor-pointer transition-colors hover:bg-muted',
                  activeId === s.id && 'bg-muted',
                )}
                onClick={() => onSelect(s.id)}
              >
                <MessageSquare className="h-3.5 w-3.5 mt-0.5 shrink-0 text-muted-foreground" />
                <div className="flex-1 min-w-0">
                  <p className={cn('text-xs truncate leading-snug', activeId === s.id && 'font-medium')}>
                    {s.title || s.source || `Session ${s.id.slice(0, 6)}`}
                  </p>
                  <p className="text-[10px] text-muted-foreground mt-0.5">
                    {s.message_count > 0 ? `${s.message_count} msgs · ` : ''}
                    {formatTime(s.started_at)}
                  </p>
                </div>
                <Button
                  size="icon"
                  variant="ghost"
                  className="h-5 w-5 shrink-0 opacity-0 group-hover:opacity-100 text-muted-foreground hover:text-destructive"
                  onClick={(e) => { e.stopPropagation(); setPendingDelete(s.id) }}
                >
                  <Trash2 className="h-3 w-3" />
                </Button>
              </div>
            ))}
          </div>
        </ScrollArea>
      </div>

      {/* Delete confirm */}
      <AlertDialog open={!!pendingDelete} onOpenChange={() => setPendingDelete(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete session?</AlertDialogTitle>
            <AlertDialogDescription>
              This will permanently remove the session and all its messages.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
              onClick={() => { if (pendingDelete) { remove.mutate(pendingDelete); setPendingDelete(null) } }}
            >
              Delete
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  )
}
