import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { FileBrowser } from '@/widgets/file-browser'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
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
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from '@/components/ui/dialog'
import { listScripts, runScript, deleteScript, readWorkspaceFile, saveWorkspaceFile, type Script, type ScriptRunResult } from '@/shared/api/workspace'
import { ScrollText, Play, Trash2, Code2, Terminal, Pencil } from 'lucide-react'

function formatDate(ts: number) {
  return new Date(ts * 1000).toLocaleDateString()
}

function ScriptCard({
  script,
  onRun,
  onEdit,
  onDelete,
}: {
  script: Script
  onRun: (s: Script) => void
  onEdit: (s: Script) => void
  onDelete: (s: Script) => void
}) {
  return (
    <div className="rounded-lg border border-border bg-card p-4 flex flex-col gap-2">
      <div className="flex items-start justify-between gap-2">
        <div className="flex items-center gap-2 min-w-0">
          <ScrollText className="h-4 w-4 text-muted-foreground shrink-0" />
          <span className="font-mono text-sm font-medium truncate">{script.name}.py</span>
        </div>
        <div className="flex items-center gap-1 shrink-0">
          <Button size="sm" variant="outline" className="h-7 px-2" onClick={() => onRun(script)}>
            <Play className="h-3 w-3 mr-1" />
            Run
          </Button>
          <Button size="sm" variant="ghost" className="h-7 px-2" onClick={() => onEdit(script)}>
            <Pencil className="h-3 w-3" />
          </Button>
          <Button size="sm" variant="ghost" className="h-7 px-2 text-destructive hover:text-destructive" onClick={() => onDelete(script)}>
            <Trash2 className="h-3 w-3" />
          </Button>
        </div>
      </div>
      {script.description && (
        <p className="text-xs text-muted-foreground">{script.description}</p>
      )}
      <div className="flex items-center gap-2 flex-wrap">
        {script.params.length > 0 && (
          <span className="text-xs text-muted-foreground">
            params: <span className="font-mono">{script.params.join(', ')}</span>
          </span>
        )}
        {script.tags.map(t => (
          <Badge key={t} variant="secondary" className="text-[10px] px-1.5 py-0">{t}</Badge>
        ))}
        <span className="text-[10px] text-muted-foreground ml-auto">{formatDate(script.modified_at)}</span>
      </div>
    </div>
  )
}

