import React, { useCallback, useEffect, useRef, useState } from 'react';
import { auth, onSessionExpired } from '../shared/viduraApi.js';
import { SIGNED_OUT_TITLE, titleForPath } from '../shared/worlds.js';
import './login.css';

// Wraps the whole desk. Nothing inside renders until the API has confirmed a
// session, so a signed-out browser never mounts the desk's polling effects
// and never fires a request it would only get a 401 for.
//
// Three states: 'checking' (asking the API about a stored token), 'in', and
// 'out' (show the form). 'checking' has its own full-screen hold so an
// already-signed-in operator does not see the login form flash on every
// reload.
// Idle timeout. The server's session lasts 12 hours so a trading day never
// interrupts itself, but a desk that can place real orders should not sit
// unlocked on a screen nobody is at. Two hours of no input signs out here
// and returns to the login screen.
//
// Deliberately input-driven rather than a plain timer: the board polls
// constantly, so "there was traffic" proves nothing about whether a person
// is present. Only a pointer, key, scroll or touch counts.
const IDLE_MS = 2 * 60 * 60 * 1000;
const IDLE_EVENTS = ['pointerdown', 'keydown', 'wheel', 'touchstart', 'focus'];

function useIdleLogout(active, onIdle) {
  useEffect(() => {
    if (!active) return undefined;
    let timer;
    const arm = () => {
      clearTimeout(timer);
      timer = setTimeout(onIdle, IDLE_MS);
    };
    // A tab restored from the background may have been away longer than the
    // window, so re-check on visibility rather than trusting the timer.
    const onVis = () => { if (!document.hidden) arm(); };
    IDLE_EVENTS.forEach((e) => window.addEventListener(e, arm, { passive: true }));
    document.addEventListener('visibilitychange', onVis);
    arm();
    return () => {
      clearTimeout(timer);
      IDLE_EVENTS.forEach((e) => window.removeEventListener(e, arm));
      document.removeEventListener('visibilitychange', onVis);
    };
  }, [active, onIdle]);
}

export default function LoginGate({ children }) {
  const [phase, setPhase] = useState('checking');
  const [username, setUsername] = useState('sampath');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [mode, setMode] = useState(null);          // paper | live | null
  const passwordRef = useRef(null);

  // On load: if the server does not require a login, go straight in.
  // Otherwise a stored token is validated against /auth/me — expired or
  // revoked tokens are cleared rather than left to 401 every later call.
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const status = await auth.status();
        if (cancelled) return;
        if (!status.login_required) { setPhase('in'); return; }
        if (auth.token() && (await auth.me().catch(() => null))) {
          if (!cancelled) setPhase('in');
          return;
        }
        auth.clearToken();
        if (!cancelled) setPhase('out');
      } catch {
        // The API is unreachable. Showing the form is the honest state:
        // the sign-in attempt will report the real connection error.
        if (!cancelled) setPhase('out');
      }
    })();
    return () => { cancelled = true; };
  }, []);

  // Paper vs live is the single most important thing to know before typing a
  // password into a trading desk, so the gate says which one this is.
  useEffect(() => {
    if (phase !== 'out') return;
    auth.health()
      .then((h) => setMode(h.paper_only ? 'paper' : 'live'))
      .catch(() => setMode(null));
  }, [phase]);

  useEffect(() => {
    if (phase === 'out') passwordRef.current?.focus();
  }, [phase]);

  // Why the form is showing, when it is not simply "you are not signed in".
  const [reason, setReason] = useState('');
  const signOutIdle = useCallback(async () => {
    await auth.logout().catch(() => { /* the token dies locally either way */ });
    setReason('signed out after 2 hours idle');
    setPhase('out');
  }, []);
  useIdleLogout(phase === 'in', signOutIdle);

  // The API answered 401 to a live call: the session died under the desk,
  // almost always because the server restarted (sessions are in-memory).
  // Route to the form instead of leaving every panel to render its own
  // copy of "Sign in to use this desk".
  useEffect(() => onSessionExpired((detail) => {
    setReason(detail && /idle/i.test(detail) ? detail : 'your session ended - sign in again');
    setPhase('out');
  }), []);

  const submit = useCallback(async (e) => {
    e.preventDefault();
    if (busy) return;
    setError('');
    setBusy(true);
    try {
      await auth.login(username.trim(), password);
      setPassword('');
      setReason('');
      setPhase('in');
    } catch (err) {
      setError(err?.detail || err?.message || 'Sign-in failed');
      setPassword('');
      passwordRef.current?.focus();
    } finally {
      setBusy(false);
    }
  }, [busy, username, password]);

  // Signed out (or still checking) the tab carries the app, not a world —
  // there is no world yet. PageTitle takes it back over once we are in.
  useEffect(() => {
    if (phase === 'in') {
      document.title = titleForPath(window.location.pathname);
      return;
    }
    document.title = SIGNED_OUT_TITLE;
  }, [phase]);

  if (phase === 'in') return children;

  if (phase === 'checking') {
    return <div className="lg-checking">signing in…</div>;
  }

  return (
    <div className="lg-root">
      <img src="/img/hero-vidura-bg.webp" alt="" className="lg-hero" />
      <div className="lg-veil" />
      <div className="lg-ring" style={{ height: '46vmin', width: '46vmin' }} />
      <div
        className="lg-ring"
        style={{
          height: '64vmin',
          width: '64vmin',
          animationDuration: '95s',
          animationDirection: 'reverse',
        }}
      />

      <div className="lg-stack">
        <p className="lg-kicker">Welcome to</p>
        <h1 style={{ margin: 0 }}>
          <span className="sr-only">VIDURA WORLD</span>
          <img src="/img/title-vidura.webp" alt="" className="lg-title" />
        </h1>
        <p className="lg-tagline">Tradier Options Desk</p>

        <form className="lg-card" onSubmit={submit}>
          <h2 className="lg-card-title">Sign in</h2>
          <p className="lg-card-sub">
            {reason || 'Your operator password'}
          </p>

          <div className="lg-field">
            <label className="lg-label" htmlFor="lg-user">Operator</label>
            <input
              id="lg-user"
              className="lg-input"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              autoComplete="username"
              spellCheck={false}
              disabled={busy}
            />
          </div>

          <div className="lg-field">
            <label className="lg-label" htmlFor="lg-pass">Password</label>
            <input
              id="lg-pass"
              ref={passwordRef}
              className="lg-input"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete="current-password"
              placeholder="••••••••"
              disabled={busy}
            />
          </div>

          <button className="lg-btn" type="submit" disabled={busy || !password}>
            {busy ? 'Signing in…' : 'Enter the desk'}
          </button>

          {error && <div className="lg-error" role="alert">{error}</div>}

          {mode && (
            <div className={`lg-mode ${mode}`}>
              {mode === 'live'
                ? '● live trading — real orders'
                : '○ paper — sandbox only'}
            </div>
          )}
        </form>
      </div>

      <div className="lg-foot">© {new Date().getFullYear()} Vidura World — by Sampath</div>
    </div>
  );
}
