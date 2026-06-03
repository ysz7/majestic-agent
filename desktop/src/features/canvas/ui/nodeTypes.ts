import type { NodeTypes } from "@xyflow/react";
import { AgentNode }   from "./AgentNode";
import { CronNode }    from "./CronNode";
import { FileNode }    from "./FileNode";
import { ReActNode }   from "./ReActNode";
import { ZapNode }     from "./ZapNode";
import { TriggerNode } from "./TriggerNode";
import { ActionNode }  from "./ActionNode";
import { OutputNode }  from "./OutputNode";

export const nodeTypes: NodeTypes = {
  agentNode:   AgentNode,
  cronNode:    CronNode,
  fileNode:    FileNode,
  reactNode:   ReActNode,
  zapNode:     ZapNode,
  triggerNode: TriggerNode,
  actionNode:  ActionNode,
  outputNode:  OutputNode,
};
