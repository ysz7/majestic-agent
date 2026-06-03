import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { memoryApi } from "@shared/api/client";
import { Trash2, Search } from "lucide-react";

type Tab = "episodic" | "lessons" | "profile";

interface Props {
  profile: string;
}

const TABS: { key: Tab; label: string }[] = [
  { key: "episodic", label: "Tasks"        },
  { key: "lessons",  label: "Lessons"      },
  { key: "profile",  label: "User Profile" },
];

export function MemoryViewer({ profile }: Props) {
  const qc = useQueryClient();
  const [tab, setTab] = useState<Tab>("episodic");
  const [search, setSearch] = useState("");

  const episodic = useQuery({
    queryKey: ["mem-episodic", profile, search],
    queryFn:  () => memoryApi.episodic(profile, search || undefined),
    enabled:  tab === "episodic",
  });

  const lessons = useQuery({
    queryKey: ["mem-lessons", profile, search],
    queryFn:  () => memoryApi.lessons(profile, search || undefined),
    enabled:  tab === "lessons",
  });

  const userProfile = useQuery({
    queryKey: ["mem-user", profile],
    queryFn:  () => memoryApi.userProfile(profile),
    enabled:  tab === "profile",
  });

  const delEpisodic = useMutation({
    mutationFn: (id: number) => memoryApi.deleteEpisodic(profile, id),
    onSuccess:  () => qc.invalidateQueries({ queryKey: ["mem-episodic", profile] }),
  });

  const delLesson = useMutation({
    mutationFn: (id: number) => memoryApi.deleteLesson(profile, id),
    onSuccess:  () => qc.invalidateQueries({ queryKey: ["mem-lessons", profile] }),
  });

  const delProfileKey = useMutation({
    mutationFn: (key: string) => memoryApi.deleteProfileKey(profile, key),
    onSuccess:  () => qc.invalidateQueries({ queryKey: ["mem-user", profile] }),
  });

  return (
    <div className="flex flex-col gap-[10px] h-full overflow-hidden">
      {/* tabs */}
      <div className="flex items-center gap-[2px] flex-shrink-0">
        {TABS.map((t) => (
          <button
            key={t.key}
            onClick={() => setTab(t.key)}
            className={`px-[10px] py-[5px] text-xs rounded-[7px] transition-colors ${
              tab === t.key
                ? "bg-bg-selected text-text-sub border border-border-strong"
                : "text-text-muted-2 hover:text-text-sub"
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {/* search */}
      {tab !== "profile" && (
        <div className="relative flex-shrink-0">
          <Search size={10} className="absolute left-[10px] top-1/2 -translate-y-1/2 text-text-muted-2" />
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search…"
            className="w-full border border-border rounded-control bg-bg-surface text-xs text-text-dim pl-[28px] pr-[11px] py-[8px] focus:outline-none focus:border-border-strong placeholder:text-text-muted-3"
          />
        </div>
      )}

      {/* lists */}
      <div className="flex-1 overflow-y-auto flex flex-col gap-[5px]">

        {tab === "episodic" && (
          episodic.isLoading ? (
            <div className="text-xs text-text-muted-2">Loading…</div>
          ) : (episodic.data?.entries ?? []).length === 0 ? (
            <div className="text-xs text-text-muted-2">No task history.</div>
          ) : (
            (episodic.data?.entries ?? []).map((e) => (
              <div
                key={e.id}
                className="border border-border rounded-node bg-bg-elevated px-[11px] py-[9px] flex gap-[9px] items-start"
              >
                <div className="flex-1 min-w-0">
                  <div className="text-xs text-text-dim truncate">{e.task}</div>
                  <div className="flex gap-[8px] mt-[3px] text-xs text-text-muted-2">
                    <span>{e.tokens_used} tok</span>
                    <span>${e.cost.toFixed(4)}</span>
                    <span>{e.duration_s.toFixed(1)}s</span>
                  </div>
                </div>
                <button
                  onClick={() => delEpisodic.mutate(e.id)}
                  className="text-text-muted-3 hover:text-red-400 flex-shrink-0 pt-[2px]"
                >
                  <Trash2 size={10} />
                </button>
              </div>
            ))
          )
        )}

        {tab === "lessons" && (
          lessons.isLoading ? (
            <div className="text-xs text-text-muted-2">Loading…</div>
          ) : (lessons.data?.entries ?? []).length === 0 ? (
            <div className="text-xs text-text-muted-2">No lessons yet.</div>
          ) : (
            (lessons.data?.entries ?? []).map((l) => (
              <div
                key={l.id}
                className="border border-border rounded-node bg-bg-elevated px-[11px] py-[9px] flex gap-[9px] items-start"
              >
                <div className="flex-1 min-w-0">
                  <div className="text-xs text-text-muted-2 mb-[3px]">{l.task_type}</div>
                  <div className="text-xs text-text-dim leading-[1.5]">{l.lesson}</div>
                  <div className="text-xs text-text-muted-3 mt-[3px]">used {l.usage_count}×</div>
                </div>
                <button
                  onClick={() => delLesson.mutate(l.id)}
                  className="text-text-muted-3 hover:text-red-400 flex-shrink-0 pt-[2px]"
                >
                  <Trash2 size={10} />
                </button>
              </div>
            ))
          )
        )}

        {tab === "profile" && (
          userProfile.isLoading ? (
            <div className="text-xs text-text-muted-2">Loading…</div>
          ) : Object.keys(userProfile.data?.profile ?? {}).length === 0 ? (
            <div className="text-xs text-text-muted-2">No user profile data.</div>
          ) : (
            Object.entries(userProfile.data?.profile ?? {}).map(([key, value]) => (
              <div
                key={key}
                className="border border-border rounded-node bg-bg-elevated px-[11px] py-[9px] flex gap-[9px] items-start"
              >
                <div className="flex-1 min-w-0">
                  <div className="text-xs text-text-muted-2 mb-[2px]">{key}</div>
                  <div className="text-xs text-text-dim">{value}</div>
                </div>
                <button
                  onClick={() => delProfileKey.mutate(key)}
                  className="text-text-muted-3 hover:text-red-400 flex-shrink-0 pt-[2px]"
                >
                  <Trash2 size={10} />
                </button>
              </div>
            ))
          )
        )}

      </div>
    </div>
  );
}
