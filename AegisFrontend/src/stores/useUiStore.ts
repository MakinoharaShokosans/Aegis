import { create } from 'zustand';

interface UiState {
  // Sidebar & Views
  sidebarOpen: boolean;
  activeView: 'chat' | 'trace' | 'context';
  previewSplitMode: 'horizontal' | 'vertical';
  previewFullScreen: boolean;

  // Modals & Drawers
  workspaceModalOpen: boolean;
  workspaceModalMode: 'create' | 'edit' | 'delete' | 'manage';
  ragCenterModalOpen: boolean;
  settingsModalOpen: boolean;
  memoryDrawerOpen: boolean;
  contextDrawerOpen: boolean;

  // View Actions
  toggleSidebar: () => void;
  setSidebarOpen: (open: boolean) => void;
  setActiveView: (view: 'chat' | 'trace' | 'context') => void;
  setPreviewSplitMode: (mode: 'horizontal' | 'vertical') => void;
  togglePreviewFullScreen: () => void;

  // Modal Actions
  openWorkspaceModal: (mode?: 'create' | 'edit' | 'delete' | 'manage') => void;
  closeWorkspaceModal: () => void;
  setRagCenterModalOpen: (open: boolean) => void;
  setSettingsModalOpen: (open: boolean) => void;
  setMemoryDrawerOpen: (open: boolean) => void;
  setContextDrawerOpen: (open: boolean) => void;
}

export const useUiStore = create<UiState>((set) => ({
  sidebarOpen: true,
  activeView: 'chat',
  previewSplitMode: 'horizontal',
  previewFullScreen: false,

  workspaceModalOpen: false,
  workspaceModalMode: 'create',
  ragCenterModalOpen: false,
  settingsModalOpen: false,
  memoryDrawerOpen: false,
  contextDrawerOpen: false,

  toggleSidebar: () => set((state) => ({ sidebarOpen: !state.sidebarOpen })),
  setSidebarOpen: (open) => set({ sidebarOpen: open }),
  setActiveView: (view) => set({ activeView: view }),
  setPreviewSplitMode: (mode) => set({ previewSplitMode: mode }),
  togglePreviewFullScreen: () => set((state) => ({ previewFullScreen: !state.previewFullScreen })),

  openWorkspaceModal: (mode = 'create') => set({ workspaceModalOpen: true, workspaceModalMode: mode }),
  closeWorkspaceModal: () => set({ workspaceModalOpen: false }),
  setRagCenterModalOpen: (open) => set({ ragCenterModalOpen: open }),
  setSettingsModalOpen: (open) => set({ settingsModalOpen: open }),
  setMemoryDrawerOpen: (open) => set({ memoryDrawerOpen: open }),
  setContextDrawerOpen: (open) => set({ contextDrawerOpen: open }),
}));
