// Lightweight, Regular or Bot only: the experience an operator picks right
// after signing in (auth/ExperienceGate.jsx), and the one fact the rest of the
// app reads to decide how much of itself to run.
//
//   lite     five panels and nothing else, each on its usual timer. The
//            API client refuses every request outside them (viduraApi.js,
//            LITE_PATHS), so what the board leaves out stays out.
//   regular  every panel, every chart, every feed on its usual timer.
//   bot      the Bot Station and nothing else. Every route leads there (the
//            gate redirects), and the API client refuses every request that
//            is not the Bot Station's own (BOT_PATHS) -- no other world's
//            feed, chart or scan is ever asked for.
//
// The choice lasts one SESSION. It is stored beside the session token and
// forgotten wherever the token changes hands -- a new sign-in, a sign-out, an
// idle sign-out, a 401, a stale token found on load (all in viduraApi.js) -- so
// a reload or a second tab inside the session keeps it, and the next session
// asks again. The previous answer is kept apart, only so the question can
// offer it first.
//
// Data and a context, deliberately free of any component: viduraApi.js reads
// it on every request, and must not drag UI into the entry bundle to do so.

import { createContext, useContext } from 'react';

export const LITE = 'lite';
export const REGULAR = 'regular';
export const BOT = 'bot';
const MODES = [LITE, REGULAR, BOT];

// Where Bot only mode lives: the one world it opens.
export const BOT_HOME = '/bot-station';

const KEY = 'vidura.experience';            // this session's answer
const LAST_KEY = 'vidura.experience.last';  // the last answer on this device

function read(key) {
  try {
    const v = localStorage.getItem(key);
    return MODES.includes(v) ? v : null;
  } catch {
    return null;                             // private mode: asked each load
  }
}

/** This session's choice, or null while it has not been made. */
export const savedExperience = () => read(KEY);

/** The last choice made on this device, in whichever session. */
export const previousExperience = () => read(LAST_KEY);

export function saveExperience(mode) {
  if (!MODES.includes(mode)) return;
  try {
    localStorage.setItem(KEY, mode);
    localStorage.setItem(LAST_KEY, mode);
  } catch { /* private mode: the choice holds for this page load only */ }
}

/** A session ended, or a new one began: the next board asks again. */
export function forgetExperience() {
  try { localStorage.removeItem(KEY); } catch { /* nothing to forget */ }
}

// ---- what THIS tab is running ---------------------------------------------
// Set by the gate for as long as a board is on screen, and read by the API
// client on every request. Deliberately not the stored value: a sign-in in
// another tab forgets that, and must not change what this tab may call while
// this tab's board is still up.
let running = null;

export function setRunningExperience(mode) { running = mode; }

export const liteRunning = () => running === LITE;
export const botRunning = () => running === BOT;

// ---- React -----------------------------------------------------------------
// Outside a gate (a probe, a one-off render) everything reads as Regular: the
// app exactly as it was before there was a choice.
export const ExperienceContext = createContext({
  mode: REGULAR, lite: false, bot: false, choose: () => {},
});

export const useExperience = () => useContext(ExperienceContext);
