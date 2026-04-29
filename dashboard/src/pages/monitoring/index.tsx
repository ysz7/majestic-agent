import { useQuery } from '@tanstack/react-query'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { apiFetch } from '@/shared/api/client'

interface Health {
  status: string
  uptime: number
  version: string
}

interface TokenStats {
  total_tokens: number
  total_cost_usd: number
  sessions: number
}

export function MonitoringPage() {
  const { data: health } = useQuery<Health>({
    queryKey: ['health'],
    queryFn: () => apiFetch('/health'),
    refetchInterval: 10_000,
  })

  const { data: tokens } = useQuery<TokenStats>({
    queryKey: ['token-stats'],
    queryFn: () => apiFetch('/api/tokens/stats'),
    refetchInterval: 30_000,
  })

  return (
    <div className="space-y-4 max-w-2xl">
      <div>
        <h2 className="text-lg font-semibold">Monitoring</h2>
        <p className="text-sm text-muted-foreground">Agent health and usage</p>
      </div>
      <div className="grid grid-cols-2 gap-3">
        <Card>
          <CardHeader className="pb-1">
            <CardTitle className="text-xs text-muted-foreground uppercase tracking-wide">Status</CardTitle>
          </CardHeader>
          <CardContent>
            <Badge variant={health?.status === 'ok' ? 'default' : 'destructive'}>
              {health?.status ?? '…'}
            </Badge>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-1">
            <CardTitle className="text-xs text-muted-foreground uppercase tracking-wide">Uptime</CardTitle>
          </CardHeader>
          <CardContent className="text-sm font-medium">
            {health?.uptime != null ? `${Math.floor(health.uptime / 60)}m` : '…'}
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-1">
            <CardTitle className="text-xs text-muted-foreground uppercase tracking-wide">Total Tokens</CardTitle>
          </CardHeader>
          <CardContent className="text-sm font-medium">
            {tokens?.total_tokens?.toLocaleString() ?? '…'}
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-1">
            <CardTitle className="text-xs text-muted-foreground uppercase tracking-wide">Cost (USD)</CardTitle>
          </CardHeader>
          <CardContent className="text-sm font-medium">
            {tokens?.total_cost_usd != null ? `$${tokens.total_cost_usd.toFixed(4)}` : '…'}
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
