import { create } from 'zustand';

interface UiState {
  sidebarOpen: boolean;
  activeView: 'chat' | 'trace';
  previewSplitMode: 'horizontal' | 'vertical';
  previewFullScreen: boolean;
  toggleSidebar: () => void;
  setSidebarOpen: (open: boolean) => void;
  setActiveView: (view: 'chat' | 'trace') => void;
  setPreviewSplitMode: (mode: 'horizontal' | 'vertical') => void;
  togglePreviewFullScreen: () => void;
}

export const useUiStore = create<UiState>((set) => ({
  sidebarOpen: true,
  activeView: 'chat',
  previewSplitMode: 'horizontal',
  previewFullScreen: false,
  toggleSidebar: () => set((state) => ({ sidebarOpen: !state.sidebarOpen })),
  setSidebarOpen: (open) => set({ sidebarOpen: open }),
  setActiveView: (view) => set({ activeView: view }),
  setPreviewSplitMode: (mode) => set({ previewSplitMode: mode }),
  togglePreviewFullScreen: () => set((state) => ({ previewFullScreen: !state.previewFullScreen })),
}));
