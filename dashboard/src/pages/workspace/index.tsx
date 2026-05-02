import { FileBrowser } from '@/widgets/file-browser'

export function WorkspacePage() {
  return (
    <div className="flex flex-col h-full">
      <div className="mb-4">
        <p className="text-sm font-medium">Workspace</p>
        <p className="text-xs text-muted-foreground">Files created and managed by the agent</p>
      </div>
      <div className="flex-1 overflow-hidden">
        <FileBrowser />
      </div>
    </div>
  )
}
