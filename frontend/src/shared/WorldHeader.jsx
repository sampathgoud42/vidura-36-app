// Desk header: ⌂ home, the world switcher, the external-apps menu and the
// app-wide notification toggle. It takes an accent colour because each
// world sets its own, and WORLDS below is the switcher's whole source of
// truth — add a route to App.jsx and an entry here and it appears.
//
// The 36 Trade Desk deliberately does NOT use this header: at 393px there
// is no room for it, so it carries its own compact bar whose mark links
// back to the Tradier Platform, where this switcher lives.

import React, { useEffect, useRef, useState } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { notifyEnabled, setNotifyEnabled } from './GlobalViduraNotify.jsx';
import { soundEnabled, setSoundEnabled, initAudio } from '../signalSounds.js';
import { auth } from './viduraApi.js';
import { confirmDialog } from './Dialog.jsx';
import { WORLDS } from './worlds.js';

// The list lives in worlds.js so App.jsx can read the titles without
// importing this component into the entry bundle. Re-exported here because
// this is where every caller already looks for it.
export { WORLDS } from './worlds.js';

// External companion apps — shown in their own burger, always new tabs.
export function externalApps() {
  return [
    { label: 'Trading View', icon: '📊', href: 'https://www.tradingview.com/chart/OI0ZrHVM/?symbol=QQQ', blurb: 'QQQ chart' },
    { label: 'G-Finance', icon: '📉', href: 'https://www.google.com/finance/beta/', blurb: 'google finance' },
    { label: 'Robin Hood', icon: '🏹', href: 'https://robinhood.com/us/en/legend/', blurb: 'legend desk' },
    { label: 'Kalshi', icon: '🎯', href: 'https://kalshi.com/portfolio', blurb: 'portfolio' },
  ];
}

// ── header iconography (inline SVG, currentColor — blends with any accent) ──
// The Vidura mark: a lotus-cup "V" holding a bindu (the counselor's third
// eye) inside a thin golden ring. Hand-drawn SVG — no Gemini API key exists
// on this machine, so nano-banana generation wasn't possible; swap the SVG
// for a generated /img asset later if one is produced.
function ViduraMark() {
  return (
    <svg className="vw-mark-svg" viewBox="0 0 48 48" aria-hidden="true">
      <defs>
        <linearGradient id="vw-gold" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#ffd166" />
          <stop offset="1" stopColor="#ff8a2b" />
        </linearGradient>
      </defs>
      <circle cx="24" cy="24" r="21" fill="none" stroke="url(#vw-gold)" strokeWidth="2" opacity="0.85" />
      <path d="M13.5 16 Q17.5 30 24 36.5 Q30.5 30 34.5 16" fill="none"
        stroke="url(#vw-gold)" strokeWidth="3.4" strokeLinecap="round" />
      <circle cx="24" cy="12.6" r="2.7" fill="url(#vw-gold)" />
    </svg>
  );
}

function IconWorlds() {
  return (
    <svg className="vw-ic" viewBox="0 0 24 24" aria-hidden="true">
      <circle cx="12" cy="12" r="5" fill="none" stroke="currentColor" strokeWidth="1.7" />
      <ellipse cx="12" cy="12" rx="10" ry="3.4" fill="none" stroke="currentColor"
        strokeWidth="1.4" transform="rotate(-18 12 12)" opacity="0.8" />
    </svg>
  );
}

function IconApps() {
  return (
    <svg className="vw-ic" viewBox="0 0 24 24" aria-hidden="true">
      {[[4, 4], [14, 4], [4, 14]].map(([x, y]) => (
        <rect key={`${x}${y}`} x={x} y={y} width="6" height="6" rx="1.6"
          fill="none" stroke="currentColor" strokeWidth="1.6" />
      ))}
      <path d="M15 19 L21 13 M21 13 v4 M21 13 h-4" fill="none" stroke="currentColor"
        strokeWidth="1.6" strokeLinecap="round" />
    </svg>
  );
}

function IconSound({ off }) {
  return (
    <svg className="vw-ic" viewBox="0 0 24 24" aria-hidden="true">
      <path d="M4 9.5 v5 h3.5 L13 19 V5 L7.5 9.5 Z" fill="currentColor" opacity="0.9" />
      {!off && (
        <path d="M15.5 9 Q17.5 12 15.5 15 M18 6.5 Q21.5 12 18 17.5" fill="none"
          stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" />
      )}
      {off && <path className="vw-ic-off" d="M15 9 L21 15 M21 9 L15 15" />}
    </svg>
  );
}

