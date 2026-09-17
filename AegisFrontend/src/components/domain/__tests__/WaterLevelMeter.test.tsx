import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { WaterLevelMeter } from '../WaterLevelMeter';

describe('WaterLevelMeter', () => {
  it('renders safe green water level when percentage is low (< 50%)', () => {
    const { container } = render(
      <WaterLevelMeter currentPct={32} maxPct={80} activeTokens={25600} />
    );

    expect(screen.getByText(/水位: 32.0% \/ 80%/i)).toBeInTheDocument();
    expect(screen.getByText(/25.6k \/ 80k tok/i)).toBeInTheDocument();
    expect(container.firstChild).toHaveClass('text-emerald-700');
  });

  it('renders moderate blue water level when percentage is between 50% and maxPct', () => {
    const { container } = render(
      <WaterLevelMeter currentPct={65} maxPct={80} />
    );

    expect(container.firstChild).toHaveClass('text-blue-700');
  });

  it('renders warning amber water level when percentage exceeds maxPct (>= 80%)', () => {
    const { container } = render(
      <WaterLevelMeter currentPct={85} maxPct={80} />
    );

    expect(container.firstChild).toHaveClass('text-amber-700');
  });
});
