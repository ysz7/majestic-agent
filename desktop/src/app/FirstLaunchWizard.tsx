import { useState, useEffect } from "react";
import { CheckCircle2, XCircle } from "lucide-react";
import { Button } from "@shared/ui-kit";
import { checkPython, isTauri } from "@shared/lib/tauri";
import { useAgentStore } from "@store/agentStore";
import { API_BASE } from "@shared/config";

const LS_KEY = "ml_connected";

export function shouldShowWizard(): boolean {
  return !localStorage.getItem(LS_KEY);
}

export function markConnected(): void {
  localStorage.setItem(LS_KEY, "1");
}

interface Props {
  onDone: () => void;
}

type Step = "welcome" | "connect" | "ollama" | "done";

type PythonStatus = "checking" | "ok" | "old" | "missing" | "skipped";

export function FirstLaunchWizard({ onDone }: Props) {
  const [step,       setStep]       = useState<Step>("welcome");
  const [token,      setToken]      = useState("");
  const [connecting, setConnecting] = useState(false);
  const [error,      setError]      = useState("");
  const setStoreToken = useAgentStore((s) => s.setToken);

  const [pythonStatus,  setPyStatus]  = useState<PythonStatus>(isTauri() ? "checking" : "skipped");
  const [pythonVersion, setPyVersion] = useState("");

  useEffect(() => {
    if (!isTauri()) return;
    checkPython().then(({ ok, version }) => {
      setPyVersion(version);
      setPyStatus(version ? (ok ? "ok" : "old") : "missing");
    });
  }, []);

  const handleConnect = async () => {
    setConnecting(true);
    setError("");
    try {
      const res = await fetch(`${API_BASE}/api/profiles`, {
        headers: { "X-Agent-Token": token },
      });
      if (res.ok) {
        if (token) setStoreToken(token);
        markConnected();
        setStep("ollama");
      } else if (res.status === 401) {
        setError("Invalid token. Check data/agent_token in your project directory.");
      } else {
        setError(`Server responded with ${res.status}. Is the agent running?`);
      }
    } catch {
      setError("Could not connect. Run: majestic run default");
    } finally {
      setConnecting(false);
    }
  };

  return (
    /* Backdrop */
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70">
      {/* Modal */}
      <div
        className="relative flex flex-col gap-[16px] bg-bg-canvas border border-border-strong rounded-node"
        style={{ width: 400, padding: "28px 24px" }}
      >
        {/* Step indicator */}
        <div className="flex items-center gap-[6px] mb-[2px]">
          {(["welcome", "connect", "ollama", "done"] as Step[]).map((s) => (
            <span
              key={s}
              className="h-[3px] flex-1 rounded-full transition-colors"
              style={{
                background:
                  step === s
                    ? "#ffffff"
                    : (
                        (step === "connect" && s === "welcome") ||
                        (step === "ollama"  && (s === "welcome" || s === "connect")) ||
                        step === "done"
                      )
                    ? "rgba(255,255,255,0.4)"
                    : "rgba(255,255,255,0.1)",
              }}
            />
          ))}
        </div>

        {/* ── Welcome ──────────────────────────── */}
        {step === "welcome" && (
          <>
            <div>
              <div className="text-brand font-bold text-text-sub mb-[6px]">
                Welcome to <b>Majestic</b>
              </div>
              <div className="text-xs text-text-muted-2 leading-[1.6]">
                This desktop app controls your Majestic AI agents.
                You need Python 3.11+ + the{" "}
                <span className="text-text-dim font-mono">majestic</span> package installed
                and at least one agent running.
              </div>
            </div>

            {/* Python status row */}
            {pythonStatus !== "skipped" && (
              <div className="flex items-center gap-[8px] border border-border rounded-node bg-bg-elevated px-[13px] py-[10px]">
                {pythonStatus === "checking" && (
                  <>
                    <span className="w-[7px] h-[7px] rounded-full bg-[#fbbf24] animate-pulse flex-shrink-0" />
                    <span className="text-xs text-text-muted-2">Checking Python…</span>
                  </>
                )}
                {pythonStatus === "ok" && (
                  <>
                    <CheckCircle2 size={14} className="text-[#4ade80] flex-shrink-0" />
                    <span className="text-xs text-text-sub">{pythonVersion}</span>
                  </>
                )}
                {pythonStatus === "old" && (
                  <>
                    <XCircle size={14} className="text-[#fbbf24] flex-shrink-0" />
                    <span className="text-xs text-text-muted-2">
                      {pythonVersion} — Majestic requires Python 3.11+
                    </span>
                  </>
                )}
                {pythonStatus === "missing" && (
                  <>
                    <XCircle size={14} className="text-red-400 flex-shrink-0" />
                    <span className="text-xs text-text-muted-2">
                      Python not found — install from{" "}
                      <span className="text-text-dim font-mono">python.org</span>
                    </span>
                  </>
                )}
              </div>
            )}

            <div className="border border-border rounded-node bg-bg-elevated px-[13px] py-[11px] flex flex-col gap-[7px]">
              <div className="text-2xs text-text-muted-3 uppercase tracking-[1.2px] font-semibold">
                Quick start
              </div>
              <code className="text-xs text-text-dim font-mono">pip install -e .</code>
              <code className="text-xs text-text-dim font-mono">majestic run default</code>
            </div>

            <div className="flex justify-end">
              <Button variant="cta" size="sm" onClick={() => setStep("connect")}>
                Next →
              </Button>
            </div>
          </>
        )}

        {/* ── Connect ──────────────────────────── */}
        {step === "connect" && (
          <>
            <div>
              <div className="text-brand font-bold text-text-sub mb-[6px]">
                Connect to agent
              </div>
              <div className="text-xs text-text-muted-2 leading-[1.6]">
                Make sure your agent is running, then click Connect.
                If the agent has auth enabled, paste the token from{" "}
                <span className="text-text-dim font-mono">data/agent_token</span>.
              </div>
            </div>

            <div className="flex flex-col gap-[5px]">
              <label className="text-2xs text-text-muted-3 uppercase tracking-[1.2px] font-semibold">
                Agent token (optional)
              </label>
              <input
                value={token}
                onChange={(e) => setToken(e.target.value)}
                placeholder="Leave empty if no auth"
                className="border border-border rounded-control bg-bg-surface text-xs text-text-dim px-[11px] py-[9px] focus:outline-none focus:border-border-strong placeholder:text-text-muted-3"
              />
            </div>

            {error && (
              <div className="text-xs text-red-400 leading-[1.5]">{error}</div>
            )}

            <div className="flex justify-between items-center">
              <button
                onClick={() => setStep("welcome")}
                className="text-xs text-text-muted-2 hover:text-text-sub"
              >
                ← Back
              </button>
              <div className="flex items-center gap-[8px]">
                <button
                  onClick={() => { markConnected(); setStep("ollama"); }}
                  className="text-xs text-text-muted-3 hover:text-text-muted-2"
                >
                  Skip for now
                </button>
                <Button
                  variant="cta"
                  size="sm"
                  onClick={handleConnect}
                  disabled={connecting}
                >
                  {connecting ? "Connecting…" : "Connect"}
                </Button>
              </div>
            </div>
          </>
        )}

        {/* ── Ollama ───────────────────────────── */}
        {step === "ollama" && (
          <>
            <div>
              <div className="text-brand font-bold text-text-sub mb-[6px]">
                Local models (optional)
              </div>
              <div className="text-xs text-text-muted-2 leading-[1.6]">
                Majestic can use <span className="text-text-dim font-mono">Ollama</span> to run
                models locally — no API key needed, fully private.
                Install it if you want to use Llama, Mistral, or other open models.
              </div>
            </div>

            <div className="border border-border rounded-node bg-bg-elevated px-[13px] py-[11px] flex flex-col gap-[7px]">
              <div className="text-2xs text-text-muted-3 uppercase tracking-[1.2px] font-semibold">
                Setup
              </div>
              <code className="text-xs text-text-dim font-mono">
                1. Download from ollama.com
              </code>
              <code className="text-xs text-text-dim font-mono">
                2. ollama pull llama3.2
              </code>
              <code className="text-xs text-text-dim font-mono">
                3. Set MAJESTIC_MODEL_REASON=ollama/llama3.2
              </code>
            </div>

            <div className="flex justify-between items-center">
              <button
                onClick={() => setStep("connect")}
                className="text-xs text-text-muted-2 hover:text-text-sub"
              >
                ← Back
              </button>
              <div className="flex items-center gap-[8px]">
                <button
                  onClick={() => setStep("done")}
                  className="text-xs text-text-muted-3 hover:text-text-muted-2"
                >
                  Skip
                </button>
                <Button variant="cta" size="sm" onClick={() => setStep("done")}>
                  Got it →
                </Button>
              </div>
            </div>
          </>
        )}

        {/* ── Done ─────────────────────────────── */}
        {step === "done" && (
          <>
            <div>
              <div className="text-brand font-bold text-text-sub mb-[6px]">
                Connected
              </div>
              <div className="text-xs text-text-muted-2 leading-[1.6]">
                Majestic is connected to your agent. You can now manage profiles,
                view memory, edit skills, and monitor tasks from this desktop app.
              </div>
            </div>

            <div className="flex items-center gap-[8px] border border-border rounded-node bg-bg-elevated px-[13px] py-[10px]">
              <span className="w-[7px] h-[7px] rounded-full bg-[#4ade80] flex-shrink-0" />
              <span className="text-xs text-text-sub">Agent is reachable</span>
            </div>

            <div className="flex justify-end">
              <Button variant="cta" size="sm" onClick={onDone}>
                Open Majestic
              </Button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
