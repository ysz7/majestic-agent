import { Outlet, useNavigate, useLocation } from "react-router-dom";
import { Sidebar }          from "@widgets/sidebar";
import { Topbar }           from "@widgets/topbar";
import { ActiveAgentCard }  from "@widgets/rpanel/ActiveAgentCard";
import { cn }               from "@shared/lib/cn";
import {
  LayoutDashboard,
  Search,
  BrainCircuit,
  Layers,
  Settings,
} from "lucide-react";

const TOOLBAR_ITEMS = [
  { icon: LayoutDashboard, label: "Canvas",   path: "/nodes"    },
  { icon: Search,          label: "Research", path: null        },
  { icon: BrainCircuit,    label: "Pains",    path: null        },
  { icon: Layers,          label: "Ideas",    path: null        },
  { icon: Settings,        label: "Config",   path: "/settings" },
];

export function AppShell() {
  const navigate = useNavigate();
  const location = useLocation();

  return (
    <div className="fixed inset-0 flex items-center justify-center bg-bg-root">
      <div
        className="relative overflow-hidden bg-bg-canvas"
        style={{
          width: "100vw",
          height: "100vh",
          border: "1px solid rgba(255,255,255,0.16)",
          borderRadius: "22px",
        }}
      >
        <Sidebar />
        <Topbar />

        {/* Right panel */}
        <div className="absolute right-3 top-11 w-[162px] z-[5] flex flex-col gap-[7px]">
          <ActiveAgentCard />
        </div>

        {/* Main content area */}
        <div
          className="absolute inset-0 overflow-hidden"
          style={{ left: 154, right: 182, top: 12, bottom: 64 }}
        >
          <Outlet />
        </div>

        {/* Bottom toolbar */}
        <div
          className="absolute bottom-[18px] left-1/2 -translate-x-1/2
                     flex items-center
                     border border-border-strong rounded-toolbar
                     bg-toolbar-gradient
                     px-2 py-[9px] z-[7]"
        >
          {TOOLBAR_ITEMS.map(({ icon: Icon, label, path }, i) => {
            const isActive = path !== null && location.pathname.startsWith(path);
            return (
              <button
                key={label}
                onClick={() => path && navigate(path)}
                disabled={path === null}
                className={cn(
                  "flex flex-col items-center gap-[5px] px-[11px] py-[5px] text-sm rounded-control transition-colors",
                  isActive  ? "text-text-sub"   : "text-text-dim hover:text-text-sub",
                  path === null && "opacity-40 cursor-default",
                )}
                style={i > 0 ? { borderLeft: "1px solid rgba(255,255,255,0.08)" } : undefined}
              >
                <Icon
                  size={14}
                  className={isActive ? "text-text-sub" : "text-text-faint"}
                />
                {label}
              </button>
            );
          })}
        </div>

        {/* TW card — bottom left (active profile indicator) */}
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
