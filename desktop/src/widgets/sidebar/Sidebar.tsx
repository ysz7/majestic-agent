import { NavLink } from "react-router-dom";
import { cn } from "@shared/lib/cn";
import {
  LayoutDashboard,
  Settings,
  BrainCircuit,
  BookOpen,
  Users,
  Folder,
} from "lucide-react";

interface NavItem {
  to: string;
  icon: React.ElementType;
  label: string;
}

const WORKSPACE: NavItem[] = [
  { to: "/nodes",    icon: LayoutDashboard, label: "Canvas"   },
];

const INTELLIGENCE: NavItem[] = [
  { to: "/research", icon: BookOpen,      label: "Research"  },
  { to: "/pains",    icon: BrainCircuit,  label: "Pains"     },
  { to: "/ideas",    icon: Folder,        label: "Ideas"     },
];

const SYSTEM: NavItem[] = [
  { to: "/agents",   icon: Users,         label: "Agents"    },
  { to: "/settings", icon: Settings,      label: "Settings"  },
];

function NavGroup({ label, items }: { label: string; items: NavItem[] }) {
  return (
    <div className="mb-[14px]">
      <div className="text-2xs font-semibold uppercase tracking-[1.4px] text-text-muted-3 mb-2">
        {label}
      </div>
      {items.map(({ to, icon: Icon, label: text }) => (
        <NavLink
          key={to}
          to={to}
          className={({ isActive }) =>
            cn(
              "flex items-center gap-2 text-base text-text-dim py-[5px] cursor-pointer",
              isActive &&
                "bg-active-gradient border border-border-strong rounded-avatar px-2 py-[6px] -mx-[2px] text-text-bright",
            )
          }
        >
          {({ isActive }) => (
            <>
              <Icon size={12} className={isActive ? "text-text-bright" : "text-text-dim"} />
              {text}
            </>
          )}
        </NavLink>
      ))}
    </div>
  );
}

export function Sidebar() {
  return (
    <aside
      className="absolute left-3 top-3 w-[130px] h-[500px]
                 border border-border rounded-sidebar
                 bg-sidebar-gradient
                 px-[13px] py-4 z-[6]
                 flex flex-col"
    >
      {/* Brand */}
      <div className="text-brand mb-[18px]">
        <b className="font-bold">Majestic</b>
        <span className="font-normal text-text-faint"> Agent</span>
      </div>

      <NavGroup label="Workspace"   items={WORKSPACE}    />
      <NavGroup label="Intelligence" items={INTELLIGENCE} />

      <div className="flex-1" />

      <NavGroup label="System" items={SYSTEM} />
    </aside>
  );
}
