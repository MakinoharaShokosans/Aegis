import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { AegisLogo, AegisBrand } from '../AegisLogo';
import { AegisAiAvatar, AegisUserAvatar, AegisSystemAvatar } from '../AegisAvatar';

describe('AegisLogo & AegisBrand components', () => {
  it('renders AegisLogo in different sizes', () => {
    const { container, rerender } = render(<AegisLogo size="sm" glow showStatus status="online" />);
    expect(container.querySelector('svg')).toBeInTheDocument();
    expect(screen.getByLabelText('Aegis Geometric Shield Logo')).toBeInTheDocument();

    rerender(<AegisLogo size="xl" glow showStatus status="busy" />);
    expect(screen.getByLabelText('Aegis Geometric Shield Logo')).toBeInTheDocument();
  });

  it('renders AegisBrand with typography and version tag', () => {
    render(<AegisBrand size="sm" version="v4.0" subtitle="高可信代码智能体" />);
    expect(screen.getByText('Aegis')).toBeInTheDocument();
    expect(screen.getByText('Agent')).toBeInTheDocument();
    expect(screen.getByText('v4.0')).toBeInTheDocument();
    expect(screen.getByText('高可信代码智能体')).toBeInTheDocument();
  });
});

describe('AegisAvatar components', () => {
  it('renders AegisAiAvatar with SVG neural core', () => {
    render(<AegisAiAvatar size="md" glow />);
    expect(screen.getByLabelText('Aegis AI Agent Avatar')).toBeInTheDocument();
  });

  it('renders AegisUserAvatar with human architect emblem', () => {
    render(<AegisUserAvatar size="md" glow />);
    expect(screen.getByLabelText('User Avatar')).toBeInTheDocument();
  });

  it('renders AegisSystemAvatar with security crest', () => {
    render(<AegisSystemAvatar size="sm" />);
    expect(screen.getByLabelText('System Shield Avatar')).toBeInTheDocument();
  });
});
