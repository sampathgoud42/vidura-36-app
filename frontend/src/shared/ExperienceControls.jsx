// The parts of the Lightweight / Regular choice that live on a board: the
// mode's mark, and the switch in each world's header. The question itself is
// auth/ExperienceGate.jsx.

import React from 'react';
import { LITE, REGULAR, useExperience } from './experience.js';
import './experienceControls.css';

/** A bolt for Lightweight, a full grid for Regular. Inline SVG in
 * currentColor, so it wears whichever header it is in. */
export function ExperienceIcon({ mode, className = '' }) {
  if (mode === LITE) {
    return (
      <svg className={className} viewBox="0 0 24 24" aria-hidden="true">
        <path d="M13.4 2.6 4.9 13.5h6.2l-1.2 7.9 8.6-11h-6.3z" fill="currentColor" />
      </svg>
    );
  }
  return (
    <svg className={className} viewBox="0 0 24 24" aria-hidden="true">
      {[[3.5, 3.5], [13, 3.5], [3.5, 13], [13, 13]].map(([x, y]) => (
        <rect key={`${x}-${y}`} x={x} y={y} width="7.5" height="7.5" rx="1.6"
          fill="none" stroke="currentColor" strokeWidth="1.8" />
      ))}
    </svg>
  );
}

const SWITCH = [
  [LITE, 'lite', 'Lightweight: five panels, each refreshing on its own'],
  [REGULAR, 'regular', 'Regular: the full desk'],
];

/** Lightweight | Regular, as two buttons rather than one toggle: a lone
 * "lite" button cannot say whether it names the mode you are in or the one
 * you would switch to. Switching remounts the board (ExperienceGate.jsx). */
export function ExperienceSwitch({ className = '' }) {
  const { mode, choose } = useExperience();
  return (
    <span className={`xp-switch ${className}`} role="group" aria-label="experience">
      {SWITCH.map(([m, text, what]) => (
        <button key={m} type="button" aria-pressed={mode === m}
          className={mode === m ? 'on' : ''}
          onClick={() => { if (mode !== m) choose(m); }}
          title={mode === m ? `${what} (on)` : `switch to ${what}`}>
          <ExperienceIcon mode={m} className="xp-switch-ic" />
          <span className="xp-switch-txt">{text}</span>
        </button>
      ))}
    </span>
  );
}