function IconBell({ off }) {
  return (
    <svg className="vw-ic" viewBox="0 0 24 24" aria-hidden="true">
      <path d="M12 4 a5.2 5.2 0 0 1 5.2 5.2 c0 3.4 1.2 4.6 2 5.4 H4.8 c0.8 -0.8 2 -2 2 -5.4 A5.2 5.2 0 0 1 12 4 Z"
        fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinejoin="round" />
      <path d="M10 17.5 a2 2 0 0 0 4 0" fill="none" stroke="currentColor" strokeWidth="1.7" />
      {off && <path className="vw-ic-off" d="M6 6 L18 18 M18 6 L6 18" />}
    </svg>
  );
}

// A door with an arrow leaving it. Not a power symbol: this ends YOUR
// session, it does not stop the desk, and on a board that can place real
// orders those two must not look alike.
function IconSignOut() {
  return (
    <svg className="vw-ic" viewBox="0 0 24 24" aria-hidden="true">
      <path d="M14 4.5 H6.5 a1.5 1.5 0 0 0 -1.5 1.5 v12 a1.5 1.5 0 0 0 1.5 1.5 H14"
        fill="none" stroke="currentColor" strokeWidth="1.7"
        strokeLinecap="round" strokeLinejoin="round" />
      <path d="M12.5 12 H21 M18 8.6 L21.4 12 L18 15.4" fill="none"
        stroke="currentColor" strokeWidth="1.7"
        strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

export default function WorldHeader({ accent = '#34d399', title, right = null, showSound = false }) {
  const [open, setOpen] = useState(null); // 'worlds' | 'apps' | null
  const [notify, setNotify] = useState(() => notifyEnabled());
  const [sound, setSound] = useState(() => soundEnabled());
  const { pathname } = useLocation();
  const panelRef = useRef(null);

  // close on route change, Escape, or outside tap (tap matters on iPad)
  useEffect(() => { setOpen(null); }, [pathname]);

  // Publish the header's real height as --vw-header-h so fixed-position
  // app furniture (the wellness reminder) can sit BELOW it instead of
  // overlapping. Re-measured on resize/wrap.
  useEffect(() => {
    const el = panelRef.current;
    if (!el) return undefined;
    const publish = () => {
      const bar = el.querySelector('.vw-header-bar') || el;
      document.documentElement.style.setProperty(
        '--vw-header-h', `${Math.round(bar.getBoundingClientRect().height)}px`
      );
    };
    publish();
    const ro = new ResizeObserver(publish);
    ro.observe(el);
    window.addEventListener('resize', publish);
    return () => {
      ro.disconnect();
      window.removeEventListener('resize', publish);
      document.documentElement.style.removeProperty('--vw-header-h');
    };
  }, []);
  useEffect(() => {
    if (!open) return undefined;
    const onKey = (e) => { if (e.key === 'Escape') setOpen(null); };
    const onDown = (e) => {
      if (panelRef.current && !panelRef.current.contains(e.target)) setOpen(null);
    };
    window.addEventListener('keydown', onKey);
    window.addEventListener('pointerdown', onDown);
    return () => {
      window.removeEventListener('keydown', onKey);
      window.removeEventListener('pointerdown', onDown);
    };
  }, [open]);

  const toggleNotify = async () => {
    const next = !notify;
    setNotify(next);
    initAudio();
    await setNotifyEnabled(next);
  };

  const toggleSound = () => {
    const next = !sound;
    setSound(next);
    setSoundEnabled(next);
    initAudio();
  };

  // Signing out is server-side and global: the token dies on the API, so
  // every world and every other tab on this browser is signed out too. Worth
  // one confirmation, because a stray tap mid-session is pure annoyance on a
  // board that reloads into a password prompt.
  const signOut = async () => {
    const ok = await confirmDialog({
      title: 'Sign out of the desk?',
      body: 'This ends the session for every world - Tradier Platform, 36 '
        + 'Trades and Bot Station - and on every tab open on this browser. '
        + 'Running bots and resting orders are NOT affected.',
      confirmText: 'Sign out',
      cancelText: 'Stay signed in',
    });
    if (!ok) return;
    await auth.logout().catch(() => { /* the token dies locally either way */ });
    window.location.reload();
  };

  const current = WORLDS.find((w) => w.path !== '/' && pathname.startsWith(w.path));

  return (
    // NB: the ref must wrap the DROPDOWN MENUS too — the outside-tap closer
    // runs on pointerdown, and when it only covered the bar, a real tap on a
    // menu item unmounted the menu before its click could navigate.
    <header className="vw-header" style={{ '--vw-accent': accent }} ref={panelRef}>
      <div className="vw-header-bar">
        {/* the Vidura mark IS the home button — always first */}
        <Link to="/" className="vw-mark" title="Tradier Platform home" aria-label="Tradier Platform home">
          <ViduraMark />
        </Link>

        <div className="vw-seg" role="group" aria-label="navigation">
          <button
            type="button"
            className={`vw-seg-btn ${open === 'worlds' ? 'on' : ''}`}
            onClick={() => setOpen((o) => (o === 'worlds' ? null : 'worlds'))}
            aria-expanded={open === 'worlds'}
            aria-haspopup="menu"
            aria-label="switch world"
            title="switch world"
          >
            <IconWorlds />
            <span className="vw-hdr-txt">worlds</span>
            <span className={`vw-chev ${open === 'worlds' ? 'up' : ''}`} aria-hidden>▾</span>
          </button>
          <span className="vw-seg-div" aria-hidden />
          <button
            type="button"
            className={`vw-seg-btn apps ${open === 'apps' ? 'on' : ''}`}
            onClick={() => setOpen((o) => (o === 'apps' ? null : 'apps'))}
            aria-expanded={open === 'apps'}
            aria-haspopup="menu"
            aria-label="external apps"
            title="external apps (open in new tabs)"
          >
            <IconApps />
            <span className="vw-hdr-txt">apps</span>
            <span className={`vw-chev ${open === 'apps' ? 'up' : ''}`} aria-hidden>▾</span>
          </button>
        </div>

        {title && <span className="vw-hdr-title">{current?.icon} {title}</span>}

        <span className="vw-hdr-spacer" />

        {/* app-wide furniture docks here (the wellness routine pill portals
            in) so it rides in the header row instead of floating below it */}
        <span className="vw-hdr-slot" id="vw-header-slot" />

        {showSound && (
          <button
            type="button"
            className={`vw-icon-btn ${sound ? 'on' : 'off'}`}
            onClick={toggleSound}
            aria-label={sound ? 'signal sounds on — tap to mute' : 'signal sounds muted — tap to enable'}
            title={sound ? 'signal sounds on' : 'signal sounds muted'}
          >
            <IconSound off={!sound} />
          </button>
        )}

        <button
          type="button"
          className={`vw-icon-btn ${notify ? 'on' : 'off'}`}
          onClick={toggleNotify}
          aria-label={notify ? 'push notifications on — tap to mute' : 'enable push notifications'}
          title={notify ? 'push notifications on — tap to mute' : 'enable push notifications'}
        >
          <IconBell off={!notify} />
        </button>

        <button
          type="button"
          className="vw-icon-btn signout"
          onClick={signOut}
          aria-label="sign out of every world"
          title="sign out (all worlds)"
        >
          <IconSignOut />
        </button>

        {right}
      </div>

      {open === 'worlds' && (
        <nav className="vw-worldmenu" role="menu" aria-label="worlds">
          <div className="vw-menu-hd">
            <span>◈ switch world</span>
            <button type="button" className="vw-menu-x" onClick={() => setOpen(null)}
              aria-label="close menu">✕</button>
          </div>
          {WORLDS.map((w) => {
            const active = pathname.startsWith(w.path);
            return (
              <Link
                key={w.path}
                to={w.path}
                role="menuitem"
                className={`vw-worlditem ${active ? 'active' : ''}`}
                onClick={() => setOpen(null)}
              >
                <span className="vw-worldicon" aria-hidden>{w.icon}</span>
                <span className="vw-worldtext">
                  <b>{w.label}</b>
                  <small>{w.blurb}</small>
                </span>
                {active && <span className="vw-worlddot" aria-label="current" />}
              </Link>
            );
          })}
        </nav>
      )}

      {open === 'apps' && (
        <nav className="vw-worldmenu vw-appsmenu" role="menu" aria-label="external apps">
          <div className="vw-menu-hd apps">
            <span>⇱ external apps · new tabs</span>
            <button type="button" className="vw-menu-x" onClick={() => setOpen(null)}
              aria-label="close menu">✕</button>
          </div>
          {externalApps().map((a) => (
            <a
              key={a.label}
              href={a.href}
              target="_blank"
              rel="noopener noreferrer"
              role="menuitem"
              className="vw-worlditem"
              onClick={() => setOpen(null)}
            >
              <span className="vw-worldicon" aria-hidden>{a.icon}</span>
              <span className="vw-worldtext">
                <b>{a.label}</b>
                <small>{a.blurb} · new tab ↗</small>
              </span>
            </a>
          ))}
        </nav>
      )}
    </header>
  );
}
