import { create } from "zustand";

interface PendingNode {
  type:    string;
  subtype: string;
}

interface CanvasStore {
  pendingNodeAdd: PendingNode | null;
  setPendingNode: (node: PendingNode | null) => void;
}

export const useCanvasStore = create<CanvasStore>((set) => ({
  pendingNodeAdd: null,
  setPendingNode: (pendingNodeAdd) => set({ pendingNodeAdd }),
}));
