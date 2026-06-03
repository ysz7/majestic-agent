import { useEffect, useRef, useState, useCallback, useMemo } from "react";
import type { Node, Edge } from "@xyflow/react";
import { wsClient } from "@shared/ws/client";
import type { WsEvent } from "@shared/api/types";
import type { ReActNodeData, ReActStepType } from "../ui/ReActNode";

const MAX_STEPS = 5;
const FADE_DELAY_MS   = 3000;
const REMOVE_DELAY_MS = 3600;

const REACT_X       = 820;
const REACT_Y_START = 60;
const REACT_Y_GAP   = 80;

interface ReActStep {
  id:       string;
  stepType: ReActStepType;
  content:  string;
  fading:   boolean;
}

let _seq = 0;

function mapStepType(type: string): ReActStepType | null {
  if (type === "REASON")    return "REASON";
  if (type === "TOOL_CALL") return "TOOL_CALL";
  if (type === "OBSERVE")   return "OBSERVE";
  return null;
}

export function useReActNodes(activeProfile: string | null): {
  nodes: Node[];
  edges: Edge[];
} {
  const [steps, setSteps] = useState<ReActStep[]>([]);
  const fadeTimer   = useRef<ReturnType<typeof setTimeout> | null>(null);
  const removeTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const clearTimers = useCallback(() => {
    if (fadeTimer.current)   { clearTimeout(fadeTimer.current);   fadeTimer.current   = null; }
    if (removeTimer.current) { clearTimeout(removeTimer.current); removeTimer.current = null; }
  }, []);

  const scheduleRemoval = useCallback(() => {
    clearTimers();
    fadeTimer.current = setTimeout(() => {
      setSteps((prev) => prev.map((s) => ({ ...s, fading: true })));
      removeTimer.current = setTimeout(() => setSteps([]), REMOVE_DELAY_MS - FADE_DELAY_MS);
    }, FADE_DELAY_MS);
  }, [clearTimers]);

  useEffect(() => {
    const unsub = wsClient.on((e: WsEvent) => {
      if (e.type === "step") {
        const stepType = mapStepType(e.step);
        if (!stepType) return;
        clearTimers();
        const id = `react-${_seq++}`;
        setSteps((prev) => [
          ...prev.slice(-(MAX_STEPS - 1)),
          { id, stepType, content: e.content.slice(0, 80), fading: false },
        ]);
      }
      if (e.type === "done" || e.type === "error") {
        scheduleRemoval();
      }
    });
    return () => { unsub(); clearTimers(); };
  }, [clearTimers, scheduleRemoval]);

  // Memoize so NodesPage doesn't re-render on every call
  const nodes = useMemo<Node[]>(
    () =>
      steps.map((step, i) => ({
        id:        step.id,
        type:      "reactNode",
        position:  { x: REACT_X, y: REACT_Y_START + i * REACT_Y_GAP },
        draggable: true,
        data: {
          stepType: step.stepType,
          content:  step.content,
          active:   i === steps.length - 1 && !step.fading,
          fading:   step.fading,
        } satisfies ReActNodeData,
      })),
    [steps],
  );

  const edges = useMemo<Edge[]>(() => {
    const result: Edge[] = [];
    if (activeProfile && steps.length > 0) {
      result.push({
        id:       "e-react-agent",
        source:   `agent-${activeProfile}`,
        target:   steps[0].id,
        animated: !steps[0].fading,
        style:    { stroke: "rgba(167,139,250,0.3)", strokeWidth: 1, strokeDasharray: "4 3" },
      });
    }
    for (let i = 0; i < steps.length - 1; i++) {
      result.push({
        id:       `e-react-${i}`,
        source:   steps[i].id,
        target:   steps[i + 1].id,
        animated: !steps[i + 1].fading,
        style:    { stroke: "rgba(167,139,250,0.2)", strokeWidth: 1 },
      });
    }
    return result;
  }, [steps, activeProfile]);

  return { nodes, edges };
}
