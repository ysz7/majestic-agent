import { create } from "zustand";
import type { Profile } from "@entities/profile/model/types";
import type { Agent } from "@entities/agent/model/types";

interface AgentStore {
  profiles: Profile[];
  runningAgents: Agent[];
  activeProfile: string | null;
  agentToken: string;

  setProfiles:      (profiles: Profile[]) => void;
  setRunningAgents: (agents: Agent[])     => void;
  setActiveProfile: (name: string)        => void;
  setToken:         (token: string)       => void;
}

export const useAgentStore = create<AgentStore>((set) => ({
  profiles:       [],
  runningAgents:  [],
  activeProfile:  null,
  agentToken:     localStorage.getItem("agent_token") ?? "",

  setProfiles:      (profiles)     => set({ profiles }),
  setRunningAgents: (runningAgents) => set({ runningAgents }),
  setActiveProfile: (name)         => set({ activeProfile: name }),
  setToken:         (token) => {
    localStorage.setItem("agent_token", token);
    set({ agentToken: token });
  },
}));
