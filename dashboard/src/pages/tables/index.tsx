import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Badge } from '@/components/ui/badge'
import { Plus, Table2 } from 'lucide-react'
import { apiFetch } from '@/shared/api/client'

interface UserTable {
  name: string
  rows: number
  created_at: string
}

export function TablesPage() {
  const qc = useQueryClient()
  const [newName, setNewName] = useState('')
  const [newCols, setNewCols] = useState('')

  const { data: tables = [] } = useQuery<UserTable[]>({
    queryKey: ['user-tables'],
    queryFn: () => apiFetch('/api/tables'),
  })

  const create = useMutation({
    mutationFn: () => apiFetch('/api/tables', {
      method: 'POST',
      body: JSON.stringify({ name: newName, columns: newCols.split(',').map((c) => c.trim()).filter(Boolean) }),
    }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['user-tables'] })
      setNewName('')
      setNewCols('')
    },
  })

  return (
    <div className="space-y-4 max-w-2xl">
      <div>
        <h2 className="text-lg font-semibold">Tables</h2>
        <p className="text-sm text-muted-foreground">User-defined tables in state.db (prefix: user_)</p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-sm">Create Table</CardTitle>
        </CardHeader>
        <CardContent className="space-y-2">
          <Input placeholder="table_name" value={newName} onChange={(e) => setNewName(e.target.value)} />
          <Input placeholder="col1, col2, col3 (TEXT by default)" value={newCols} onChange={(e) => setNewCols(e.target.value)} />
          <Button size="sm" onClick={() => create.mutate()} disabled={!newName || create.isPending}>
            <Plus className="h-3.5 w-3.5 mr-1" />
            Create
          </Button>
        </CardContent>
      </Card>

      {tables.length === 0 && (
        <p className="text-sm text-muted-foreground">No user tables yet.</p>
      )}
      {tables.map((t) => (
        <Card key={t.name}>
          <CardHeader className="pb-2 flex-row items-center justify-between">
            <CardTitle className="text-sm flex items-center gap-2">
              <Table2 className="h-4 w-4" />
              user_{t.name}
            </CardTitle>
            <Badge variant="secondary">{t.rows} rows</Badge>
          </CardHeader>
        </Card>
      ))}
    </div>
  )
}
