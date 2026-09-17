import { create } from 'zustand';
import type { OpenTab } from '@/types';

interface WorkspaceState {
  tabs: OpenTab[];
  activeTabId: string | null;
  openTab: (tab: Omit<OpenTab, 'id'>) => void;
  closeTab: (tabId: string) => void;
  setActiveTab: (tabId: string) => void;
  updateTabContent: (tabId: string, content: string) => void;
  setTabStale: (filePath: string, isStale: boolean) => void;
}

export const useWorkspaceStore = create<WorkspaceState>((set) => ({
  tabs: [],
  activeTabId: null,

  openTab: (tabData) => {
    set((state) => {
      const existing = state.tabs.find((t) => t.filePath === tabData.filePath);
      if (existing) {
        return { activeTabId: existing.id };
      }
      const newTab: OpenTab = {
        ...tabData,
        id: `tab-${Date.now()}-${Math.random().toString(36).substring(2, 7)}`,
      };
      return {
        tabs: [...state.tabs, newTab],
        activeTabId: newTab.id,
      };
    });
  },

  closeTab: (tabId) => {
    set((state) => {
      const remaining = state.tabs.filter((t) => t.id !== tabId);
      let nextActive = state.activeTabId;
      if (state.activeTabId === tabId) {
        nextActive = remaining.length > 0 ? remaining[remaining.length - 1].id : null;
      }
      return {
        tabs: remaining,
        activeTabId: nextActive,
      };
    });
  },

  setActiveTab: (tabId) => set({ activeTabId: tabId }),

  updateTabContent: (tabId, content) => {
    set((state) => ({
      tabs: state.tabs.map((t) => (t.id === tabId ? { ...t, content, isStale: false } : t)),
    }));
  },

  setTabStale: (filePath, isStale) => {
    set((state) => ({
      tabs: state.tabs.map((t) => (t.filePath === filePath ? { ...t, isStale } : t)),
    }));
  },
}));
