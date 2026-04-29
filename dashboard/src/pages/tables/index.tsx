import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Badge } from '@/components/ui/badge'
import { ScrollArea } from '@/components/ui/scroll-area'
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from '@/components/ui/dialog'
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel,
  AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle,
} from '@/components/ui/alert-dialog'
import { Plus, Trash2, Table2, Pencil, ChevronLeft, X } from 'lucide-react'
import {
  getTables, createTable, deleteTable,
  getRows, addRow, updateRow, deleteRow,
} from '@/shared/api/tables'
import type { UserTable } from '@/entities/user-table/model'
import { cn } from '@/lib/utils'

// ── Create table dialog ───────────────────────────────────────────────────────

function CreateTableDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const qc = useQueryClient()
  const [name, setName] = useState('')
  const [cols, setCols] = useState<string[]>([''])

  const create = useMutation({
    mutationFn: () => createTable(name.trim(), cols.filter(Boolean)),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['tables'] }); onClose(); setName(''); setCols(['']) },
  })

  const addCol = () => setCols((c) => [...c, ''])
  const setCol = (i: number, v: string) => setCols((c) => c.map((x, j) => (j === i ? v : x)))
  const removeCol = (i: number) => setCols((c) => c.filter((_, j) => j !== i))

  return (
    <Dialog open={open} onOpenChange={onClose}>
      <DialogContent className="max-w-sm">
        <DialogHeader><DialogTitle>Create Table</DialogTitle></DialogHeader>
        <div className="space-y-3 py-1">
          <div className="space-y-1.5">
            <Label className="text-xs">Table name</Label>
            <Input placeholder="my_notes" value={name} onChange={(e) => setName(e.target.value)} />
          </div>
          <div className="space-y-1.5">
            <Label className="text-xs">Columns</Label>
            {cols.map((c, i) => (
              <div key={i} className="flex gap-1.5">
                <Input
                  className="flex-1"
                  placeholder={`column_${i + 1}`}
                  value={c}
                  onChange={(e) => setCol(i, e.target.value)}
                />
                <Button size="icon" variant="ghost" className="h-9 w-9 shrink-0" onClick={() => removeCol(i)}>
                  <X className="h-3.5 w-3.5" />
                </Button>
              </div>
            ))}
            <Button size="sm" variant="outline" className="w-full" onClick={addCol}>
              <Plus className="h-3.5 w-3.5 mr-1.5" /> Add Column
            </Button>
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" size="sm" onClick={onClose}>Cancel</Button>
          <Button size="sm" onClick={() => create.mutate()} disabled={!name.trim() || create.isPending}>
            {create.isPending ? 'Creating…' : 'Create'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

// ── Row editor dialog ─────────────────────────────────────────────────────────

function RowDialog({
  open, tableName, columns, initial, rowId, onClose,
}: {
  open: boolean; tableName: string; columns: string[]
  initial: Record<string, string>; rowId: number | null; onClose: () => void
}) {
  const qc = useQueryClient()
  const [form, setForm] = useState<Record<string, string>>(initial)
  const isEdit = rowId !== null

  const save = useMutation({
    mutationFn: () => isEdit ? updateRow(tableName, rowId!, form) : addRow(tableName, form),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['rows', tableName] }); onClose() },
  })

  return (
    <Dialog open={open} onOpenChange={onClose}>
      <DialogContent className="max-w-sm">
        <DialogHeader><DialogTitle>{isEdit ? 'Edit Row' : 'Add Row'}</DialogTitle></DialogHeader>
        <div className="space-y-3 py-1">
          {columns.map((col) => (
            <div key={col} className="space-y-1.5">
              <Label className="text-xs">{col}</Label>
              <Input
                value={form[col] ?? ''}
                onChange={(e) => setForm((f) => ({ ...f, [col]: e.target.value }))}
              />
            </div>
          ))}
        </div>
        <DialogFooter>
          <Button variant="outline" size="sm" onClick={onClose}>Cancel</Button>
          <Button size="sm" onClick={() => save.mutate()} disabled={save.isPending}>
            {save.isPending ? 'Saving…' : isEdit ? 'Update' : 'Add'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

// ── Table view ────────────────────────────────────────────────────────────────

function TableView({ table, onBack }: { table: UserTable; onBack: () => void }) {
  const qc = useQueryClient()
  const { data } = useQuery({
    queryKey: ['rows', table.name],
    queryFn: () => getRows(table.name),
  })
  const [rowDialog, setRowDialog] = useState<{ open: boolean; id: number | null; initial: Record<string, string> }>({
    open: false, id: null, initial: {},
  })
  const [delRow, setDelRow] = useState<number | null>(null)

  const columns = data?.columns ?? table.columns
  const rows = data?.rows ?? []

  const del = useMutation({
    mutationFn: (id: number) => deleteRow(table.name, id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['rows', table.name] }),
  })

  const openAdd = () => setRowDialog({ open: true, id: null, initial: Object.fromEntries(columns.map((c) => [c, ''])) })
  const openEdit = (row: Record<string, string>) =>
    setRowDialog({ open: true, id: Number(row.id), initial: row })

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2">
        <Button size="icon" variant="ghost" className="h-7 w-7" onClick={onBack}>
          <ChevronLeft className="h-4 w-4" />
        </Button>
        <span className="font-medium text-sm">user_{table.name}</span>
        <Badge variant="secondary" className="text-xs">{rows.length} rows</Badge>
        <div className="ml-auto">
          <Button size="sm" onClick={openAdd}>
            <Plus className="h-3.5 w-3.5 mr-1.5" /> Add Row
          </Button>
        </div>
      </div>

      <div className="border rounded-md overflow-hidden">
        <ScrollArea className="max-h-[calc(100vh-16rem)]">
          <table className="w-full text-xs">
            <thead className="bg-muted/50 sticky top-0">
              <tr>
                <th className="text-left px-3 py-2 font-medium text-muted-foreground w-12">id</th>
                {columns.map((c) => (
                  <th key={c} className="text-left px-3 py-2 font-medium text-muted-foreground">{c}</th>
                ))}
                <th className="w-16" />
              </tr>
            </thead>
            <tbody>
              {rows.length === 0 && (
                <tr><td colSpan={columns.length + 2} className="px-3 py-6 text-center text-muted-foreground">No rows yet</td></tr>
              )}
              {rows.map((row) => (
                <tr key={row.id} className="border-t hover:bg-muted/30 transition-colors">
                  <td className="px-3 py-2 text-muted-foreground">{row.id}</td>
                  {columns.map((c) => (
                    <td key={c} className="px-3 py-2 max-w-[200px] truncate">{row[c] ?? ''}</td>
                  ))}
                  <td className="px-2 py-1">
                    <div className="flex gap-0.5 justify-end">
                      <Button size="icon" variant="ghost" className="h-6 w-6" onClick={() => openEdit(row)}>
                        <Pencil className="h-3 w-3" />
                      </Button>
                      <Button
                        size="icon" variant="ghost"
                        className="h-6 w-6 text-muted-foreground hover:text-destructive"
                        onClick={() => setDelRow(Number(row.id))}
                      >
                        <Trash2 className="h-3 w-3" />
                      </Button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </ScrollArea>
      </div>

      <RowDialog
        open={rowDialog.open}
        tableName={table.name}
        columns={columns}
        initial={rowDialog.initial}
        rowId={rowDialog.id}
        onClose={() => setRowDialog((s) => ({ ...s, open: false }))}
      />

      <AlertDialog open={delRow !== null} onOpenChange={() => setDelRow(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete row #{delRow}?</AlertDialogTitle>
            <AlertDialogDescription>This cannot be undone.</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
              onClick={() => { if (delRow !== null) { del.mutate(delRow); setDelRow(null) } }}
            >Delete</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  )
}

// ── Main page ─────────────────────────────────────────────────────────────────

export function TablesPage() {
  const qc = useQueryClient()
  const { data: tables = [], isLoading } = useQuery({ queryKey: ['tables'], queryFn: getTables })
  const [createOpen, setCreateOpen] = useState(false)
  const [active, setActive] = useState<UserTable | null>(null)
  const [pendingDelete, setPendingDelete] = useState<string | null>(null)

  const drop = useMutation({
    mutationFn: (name: string) => deleteTable(name),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['tables'] }); if (active?.name === pendingDelete) setActive(null) },
  })

  if (active) return <TableView table={active} onBack={() => setActive(null)} />

  return (
    <div className="space-y-4 max-w-2xl">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold">Tables</h2>
          <p className="text-sm text-muted-foreground">
            User tables in state.db (prefix: user_) — visible to agent
          </p>
        </div>
        <Button size="sm" onClick={() => setCreateOpen(true)}>
          <Plus className="h-3.5 w-3.5 mr-1.5" /> New Table
        </Button>
      </div>

      {isLoading && <p className="text-sm text-muted-foreground">Loading…</p>}
      {!isLoading && tables.length === 0 && (
        <p className="text-sm text-muted-foreground">No tables yet. Create one to get started.</p>
      )}

      <div className="space-y-2">
        {tables.map((t) => (
          <Card
            key={t.name}
            className={cn('cursor-pointer hover:bg-muted/30 transition-colors')}
            onClick={() => setActive(t)}
          >
            <CardHeader className="pb-2 flex-row items-center justify-between">
              <CardTitle className="text-sm flex items-center gap-2">
                <Table2 className="h-3.5 w-3.5 text-muted-foreground" />
                user_{t.name}
              </CardTitle>
              <div className="flex items-center gap-2" onClick={(e) => e.stopPropagation()}>
                <Badge variant="secondary" className="text-xs">{t.rows} rows</Badge>
                <Button
                  size="icon" variant="ghost"
                  className="h-6 w-6 text-muted-foreground hover:text-destructive"
                  onClick={() => setPendingDelete(t.name)}
                >
                  <Trash2 className="h-3 w-3" />
                </Button>
              </div>
            </CardHeader>
            {t.columns.length > 0 && (
              <CardContent className="pb-3">
                <p className="text-xs text-muted-foreground font-mono">
                  {t.columns.join(', ')}
                </p>
              </CardContent>
            )}
          </Card>
        ))}
      </div>

      <CreateTableDialog open={createOpen} onClose={() => setCreateOpen(false)} />

      <AlertDialog open={!!pendingDelete} onOpenChange={() => setPendingDelete(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Drop table "user_{pendingDelete}"?</AlertDialogTitle>
            <AlertDialogDescription>All rows will be permanently deleted.</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
              onClick={() => { if (pendingDelete) { drop.mutate(pendingDelete); setPendingDelete(null) } }}
            >Drop</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  )
}
