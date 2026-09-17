import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { HitlApprovalCard } from '../HitlApprovalCard';
import type { HITLApprovalRequest } from '@/types';

describe('HitlApprovalCard', () => {
  const mockApproval: HITLApprovalRequest = {
    approval_id: 'appr-sec-001',
    task_id: 'task-100',
    action_type: 'network_egress',
    command: 'curl -X POST https://external.api/push',
    reason: '试图进行外部网络出口请求，违反默认只读隔离基线',
    cwd: '/home/Skualeilu/Projects/Aegis',
    created_at: new Date().toISOString(),
  };

  it('renders approval details and security warning', () => {
    render(
      <HitlApprovalCard
        approval={mockApproval}
        onApprove={vi.fn()}
        onReject={vi.fn()}
      />
    );

    expect(screen.getByText(/人机协同权限越级审批卡片/i)).toBeInTheDocument();
    expect(screen.getByText(/curl -X POST https:\/\/external.api\/push/i)).toBeInTheDocument();
    expect(screen.getByText(/试图进行外部网络出口请求/i)).toBeInTheDocument();
  });

  it('triggers onApprove with "once" decision on clicking 批准本次', () => {
    const handleApprove = vi.fn();
    render(
      <HitlApprovalCard
        approval={mockApproval}
        onApprove={handleApprove}
        onReject={vi.fn()}
      />
    );

    const onceBtn = screen.getByRole('button', { name: /批准本次/i });
    fireEvent.click(onceBtn);

    expect(handleApprove).toHaveBeenCalledTimes(1);
    expect(handleApprove).toHaveBeenCalledWith('appr-sec-001', 'once');
  });

  it('triggers onApprove with "always" decision on clicking 当前会话免审', () => {
    const handleApprove = vi.fn();
    render(
      <HitlApprovalCard
        approval={mockApproval}
        onApprove={handleApprove}
        onReject={vi.fn()}
      />
    );

    const alwaysBtn = screen.getByRole('button', { name: /当前会话免审/i });
    fireEvent.click(alwaysBtn);

    expect(handleApprove).toHaveBeenCalledTimes(1);
    expect(handleApprove).toHaveBeenCalledWith('appr-sec-001', 'always');
  });

  it('shows input on clicking 拒绝 and triggers onReject on confirmation', () => {
    const handleReject = vi.fn();
    render(
      <HitlApprovalCard
        approval={mockApproval}
        onApprove={vi.fn()}
        onReject={handleReject}
      />
    );

    const rejectBtn = screen.getByRole('button', { name: /拒绝并指示改道/i });
    fireEvent.click(rejectBtn);

    // Input box should now be visible
    const input = screen.getByPlaceholderText(/输入拒绝原因/i);
    fireEvent.change(input, { target: { value: '禁止网络出口' } });

    const confirmBtn = screen.getByRole('button', { name: /确认拒绝/i });
    fireEvent.click(confirmBtn);

    expect(handleReject).toHaveBeenCalledTimes(1);
    expect(handleReject).toHaveBeenCalledWith('appr-sec-001', '禁止网络出口');
  });
});
