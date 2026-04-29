import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Trash2 } from 'lucide-react'
import { apiFetch } from '@/shared/api/client'

interface MemoryEntry {
  key: string
  value: string
  scope: string
}

export function MemoryPage() {
  const qc = useQueryClient()
  const { data: entries = [] } = useQuery<MemoryEntry[]>({
    queryKey: ['memory'],
    queryFn: () => apiFetch('/api/memory'),
  })

  const forget = useMutation({
    mutationFn: (key: string) => apiFetch(`/api/memory/${encodeURIComponent(key)}`, { method: 'DELETE' }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['memory'] }),
  })

  return (
    <div className="space-y-4 max-w-2xl">
      <div>
        <h2 className="text-lg font-semibold">Memory</h2>
        <p className="text-sm text-muted-foreground">{entries.length} stored entries</p>
      </div>
      {entries.length === 0 && (
        <p className="text-sm text-muted-foreground">No memory entries yet.</p>
      )}
      {entries.map((entry) => (
        <Card key={entry.key}>
          <CardHeader className="pb-2 flex-row items-start justify-between">
            <div className="space-y-1">
              <CardTitle className="text-sm font-medium">{entry.key}</CardTitle>
              <Badge variant="secondary" className="text-xs">{entry.scope}</Badge>
            </div>
            <Button size="icon" variant="ghost" className="h-7 w-7 text-muted-foreground" onClick={() => forget.mutate(entry.key)}>
              <Trash2 className="h-3.5 w-3.5" />
            </Button>
          </CardHeader>
          <CardContent>
            <p className="text-sm text-muted-foreground">{entry.value}</p>
          </CardContent>
        </Card>
      ))}
    </div>
  )
}
