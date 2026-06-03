import {
  ReactFlow,
  Background,
  BackgroundVariant,
  Controls,
  useNodesState,
  useEdgesState,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { useEffect, useMemo } from "react";
import { nodeTypes }      from "@features/canvas/ui/nodeTypes";
import { useCanvasData }  from "@features/canvas/model/useCanvasData";
import { useReActNodes }  from "@features/canvas/model/useReActNodes";
import { useAgentStore }  from "@store/agentStore";

export function NodesPage() {
  const activeProfile = useAgentStore((s) => s.activeProfile);

  const { nodes: dataNodes, edges: dataEdges, isLoading } = useCanvasData(activeProfile);
  const { nodes: reactNodes, edges: reactEdges }          = useReActNodes(activeProfile);

  // Merge canvas data + live ReAct nodes
  const allNodes = useMemo(
    () => [...dataNodes, ...reactNodes],
    [dataNodes, reactNodes],
  );
  const allEdges = useMemo(
    () => [...dataEdges, ...reactEdges],
    [dataEdges, reactEdges],
  );

  const [nodes, setNodes, onNodesChange] = useNodesState(allNodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState(allEdges);

  // Sync static canvas data (polling)
  useEffect(() => { setNodes(allNodes); }, [allNodes, setNodes]);
  useEffect(() => { setEdges(allEdges); }, [allEdges, setEdges]);

  return (
    <div className="w-full h-full">
      {isLoading ? (
        <div className="w-full h-full flex items-center justify-center">
          <span className="text-xs text-text-muted-2">Loading…</span>
        </div>
      ) : (
        <ReactFlow
          nodes={nodes}
          edges={edges}
          nodeTypes={nodeTypes}
          onNodesChange={onNodesChange}
          onEdgesChange={onEdgesChange}
          fitView
          fitViewOptions={{ padding: 0.2 }}
          minZoom={0.3}
          maxZoom={2.5}
          style={{ background: "#060606" }}
          proOptions={{ hideAttribution: true }}
        >
          <Background
            variant={BackgroundVariant.Dots}
            gap={24}
            size={1}
            color="rgba(255,255,255,0.04)"
          />
          <Controls />
        </ReactFlow>
      )}
    </div>
  );
}
