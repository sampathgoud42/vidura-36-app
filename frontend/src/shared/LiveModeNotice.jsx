// Shown whenever a world's mode toggle is set to LIVE.
//
// Two states, both worth saying out loud before anyone clicks start:
//   locked   — the server runs TBOT_PAPER_ONLY=true, so a live start will
//              be refused. Say so up front and give the exact commands.
//   armed    — live is unlocked: the next start places REAL orders.

import React, { useEffect, useState } from 'react';
import { vidura } from './viduraApi.js';
import './liveMode.css';

// One /health probe shared by every notice on the page, with a short TTL so
// that unlocking the server (restart with TBOT_PAPER_ONLY=false) is picked
// up by toggling PAPER→LIVE again instead of needing a full page reload.
const LOCK_TTL_MS = 30000;
let _cached = null;
let _cachedAt = 0;

function fresh() {
  return _cached && performance.now() - _cachedAt < LOCK_TTL_MS ? _cached : null;
}

export function useLiveLock(active) {
  const [state, setState] = useState(fresh);
  useEffect(() => {
    if (!active) return undefined;
    const hit = fresh();
    if (hit) { setState(hit); return undefined; }
    let alive = true;
    vidura
      .health()
      .then((h) => {
        _cached = { paperOnly: h.paper_only !== false, ok: true };
        _cachedAt = performance.now();
        if (alive) setState(_cached);
      })
      .catch(() => {
        // API unreachable — a live start cannot succeed either way.
        if (alive) setState({ paperOnly: true, ok: false });
      });
    return () => { alive = false; };
  }, [active]);
  return state;
}

export default function LiveModeNotice({ mode, accent = '#f87171' }) {
  const live = mode === 'live';
  const lock = useLiveLock(live);
  if (!live) return null;

  if (lock && !lock.paperOnly) {
    return (
      <div className="vw-live-note armed" style={{ '--lm': accent }} role="alert">
        <b>🔴 LIVE ARMED — real money.</b> The next start places real orders on
        Kalshi with the credentials in your user folder. Check your balance and
        contract size first; the bot will not ask again after the confirmation.
      </div>
    );
  }

  return (
    <div className="vw-live-note locked" role="alert">
      <b>🔒 Live trading is locked on this server.</b> Starting in LIVE will be
      refused (<code>TBOT_PAPER_ONLY=true</code>). This is a deliberate guard —
      unlock it yourself, from a terminal, when you mean to trade real money:
      <pre>set TBOT_PAPER_ONLY=false{'\n'}restart.bat</pre>
      <span className="vw-live-hint">
        Until then PAPER runs the identical engine with simulated fills.
      </span>
    </div>
  );
}
