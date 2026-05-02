import { useState, useEffect } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { readWorkspaceFile, saveWorkspaceFile } from '@/shared/api/workspace'
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
import { Eye, Save, Download, Code } from 'lucide-react'

export interface FileRef {
  path: string
  name: string
}

interface Props {
  file: FileRef | null
  onClose: () => void
}

type RenderMode = 'preview' | 'source'

function fileKind(name: string): 'html' | 'markdown' | 'code' | 'image' | 'csv' | 'text' {
  const ext = name.split('.').pop()?.toLowerCase() ?? ''
  if (ext === 'html' || ext === 'htm') return 'html'
  if (ext === 'md' || ext === 'markdown') return 'markdown'
  if (['png', 'jpg', 'jpeg', 'gif', 'svg', 'webp'].includes(ext)) return 'image'
  if (ext === 'csv') return 'csv'
  if (['py', 'js', 'ts', 'tsx', 'jsx', 'json', 'yaml', 'yml', 'sh', 'bash', 'sql', 'css', 'xml', 'toml', 'ini', 'rs', 'go', 'rb', 'java', 'kt', 'swift', 'c', 'cpp', 'h'].includes(ext)) return 'code'
  return 'text'
}

function CsvTable({ content }: { content: string }) {
  const lines = content.trim().split('\n')
  if (lines.length === 0) return null
  const headers = lines[0].split(',').map(h => h.trim().replace(/^"|"$/g, ''))
  const rows = lines.slice(1).map(l => l.split(',').map(c => c.trim().replace(/^"|"$/g, '')))
  return (
    <div className="overflow-auto">
      <table className="w-full text-xs border-collapse">
        <thead>
          <tr className="border-b border-border">
            {headers.map((h, i) => (
              <th key={i} className="px-3 py-1.5 text-left font-medium text-muted-foreground whitespace-nowrap">{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, ri) => (
            <tr key={ri} className="border-b border-border/50 hover:bg-muted/40">
              {row.map((cell, ci) => (
                <td key={ci} className="px-3 py-1.5 whitespace-nowrap">{cell}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export function FileViewer({ file, onClose }: Props) {
  const qc = useQueryClient()
  const [content, setContent] = useState('')
  const [originalContent, setOriginalContent] = useState('')
  const [renderMode, setRenderMode] = useState<RenderMode>('preview')
  const [fileData, setFileData] = useState<Awaited<ReturnType<typeof readWorkspaceFile>> | null>(null)
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    if (!file) return
    setLoading(true)
    setRenderMode('preview')
    setContent('')
    setOriginalContent('')
    setFileData(null)
    readWorkspaceFile(file.path)
      .then((data) => {
        setFileData(data)
        if (data.type === 'text' && data.content !== undefined) {
          setContent(data.content)
          setOriginalContent(data.content)
        }
      })
      .finally(() => setLoading(false))
  }, [file?.path])

  const save = useMutation({
    mutationFn: () => saveWorkspaceFile(file!.path, content),
    onSuccess: () => {
      setOriginalContent(content)
      qc.invalidateQueries({ queryKey: ['workspace'] })
    },
  })

  if (!file) return null

  const kind = fileKind(file.name)
  const isDirty = content !== originalContent
  const canEdit = kind !== 'image' && kind !== 'html' && fileData?.type === 'text'
  const showToggle = kind === 'html' || kind === 'markdown'

  return (
    <Dialog open={!!file} onOpenChange={(o) => !o && onClose()}>
      <DialogContent
        style={{ width: '720px', maxWidth: 'calc(100vw - 2rem)', height: '88vh' }}
        className="flex flex-col gap-0 p-0 sm:max-w-none"
      >
        {/* Header */}
        <DialogHeader className="px-4 pt-4 pb-2 border-b flex-row items-center gap-2 shrink-0">
          <div className="flex items-center gap-2 min-w-0 flex-1">
            <DialogTitle className="text-sm truncate font-mono">{file.name}</DialogTitle>
            {isDirty && <Badge variant="outline" className="text-[10px] h-4 px-1 shrink-0">unsaved</Badge>}
          </div>
          {showToggle && (
            <div className="flex items-center border rounded-md overflow-hidden shrink-0">
              <button
                className={`px-2.5 py-1 text-xs transition-colors ${renderMode === 'preview' ? 'bg-muted text-foreground' : 'text-muted-foreground hover:text-foreground'}`}
                onClick={() => setRenderMode('preview')}
              >
                <Eye className="h-3 w-3 inline mr-1" />Preview
              </button>
              <button
                className={`px-2.5 py-1 text-xs transition-colors border-l ${renderMode === 'source' ? 'bg-muted text-foreground' : 'text-muted-foreground hover:text-foreground'}`}
                onClick={() => setRenderMode('source')}
              >
                <Code className="h-3 w-3 inline mr-1" />Source
              </button>
            </div>
          )}
        </DialogHeader>

        {/* Body */}
        <div className="flex-1 overflow-auto">
          {loading && <p className="text-sm text-muted-foreground p-4">Loading…</p>}

          {/* HTML — sandboxed iframe */}
          {!loading && kind === 'html' && renderMode === 'preview' && content && (
            <iframe
              srcDoc={content}
              sandbox="allow-scripts"
              className="w-full h-full border-0 bg-white"
              title={file.name}
            />
          )}

          {/* HTML source / any code / plain text */}
          {!loading && fileData?.type === 'text' && (renderMode === 'source' || kind === 'code' || kind === 'text') && (
            canEdit ? (
              <Textarea
                value={content}
                onChange={(e) => setContent(e.target.value)}
                className="h-full min-h-[400px] font-mono text-xs resize-none rounded-none border-0 focus-visible:ring-0"
                spellCheck={false}
              />
            ) : (
              <pre className="p-4 text-xs font-mono whitespace-pre-wrap break-words leading-relaxed">{content}</pre>
            )
          )}

          {/* Markdown */}
          {!loading && kind === 'markdown' && renderMode === 'preview' && (
            <div className="prose prose-sm dark:prose-invert max-w-none p-4 [&>*:first-child]:mt-0">
              <ReactMarkdown remarkPlugins={[remarkGfm]}>{content}</ReactMarkdown>
            </div>
          )}

          {/* CSV table */}
          {!loading && kind === 'csv' && fileData?.type === 'text' && (
            <div className="p-4">
              <CsvTable content={content} />
            </div>
          )}

          {/* Image */}
          {!loading && kind === 'image' && fileData?.type === 'image' && fileData.content_b64 && (
            <div className="p-4 flex justify-center">
              <img
                src={`data:${fileData.mime};base64,${fileData.content_b64}`}
                alt={file.name}
                className="max-w-full h-auto rounded"
              />
            </div>
          )}

          {/* Binary */}
          {!loading && fileData?.type === 'binary' && (
            <div className="flex flex-col items-center justify-center h-40 gap-3 text-muted-foreground">
              <p className="text-sm">Binary file — {formatSize(fileData.size)}</p>
            </div>
          )}
        </div>

        {/* Footer */}
        <DialogFooter className="px-4 pb-4 pt-2 border-t flex-row items-center justify-between shrink-0">
          <a
            href={`/api/workspace/file?path=${encodeURIComponent(file.path)}&download=1`}
            download={file.name}
            className="inline-flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground transition-colors"
          >
            <Download className="h-3.5 w-3.5" />Download
          </a>
          <div className="flex gap-2">
            <Button variant="outline" size="sm" onClick={onClose}>Close</Button>
            {canEdit && (
              <Button
                size="sm"
                onClick={() => save.mutate()}
                disabled={!isDirty || save.isPending}
              >
                <Save className="h-3.5 w-3.5 mr-1.5" />
                {save.isPending ? 'Saving…' : 'Save'}
              </Button>
            )}
          </div>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}
