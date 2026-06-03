import type { Node } from "@xyflow/react";
import { X, Trash2 } from "lucide-react";

export const WORKFLOW_TYPES = new Set(["triggerNode", "actionNode", "outputNode"]);

type FieldType = "text" | "textarea" | "select";

interface Field {
  key:          string;
  label:        string;
  type:         FieldType;
  placeholder?: string;
  options?:     string[];
}

// Field schema keyed by `${type}:${subtype}`
const FIELDS: Record<string, Field[]> = {
  "triggerNode:manual": [
    { key: "label", label: "Name", type: "text", placeholder: "Manual trigger" },
  ],
  "triggerNode:cron": [
    { key: "label",    label: "Name",     type: "text", placeholder: "Morning run" },
    { key: "schedule", label: "Schedule (cron)", type: "text", placeholder: "0 9 * * *" },
  ],
  "actionNode:research": [
    { key: "query", label: "Query", type: "textarea", placeholder: "AI news today" },
  ],
  "actionNode:prompt": [
    { key: "prompt", label: "Prompt", type: "textarea", placeholder: "Summarize {prev_output}" },
    { key: "model",  label: "Model override (optional)", type: "text", placeholder: "anthropic/claude-sonnet-4-5" },
  ],
  "actionNode:http": [
    { key: "method", label: "Method", type: "select", options: ["GET", "POST", "PUT", "DELETE"] },
    { key: "url",    label: "URL",    type: "text",   placeholder: "https://api.example.com/data" },
    { key: "body",   label: "Body (optional)", type: "textarea", placeholder: "{ \"key\": \"value\" }" },
  ],
  "actionNode:python": [
    { key: "code", label: "Python code", type: "textarea", placeholder: "print({prev_output})" },
  ],
  "outputNode:notify": [
    { key: "title", label: "Title", type: "text",     placeholder: "Done" },
    { key: "body",  label: "Body",  type: "textarea", placeholder: "{prev_output}" },
  ],
  "outputNode:savefile": [
    { key: "filename", label: "Filename", type: "text",   placeholder: "output/{date}.md" },
    { key: "mode",     label: "Mode",     type: "select", options: ["overwrite", "append"] },
  ],
  "outputNode:agent": [
    { key: "target", label: "Target agent", type: "text", placeholder: "writer" },
  ],
};

interface NodeConfigPanelProps {
  node:      Node;
  onChange:  (key: string, value: string) => void;
  onDelete:  () => void;
  onClose:   () => void;
}

export function NodeConfigPanel({ node, onChange, onDelete, onClose }: NodeConfigPanelProps) {
  const subtype = String(node.data?.subtype ?? "");
  const fields  = FIELDS[`${node.type}:${subtype}`] ?? [];

  const heading = subtype
    ? subtype.charAt(0).toUpperCase() + subtype.slice(1)
    : node.type ?? "Node";

  return (
    <div
      className="absolute top-3 right-3 z-[8] flex flex-col gap-[10px]
                 rounded-[12px] border border-border-strong bg-node-gradient
                 px-3 py-3 shadow-lg"
      style={{ width: 230 }}
      onClick={(e) => e.stopPropagation()}
    >
      {/* Header */}
      <div className="flex items-center justify-between">
        <span className="text-base text-text-sub">{heading}</span>
        <button onClick={onClose} className="text-text-faint hover:text-text-sub transition-colors">
          <X size={12} />
        </button>
      </div>

      {/* Fields */}
      {fields.length === 0 ? (
        <div className="text-xs text-text-muted-3">No settings for this node.</div>
      ) : (
        fields.map((f) => {
          const value = String(node.data?.[f.key] ?? "");
          return (
            <div key={f.key} className="flex flex-col gap-[4px]">
              <label className="text-[9px] text-text-muted-3 uppercase tracking-[1px] font-semibold">
                {f.label}
              </label>
              {f.type === "textarea" ? (
                <textarea
                  value={value}
                  onChange={(e) => onChange(f.key, e.target.value)}
                  placeholder={f.placeholder}
                  rows={3}
                  className="bg-bg-elevated border border-border rounded-[7px] px-[8px] py-[6px] text-xs text-text-sub placeholder:text-text-muted-3 outline-none focus:border-border-strong resize-none font-mono"
                />
              ) : f.type === "select" ? (
                <select
                  value={value || f.options?.[0]}
                  onChange={(e) => onChange(f.key, e.target.value)}
                  className="bg-bg-elevated border border-border rounded-[7px] px-[8px] py-[6px] text-xs text-text-sub outline-none focus:border-border-strong"
                >
                  {f.options?.map((opt) => (
                    <option key={opt} value={opt}>{opt}</option>
                  ))}
                </select>
              ) : (
                <input
                  value={value}
                  onChange={(e) => onChange(f.key, e.target.value)}
                  placeholder={f.placeholder}
                  className="bg-bg-elevated border border-border rounded-[7px] px-[8px] py-[6px] text-xs text-text-sub placeholder:text-text-muted-3 outline-none focus:border-border-strong"
                />
              )}
            </div>
          );
        })
      )}

      {/* Variable hint */}
      {fields.length > 0 && (
        <div className="text-[9px] text-text-muted-3 leading-[1.5] border-t border-border pt-[7px]">
          Variables: <span className="font-mono text-text-muted-2">{"{prev_output}"}</span>{" "}
          <span className="font-mono text-text-muted-2">{"{date}"}</span>{" "}
          <span className="font-mono text-text-muted-2">{"{agent_name}"}</span>
        </div>
      )}

      {/* Delete */}
      <button
        onClick={onDelete}
        className="flex items-center justify-center gap-[5px] text-xs text-text-muted-2 hover:text-red-400 border border-border hover:border-red-400/40 rounded-[7px] py-[6px] transition-colors"
      >
        <Trash2 size={10} /> Delete node
      </button>
    </div>
  );
}
