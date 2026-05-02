import { useState, useEffect } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import ReactMarkdown from 'react-markdown'
import { readWorkspaceFile, saveWorkspaceFile, type WorkspaceItem } from '@/shared/api/workspace'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import { Badge } from '@/components/ui/badge'
import { Eye, Edit2, Save } from 'lucide-react'

interface Props {
  file: WorkspaceItem | null
  onClose: () => void
}

export function FileViewer({ file, onClose }: Props) {
  const qc = useQueryClient()
  const [content, setContent] = useState('')
  const [originalContent, setOriginalContent] = useState('')
  const [mode, setMode] = useState<'view' | 'edit'>('view')
  const [fileData, setFileData] = useState<Awaited<ReturnType<typeof readWorkspaceFile>> | null>(null)
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    if (!file) return
    setLoading(true)
    setMode('view')
    readWorkspaceFile(file.path)
      .then((data) => {
        setFileData(data)
        if (data.type === 'text' && data.content !== undefined) {
          setContent(data.content)
          setOriginalContent(data.content)
        }
      })
      .finally(() => setLoading(false))
  }, [file])

  const save = useMutation({
    mutationFn: () => saveWorkspaceFile(file!.path, content),
    onSuccess: () => {
      setOriginalContent(content)
      qc.invalidateQueries({ queryKey: ['workspace'] })
    },
  })

  const isDirty = content !== originalContent
  const isMarkdown = file?.name.endsWith('.md')

  if (!file) return null

  return (
    <Dialog open={!!file} onOpenChange={(o) => !o && onClose()}>
      <DialogContent
        style={{ width: '680px', maxWidth: 'calc(100vw - 2rem)', height: '85vh' }}
        className="flex flex-col gap-0 p-0 sm:max-w-none"
      >
        <DialogHeader className="px-4 pt-4 pb-2 border-b flex-row items-center gap-2">
          <div className="flex items-center gap-2 min-w-0 flex-1">
            <DialogTitle className="text-sm truncate">{file.name}</DialogTitle>
            {isDirty && <Badge variant="outline" className="text-[10px] h-4 px-1">unsaved</Badge>}
          </div>
        </DialogHeader>

        <div className="flex-1 overflow-auto p-4">
          {loading && <p className="text-sm text-muted-foreground">Loading…</p>}

          {!loading && fileData?.type === 'text' && (
            <>
              {isMarkdown && mode === 'view' ? (
                <div className="prose prose-sm dark:prose-invert max-w-none">
                  <ReactMarkdown>{content}</ReactMarkdown>
                </div>
              ) : (
                <Textarea
                  value={content}
                  onChange={(e) => { setContent(e.target.value); setMode('edit') }}
                  className="h-full min-h-[400px] font-mono text-xs resize-none"
                  spellCheck={false}
                />
              )}
            </>
          )}

          {!loading && fileData?.type === 'image' && fileData.content_b64 && (
            <img
              src={`data:${fileData.mime};base64,${fileData.content_b64}`}
              alt={file.name}
              className="max-w-full h-auto rounded"
            />
          )}

          {!loading && fileData?.type === 'binary' && (
            <div className="flex flex-col items-center justify-center h-40 gap-3 text-muted-foreground">
              <p className="text-sm">Binary file — {formatSize(fileData.size)}</p>
              <a
                href={`/api/workspace/file?path=${encodeURIComponent(file.path)}`}
                download={file.name}
                className="inline-flex items-center justify-center rounded-md border border-input bg-background px-3 py-1.5 text-sm font-medium hover:bg-accent hover:text-accent-foreground transition-colors"
              >
                Download
              </a>
            </div>
          )}
        </div>

        {fileData?.type === 'text' && (
          <DialogFooter className="px-4 pb-4 pt-2 border-t flex-row items-center justify-between">
            <div>
              {isMarkdown && (
                <Button
                  size="sm" variant="ghost"
                  onClick={() => setMode(m => m === 'view' ? 'edit' : 'view')}
                >
                  {mode === 'view'
                    ? <><Edit2 className="h-3.5 w-3.5 mr-1.5" />Edit</>
                    : <><Eye className="h-3.5 w-3.5 mr-1.5" />Preview</>
                  }
                </Button>
              )}
            </div>
            <div className="flex gap-2">
              <Button variant="outline" onClick={onClose}>Close</Button>
              <Button
                onClick={() => save.mutate()}
                disabled={!isDirty || save.isPending}
              >
                <Save className="h-3.5 w-3.5 mr-1.5" />
                {save.isPending ? 'Saving…' : 'Save'}
              </Button>
            </div>
          </DialogFooter>
        )}
      </DialogContent>
    </Dialog>
  )
}

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}
