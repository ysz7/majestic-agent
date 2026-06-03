import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { useEffect } from "react";
import { wsClient }             from "@shared/ws/client";
import { useNotificationBridge } from "@shared/hooks/useNotificationBridge";
import { useAgentStore }        from "@store/agentStore";

import { ApiError } from "@shared/api/client";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 10_000,
      // Don't retry on 401/403 — token missing, wizard will fix it
      retry: (count, err) => {
        if (err instanceof ApiError && (err.status === 401 || err.status === 403)) return false;
        return count < 1;
      },
      // Stop refetching when unauthorized
      refetchInterval: (query) => {
        if (query.state.error instanceof ApiError &&
            (query.state.error.status === 401 || query.state.error.status === 403)) return false;
        return false; // individual queries set their own intervals
      },
    },
  },
});

function WsProvider({ children }: { children: ReactNode }) {
  const token = useAgentStore((s) => s.agentToken);

  // Connect WS when token is available (empty token = no-auth agent)
  useEffect(() => {
    wsClient.connect(token);
    return () => wsClient.disconnect();
  }, [token]);

  // Wire WS events → native Tauri notifications
  useNotificationBridge();

  return <>{children}</>;
}

export function Providers({ children }: { children: ReactNode }) {
  return (
    <QueryClientProvider client={queryClient}>
      <WsProvider>{children}</WsProvider>
    </QueryClientProvider>
  );
}
