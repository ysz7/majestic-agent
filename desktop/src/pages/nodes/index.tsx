import {
  ReactFlow,
  Background,
  BackgroundVariant,
  Controls,
  useNodesState,
  useEdgesState,
  addEdge,
  useReactFlow,
  ReactFlowProvider,
  type Connection,
  type Node,
  type Edge,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { useEffect, useMemo, useCallback, useState } from "react";
import { nodeTypes }      from "@features/canvas/ui/nodeTypes";
import { NodeConfigPanel, WORKFLOW_TYPES } from "@features/canvas/ui/NodeConfigPanel";
import { WorkflowBar }    from "@features/canvas/ui/WorkflowBar";
import { useCanvasData }  from "@features/canvas/model/useCanvasData";
import { useReActNodes }  from "@features/canvas/model/useReActNodes";
import { useAgentStore }  from "@store/agentStore";
import { useCanvasStore } from "@store/canvasStore";
import type { Workflow }  from "@shared/api/types";

export function NodesPage() {
  return (
    <ReactFlowProvider>
      <NodesPageInner />
    </ReactFlowProvider>
  );
}

function isWorkflowNode(n: Node): boolean {
  return WORKFLOW_TYPES.has(n.type ?? "");
}

function NodesPageInner() {
  const activeProfile = useAgentStore((s) => s.activeProfile);
  const { screenToFlowPosition } = useReactFlow();

  const { nodes: dataNodes, edges: dataEdges, isLoading } =
    useCanvasData(activeProfile);
  const { nodes: reactNodes, edges: reactEdges } = useReActNodes(activeProfile);

  const dataAndReactNodes = useMemo(
    () => [...dataNodes, ...reactNodes],
    [dataNodes, reactNodes],
  );
  const dataAndReactEdges = useMemo(
    () => [...dataEdges, ...reactEdges],
    [dataEdges, reactEdges],
  );

  const [nodes, setNodes, onNodesChange] = useNodesState<Node>([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [workflowId, setWorkflowId]     = useState<string | null>(null);
  const [workflowName, setWorkflowName] = useState("");

  // Sync polling-driven nodes WITHOUT wiping user-created workflow nodes.
  useEffect(() => {
    setNodes((prev) => [
      ...dataAndReactNodes,
      ...prev.filter(isWorkflowNode),
    ]);
  }, [dataAndReactNodes, setNodes]);

  // Sync polling-driven edges; keep user-created workflow edges (data.wf flag).
  useEffect(() => {
    setEdges((prev) => [
      ...dataAndReactEdges,
      ...prev.filter((e) => (e.data as { wf?: boolean } | undefined)?.wf),
    ]);
  }, [dataAndReactEdges, setEdges]);

  // Add node from the toolbar palette
  const { pendingNodeAdd, setPendingNode } = useCanvasStore();
  useEffect(() => {
    if (!pendingNodeAdd) return;
    const { type, subtype } = pendingNodeAdd;
    const center = screenToFlowPosition({
      x: window.innerWidth / 2,
      y: window.innerHeight / 2,
    });
    setNodes((nds) => [
      ...nds,
      {
        id:       `${type}-${Date.now()}`,
        type,
        position: {
          x: center.x + (Math.random() - 0.5) * 100,
          y: center.y + (Math.random() - 0.5) * 60,
        },
        data:     { subtype, label: subtype },
      },
    ]);
    setPendingNode(null);
  }, [pendingNodeAdd, screenToFlowPosition, setNodes, setPendingNode]);

  const onConnect = useCallback(
    (connection: Connection) =>
      setEdges((eds) =>
        addEdge(
          {
            ...connection,
            data:  { wf: true },
            style: { stroke: "rgba(255,255,255,0.2)", strokeWidth: 1.5 },
          },
          eds,
        ),
      ),
    [setEdges],
  );

  const onNodeClick = useCallback((_: React.MouseEvent, node: Node) => {
    setSelectedId(isWorkflowNode(node) ? node.id : null);
  }, []);

  const updateNodeData = useCallback(
    (key: string, value: string) => {
      if (!selectedId) return;
      setNodes((nds) =>
        nds.map((n) =>
          n.id === selectedId ? { ...n, data: { ...n.data, [key]: value } } : n,
        ),
      );
    },
    [selectedId, setNodes],
  );

  const deleteSelected = useCallback(() => {
    if (!selectedId) return;
    setNodes((nds) => nds.filter((n) => n.id !== selectedId));
    setEdges((eds) =>
      eds.filter((e) => e.source !== selectedId && e.target !== selectedId),
    );
    setSelectedId(null);
  }, [selectedId, setNodes, setEdges]);

  const selectedNode = nodes.find((n) => n.id === selectedId) ?? null;

  // ── Workflow save / load ────────────────────────────────────────────────────
  const collectWorkflow = useCallback(() => {
    const wfNodes = nodes.filter(isWorkflowNode).map((n) => ({
      id:       n.id,
      type:     n.type ?? "",
      position: n.position,
      data:     n.data,
    }));
    const wfNodeIds = new Set(wfNodes.map((n) => n.id));
    const wfEdges = edges
      .filter((e) => (e.data as { wf?: boolean } | undefined)?.wf)
      .filter((e) => wfNodeIds.has(e.source) && wfNodeIds.has(e.target))
      .map((e) => ({
        id:           e.id,
        source:       e.source,
        target:       e.target,
        sourceHandle: e.sourceHandle ?? null,
        targetHandle: e.targetHandle ?? null,
      }));
    return { nodes: wfNodes, edges: wfEdges };
  }, [nodes, edges]);

  const loadWorkflow = useCallback(
    (wf: Workflow) => {
      setSelectedId(null);
      setWorkflowId(wf.id);
      setWorkflowName(wf.name);
      // Replace the workflow layer; keep polling-driven data/react nodes.
      setNodes((prev) => [
        ...prev.filter((n) => !isWorkflowNode(n)),
        ...wf.nodes.map((n) => ({
          id: n.id, type: n.type, position: n.position, data: n.data,
        })),
      ]);
      setEdges((prev) => [
        ...prev.filter((e) => !(e.data as { wf?: boolean } | undefined)?.wf),
        ...wf.edges.map((e) => ({
          ...e,
          data:  { wf: true },
          style: { stroke: "rgba(255,255,255,0.2)", strokeWidth: 1.5 },
        })),
      ]);
    },
    [setNodes, setEdges],
  );

  const newWorkflow = useCallback(() => {
    setSelectedId(null);
    setWorkflowId(null);
    setWorkflowName("");
    setNodes((prev) => prev.filter((n) => !isWorkflowNode(n)));
    setEdges((prev) => prev.filter((e) => !(e.data as { wf?: boolean } | undefined)?.wf));
  }, [setNodes, setEdges]);

  return (
    <div className="w-full h-full relative">
      {isLoading ? (
        <div className="w-full h-full flex items-center justify-center">
          <span className="text-xs text-text-muted-2">Loading…</span>
        </div>
      ) : (
        <>
          <ReactFlow
            nodes={nodes}
            edges={edges}
            nodeTypes={nodeTypes}
            onNodesChange={onNodesChange}
            onEdgesChange={onEdgesChange}
            onConnect={onConnect}
            onNodeClick={onNodeClick}
            onPaneClick={() => setSelectedId(null)}
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

          <WorkflowBar
            profile={activeProfile}
            currentId={workflowId}
            name={workflowName}
            onNameChange={setWorkflowName}
            getWorkflow={collectWorkflow}
            onLoad={loadWorkflow}
            onNew={newWorkflow}
            onSaved={setWorkflowId}
          />

          {selectedNode && (
            <NodeConfigPanel
              node={selectedNode}
              onChange={updateNodeData}
              onDelete={deleteSelected}
              onClose={() => setSelectedId(null)}
            />
          )}
        </>
      )}
    </div>
  );
}
