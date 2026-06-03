import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { Providers }     from "./providers";
import { AppShell }      from "@widgets/shell/AppShell";
import { NodesPage }     from "@pages/nodes";
import { SettingsPage }  from "@pages/settings";
import { useAutoConnect } from "./useAutoConnect";

function AppRoutes() {
  const { status, error } = useAutoConnect();

  if (status === "checking" || status === "starting") {
    return (
      <div className="fixed inset-0 flex flex-col items-center justify-center bg-bg-canvas gap-[12px]">
        <div className="w-[28px] h-[28px] rounded-full border-2 border-border border-t-text-dim animate-spin" />
        <div className="text-xs text-text-muted-2">
          {status === "starting" ? "Starting agent…" : "Connecting…"}
        </div>
      </div>
    );
  }

  if (status === "error") {
    return (
      <div className="fixed inset-0 flex flex-col items-center justify-center bg-bg-canvas gap-[10px] px-[32px]">
        <div className="text-xs text-red-400 text-center leading-[1.6] max-w-[320px]">{error}</div>
        <button
          onClick={() => window.location.reload()}
          className="mt-[4px] text-xs text-text-muted-2 border border-border rounded-[7px] px-[14px] py-[7px] hover:border-border-strong"
        >
          Retry
        </button>
      </div>
    );
  }

  return (
    <BrowserRouter>
      <Routes>
        <Route element={<AppShell />}>
          <Route index element={<Navigate to="/nodes" replace />} />
          <Route path="/nodes"    element={<NodesPage />} />
          <Route path="/settings" element={<SettingsPage />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}

export function App() {
  return (
    <Providers>
      <AppRoutes />
    </Providers>
  );
}
