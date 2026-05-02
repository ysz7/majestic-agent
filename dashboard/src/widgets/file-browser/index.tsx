import { useRef, useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  listWorkspace, deleteWorkspaceFile, uploadWorkspaceFile, mkdirWorkspace,
  type WorkspaceItem,
} from '@/shared/api/workspace'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
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
  Folder, FileText, FileImage, File, Trash2, Upload, FolderPlus, ChevronRight,
} from 'lucide-react'
import { FileViewer } from '@/widgets/file-viewer'

function FileIcon({ type }: { type: WorkspaceItem['type'] }) {
  if (type === 'dir')    return <Folder   className="h-8 w-8 text-yellow-400/80" />
  if (type === 'image')  return <FileImage className="h-8 w-8 text-blue-400/80" />
  if (type === 'text')   return <FileText  className="h-8 w-8 text-green-400/80" />
  return <File className="h-8 w-8 text-muted-foreground" />
}

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}

export function FileBrowser() {
  const qc = useQueryClient()
  const [currentPath, setCurrentPath] = useState('')
  const [selectedFile, setSelectedFile] = useState<WorkspaceItem | null>(null)
  const [deleteTarget, setDeleteTarget] = useState<WorkspaceItem | null>(null)
  const [newFolderName, setNewFolderName] = useState('')
  const [showNewFolder, setShowNewFolder] = useState(false)
  const uploadRef = useRef<HTMLInputElement>(null)

  const { data, isLoading } = useQuery({
    queryKey: ['workspace', currentPath],
    queryFn: () => listWorkspace(currentPath),
  })

  const remove = useMutation({
    mutationFn: (path: string) => deleteWorkspaceFile(path),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['workspace'] }),
  })

  const mkdir = useMutation({
    mutationFn: (path: string) => mkdirWorkspace(path),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['workspace'] })
      setShowNewFolder(false)
      setNewFolderName('')
    },
  })

  const upload = useMutation({
    mutationFn: async (file: File) => {
      const b64 = await fileToBase64(file)
      return uploadWorkspaceFile(currentPath, file.name, b64)
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ['workspace'] }),
  })

  // Build breadcrumb segments
  const segments = currentPath ? currentPath.split('/').filter(Boolean) : []

  const navigateTo = (path: string) => setCurrentPath(path)

  const handleItemClick = (item: WorkspaceItem) => {
    if (item.type === 'dir') {
      setCurrentPath(item.path)
    } else {
      setSelectedFile(item)
    }
  }

  const handleUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (file) upload.mutate(file)
    e.target.value = ''
  }

  const handleMkdir = () => {
    if (!newFolderName.trim()) return
    const path = currentPath ? `${currentPath}/${newFolderName.trim()}` : newFolderName.trim()
    mkdir.mutate(path)
  }

  return (
    <div className="flex flex-col h-full">
      {/* Toolbar */}
      <div className="flex items-center justify-between mb-3 gap-2">
        {/* Breadcrumb */}
        <div className="flex items-center gap-1 text-sm min-w-0 flex-1">
          <button
            className="text-muted-foreground hover:text-foreground transition-colors shrink-0"
            onClick={() => navigateTo('')}
          >
            workspace
          </button>
          {segments.map((seg, i) => {
            const segPath = segments.slice(0, i + 1).join('/')
            return (
              <span key={segPath} className="flex items-center gap-1 min-w-0">
                <ChevronRight className="h-3 w-3 text-muted-foreground shrink-0" />
                <button
                  className={`hover:text-foreground transition-colors truncate ${i === segments.length - 1 ? 'text-foreground' : 'text-muted-foreground'}`}
                  onClick={() => navigateTo(segPath)}
                >
                  {seg}
                </button>
              </span>
            )
          })}
        </div>

        {/* Actions */}
        <div className="flex items-center gap-1.5 shrink-0">
          <Button size="sm" variant="outline" onClick={() => setShowNewFolder(true)}>
            <FolderPlus className="h-3.5 w-3.5 mr-1.5" />
            New folder
          </Button>
          <Button size="sm" variant="outline" onClick={() => uploadRef.current?.click()}>
            <Upload className="h-3.5 w-3.5 mr-1.5" />
            Upload
          </Button>
          <input ref={uploadRef} type="file" className="hidden" onChange={handleUpload} />
        </div>
      </div>

      {/* New folder input */}
      {showNewFolder && (
        <div className="flex items-center gap-2 mb-3">
          <Input
            autoFocus
            placeholder="Folder name"
            value={newFolderName}
            onChange={(e) => setNewFolderName(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter') handleMkdir(); if (e.key === 'Escape') setShowNewFolder(false) }}
            className="h-8 text-sm"
          />
          <Button size="sm" onClick={handleMkdir} disabled={mkdir.isPending}>Create</Button>
          <Button size="sm" variant="ghost" onClick={() => setShowNewFolder(false)}>Cancel</Button>
        </div>
      )}

      {/* File grid */}
      {isLoading && <p className="text-sm text-muted-foreground py-4">Loading…</p>}

      {!isLoading && (!data?.items || data.items.length === 0) && (
        <div className="flex flex-col items-center justify-center py-16 text-muted-foreground gap-2">
          <Folder className="h-10 w-10 opacity-30" />
          <p className="text-sm">Empty folder</p>
        </div>
      )}

      <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6 gap-2 overflow-auto">
        {data?.items.map((item) => (
          <div
            key={item.path}
            className="group relative flex flex-col items-center gap-1.5 p-3 rounded-lg border border-transparent hover:border-border hover:bg-accent/40 cursor-pointer transition-colors"
            onClick={() => handleItemClick(item)}
          >
            <FileIcon type={item.type} />
            <span className="text-xs text-center leading-tight break-all line-clamp-2 w-full text-center">
              {item.name}
            </span>
            {item.type !== 'dir' && (
              <span className="text-[10px] text-muted-foreground">{formatSize(item.size)}</span>
            )}
            {/* Delete button */}
            <button
              className="absolute top-1.5 right-1.5 opacity-0 group-hover:opacity-100 transition-opacity p-0.5 rounded hover:bg-destructive/20 hover:text-destructive"
              onClick={(e) => { e.stopPropagation(); setDeleteTarget(item) }}
            >
              <Trash2 className="h-3 w-3" />
            </button>
          </div>
        ))}
      </div>

      {/* File viewer */}
      <FileViewer file={selectedFile} onClose={() => setSelectedFile(null)} />

      {/* Delete confirm */}
      <AlertDialog open={!!deleteTarget} onOpenChange={(o) => !o && setDeleteTarget(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete {deleteTarget?.type === 'dir' ? 'folder' : 'file'}?</AlertDialogTitle>
            <AlertDialogDescription>
              <strong>{deleteTarget?.name}</strong> will be permanently deleted.
              {deleteTarget?.type === 'dir' && ' All contents will be removed.'}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
              onClick={() => {
                if (deleteTarget) {
                  remove.mutate(deleteTarget.path)
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

async function fileToBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => {
      const result = reader.result as string
      resolve(result.split(',')[1])
    }
    reader.onerror = reject
    reader.readAsDataURL(file)
  })
}
