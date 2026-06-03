import { Bot, Clock, MousePointer, Search, Bell, Globe, Code, FileText, X } from "lucide-react";
import { useCanvasStore } from "@store/canvasStore";

interface PaletteNode {
  type:    string;
  subtype: string;
  label:   string;
  icon:    React.ElementType;
  color:   string;
}

interface PaletteGroup {
  category: string;
  nodes:    PaletteNode[];
}

const PALETTE: PaletteGroup[] = [
  {
    category: "Triggers",
    nodes: [
      { type: "triggerNode", subtype: "manual",   label: "Manual",   icon: MousePointer, color: "#4ade80" },
      { type: "triggerNode", subtype: "cron",     label: "Schedule", icon: Clock,        color: "#4ade80" },
    ],
  },
  {
    category: "Actions",
    nodes: [
      { type: "actionNode", subtype: "research", label: "Research", icon: Search,   color: "#60a5fa" },
      { type: "actionNode", subtype: "prompt",   label: "Prompt",   icon: Bot,      color: "#60a5fa" },
      { type: "actionNode", subtype: "http",     label: "HTTP",     icon: Globe,    color: "#60a5fa" },
      { type: "actionNode", subtype: "python",   label: "Python",   icon: Code,     color: "#60a5fa" },
    ],
  },
  {
    category: "Output",
    nodes: [
      { type: "outputNode", subtype: "notify",   label: "Notify",    icon: Bell,     color: "#c084fc" },
      { type: "outputNode", subtype: "savefile", label: "Save File", icon: FileText, color: "#c084fc" },
      { type: "outputNode", subtype: "agent",    label: "Agent",     icon: Bot,      color: "#c084fc" },
    ],
  },
];

interface NodePaletteProps {
  onClose: () => void;
}

export function NodePalette({ onClose }: NodePaletteProps) {
  const setPendingNode = useCanvasStore((s) => s.setPendingNode);

  const handleSelect = (type: string, subtype: string) => {
    setPendingNode({ type, subtype });
    onClose();
  };

  return (
    <div
      className="flex flex-col gap-[10px] p-3 rounded-[12px] border border-border bg-node-gradient shadow-lg"
      style={{ width: 280 }}
    >
      {/* Header */}
      <div className="flex items-center justify-between">
        <span className="text-[9px] text-text-muted-3 uppercase tracking-[1.4px] font-semibold">
          Add Node
        </span>
        <button
          onClick={onClose}
          className="text-text-faint hover:text-text-sub transition-colors"
        >
          <X size={11} />
        </button>
      </div>

      {/* Groups */}
      {PALETTE.map(({ category, nodes }) => (
        <div key={category}>
          <div className="text-[9px] text-text-muted-3 uppercase tracking-[1.2px] font-semibold mb-[5px]">
            {category}
          </div>
          <div className="grid grid-cols-3 gap-[5px]">
            {nodes.map(({ type, subtype, label, icon: Icon, color }) => (
              <button
                key={subtype}
                onClick={() => handleSelect(type, subtype)}
                className="flex flex-col items-center gap-[5px] px-[6px] py-[8px] rounded-[8px] border border-border hover:border-border-strong bg-bg-elevated hover:bg-bg-active text-xs text-text-dim hover:text-text-sub transition-colors"
              >
                <Icon size={13} style={{ color }} />
                <span className="text-[9px] leading-none">{label}</span>
              </button>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}
