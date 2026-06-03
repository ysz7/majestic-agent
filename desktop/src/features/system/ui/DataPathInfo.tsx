import { useEffect, useState } from "react";
import { FolderOpen } from "lucide-react";
import { getDataDir, isTauri } from "@shared/lib/tauri";

export function DataPathInfo() {
  const [path, setPath] = useState("");
  const available = isTauri();

  useEffect(() => {
    if (!available) return;
    getDataDir().then(setPath);
  }, [available]);

  const openFolder = async () => {
    if (!path) return;
    try {
      // Use Tauri shell plugin to open folder in OS file manager
      const { open } = await import("@tauri-apps/plugin-shell");
      await open(path);
    } catch {
      // graceful fallback — just show path
    }
  };

  return (
    <div className="flex flex-col gap-[5px]">
      <div className="text-2xs text-text-muted-3 uppercase tracking-[1.2px] font-semibold">
        Data Directory
      </div>
      <div className="border border-border rounded-node bg-bg-elevated px-[11px] py-[9px] flex items-center gap-[8px]">
        <div className="flex-1 min-w-0">
          <div className="text-xs text-text-dim font-mono truncate">
            {available ? (path || "Detecting…") : "Only available in desktop app"}
          </div>
          <div className="text-xs text-text-muted-3 mt-[2px]">
            Profiles, data and settings are stored here when installed
          </div>
        </div>
        {available && path && (
          <button
            onClick={openFolder}
            title="Open in file manager"
            className="flex-shrink-0 text-text-muted-3 hover:text-text-sub transition-colors"
          >
            <FolderOpen size={13} />
          </button>
        )}
      </div>
    </div>
  );
}
