import type { ReactNode } from 'react'
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

function Page({ children }: { children: ReactNode }) {
  return <div className="flex-1 overflow-auto p-4">{children}</div>
}

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
                  <Route path="settings" element={<Page><SettingsPage /></Page>} />
                  <Route path="memory" element={<Page><MemoryPage /></Page>} />
                  <Route path="skills" element={<Page><SkillsPage /></Page>} />
                  <Route path="tables" element={<Page><TablesPage /></Page>} />
                  <Route path="monitoring" element={<Page><MonitoringPage /></Page>} />
                </Routes>
              </AppLayout>
            </Guard>
          }
        />
      </Routes>
    </BrowserRouter>
  )
}
