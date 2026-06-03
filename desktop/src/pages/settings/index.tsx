import { useState } from "react";
import { useQuery }  from "@tanstack/react-query";
import { ProfileList }      from "@features/profiles/ui/ProfileList";
import { ProfileForm }      from "@features/profiles/ui/ProfileForm";
import { MemoryViewer }     from "@features/memory/ui/MemoryViewer";
import { SkillEditor }      from "@features/skills/ui/SkillEditor";
import { BudgetPanel }      from "@features/budget/ui/BudgetPanel";
import { AutoLaunchToggle } from "@features/system/ui/AutoLaunchToggle";
import { DataPathInfo }     from "@features/system/ui/DataPathInfo";
import { profilesApi }      from "@shared/api/client";
import { useAgentStore }    from "@store/agentStore";

type MainTab = "profiles" | "memory" | "skills" | "budget" | "system";

const MAIN_TABS: { key: MainTab; label: string }[] = [
  { key: "profiles", label: "Profiles" },
  { key: "memory",   label: "Memory"   },
  { key: "skills",   label: "Skills"   },
  { key: "budget",   label: "Budget"   },
  { key: "system",   label: "System"   },
];

export function SettingsPage() {
  const [tab,         setTab]    = useState<MainTab>("profiles");
  const [editProfile, setEdit]   = useState<string | undefined>(undefined);
  const [creating,    setCreate] = useState(false);

  const activeProfile    = useAgentStore((s) => s.activeProfile);
  const setActiveProfile = useAgentStore((s) => s.setActiveProfile);

  const { data: profilesData } = useQuery({
    queryKey: ["profiles"],
    queryFn:  profilesApi.list,
  });
  const allProfiles = profilesData?.profiles ?? [];
  const selectedProfile = activeProfile ?? allProfiles[0]?.profile ?? null;

  const switchTab = (t: MainTab) => {
    setTab(t);
    setEdit(undefined);
    setCreate(false);
  };

  return (
    <div className="w-full h-full flex flex-col gap-[10px] overflow-hidden py-[2px] pr-[2px]">
      {/* Main tab bar */}
      <div className="flex items-center gap-[2px] flex-shrink-0">
        {MAIN_TABS.map((t) => (
          <button
            key={t.key}
            onClick={() => switchTab(t.key)}
            className={`px-[12px] py-[6px] text-xs rounded-[8px] transition-colors ${
              tab === t.key
                ? "bg-bg-selected text-text-sub border border-border-strong"
                : "text-text-muted-2 hover:text-text-sub"
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {/* Profile selector for non-profile tabs */}
      {tab !== "profiles" && allProfiles.length > 0 && (
        <div className="flex items-center gap-[7px] flex-shrink-0">
          <span className="text-2xs text-text-muted-3 uppercase tracking-[1.2px] font-semibold">
            Profile:
          </span>
          <select
            value={selectedProfile ?? ""}
            onChange={(e) => setActiveProfile(e.target.value)}
            className="border border-border rounded-control bg-bg-surface text-xs text-text-dim px-[9px] py-[6px] focus:outline-none focus:border-border-strong"
          >
            {allProfiles.map((p) => (
              <option key={p.profile} value={p.profile}>
                {p.name} ({p.profile})
              </option>
            ))}
          </select>
        </div>
      )}

      {/* Content */}
      <div className="flex-1 overflow-y-auto overflow-x-hidden">
        {tab === "profiles" && (
          editProfile !== undefined || creating ? (
            <ProfileForm
              profile={editProfile}
              onClose={() => { setEdit(undefined); setCreate(false); }}
            />
          ) : (
            <ProfileList
              onEdit={(p) => setEdit(p)}
              onCreate={() => setCreate(true)}
            />
          )
        )}

        {tab === "memory" && (
          selectedProfile
            ? <MemoryViewer profile={selectedProfile} />
            : <div className="text-xs text-text-muted-2">No profiles. Create one in Profiles tab.</div>
        )}

        {tab === "skills" && (
          selectedProfile
            ? <SkillEditor profile={selectedProfile} />
            : <div className="text-xs text-text-muted-2">No profiles. Create one in Profiles tab.</div>
        )}

        {tab === "budget" && (
          selectedProfile
            ? <BudgetPanel profile={selectedProfile} />
            : <div className="text-xs text-text-muted-2">No profiles. Create one in Profiles tab.</div>
        )}

        {tab === "system" && (
          <div className="flex flex-col gap-[14px]">
            <div className="text-2xs text-text-muted-3 uppercase tracking-[1.2px] font-semibold">
              System
            </div>
            <AutoLaunchToggle />
            <DataPathInfo />
          </div>
        )}
      </div>
    </div>
  );
}
