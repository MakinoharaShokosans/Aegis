import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, act } from '@testing-library/react';
import { ProjectsTree } from '../ProjectsTree';
import { useWorkspaceStore } from '@/stores/useWorkspaceStore';
import { useTaskStore } from '@/stores/useTaskStore';

vi.mock('@/api', () => ({
  sessionApi: {
    list: vi.fn().mockImplementation((wsId: string) => {
      if (wsId === 'ws-2') {
        return Promise.resolve([
          {
            id: 'sess-3',
            workspace_id: 'ws-2',
            title: '在线测视力网页构想',
            status: 'active',
            created_at: new Date().toISOString(),
            updated_at: new Date().toISOString(),
          },
        ]);
      }
      return Promise.resolve([
        {
          id: 'sess-1',
          workspace_id: 'ws-1',
          title: '项目只读探索与分析',
          status: 'active',
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
        },
      ]);
    }),
    getTurns: vi.fn().mockResolvedValue([]),
    create: vi.fn(),
    delete: vi.fn(),
  },
  workspaceApi: {
    list: vi.fn().mockResolvedValue([]),
    create: vi.fn(),
    update: vi.fn(),
    delete: vi.fn(),
  },
  memoryApi: {
    list: vi.fn().mockResolvedValue([]),
  },
  fileApi: {
    getTree: vi.fn().mockResolvedValue([]),
  },
}));

describe('ProjectsTree', () => {
  beforeEach(() => {
    useWorkspaceStore.setState({
      workspaces: [
        {
          id: 'ws-1',
          name: 'Aegis',
          root_path: '/home/aegis',
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
        },
        {
          id: 'ws-2',
          name: 'EyesPro',
          root_path: '/home/eyespro',
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
        },
      ],
      workspaceSessions: {
        'ws-1': [
          {
            id: 'sess-1',
            workspace_id: 'ws-1',
            title: '项目只读探索与分析',
            status: 'active',
            created_at: new Date(Date.now() - 60000).toISOString(),
            updated_at: new Date(Date.now() - 60000).toISOString(),
          },
          {
            id: 'sess-2',
            workspace_id: 'ws-1',
            title: 'Project Architecture Ex...',
            status: 'active',
            created_at: new Date(Date.now() - 86400000).toISOString(),
            updated_at: new Date(Date.now() - 86400000).toISOString(),
          },
        ],
        'ws-2': [
          {
            id: 'sess-3',
            workspace_id: 'ws-2',
            title: '在线测视力网页构想',
            status: 'active',
            created_at: new Date(Date.now() - 14 * 60000).toISOString(),
            updated_at: new Date(Date.now() - 14 * 60000).toISOString(),
          },
        ],
      },
      activeWorkspaceId: 'ws-1',
      activeSessionId: 'sess-1',
    });

    useTaskStore.setState({
      tasks: {},
      currentTaskId: null,
    });
  });

  it('renders workspaces and their child sessions correctly', () => {
    render(<ProjectsTree />);

    expect(screen.getByText('Projects')).toBeInTheDocument();
    expect(screen.getByText('Aegis')).toBeInTheDocument();
    expect(screen.getByText('EyesPro')).toBeInTheDocument();
    expect(screen.getByText('项目只读探索与分析')).toBeInTheDocument();
    expect(screen.getByText('在线测视力网页构想')).toBeInTheDocument();
  });

  it('collapses and expands workspace folders on click', () => {
    render(<ProjectsTree />);

    // Initially open
    expect(screen.getByText('在线测视力网页构想')).toBeInTheDocument();

    // Click on EyesPro workspace to toggle collapse
    fireEvent.click(screen.getByText('EyesPro'));

    // Should be collapsed now
    expect(screen.queryByText('在线测视力网页构想')).not.toBeInTheDocument();

    // Click again to expand
    fireEvent.click(screen.getByText('EyesPro'));
    expect(screen.getByText('在线测视力网页构想')).toBeInTheDocument();
  });

  it('switches active session and workspace when clicking a session', async () => {
    render(<ProjectsTree />);

    const eyesProSession = screen.getByText('在线测视力网页构想');
    await act(async () => {
      fireEvent.click(eyesProSession);
    });

    expect(useWorkspaceStore.getState().activeWorkspaceId).toBe('ws-2');
    expect(useWorkspaceStore.getState().activeSessionId).toBe('sess-3');
  });
});
