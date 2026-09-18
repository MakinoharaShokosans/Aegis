/**
 * Aegis Project Brand Logo
 * Minimalist geometric line-art Aegis Shield.
 * Transparent background, single-tone light-blue palette, precision geometric lines.
 */

import React from 'react';

export type LogoSize = 'xs' | 'sm' | 'md' | 'lg' | 'xl' | '2xl';

interface AegisLogoProps {
  size?: LogoSize;
  className?: string;
  glow?: boolean;
  showStatus?: boolean;
  status?: 'online' | 'busy' | 'idle' | 'warning';
}

const sizeConfig: Record<LogoSize, { box: string; stroke: number; dot: string }> = {
  xs: { box: 'w-4 h-4', stroke: 1.75, dot: 'w-1.5 h-1.5 -bottom-0.5 -right-0.5' },
  sm: { box: 'w-6 h-6', stroke: 1.75, dot: 'w-2 h-2 -bottom-0.5 -right-0.5' },
  md: { box: 'w-8 h-8', stroke: 1.75, dot: 'w-2.5 h-2.5 -bottom-0.5 -right-0.5' },
  lg: { box: 'w-12 h-12', stroke: 1.8, dot: 'w-3 h-3 -bottom-0.5 -right-0.5' },
  xl: { box: 'w-16 h-16', stroke: 1.8, dot: 'w-3.5 h-3.5 -bottom-1 -right-1' },
  '2xl': { box: 'w-20 h-20', stroke: 1.9, dot: 'w-4 h-4 -bottom-1 -right-1' },
};

const statusColors = {
  online: 'bg-emerald-500 ring-white',
  busy: 'bg-blue-500 ring-white animate-pulse',
  idle: 'bg-slate-400 ring-white',
  warning: 'bg-amber-500 ring-white',
};

export const AegisLogo: React.FC<AegisLogoProps> = ({
  size = 'sm',
  className = '',
  glow = false,
  showStatus = false,
  status = 'online',
}) => {
  const { box, stroke, dot } = sizeConfig[size];

  return (
    <div className={`relative inline-flex items-center justify-center shrink-0 select-none bg-transparent ${box} ${className}`}>
      {/* Optional Soft Line Glow for Hero/Empty states */}
      {glow && (
        <div
          className="absolute inset-0 rounded-full bg-blue-400/15 blur-md -z-10 animate-pulse pointer-events-none"
          style={{ transform: 'scale(1.3)' }}
        />
      )}

      <svg
        viewBox="0 0 24 24"
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
        className="w-full h-full text-blue-500 overflow-visible"
        aria-label="Aegis Geometric Shield Logo"
      >
        {/* Outer Faceted Geometric Shield */}
        <path
          d="M 12 2.5 L 19.5 5.5 L 19.5 11.5 C 19.5 16.2 16.2 19.8 12 21.5 C 7.8 19.8 4.5 16.2 4.5 11.5 L 4.5 5.5 Z"
          stroke="currentColor"
          strokeWidth={stroke}
          strokeLinecap="round"
          strokeLinejoin="round"
        />

        {/* Inner Central Geometric Diamond Core */}
        <path
          d="M 12 7 L 15.5 11.2 L 12 15.4 L 8.5 11.2 Z"
          stroke="currentColor"
          strokeWidth={stroke}
          strokeLinecap="round"
          strokeLinejoin="round"
        />

        {/* Geometric Ray Lines connecting Facets */}
        <path
          d="M 12 2.5 L 12 7 M 12 15.4 L 12 21.5 M 4.5 5.5 L 8.5 11.2 M 19.5 5.5 L 15.5 11.2"
          stroke="currentColor"
          strokeWidth={stroke * 0.9}
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeOpacity="0.75"
        />
      </svg>

      {/* Optional Realtime Status Indicator Dot */}
      {showStatus && (
        <span
          className={`absolute ${dot} rounded-full ring-2 ${statusColors[status]} shadow-xs`}
        />
      )}
    </div>
  );
};

interface AegisBrandProps {
  size?: 'sm' | 'md' | 'lg';
  className?: string;
  version?: string;
  subtitle?: string;
}

export const AegisBrand: React.FC<AegisBrandProps> = ({
  size = 'sm',
  className = '',
  version = 'v4.0',
  subtitle,
}) => {
  return (
    <div className={`flex items-center gap-2 select-none ${className}`}>
      <AegisLogo size={size} />
      <div className="flex flex-col">
        <div className="flex items-center gap-1.5">
          <span className="font-bold text-slate-800 tracking-tight text-sm">
            Aegis<span className="text-blue-600 font-extrabold">Agent</span>
          </span>
          {version && (
            <span className="px-1.5 py-0.2 bg-slate-100 text-slate-600 font-mono text-[10px] rounded border border-slate-200/80 font-medium">
              {version}
            </span>
          )}
        </div>
        {subtitle && (
          <span className="text-[10px] text-slate-400 font-sans tracking-normal -mt-0.5">
            {subtitle}
          </span>
        )}
      </div>
    </div>
  );
};
