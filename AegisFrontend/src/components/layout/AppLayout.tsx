import React, { useEffect } from 'react';
import { PanelGroup, Panel, PanelResizeHandle } from 'react-resizable-panels';
import { AppHeader } from './AppHeader';
import { StatusBar } from './StatusBar';
import { Sidebar } from '../sidebar/Sidebar';
import { ChatPane } from '../chat/ChatPane';
import { CanvasPane } from '../canvas/CanvasPane';
import { WorkspaceModal } from '../modals/WorkspaceModal';
import { RagCenterModal } from '../modals/RagCenterModal';
import { SettingsModal } from '../modals/SettingsModal';
import { MemoryDrawer } from '../drawer/MemoryDrawer';
import { ContextDrawer } from '../drawer/ContextDrawer';
import { useUiStore } from '@/stores/useUiStore';
import { useWorkspaceStore } from '@/stores/useWorkspaceStore';

export const AppLayout: React.FC = () => {
  const { previewFullScreen } = useUiStore();
  const { fetchWorkspaces } = useWorkspaceStore();

  useEffect(() => {
    fetchWorkspaces();
  }, [fetchWorkspaces]);

  if (previewFullScreen) {
    return (
      <div className="flex flex-col h-screen w-screen overflow-hidden bg-white">
        <CanvasPane />
      </div>
    );
  }

  return (
    <div className="flex flex-col h-screen w-screen overflow-hidden bg-slate-50">
      {/* Top Global Navigation Bar */}
      <AppHeader />

      {/* Main 3-Pane Resizable Workspace */}
      <div className="flex-1 flex min-h-0">
        <Sidebar />

        <div className="flex-1 h-full min-w-0 bg-white">
          <PanelGroup direction="horizontal">
            {/* Middle Stage: Chat & Trace */}
            <Panel defaultSize={50} minSize={30} className="h-full">
              <ChatPane />
            </Panel>

            {/* Resizable Divider */}
            <PanelResizeHandle className="w-1 bg-slate-200 hover:bg-brand-500 transition-colors cursor-col-resize select-none" />

            {/* Right Stage: Canvas / Specs Reader / Editor */}
            <Panel defaultSize={50} minSize={25} className="h-full">
              <CanvasPane />
            </Panel>
          </PanelGroup>
        </div>
      </div>

      {/* Bottom Status Bar */}
      <StatusBar />

      {/* Global Modals & Drawers */}
      <WorkspaceModal />
      <RagCenterModal />
      <SettingsModal />
      <MemoryDrawer />
      <ContextDrawer />
    </div>
  );
};
