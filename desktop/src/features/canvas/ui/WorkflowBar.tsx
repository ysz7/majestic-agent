import { useState, useEffect } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Save, ChevronDown, Plus, Check, Loader2, Trash2, Play } from "lucide-react";
import { workflowsApi } from "@shared/api/client";
import { wsClient } from "@shared/ws/client";
import type { Workflow, WorkflowNodeDef, WorkflowEdgeDef } from "@shared/api/types";
import { cn } from "@shared/lib/cn";

interface WorkflowBarProps {
  profile:        string | null;
  currentId:      string | null;
  name:           string;
  onNameChange:   (name: string) => void;
  getWorkflow:    () => { nodes: WorkflowNodeDef[]; edges: WorkflowEdgeDef[] };
  onLoad:         (wf: Workflow) => void;
  onNew:          () => void;
  onSaved:        (id: string) => void;
}

export function WorkflowBar({
  profile, currentId, name, onNameChange, getWorkflow, onLoad, onNew, onSaved,
}: WorkflowBarProps) {
  const qc = useQueryClient();
  const [menuOpen, setMenuOpen] = useState(false);
  const [justSaved, setJustSaved] = useState(false);
  const [running, setRunning] = useState(false);

  // Reset the running indicator when the workflow finishes or errors.
  useEffect(() => {
    const off = wsClient.on((event) => {
      if (
        (event.type === "workflow_done" || event.type === "workflow_error") &&
        event.workflow_id === currentId
      ) {
        setRunning(false);
      }
    });
    return off;
  }, [currentId]);

  const { data } = useQuery({
    queryKey: ["workflows", profile],
    queryFn:  () => workflowsApi.list(profile!),
    enabled:  !!profile,
  });
  const workflows = data?.workflows ?? [];

  const save = useMutation({
    mutationFn: () => {
      const { nodes, edges } = getWorkflow();
      const body = { name: name.trim() || "Untitled", nodes, edges };
      return currentId
        ? workflowsApi.update(profile!, currentId, body)
        : workflowsApi.create(profile!, body);
    },
    onSuccess: (res) => {
      qc.invalidateQueries({ queryKey: ["workflows", profile] });
      onSaved(res.workflow.id);
      setJustSaved(true);
      setTimeout(() => setJustSaved(false), 1500);
    },
  });

  const remove = useMutation({
    mutationFn: (id: string) => workflowsApi.remove(profile!, id),
    onSuccess:  () => qc.invalidateQueries({ queryKey: ["workflows", profile] }),
  });

  const runWf = useMutation({
    mutationFn: () => workflowsApi.run(profile!, currentId!),
    onMutate:   () => setRunning(true),
    onError:    () => setRunning(false),
  });

  if (!profile) return null;

  return (
    <div className="absolute top-3 left-3 z-[8] flex items-center gap-[6px]">
      {/* Name input */}
      <input
        value={name}
        onChange={(e) => onNameChange(e.target.value)}
        placeholder="Workflow name"
        className="w-[140px] bg-node-gradient border border-border rounded-[8px] px-[9px] py-[6px] text-xs text-text-sub placeholder:text-text-muted-3 outline-none focus:border-border-strong"
      />

      {/* Save */}
      <button
        onClick={() => save.mutate()}
        disabled={save.isPending}
        className={cn(
          "flex items-center gap-[5px] px-[9px] py-[6px] rounded-[8px] border text-xs transition-colors",
          justSaved
            ? "border-green-400/40 text-green-300"
            : "border-border text-text-dim hover:text-text-sub hover:border-border-strong",
        )}
      >
        {save.isPending
          ? <Loader2 size={11} className="animate-spin" />
          : justSaved
            ? <Check size={11} />
            : <Save size={11} />}
        {justSaved ? "Saved" : "Save"}
      </button>

      {/* Run — only when a saved workflow is loaded */}
      <button
        onClick={() => runWf.mutate()}
        disabled={!currentId || running}
        title={currentId ? "Run workflow" : "Save the workflow first"}
        className={cn(
          "flex items-center gap-[5px] px-[9px] py-[6px] rounded-[8px] border text-xs transition-colors",
          running
            ? "border-green-400/40 text-green-300"
            : "border-border text-text-dim hover:text-text-sub hover:border-border-strong disabled:opacity-40",
        )}
      >
        {running
          ? <Loader2 size={11} className="animate-spin" />
          : <Play size={11} />}
        {running ? "Running" : "Run"}
      </button>

      {/* Load dropdown */}
      <div className="relative">
        <button
          onClick={() => setMenuOpen((v) => !v)}
          className="flex items-center gap-[5px] px-[9px] py-[6px] rounded-[8px] border border-border text-text-dim hover:text-text-sub hover:border-border-strong text-xs transition-colors"
        >
          Load <ChevronDown size={11} />
        </button>
        {menuOpen && (
          <div className="absolute top-[34px] left-0 w-[200px] rounded-[10px] border border-border-strong bg-node-gradient shadow-lg py-[5px] z-[9]">
            <button
              onClick={() => { onNew(); setMenuOpen(false); }}
              className="flex items-center gap-[6px] w-full px-[10px] py-[6px] text-xs text-text-dim hover:text-text-sub hover:bg-bg-active transition-colors"
            >
              <Plus size={11} /> New workflow
            </button>
            {workflows.length > 0 && <div className="h-px bg-border my-[4px]" />}
            {workflows.map((wf) => (
              <div
                key={wf.id}
                className="flex items-center group hover:bg-bg-active transition-colors"
              >
                <button
                  onClick={() => { onLoad(wf); setMenuOpen(false); }}
                  className={cn(
                    "flex-1 text-left px-[10px] py-[6px] text-xs truncate",
                    wf.id === currentId ? "text-text-sub" : "text-text-dim",
                  )}
                >
                  {wf.name}
                </button>
                <button
                  onClick={() => remove.mutate(wf.id)}
                  className="px-[8px] text-text-muted-3 hover:text-red-400 transition-colors"
                  title="Delete"
                >
                  <Trash2 size={10} />
                </button>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
