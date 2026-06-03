/**
 * On app start: read agent token from disk → try to connect → auto-start agent if down.
 * Returns { ready, error } so App.tsx knows whether to show the wizard or open directly.
 */
import { useEffect, useState } from "react";
import { isTauri, readAgentToken, startAgent } from "@shared/lib/tauri";
import { useAgentStore } from "@store/agentStore";
import { API_BASE } from "@shared/config";
import { markConnected } from "./FirstLaunchWizard";

type Status = "checking" | "ready" | "starting" | "error";

async function probe(token: string): Promise<boolean> {
  try {
    const res = await fetch(`${API_BASE}/api/profiles`, {
      headers: { "X-Agent-Token": token },
    });
    return res.ok;
  } catch {
    return false;
  }
}

async function waitForAgent(token: string, retries = 15, delayMs = 2000): Promise<boolean> {
  for (let i = 0; i < retries; i++) {
    if (await probe(token)) return true;
    await new Promise((r) => setTimeout(r, delayMs));
  }
  return false;
}

export function useAutoConnect(): { status: Status; error: string } {
  const [status, setStatus] = useState<Status>("checking");
  const [error,  setError]  = useState("");
  const setToken = useAgentStore((s) => s.setToken);

  useEffect(() => {
    let cancelled = false;

    async function run() {
      // 1. Read token from disk (Tauri) or localStorage (browser dev)
      let token = "";
      if (isTauri()) {
        token = await readAgentToken();
      } else {
        token = localStorage.getItem("agent_token") ?? "";
      }

      if (token) setToken(token);

      // 2. Try connecting
      if (await probe(token)) {
        if (!cancelled) { markConnected(); setStatus("ready"); }
        return;
      }

      // 3. Agent not running → auto-start it
      if (isTauri()) {
        if (!cancelled) setStatus("starting");
        try {
          await startAgent("default");
        } catch (e) {
          if (!cancelled) { setError(`Could not start agent: ${(e as Error).message}`); setStatus("error"); }
          return;
        }

        // 4. Wait up to 30s for agent to be ready
        const ok = await waitForAgent(token);
        if (!cancelled) {
          if (ok) { markConnected(); setStatus("ready"); }
          else    { setError("Agent started but is not responding. Run: majestic run default"); setStatus("error"); }
        }
      } else {
        // Browser dev without Tauri — just show error
        if (!cancelled) {
          setError("Agent not running. Start it with: majestic run default");
          setStatus("error");
        }
      }
    }

    run();
    return () => { cancelled = true; };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return { status, error };
}
