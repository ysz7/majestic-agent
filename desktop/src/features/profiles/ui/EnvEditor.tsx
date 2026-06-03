import { useState, useEffect } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Eye, EyeOff, Plus, Trash2 } from "lucide-react";
import { profilesApi } from "@shared/api/client";
import type { EnvEntry } from "@shared/api/types";
import { Button } from "@shared/ui-kit";

interface Props {
  profile: string;
}

const _SENSITIVE = ["KEY", "SECRET", "TOKEN", "PASSWORD", "PASS", "PWD"];
const isSensitive = (key: string) =>
  _SENSITIVE.some((w) => key.toUpperCase().includes(w));

export function EnvEditor({ profile }: Props) {
  const qc = useQueryClient();
  const [rows, setRows]       = useState<EnvEntry[]>([]);
  const [revealed, setReveal] = useState<Set<number>>(new Set());
  const [dirty, setDirty]     = useState(false);

  const { data, isLoading } = useQuery({
    queryKey: ["env", profile],
    queryFn:  () => profilesApi.getEnv(profile),
  });

  useEffect(() => {
    if (!data) return;
    setRows(data.entries.map((e) => ({ ...e })));
    setReveal(new Set());
    setDirty(false);
  }, [data]);

  const save = useMutation({
    mutationFn: () => profilesApi.updateEnv(profile, rows),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["env", profile] });
      setDirty(false);
    },
  });

  const update = (i: number, field: "key" | "value", val: string) => {
    setRows((prev) => prev.map((r, idx) => idx === i ? { ...r, [field]: val, masked: isSensitive(field === "key" ? val : r.key) } : r));
    setDirty(true);
  };

  const addRow = () => {
    setRows((prev) => [...prev, { key: "", value: "", masked: false }]);
    setDirty(true);
  };

  const removeRow = (i: number) => {
    setRows((prev) => prev.filter((_, idx) => idx !== i));
    setReveal((prev) => { const s = new Set(prev); s.delete(i); return s; });
    setDirty(true);
  };

  const toggleReveal = (i: number) =>
    setReveal((prev) => {
      const s = new Set(prev);
      s.has(i) ? s.delete(i) : s.add(i);
      return s;
    });

  if (isLoading) return <div className="text-xs text-text-muted-2">Loading…</div>;

  return (
    <div className="flex flex-col gap-[10px]">
      <div className="text-2xs text-text-muted-3 uppercase tracking-[1.2px] font-semibold">
        Environment Variables
      </div>

      <div className="flex flex-col gap-[5px]">
        {/* Header row */}
        <div className="grid grid-cols-[1fr_1fr_28px] gap-[5px]">
          <span className="text-2xs text-text-muted-3 uppercase tracking-[1.2px] font-semibold px-[2px]">Key</span>
          <span className="text-2xs text-text-muted-3 uppercase tracking-[1.2px] font-semibold px-[2px]">Value</span>
          <span />
        </div>

        {rows.length === 0 && (
          <div className="text-xs text-text-muted-3 py-[6px]">No variables. Add one below.</div>
        )}

        {rows.map((row, i) => {
          const isHidden = row.masked && !revealed.has(i);
          return (
            <div key={i} className="grid grid-cols-[1fr_1fr_28px] gap-[5px] items-center">
              <input
                value={row.key}
                onChange={(e) => update(i, "key", e.target.value)}
                placeholder="VAR_NAME"
                className="border border-border rounded-control bg-bg-surface text-xs text-text-dim px-[9px] py-[7px] focus:outline-none focus:border-border-strong font-mono w-full"
              />
              <div className="relative flex items-center">
                <input
                  value={row.value}
                  onChange={(e) => update(i, "value", e.target.value)}
                  type={isHidden ? "password" : "text"}
                  placeholder="value"
                  className="border border-border rounded-control bg-bg-surface text-xs text-text-dim px-[9px] py-[7px] pr-[28px] focus:outline-none focus:border-border-strong font-mono w-full"
                />
                {row.masked && (
                  <button
                    onClick={() => toggleReveal(i)}
                    className="absolute right-[7px] text-text-muted-3 hover:text-text-sub"
                  >
                    {revealed.has(i) ? <EyeOff size={12} /> : <Eye size={12} />}
                  </button>
                )}
              </div>
              <button
                onClick={() => removeRow(i)}
                className="flex items-center justify-center text-text-muted-3 hover:text-red-400 transition-colors"
              >
                <Trash2 size={13} />
              </button>
            </div>
          );
        })}
      </div>

      <div className="flex items-center justify-between pt-[2px]">
        <button
          onClick={addRow}
          className="flex items-center gap-[5px] text-xs text-text-muted-2 hover:text-text-sub"
        >
          <Plus size={12} /> Add variable
        </button>
        <Button
          variant="cta"
          size="sm"
          onClick={() => save.mutate()}
          disabled={!dirty || save.isPending}
        >
          {save.isPending ? "Saving…" : "Save"}
        </Button>
      </div>

      {save.error && (
        <div className="text-xs text-red-400">{(save.error as Error).message}</div>
      )}

      <div className="text-2xs text-text-muted-3 leading-[1.5] border-t border-border pt-[8px] mt-[2px]">
        Changes are written to <span className="font-mono text-text-dim">profiles/{profile}/.env</span>
        . The agent must be restarted to pick up new values.
      </div>
    </div>
  );
}
