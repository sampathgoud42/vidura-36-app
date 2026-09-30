import React, {
  useCallback, useLayoutEffect, useMemo, useState,
} from 'react';
import { Link } from 'react-router-dom';
import { auth } from '../shared/viduraApi.js';
import {
  ExperienceContext, LITE, REGULAR, previousExperience, saveExperience,
  savedExperience, setRunningExperience, useExperience,
} from '../shared/experience.js';
import { ExperienceIcon } from '../shared/ExperienceControls.jsx';
import './experienceGate.css';

// Lightweight or Regular, asked once per session, straight after sign-in.
//
// Sits inside LoginGate, so it only ever runs for a signed-in operator, and it
// renders nothing but the question until the question has an answer. No world
// mounts before then, so nothing is fetched before the operator has said how
// much of the desk to run.
//
// The answer is the key of everything below it. Switching remounts the world
// on screen from scratch, which is what makes a switch honest: every timer and
// socket the old experience started is torn down with it, and the new one
// starts its own. Nothing has to be told to stop polling.

const CHOICES = [
  {
    mode: LITE,
    name: 'Lightweight Mode',
    blurb: 'Just the five panels for trading, each refreshing on its own. '
      + 'Everything else on the desk, and every feed behind it, stays off.',
    points: ['Trade & auto-trade', 'One large chart (SPY, or your pick)', 'Managed positions',
      'Super signals', 'Best pair'],
    go: 'Use lightweight',
  },
  {
    mode: REGULAR,
    name: 'Regular Mode',
    blurb: 'The full desk as it always runs, every panel on its standard '
      + 'refresh.',
    points: ['Every panel and board', 'The multi-chart grid', 'Live index stream',
      'HOT scan, options flow, tickers', 'Bot Station'],
    go: 'Use regular',
  },
];

export default function ExperienceGate({ children }) {
  const [mode, setMode] = useState(savedExperience);

  // A layout effect, so it lands before any effect below it: a board's first
  // requests go out from its effects, and the API client has to know what it
  // is serving by then.
  useLayoutEffect(() => {
    setRunningExperience(mode);
    return () => setRunningExperience(null);
  }, [mode]);

  const choose = useCallback((next) => {
    saveExperience(next);
    setMode(next);
  }, []);

  const value = useMemo(() => ({ mode, lite: mode === LITE, choose }), [mode, choose]);

  if (!mode) return <ExperienceChooser onChoose={choose} />;

  return (
    <ExperienceContext.Provider value={value}>
      <React.Fragment key={mode}>{children}</React.Fragment>
    </ExperienceContext.Provider>
  );
}

function ExperienceChooser({ onChoose }) {
  const last = previousExperience();
  const [leaving, setLeaving] = useState(false);

  // Nothing else is on the page, so the keyboard starts on an answer: the one
  // given last time, which Enter then repeats, or the first when there is none.
  // (The tab keeps LoginGate's title: like the sign-in, this has no world yet.)
  const first = last || LITE;

  // The one way out of a blocking screen that is not an answer.
  const signOut = async () => {
    setLeaving(true);
    await auth.logout().catch(() => { /* the token dies locally either way */ });
    window.location.reload();
  };

  return (
    <div className="xp-root">
      <main className="xp-center">
        <div className="xp-stack" role="dialog" aria-modal="true"
          aria-labelledby="xp-title" aria-describedby="xp-sub">
          <p className="xp-kicker">signed in</p>
          <h1 className="xp-title" id="xp-title">Choose your experience</h1>
          <p className="xp-sub" id="xp-sub">
            For this session on this device. You can switch at any time from the header.
          </p>

          <div className="xp-options">
            {CHOICES.map((c) => (
              <button key={c.mode} type="button" className={`xp-card ${c.mode}`}
                autoFocus={c.mode === first} disabled={leaving}
                onClick={() => onChoose(c.mode)}>
                <span className="xp-card-hd">
                  <ExperienceIcon mode={c.mode} className="xp-icon" />
                  <span className="xp-name">{c.name}</span>
                  {c.mode === last && <span className="xp-last">last used</span>}
                </span>
                <span className="xp-blurb">{c.blurb}</span>
                <span className="xp-points">
                  {c.points.map((p) => <span key={p} className="xp-point">{p}</span>)}
                </span>
                <span className="xp-go">{c.go} &rarr;</span>
              </button>
            ))}
          </div>

          <button type="button" className="xp-signout" onClick={signOut} disabled={leaving}>
            {leaving ? 'signing out…' : 'not you? sign out'}
          </button>
        </div>
      </main>
    </div>
  );
}

/** A world with no Lightweight form. In that mode it says so -- the same wall
 * a disabled world gets -- instead of mounting and starting the very feeds the
 * mode switched off. Its bundle is not even fetched. */
export function RegularOnly({ world, children }) {
  const { lite, choose } = useExperience();
  if (!lite) return children;
  return (
    <div className="wg-stop" role="alert">
      <div className="wg-card xp-wall">
        <div className="wg-mark">
          <img src="/vidura-logo.svg" alt="" width="34" height="34" />
        </div>
        <h1 className="wg-title">Regular mode only</h1>
        <p className="wg-world">{world}</p>
        <p className="wg-body">
          {world} runs live feeds of its own, and Lightweight mode keeps to
          {' '}its five panels. Switch to Regular to open it.
        </p>
        <div className="wg-open">
          <button type="button" className="wg-link" onClick={() => choose(REGULAR)}>
            switch to Regular
          </button>
          <Link className="wg-link" to="/">back to the trading desk</Link>
        </div>
      </div>
    </div>
  );
}
