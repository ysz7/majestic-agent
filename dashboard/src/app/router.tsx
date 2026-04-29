import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { getSetupStatus } from '@/shared/api/setup'
import { OnboardingPage } from '@/pages/onboarding'
import { ChatPage } from '@/pages/chat'
import { SettingsPage } from '@/pages/settings'
import { MemoryPage } from '@/pages/memory'
import { SkillsPage } from '@/pages/skills'
import { TablesPage } from '@/pages/tables'
import { MonitoringPage } from '@/pages/monitoring'
import { AppLayout } from './layout'

function Guard({ children }: { children: React.ReactNode }) {
  const { data, isLoading } = useQuery({
    queryKey: ['setup-status'],
    queryFn: getSetupStatus,
    retry: false,
  })

  if (isLoading) return null
  if (!data?.configured) return <Navigate to="/onboarding" replace />
  return <>{children}</>
}

export function AppRouter() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/onboarding" element={<OnboardingPage />} />
        <Route
          path="/*"
          element={
            <Guard>
              <AppLayout>
                <Routes>
                  <Route index element={<Navigate to="/chat" replace />} />
                  <Route path="chat" element={<ChatPage />} />
                  <Route path="settings" element={<SettingsPage />} />
                  <Route path="memory" element={<MemoryPage />} />
                  <Route path="skills" element={<SkillsPage />} />
                  <Route path="tables" element={<TablesPage />} />
                  <Route path="monitoring" element={<MonitoringPage />} />
                </Routes>
              </AppLayout>
            </Guard>
          }
        />
      </Routes>
    </BrowserRouter>
  )
}
