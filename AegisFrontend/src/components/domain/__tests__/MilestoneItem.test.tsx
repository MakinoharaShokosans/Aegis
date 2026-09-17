import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { MilestoneItem } from '../MilestoneItem';

describe('MilestoneItem', () => {
  it('renders completed milestone with strikethrough text', () => {
    render(
      <MilestoneItem
        milestone={{ id: 'm-1', title: '完成架构设计', status: 'completed' }}
      />
    );

    const titleEl = screen.getByText('完成架构设计');
    expect(titleEl).toBeInTheDocument();
    expect(titleEl).toHaveClass('line-through');
  });

  it('renders in-progress milestone and handles toggle click', () => {
    const handleToggle = vi.fn();
    render(
      <MilestoneItem
        milestone={{ id: 'm-2', title: '编写测试用例', status: 'in_progress' }}
        onToggle={handleToggle}
      />
    );

    const item = screen.getByText('编写测试用例');
    expect(item).toBeInTheDocument();
    expect(item).not.toHaveClass('line-through');

    fireEvent.click(item);
    expect(handleToggle).toHaveBeenCalledWith('m-2');
  });
});
