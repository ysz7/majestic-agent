import { useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  Sidebar,
  SidebarContent,
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarHeader,
  SidebarFooter,
} from '@/components/ui/sidebar'
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
import { ScrollArea } from '@/components/ui/scroll-area'
import {
  MessageSquare,
  Settings,
  Brain,
  Zap,
  Table2,
  Activity,
  FolderOpen,
  Plus,
  Trash2,
} from 'lucide-react'
import { getSessions, deleteSession } from '@/shared/api/sessions'
import { cn } from '@/lib/utils'

const navItems = [
  { label: 'Chat', icon: MessageSquare, href: '/chat' },
  { label: 'Files', icon: FolderOpen, href: '/workspace' },
  { label: 'Memory', icon: Brain, href: '/memory' },
  { label: 'Skills', icon: Zap, href: '/skills' },
  { label: 'Tables', icon: Table2, href: '/tables' },
  { label: 'Monitoring', icon: Activity, href: '/monitoring' },
  { label: 'Settings', icon: Settings, href: '/settings' },
]

function formatTime(iso: string) {
  if (!iso) return ''
  const d = new Date(iso)
  const diffH = (Date.now() - d.getTime()) / 3_600_000
  if (diffH < 1) return `${Math.round(diffH * 60)}m ago`
  if (diffH < 24) return `${Math.round(diffH)}h ago`
  return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
}

export function AppSidebar() {
  const location = useLocation()
  const navigate = useNavigate()
  const qc = useQueryClient()
  const [pendingDelete, setPendingDelete] = useState<string | null>(null)

  const { data: sessions = [] } = useQuery({
    queryKey: ['sessions'],
    queryFn: getSessions,
    refetchInterval: 15_000,
  })

  const remove = useMutation({
    mutationFn: (id: string) => deleteSession(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['sessions'] }),
  })

  const urlSession = location.pathname === '/chat'
    ? new URLSearchParams(location.search).get('session')
    : null

  return (
    <>
      <Sidebar>
        <SidebarHeader className="px-4 py-4">
          <div className="flex items-center gap-2">
            <img src="/majestic-icon.png" alt="Majestic" className="h-6 w-6 rounded-sm" />
            <span className="font-semibold text-sm tracking-tight">Majestic</span>
          </div>
        </SidebarHeader>

        <SidebarContent>
          {/* Navigation */}
          <SidebarGroup>
            <SidebarGroupLabel>Navigation</SidebarGroupLabel>
            <SidebarGroupContent>
              <SidebarMenu>
                {navItems.map((item) => (
                  <SidebarMenuItem key={item.href}>
                    <SidebarMenuButton
                      isActive={location.pathname === item.href}
                      onClick={() => navigate(item.href)}
                    >
                      <item.icon />
                      <span>{item.label}</span>
                    </SidebarMenuButton>
                  </SidebarMenuItem>
                ))}
              </SidebarMenu>
            </SidebarGroupContent>
          </SidebarGroup>

          {/* Sessions */}
          <SidebarGroup>
            <SidebarGroupLabel className="flex items-center justify-between pr-1">
              <span>Chats</span>
              <button
                className="h-5 w-5 flex items-center justify-center rounded hover:bg-sidebar-accent text-muted-foreground hover:text-foreground transition-colors"
                onClick={() => navigate('/chat', { state: { newChat: true } })}
                title="New chat"
              >
                <Plus className="h-3.5 w-3.5" />
              </button>
            </SidebarGroupLabel>
            <SidebarGroupContent>
              <ScrollArea className="max-h-[55vh]">
                <div className="px-1 pb-1 space-y-0.5">
                  {sessions.length === 0 && (
                    <p className="text-xs text-muted-foreground px-2 py-3 text-center">No chats yet</p>
                  )}
                  {sessions.map((s) => {
                    const isActive = urlSession === s.id
                    const label = s.title || s.source || `Chat ${s.id.slice(0, 6)}`
                    return (
                      <div
                        key={s.id}
                        className={cn(
                          'group flex items-center gap-1.5 rounded-md px-2 py-1.5 cursor-pointer transition-colors hover:bg-sidebar-accent',
                          isActive && 'bg-sidebar-accent',
                        )}
                        onClick={() => navigate(`/chat?session=${encodeURIComponent(s.id)}`)}
                      >
                        <MessageSquare className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
                        <div className="flex-1 min-w-0">
                          <p className={cn('text-xs truncate leading-snug', isActive && 'font-medium')}>
                            {label}
                          </p>
                          <p className="text-[10px] text-muted-foreground">{formatTime(s.started_at)}</p>
                        </div>
                        <button
                          className="opacity-0 group-hover:opacity-100 h-5 w-5 flex items-center justify-center rounded text-muted-foreground hover:text-destructive shrink-0 transition-opacity"
                          onClick={(e) => { e.stopPropagation(); setPendingDelete(s.id) }}
                        >
                          <Trash2 className="h-3 w-3" />
                        </button>
                      </div>
                    )
                  })}
                </div>
              </ScrollArea>
            </SidebarGroupContent>
          </SidebarGroup>
        </SidebarContent>

        <SidebarFooter />
      </Sidebar>

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
              onClick={() => {
                if (pendingDelete) { remove.mutate(pendingDelete); setPendingDelete(null) }
              }}
            >
              Delete
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  )
}
