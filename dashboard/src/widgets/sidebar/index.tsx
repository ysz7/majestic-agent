import { useLocation, useNavigate } from 'react-router-dom'
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
  MessageSquare,
  Settings,
  Brain,
  Zap,
  Table2,
  Activity,
  FolderOpen,
} from 'lucide-react'

const navItems = [
  { label: 'Chat', icon: MessageSquare, href: '/chat' },
  { label: 'Workspace', icon: FolderOpen, href: '/workspace' },
  { label: 'Memory', icon: Brain, href: '/memory' },
  { label: 'Skills', icon: Zap, href: '/skills' },
  { label: 'Tables', icon: Table2, href: '/tables' },
  { label: 'Monitoring', icon: Activity, href: '/monitoring' },
  { label: 'Settings', icon: Settings, href: '/settings' },
]

export function AppSidebar() {
  const location = useLocation()
  const navigate = useNavigate()

  return (
    <Sidebar>
      <SidebarHeader className="px-4 py-4">
        <div className="flex items-center gap-2">
          <img src="/majestic-icon.png" alt="Majestic" className="h-6 w-6 rounded-sm" />
          <span className="font-semibold text-sm tracking-tight">Majestic</span>
        </div>
      </SidebarHeader>
      <SidebarContent>
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
      </SidebarContent>
      <SidebarFooter />
    </Sidebar>
  )
}
