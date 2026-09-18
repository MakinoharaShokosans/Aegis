import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { InputConsole } from '../InputConsole';

describe('InputConsole', () => {
  it('renders textarea, permission baseline selector and model selector', () => {
    render(<InputConsole onSend={vi.fn()} />);

    expect(screen.getByPlaceholderText(/输入任务目标/i)).toBeInTheDocument();
    expect(screen.getByDisplayValue(/工作区写入/i)).toBeInTheDocument();
    expect(screen.getByDisplayValue(/gpt-5.6-terra \+ gpt-5.4-mini/i)).toBeInTheDocument();
  });

  it('triggers onSend on clicking submit button with prompt and selected options', () => {
    const handleSend = vi.fn();
    render(<InputConsole onSend={handleSend} />);

    const textarea = screen.getByPlaceholderText(/输入任务目标/i);
    fireEvent.change(textarea, { target: { value: '实现新特性' } });

    const submitBtn = screen.getByTitle(/发送任务/i);
    fireEvent.click(submitBtn);

    expect(handleSend).toHaveBeenCalledTimes(1);
    expect(handleSend).toHaveBeenCalledWith('实现新特性', {
      permissionLevel: 'workspace_write',
      model: 'Dual-Tier: gpt-5.6-terra + gpt-5.4-mini',
    });
  });

  it('submits on Enter key and prevents default, but allows Shift+Enter for newlines', () => {
    const handleSend = vi.fn();
    render(<InputConsole onSend={handleSend} />);

    const textarea = screen.getByPlaceholderText(/输入任务目标/i);
    fireEvent.change(textarea, { target: { value: '回车测试' } });

    // Enter without shift
    fireEvent.keyDown(textarea, { key: 'Enter', shiftKey: false });
    expect(handleSend).toHaveBeenCalledTimes(1);
    expect(handleSend).toHaveBeenCalledWith('回车测试', expect.anything());

    // Shift+Enter
    fireEvent.change(textarea, { target: { value: '换行测试' } });
    fireEvent.keyDown(textarea, { key: 'Enter', shiftKey: true });
    expect(handleSend).toHaveBeenCalledTimes(1); // not called again
  });

  it('shows Slash command menu when typing "/"', () => {
    render(<InputConsole onSend={vi.fn()} />);

    const textarea = screen.getByPlaceholderText(/输入任务目标/i);
    fireEvent.change(textarea, { target: { value: '/' } });

    expect(screen.getByText(/快捷指令/i)).toBeInTheDocument();
    expect(screen.getByText(/\/rag/i)).toBeInTheDocument();
    expect(screen.getByText(/\/test/i)).toBeInTheDocument();
    expect(screen.getByText(/\/plan/i)).toBeInTheDocument();
  });
});
