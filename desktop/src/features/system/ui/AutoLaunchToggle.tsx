import { useEffect, useState } from "react";
import { getAutolaunch, setAutolaunch, isTauri } from "@shared/lib/tauri";

export function AutoLaunchToggle() {
  const [enabled,  setEnabled]  = useState(false);
  const [loading,  setLoading]  = useState(true);
  const [pending,  setPending]  = useState(false);
  const available = isTauri();

  useEffect(() => {
    if (!available) { setLoading(false); return; }
    getAutolaunch().then((v) => { setEnabled(v); setLoading(false); });
  }, [available]);

  const toggle = async () => {
    if (!available || pending) return;
    setPending(true);
    await setAutolaunch(!enabled);
    setEnabled((v) => !v);
    setPending(false);
  };

  return (
    <div
      className={`flex items-center justify-between border border-border rounded-node bg-bg-elevated px-[11px] py-[9px] ${
        !available ? "opacity-40" : ""
      }`}
    >
      <div>
        <div className="text-xs text-text-dim">Start on login</div>
        <div className="text-xs text-text-muted-2 mt-[2px]">
          {available ? "Launch Majestic when system starts" : "Only available in desktop app"}
        </div>
      </div>

      {loading ? (
        <div className="w-[32px] h-[17px] rounded-full border border-border bg-bg-surface" />
      ) : (
        <button
          onClick={toggle}
          disabled={!available || pending}
          className={`relative w-[32px] h-[17px] rounded-full border transition-colors ${
            enabled
              ? "bg-text-bright border-text-bright"
              : "bg-bg-surface border-border"
          }`}
        >
          <span
            className={`absolute top-[2px] w-[11px] h-[11px] rounded-full transition-all ${
              enabled
                ? "left-[17px] bg-bg-canvas"
                : "left-[2px] bg-text-muted-2"
            }`}
          />
        </button>
      )}
    </div>
  );
}
