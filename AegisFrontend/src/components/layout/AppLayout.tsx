import React from 'react';
import { PanelGroup, Panel, PanelResizeHandle } from 'react-resizable-panels';
import { Sidebar } from '../sidebar/Sidebar';
import { ChatPane } from '../chat/ChatPane';
import { CanvasPane } from '../canvas/CanvasPane';
import { useUiStore } from '@/stores/useUiStore';

export const AppLayout: React.FC = () => {
  const { previewFullScreen } = useUiStore();

  if (previewFullScreen) {
    return (
      <div className="flex h-screen w-screen overflow-hidden bg-white">
        <CanvasPane />
      </div>
    );
  }

  return (
    <div className="flex h-screen w-screen overflow-hidden bg-white">
      <Sidebar />
      <div className="flex-1 h-full min-w-0">
        <PanelGroup direction="horizontal">
          {/* Middle Stage: Chat and Trace */}
          <Panel defaultSize={50} minSize={30} className="h-full">
            <ChatPane />
          </Panel>

          {/* Resizable Divider */}
          <PanelResizeHandle className="w-1 bg-border-subtle hover:bg-brand-500 transition-colors cursor-col-resize select-none" />

          {/* Right Stage: Canvas / Editor */}
          <Panel defaultSize={50} minSize={25} className="h-full">
            <CanvasPane />
          </Panel>
        </PanelGroup>
      </div>
    </div>
  );
};
