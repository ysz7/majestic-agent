import { useState, useRef, useEffect } from "react";
import { Outlet, useNavigate, useLocation } from "react-router-dom";
import { Sidebar }      from "@widgets/sidebar";
import { Topbar }       from "@widgets/topbar";
import { ChatPanel }    from "@widgets/chat";
import { NodePalette }  from "@widgets/palette";
import { cn }           from "@shared/lib/cn";
import {
  LayoutDashboard,
  Settings,
  PlusSquare,
} from "lucide-react";

export function AppShell() {
  const navigate  = useNavigate();
  const location  = useLocation();
  const [paletteOpen, setPaletteOpen] = useState(false);
  const paletteRef = useRef<HTMLDivElement>(null);

  const isCanvas = location.pathname.startsWith("/nodes");

  // Close palette on outside click
  useEffect(() => {
    if (!paletteOpen) return;
    function handle(e: MouseEvent) {
      if (paletteRef.current && !paletteRef.current.contains(e.target as Node)) {
        setPaletteOpen(false);
      }
    }
    document.addEventListener("mousedown", handle);
    return () => document.removeEventListener("mousedown", handle);
  }, [paletteOpen]);

  return (
    <div className="fixed inset-0 flex items-center justify-center bg-bg-root">
      <div
        className="relative overflow-hidden bg-bg-canvas"
        style={{ width: "100vw", height: "100vh" }}
      >
        <Sidebar />
        <Topbar />

        {/* Chat panel — right side, full height below topbar */}
        <div className="absolute right-3 top-11 bottom-3 z-[5] flex flex-col" style={{ width: 258 }}>
          <ChatPanel />
        </div>

        {/* Main content area */}
        <div
          className="absolute inset-0 overflow-hidden"
          style={{ left: 154, right: 273, top: 12, bottom: 0 }}
        >
          <Outlet />
        </div>

        {/* Node palette popover — floats above toolbar, anchored to Nodes button */}
        {paletteOpen && isCanvas && (
          <div
            ref={paletteRef}
            className="absolute bottom-[64px] left-1/2 -translate-x-1/2 z-[10]"
          >
            <NodePalette onClose={() => setPaletteOpen(false)} />
          </div>
        )}

        {/* Bottom toolbar */}
        <div
          className="absolute bottom-[18px] left-1/2 -translate-x-1/2
                     flex items-center
                     border border-border-strong rounded-toolbar
                     bg-toolbar-gradient
                     px-2 py-[9px] z-[7]"
        >
          {/* Canvas */}
          {(["Canvas|/nodes", "Config|/settings"] as const).map((item, i) => {
            const [label, path] = item.split("|") as [string, string];
            const isActive = location.pathname.startsWith(path);
            const Icon = i === 0 ? LayoutDashboard : Settings;
            return (
              <button
                key={label}
                onClick={() => navigate(path)}
                className={cn(
                  "flex flex-col items-center gap-[5px] px-[11px] py-[5px] text-sm rounded-control transition-colors",
                  isActive ? "text-text-sub" : "text-text-dim hover:text-text-sub",
                )}
                style={i > 0 ? { borderLeft: "1px solid rgba(255,255,255,0.08)" } : undefined}
              >
                <Icon size={14} className={isActive ? "text-text-sub" : "text-text-faint"} />
                {label}
              </button>
            );
          })}

          {/* Add Node button — only on canvas page */}
          {isCanvas && (
            <button
              onClick={() => setPaletteOpen((v) => !v)}
              className={cn(
                "flex flex-col items-center gap-[5px] px-[11px] py-[5px] text-sm rounded-control transition-colors",
                paletteOpen
                  ? "text-text-sub"
                  : "text-text-dim hover:text-text-sub",
              )}
              style={{ borderLeft: "1px solid rgba(255,255,255,0.08)" }}
            >
              <PlusSquare
                size={14}
                className={paletteOpen ? "text-text-sub" : "text-text-faint"}
              />
              Nodes
            </button>
          )}
        </div>

        {/* Active profile indicator — bottom left */}
        <div
          className="absolute left-3 bottom-[18px] z-[6]
                     flex items-center gap-[10px]
                     border border-border rounded-tw-card
                     bg-node-gradient
                     px-[13px] py-[9px] pl-[9px]"
        >
          <div
            className="w-7 h-7 rounded-avatar bg-bg-active
                       flex items-center justify-center
                       text-base font-bold text-text-sub"
          >
            M
          </div>
          <div>
            <div className="text-md text-text-sub">Majestic</div>
            <div className="flex items-center gap-[5px] text-xs text-text-muted-2 mt-[2px]">
              <span className="w-[5px] h-[5px] rounded-full bg-text-bright" />
              foreground
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
