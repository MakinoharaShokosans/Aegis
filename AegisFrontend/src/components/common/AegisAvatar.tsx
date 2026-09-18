/**
 * Aegis Modern Minimalist Line-Art Avatar System
 * Transparent background, clean geometric line work, single-tone light palette.
 */

import React from 'react';

export type AvatarSize = 'xs' | 'sm' | 'md' | 'lg' | 'xl';

interface AvatarBaseProps {
  size?: AvatarSize;
  className?: string;
  glow?: boolean;
}

const sizeMap: Record<AvatarSize, { box: string; stroke: number }> = {
  xs: { box: 'w-4 h-4', stroke: 1.6 },
  sm: { box: 'w-5 h-5', stroke: 1.7 },
  md: { box: 'w-6 h-6', stroke: 1.75 },
  lg: { box: 'w-8 h-8', stroke: 1.8 },
  xl: { box: 'w-10 h-10', stroke: 1.9 },
};

/**
 * AI Autonomous Agent Avatar
 * Transparent background with geometric line-art quantum neural prism in soft light blue.
 */
export const AegisAiAvatar: React.FC<AvatarBaseProps> = ({
  size = 'md',
  className = '',
  glow = false,
}) => {
  const { box, stroke } = sizeMap[size];

  return (
    <div
      className={`relative inline-flex items-center justify-center shrink-0 select-none bg-transparent ${box} ${className}`}
      aria-label="Aegis AI Agent Avatar"
    >
      {glow && (
        <div
          className="absolute inset-0 rounded-full bg-blue-400/15 blur-xs -z-10 animate-pulse pointer-events-none"
          style={{ transform: 'scale(1.2)' }}
        />
      )}

      <svg
        viewBox="0 0 24 24"
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
        className="w-full h-full text-blue-500 overflow-visible"
      >
        {/* Outer Hexagonal Geometric Frame */}
        <path
          d="M 12 2.5 L 19.5 6.8 L 19.5 15.5 L 12 19.8 L 4.5 15.5 L 4.5 6.8 Z"
          stroke="currentColor"
          strokeWidth={stroke}
          strokeLinecap="round"
          strokeLinejoin="round"
        />

        {/* 3 Converging Isometric Core Axes */}
        <path
          d="M 12 2.5 L 12 11.2 M 19.5 15.5 L 12 11.2 M 4.5 15.5 L 12 11.2"
          stroke="currentColor"
          strokeWidth={stroke}
          strokeLinecap="round"
          strokeLinejoin="round"
        />

        {/* Inner Floating Diamond Spark */}
        <path
          d="M 12 8.5 L 14.5 11.2 L 12 13.9 L 9.5 11.2 Z"
          stroke="currentColor"
          strokeWidth={stroke * 0.9}
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
    </div>
  );
};

/**
 * Human Developer / User Avatar
 * Transparent background with geometric line-art architect silhouette in soft slate.
 */
export const AegisUserAvatar: React.FC<AvatarBaseProps> = ({
  size = 'md',
  className = '',
}) => {
  const { box, stroke } = sizeMap[size];

  return (
    <div
      className={`relative inline-flex items-center justify-center shrink-0 select-none bg-transparent ${box} ${className}`}
      aria-label="User Avatar"
    >
      <svg
        viewBox="0 0 24 24"
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
        className="w-full h-full text-slate-500 overflow-visible"
      >
        {/* Geometric Circular Outer Frame */}
        <circle
          cx="12"
          cy="12"
          r="9.5"
          stroke="currentColor"
          strokeWidth={stroke}
          strokeLinecap="round"
        />

        {/* Minimalist Geometric Head */}
        <circle
          cx="12"
          cy="8.5"
          r="3"
          stroke="currentColor"
          strokeWidth={stroke}
          strokeLinecap="round"
        />

        {/* Minimalist Geometric Shoulders */}
        <path
          d="M 6.5 17.5 C 7.2 14.5 9.2 13.5 12 13.5 C 14.8 13.5 16.8 14.5 17.5 17.5"
          stroke="currentColor"
          strokeWidth={stroke}
          strokeLinecap="round"
        />
      </svg>
    </div>
  );
};

/**
 * System Security & Kernel Avatar
 * Transparent background with clean minimalist shield wireframe in soft slate.
 */
export const AegisSystemAvatar: React.FC<AvatarBaseProps> = ({
  size = 'sm',
  className = '',
}) => {
  const { box, stroke } = sizeMap[size];

  return (
    <div
      className={`inline-flex items-center justify-center shrink-0 select-none bg-transparent ${box} ${className}`}
      aria-label="System Shield Avatar"
    >
      <svg
        viewBox="0 0 24 24"
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
        className="w-full h-full text-slate-400 overflow-visible"
      >
        <path
          d="M 12 3 L 19 6.2 C 19 13.2 15.5 17.5 12 19.8 C 8.5 17.5 5 13.2 5 6.2 Z"
          stroke="currentColor"
          strokeWidth={stroke}
          strokeLinecap="round"
          strokeLinejoin="round"
        />
        <path
          d="M 9.5 11.5 L 11.5 13.5 L 15 9.5"
          stroke="currentColor"
          strokeWidth={stroke}
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
    </div>
  );
};