function RunDialog({
  script,
  onClose,
}: {
  script: Script | null
  onClose: () => void
}) {
  const [paramValues, setParamValues] = useState<Record<string, string>>({})
  const [result, setResult] = useState<ScriptRunResult | null>(null)
  const [running, setRunning] = useState(false)

  const handleRun = async () => {
    if (!script) return
    setRunning(true)
    setResult(null)
    try {
      const res = await runScript(script.name, paramValues)
      setResult(res)
    } finally {
      setRunning(false)
    }
  }

  const handleOpenChange = (open: boolean) => {
    if (!open) {
      onClose()
      setParamValues({})
      setResult(null)
    }
  }

  return (
    <Dialog open={!!script} onOpenChange={handleOpenChange}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Terminal className="h-4 w-4" />
            Run: {script?.name}.py
          </DialogTitle>
        </DialogHeader>

        {script && script.params.length > 0 && (
          <div className="space-y-3">
            <p className="text-xs text-muted-foreground">Parameters (injected as env vars):</p>
            {script.params.map(p => (
              <div key={p} className="space-y-1">
                <Label className="text-xs font-mono">{p}</Label>
                <Input
                  className="h-8 text-sm font-mono"
                  placeholder={`value for ${p}`}
                  value={paramValues[p] ?? ''}
                  onChange={e => setParamValues(prev => ({ ...prev, [p]: e.target.value }))}
                />
              </div>
            ))}
          </div>
        )}

        {result && (
          <div className="space-y-2">
            <div className="flex items-center gap-2">
              <span className="text-xs text-muted-foreground">
                Exit code: <span className={result.exit_code === 0 ? 'text-green-400' : 'text-red-400'}>{result.exit_code ?? '—'}</span>
              </span>
            </div>
            {result.stdout && (
              <div>
                <p className="text-xs text-muted-foreground mb-1">stdout:</p>
                <pre className="text-xs bg-muted rounded p-2 overflow-auto max-h-48 whitespace-pre-wrap">{result.stdout}</pre>
              </div>
            )}
            {result.stderr && (
              <div>
                <p className="text-xs text-muted-foreground mb-1">stderr:</p>
                <pre className="text-xs bg-destructive/10 text-destructive rounded p-2 overflow-auto max-h-32 whitespace-pre-wrap">{result.stderr}</pre>
              </div>
            )}
            {result.error && (
              <p className="text-xs text-destructive">{result.error}</p>
            )}
          </div>
        )}

        <DialogFooter>
          <Button variant="outline" onClick={onClose}>Close</Button>
          <Button onClick={handleRun} disabled={running}>
            <Play className="h-3.5 w-3.5 mr-1.5" />
            {running ? 'Running…' : 'Run'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function EditDialog({
  script,
  onClose,
}: {
  script: Script | null
  onClose: () => void
}) {
  const qc = useQueryClient()
  const [code, setCode] = useState('')
  const [loaded, setLoaded] = useState(false)
  const [saving, setSaving] = useState(false)

  const handleOpenChange = (open: boolean) => {
    if (open && script && !loaded) {
      readWorkspaceFile(`scripts/${script.name}.py`).then(r => {
        setCode(r.content ?? '')
        setLoaded(true)
      })
    }
    if (!open) {
      onClose()
      setLoaded(false)
      setCode('')
    }
  }

  const handleSave = async () => {
    if (!script) return
    setSaving(true)
    try {
      await saveWorkspaceFile(`scripts/${script.name}.py`, code)
      qc.invalidateQueries({ queryKey: ['scripts'] })
      onClose()
    } finally {
      setSaving(false)
    }
  }

  return (
    <Dialog open={!!script} onOpenChange={handleOpenChange}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Code2 className="h-4 w-4" />
            Edit: {script?.name}.py
          </DialogTitle>
        </DialogHeader>
        <Textarea
          className="font-mono text-xs min-h-[300px]"
          value={code}
          onChange={e => setCode(e.target.value)}
          placeholder="Loading…"
        />
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>Cancel</Button>
          <Button onClick={handleSave} disabled={saving}>{saving ? 'Saving…' : 'Save'}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function ScriptsTab() {
  const qc = useQueryClient()
  const { data, isLoading } = useQuery({
    queryKey: ['scripts'],
    queryFn: listScripts,
  })

  const remove = useMutation({
    mutationFn: (name: string) => deleteScript(name),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['scripts'] }),
  })

  const [runTarget, setRunTarget] = useState<Script | null>(null)
  const [editTarget, setEditTarget] = useState<Script | null>(null)
  const [deleteTarget, setDeleteTarget] = useState<Script | null>(null)

  const scripts = data?.scripts ?? []

  return (
    <div className="flex flex-col gap-3">
      <p className="text-xs text-muted-foreground">
        Scripts created by the agent — stored in <span className="font-mono">workspace/scripts/</span>.
        Use <span className="font-mono">save_script</span> / <span className="font-mono">run_script</span> tools.
      </p>

      {isLoading && <p className="text-sm text-muted-foreground py-4">Loading…</p>}

      {!isLoading && scripts.length === 0 && (
        <div className="flex flex-col items-center justify-center py-16 text-muted-foreground gap-2">
          <ScrollText className="h-10 w-10 opacity-30" />
          <p className="text-sm">No scripts yet</p>
          <p className="text-xs">Ask the agent to save a reusable script with <span className="font-mono">save_script</span></p>
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
        {scripts.map(s => (
          <ScriptCard
            key={s.name}
            script={s}
            onRun={setRunTarget}
            onEdit={setEditTarget}
            onDelete={setDeleteTarget}
          />
        ))}
      </div>

      <RunDialog script={runTarget} onClose={() => setRunTarget(null)} />
      <EditDialog script={editTarget} onClose={() => setEditTarget(null)} />

      <AlertDialog open={!!deleteTarget} onOpenChange={o => !o && setDeleteTarget(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete script?</AlertDialogTitle>
            <AlertDialogDescription>
              <strong>{deleteTarget?.name}.py</strong> will be permanently deleted.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
              onClick={() => {
                if (deleteTarget) {
                  remove.mutate(deleteTarget.name)
                  setDeleteTarget(null)
                }
              }}
            >
              Delete
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  )
}

export function WorkspacePage() {
  return (
    <div className="flex flex-col h-full">
      <div className="mb-4">
        <p className="text-sm font-medium">Files</p>
        <p className="text-xs text-muted-foreground">Files and scripts created and managed by the agent</p>
      </div>
      <Tabs defaultValue="files" className="flex flex-col flex-1 min-h-0">
        <TabsList className="mb-3 w-fit">
          <TabsTrigger value="files">Files</TabsTrigger>
          <TabsTrigger value="scripts">Scripts</TabsTrigger>
        </TabsList>
        <TabsContent value="files" className="flex-1 overflow-hidden mt-0">
          <FileBrowser />
        </TabsContent>
        <TabsContent value="scripts" className="flex-1 overflow-auto mt-0">
          <ScriptsTab />
        </TabsContent>
      </Tabs>
    </div>
  )
}
