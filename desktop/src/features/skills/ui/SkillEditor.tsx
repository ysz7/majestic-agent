import { useState, useRef } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { skillsApi, tasksApi } from "@shared/api/client";
import { Button } from "@shared/ui-kit";
import { FlaskConical, Pencil, Trash2, Plus, X, Check, Loader2 } from "lucide-react";
import type { Skill } from "@shared/api/types";

interface Props {
  profile: string;
}

function toYaml(s: Skill): string {
  return [
    `name: ${s.name}`,
    `description: ${String(s.description ?? "")}`,
    `triggers:`,
    ...(s.triggers ?? []).map((t) => `  - ${t}`),
    `steps:`,
    ...(s.steps ?? []).map((st) => `  - ${st}`),
  ].join("\n");
}

function parseYaml(text: string): Record<string, unknown> {
  const result: Record<string, unknown> = {};
  let listKey: string | null = null;

  for (const line of text.split("\n")) {
    const item = line.match(/^ {2}- (.+)/);
    if (item && listKey) {
      (result[listKey] as string[]).push(item[1]);
      continue;
    }
    const kv = line.match(/^(\w+):\s*(.*)/);
    if (kv) {
      const [, key, val] = kv;
      if (val === "") {
        result[key] = [];
        listKey = key;
      } else {
        result[key] = val;
        listKey = null;
      }
    }
  }
  return result;
}

const INITIAL_YAML =
  "name: my_skill\ndescription: \ntriggers:\n  - keyword\nsteps:\n  - Step 1";

// ── Test panel ────────────────────────────────────────────────────────────────

interface TestPanelProps {
  skill: Skill;
  onClose: () => void;
}

type TestState = "idle" | "running" | "done" | "error";

function TestPanel({ skill, onClose }: TestPanelProps) {
  const firstTrigger = (skill.triggers as string[] | undefined)?.[0] ?? "";
  const [trigger, setTrigger] = useState(firstTrigger);
  const [state,   setState]   = useState<TestState>("idle");
  const [result,  setResult]  = useState("");
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const stop = () => {
    if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null; }
  };

  const run = async () => {
    if (!trigger.trim() || state === "running") return;
    setState("running");
    setResult("");
    stop();

    let taskId: string;
    try {
      const res = await tasksApi.submit(trigger.trim());
      taskId = res.task_id;
    } catch (e) {
      setState("error");
      setResult(`Could not submit task: ${(e as Error).message}`);
      return;
    }

    let waited = 0;
    pollRef.current = setInterval(async () => {
      waited += 2;
      if (waited > 60) {
        stop();
        setState("error");
        setResult("Timeout — agent did not respond in 60 s");
        return;
      }
      try {
        const s = await tasksApi.status(taskId);
        if (s.status === "done" || s.result) {
          stop();
          setState("done");
          setResult(s.result ?? "");
        } else if (s.status === "error") {
          stop();
          setState("error");
          setResult(s.error ?? "Unknown error");
        }
      } catch {
        // transient error — keep polling
      }
    }, 2000);
  };

  // cleanup on unmount
  const handleClose = () => { stop(); onClose(); };

  return (
    <div className="border border-border-strong rounded-node bg-bg-elevated p-[11px] flex flex-col gap-[8px] mt-[4px]">
      <div className="flex items-center justify-between">
        <span className="text-xs text-text-sub flex items-center gap-[5px]">
          <FlaskConical size={11} className="text-text-muted-2" />
          Test: <span className="text-text-muted-2">{skill.name}</span>
        </span>
        <button onClick={handleClose} className="text-text-muted-3 hover:text-text-sub">
          <X size={11} />
        </button>
      </div>

      {/* Trigger input + quick-fill chips */}
      <div className="flex flex-col gap-[5px]">
        {(skill.triggers as string[] | undefined)?.length ? (
          <div className="flex flex-wrap gap-[4px]">
            {(skill.triggers as string[]).map((t) => (
              <button
                key={t}
                onClick={() => setTrigger(t)}
                className={`px-[6px] py-[2px] text-[10px] rounded-[5px] border transition-colors ${
                  trigger === t
                    ? "bg-bg-selected border-border-strong text-text-sub"
                    : "border-border text-text-muted-3 hover:border-border-strong"
                }`}
              >
                {t}
              </button>
            ))}
          </div>
        ) : null}
        <div className="flex gap-[5px]">
          <input
            value={trigger}
            onChange={(e) => setTrigger(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && run()}
            placeholder="Enter trigger phrase…"
            className="flex-1 border border-border rounded-control bg-bg-surface text-xs text-text-dim px-[9px] py-[7px] focus:outline-none focus:border-border-strong"
          />
          <Button
            size="sm"
            variant="cta"
            onClick={run}
            disabled={!trigger.trim() || state === "running"}
          >
            {state === "running" ? <Loader2 size={11} className="animate-spin" /> : "Send"}
          </Button>
        </div>
      </div>

      {/* Result */}
      {(state === "done" || state === "error") && (
        <div
          className={`rounded-control border px-[10px] py-[8px] text-xs leading-[1.5] font-mono whitespace-pre-wrap ${
            state === "error"
              ? "border-red-400/30 bg-[rgba(248,113,113,0.07)] text-red-300"
              : "border-border bg-bg-surface text-text-dim"
          }`}
        >
          {result || "(empty response)"}
        </div>
      )}

      {state === "running" && (
        <div className="text-xs text-text-muted-3 flex items-center gap-[6px]">
          <Loader2 size={11} className="animate-spin" /> Waiting for agent…
        </div>
      )}
    </div>
  );
}

