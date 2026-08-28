import React, { useEffect, useState } from 'react';
import { Navigate, useLocation } from 'react-router-dom';
import { api, ensureUser } from '../shared/viduraApi.js';
import './worldgate.css';

// Per-operator world flags, from worlds.json on the server.
//
// A disabled world is a HARD STOP, not a hidden link: someone following an
// old bookmark is told why, rather than landing on a blank page. It is
// advisory rather than a security boundary — every endpoint underneath
// stays behind the same login it always had — so the message says "disabled"
// and not "denied".

let cached = null;          // one fetch per page load, shared by every route

export function useWorlds() {
  const [state, setState] = useState(cached);

  useEffect(() => {
    if (cached) return undefined;
    let dead = false;
    (async () => {
      try {
        // /auth/me answers identity AND world access together. This used to
        // be two calls, the second passing user_id — which is what let the
        // desk ask about somebody else's worlds. One call, one round trip
        // fewer, and no way to ask on another operator's behalf.
        const user = await ensureUser();
        if (dead) return;
        cached = {
          worlds: user.worlds || {},
          default: user.default || null,
          any_enabled: Object.values(user.worlds || {}).some(Boolean),
          user,
        };
        setState(cached);
      } catch (e) {
        // Never lock the operator out because the flag service hiccuped:
        // failing open here is the safe direction, since the real gate is
        // the login they already passed.
        if (dead) return;
        cached = { worlds: {}, default: null, any_enabled: true, user: null,
          error: e?.detail || e?.message || 'world flags unavailable' };
        setState(cached);
      }
    })();
    return () => { dead = true; };
  }, []);

  return state;
}

export function WorldGate({ id, children }) {
  const worlds = useWorlds();
  const location = useLocation();

  if (!worlds) return <div className="wg-wait">checking access…</div>;

  // Unknown to the config = allowed. Only an explicit false closes a world.
  const enabled = worlds.worlds?.[id] !== false;
  if (enabled) return children;

  const open = Object.entries(worlds.worlds || {})
    .filter(([, on]) => on).map(([w]) => w);

  return (
    <div className="wg-stop" role="alert">
      <div className="wg-card">
        <div className="wg-mark">
          <img src="/vidura-logo.svg" alt="" width="34" height="34" />
        </div>
        <h1 className="wg-title">World disabled</h1>
        <p className="wg-world">{id}</p>
        <p className="wg-body">
          This world is switched off for
          {' '}<b>{worlds.user?.username || 'your account'}</b>.
          {' '}Contact your administrator to have it enabled.
        </p>
        {open.length > 0 && (
          <div className="wg-open">
            <span className="wg-openk">still open to you</span>
            {open.map((w) => (
              <a key={w} className="wg-link" href={`/${w}`}>{w}</a>
            ))}
          </div>
        )}
        <p className="wg-path">{location.pathname}</p>
      </div>
    </div>
  );
}

const isMobile = () => {
  const ua = navigator.userAgent;
  if (/iPhone|iPod|Android.*Mobile/i.test(ua)) return true;
  if (/iPad/i.test(ua)) return true;
  if (/Android/i.test(ua) && !/Windows/i.test(ua)) return true;
  return false;
};

/** Send "/" to whichever world this operator actually lands on. */
export function DefaultWorld() {
  const worlds = useWorlds();
  if (!worlds) return <div className="wg-wait">loading…</div>;

  if (!worlds.any_enabled) {
    return (
      <div className="wg-stop" role="alert">
        <div className="wg-card">
          <div className="wg-mark">
            <img src="/vidura-logo.svg" alt="" width="34" height="34" />
          </div>
          <h1 className="wg-title">No worlds enabled</h1>
          <p className="wg-body">
            Every world is switched off for
            {' '}<b>{worlds.user?.username || 'your account'}</b>.
            {' '}Contact your administrator.
          </p>
        </div>
      </div>
    );
  }
  const target = isMobile() ? '36-trade-desk' : 'tradier-platform';
  return <Navigate to={`/${target}`} replace />;
}
