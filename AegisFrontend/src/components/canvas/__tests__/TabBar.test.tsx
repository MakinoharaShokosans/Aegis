import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { TabBar } from '../TabBar';
import type { OpenTab } from '@/types';

describe('TabBar', () => {
  const mockTabs: OpenTab[] = [
    {
      id: 'tab-1',
      filePath: 'src/app.py',
      title: 'app.py',
      language: 'python',
      content: 'print("hello")',
      isModified: true,
    },
    {
      id: 'tab-2',
      filePath: 'docs/api.md',
      title: 'api.md',
      language: 'markdown',
      content: '# API Specs',
      isModified: false,
    },
  ];

  it('renders all tabs and highlights active tab', () => {
    render(
      <TabBar
        tabs={mockTabs}
        activeTab={mockTabs[0]}
        viewMode="editor"
        isMarkdown={false}
        previewFullScreen={false}
        onSelectTab={vi.fn()}
        onCloseTab={vi.fn()}
        onChangeViewMode={vi.fn()}
        onSave={vi.fn()}
        onToggleFullScreen={vi.fn()}
      />
    );

    expect(screen.getByText('app.py')).toBeInTheDocument();
    expect(screen.getByText('api.md')).toBeInTheDocument();
    expect(screen.getByTitle('已修改未保存')).toBeInTheDocument();
  });

  it('triggers onSelectTab on tab click', () => {
    const handleSelectTab = vi.fn();
    render(
      <TabBar
        tabs={mockTabs}
        activeTab={mockTabs[0]}
        viewMode="editor"
        isMarkdown={false}
        previewFullScreen={false}
        onSelectTab={handleSelectTab}
        onCloseTab={vi.fn()}
        onChangeViewMode={vi.fn()}
        onSave={vi.fn()}
        onToggleFullScreen={vi.fn()}
      />
    );

    fireEvent.click(screen.getByText('api.md'));
    expect(handleSelectTab).toHaveBeenCalledWith('tab-2');
  });

  it('triggers onCloseTab on close icon click', () => {
    const handleCloseTab = vi.fn();
    render(
      <TabBar
        tabs={mockTabs}
        activeTab={mockTabs[0]}
        viewMode="editor"
        isMarkdown={false}
        previewFullScreen={false}
        onSelectTab={vi.fn()}
        onCloseTab={handleCloseTab}
        onChangeViewMode={vi.fn()}
        onSave={vi.fn()}
        onToggleFullScreen={vi.fn()}
      />
    );

    const closeBtns = screen.getAllByTitle('关闭标签页');
    fireEvent.click(closeBtns[0]);
    expect(handleCloseTab).toHaveBeenCalledWith('tab-1');
  });

  it('triggers onSave when save button is clicked for modified tab', () => {
    const handleSave = vi.fn();
    render(
      <TabBar
        tabs={mockTabs}
        activeTab={mockTabs[0]} // isModified = true
        viewMode="editor"
        isMarkdown={false}
        previewFullScreen={false}
        onSelectTab={vi.fn()}
        onCloseTab={vi.fn()}
        onChangeViewMode={vi.fn()}
        onSave={handleSave}
        onToggleFullScreen={vi.fn()}
      />
    );

    const saveBtn = screen.getByTitle(/保存修改/i);
    fireEvent.click(saveBtn);
    expect(handleSave).toHaveBeenCalledTimes(1);
  });
});