// ── Main component ────────────────────────────────────────────────────────────

export function SkillEditor({ profile }: Props) {
  const qc = useQueryClient();
  const [editingFile, setEditingFile] = useState<string | null>(null);
  const [testingFile, setTestingFile] = useState<string | null>(null);
  const [creating,    setCreating]    = useState(false);
  const [yaml,        setYaml]        = useState("");

  const { data, isLoading } = useQuery({
    queryKey: ["skills", profile],
    queryFn:  () => skillsApi.list(profile),
  });

  const update = useMutation({
    mutationFn: ({ name, body }: { name: string; body: Record<string, unknown> }) =>
      skillsApi.update(profile, name, body),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["skills", profile] }); setEditingFile(null); },
  });

  const create = useMutation({
    mutationFn: (body: Record<string, unknown>) => skillsApi.create(profile, body),
    onSuccess:  () => { qc.invalidateQueries({ queryKey: ["skills", profile] }); setCreating(false); },
  });

  const remove = useMutation({
    mutationFn: (name: string) => skillsApi.remove(profile, name),
    onSuccess:  () => qc.invalidateQueries({ queryKey: ["skills", profile] }),
  });

  const skills = data?.skills ?? [];

  return (
    <div className="flex flex-col gap-[10px] h-full overflow-hidden">
      <div className="flex items-center justify-between flex-shrink-0">
        <span className="text-2xs text-text-muted-3 uppercase tracking-[1.2px] font-semibold">Skills</span>
        <Button
          size="sm"
          variant="cta"
          onClick={() => { setYaml(INITIAL_YAML); setCreating(true); }}
        >
          <Plus size={10} className="mr-1" />New
        </Button>
      </div>

      {/* create form */}
      {creating && (
        <div className="border border-border-strong rounded-node bg-bg-elevated p-[11px] flex flex-col gap-[7px] flex-shrink-0">
          <div className="flex items-center justify-between">
            <span className="text-xs text-text-sub">New Skill</span>
            <button onClick={() => setCreating(false)}>
              <X size={11} className="text-text-muted-2" />
            </button>
          </div>
          <textarea
            value={yaml}
            onChange={(e) => setYaml(e.target.value)}
            rows={8}
            className="w-full border border-border rounded-control bg-bg-surface text-xs text-text-dim px-[10px] py-[8px] focus:outline-none focus:border-border-strong font-mono resize-none"
          />
          <div className="flex justify-end gap-[5px]">
            <Button size="sm" variant="default" onClick={() => setCreating(false)}>Cancel</Button>
            <Button
              size="sm"
              variant="cta"
              onClick={() => create.mutate(parseYaml(yaml))}
              disabled={create.isPending}
            >
              <Check size={10} className="mr-1" />Save
            </Button>
          </div>
        </div>
      )}

      {/* list */}
      <div className="flex-1 overflow-y-auto flex flex-col gap-[5px]">
        {isLoading ? (
          <div className="text-xs text-text-muted-2">Loading…</div>
        ) : skills.length === 0 ? (
          <div className="text-xs text-text-muted-2">No skills yet.</div>
        ) : (
          skills.map((skill) => (
            <div key={skill._filename}>
              {editingFile === skill._filename ? (
                /* edit form */
                <div className="border border-border-strong rounded-node bg-bg-elevated p-[11px] flex flex-col gap-[7px]">
                  <div className="flex items-center justify-between">
                    <span className="text-xs text-text-sub">{skill.name}</span>
                    <button onClick={() => setEditingFile(null)}>
                      <X size={11} className="text-text-muted-2" />
                    </button>
                  </div>
                  <textarea
                    value={yaml}
                    onChange={(e) => setYaml(e.target.value)}
                    rows={8}
                    className="w-full border border-border rounded-control bg-bg-surface text-xs text-text-dim px-[10px] py-[8px] focus:outline-none focus:border-border-strong font-mono resize-none"
                  />
                  <div className="flex justify-end gap-[5px]">
                    <Button size="sm" variant="default" onClick={() => setEditingFile(null)}>Cancel</Button>
                    <Button
                      size="sm"
                      variant="cta"
                      onClick={() => update.mutate({ name: skill.name, body: parseYaml(yaml) })}
                      disabled={update.isPending}
                    >
                      <Check size={10} className="mr-1" />Save
                    </Button>
                  </div>
                </div>
              ) : (
                /* row */
                <div className="border border-border rounded-node bg-bg-elevated px-[11px] py-[9px] flex items-start gap-[9px]">
                  <div className="flex-1 min-w-0">
                    <div className="text-xs text-text-sub">{skill.name}</div>
                    {skill.description && (
                      <div className="text-xs text-text-muted-2 mt-[3px] truncate">
                        {String(skill.description)}
                      </div>
                    )}
                    {(skill.triggers as string[] | undefined)?.length ? (
                      <div className="flex gap-[4px] flex-wrap mt-[5px]">
                        {(skill.triggers as string[]).slice(0, 3).map((t) => (
                          <span
                            key={t}
                            className="border border-border rounded-badge bg-bg-elevated px-[6px] py-[3px] text-xs text-text-muted-2"
                          >
                            {t}
                          </span>
                        ))}
                      </div>
                    ) : null}
                  </div>
                  <div className="flex items-center gap-[4px] flex-shrink-0">
                    <button
                      onClick={() => setTestingFile(
                        testingFile === skill._filename ? null : skill._filename,
                      )}
                      title="Test skill"
                      className={`p-[3px] transition-colors ${
                        testingFile === skill._filename
                          ? "text-text-sub"
                          : "text-text-muted-3 hover:text-text-sub"
                      }`}
                    >
                      <FlaskConical size={10} />
                    </button>
                    <button
                      onClick={() => {
                        setTestingFile(null);
                        setEditingFile(skill._filename);
                        setYaml(toYaml(skill));
                      }}
                      className="p-[3px] text-text-muted-3 hover:text-text-sub"
                    >
                      <Pencil size={10} />
                    </button>
                    <button
                      onClick={() => {
                        if (window.confirm(`Delete skill "${skill.name}"?`)) {
                          setTestingFile(null);
                          remove.mutate(skill.name);
                        }
                      }}
                      className="p-[3px] text-text-muted-3 hover:text-red-400"
                    >
                      <Trash2 size={10} />
                    </button>
                  </div>
                </div>
              )}

              {/* Test panel — shown below the row */}
              {testingFile === skill._filename && editingFile !== skill._filename && (
                <TestPanel skill={skill} onClose={() => setTestingFile(null)} />
              )}
            </div>
          ))
        )}
      </div>
    </div>
  );
}
