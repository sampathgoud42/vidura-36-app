// Signal sounds — two synthesized tones (Web Audio, no audio assets):
//   LONG  → bright rising chime  (C5 → G5 sines)
//   SHORT → dark falling tone    (G4 → A3 triangles)
// Used by <GlobalSignalSound> so a new live-desk signal is audible on ANY of
// the seven Vidura World sites. The on/off preference persists in the browser.
//
// Browser autoplay rules: an AudioContext starts suspended until the user
// interacts with the page. The 🔊 toggle click unlocks it immediately; after a
// full reload the first click/keypress anywhere re-unlocks it.

const KEY = 'vidura.signalsound';
let ctx = null;

export const soundEnabled = () => {
  try { return localStorage.getItem(KEY) !== '0'; } catch { return true; }
};
export const setSoundEnabled = (on) => {
  try { localStorage.setItem(KEY, on ? '1' : '0'); } catch { /* ignore */ }
};

function ensureCtx() {
  if (typeof window === 'undefined') return null;
  if (!ctx) {
    const AC = window.AudioContext || window.webkitAudioContext;
    if (!AC) return null;
    ctx = new AC();
    const unlock = () => { if (ctx && ctx.state === 'suspended') ctx.resume().catch(() => {}); };
    window.addEventListener('pointerdown', unlock, { passive: true });
    window.addEventListener('keydown', unlock);
  }
  if (ctx.state === 'suspended') ctx.resume().catch(() => {});
  return ctx;
}

function tone(c, { freq, to = freq, at, dur, type = 'sine', vol = 0.18 }) {
  const o = c.createOscillator();
  const g = c.createGain();
  o.type = type;
  o.frequency.setValueAtTime(freq, at);
  if (to !== freq) o.frequency.exponentialRampToValueAtTime(to, at + dur);
  g.gain.setValueAtTime(0.0001, at);
  g.gain.exponentialRampToValueAtTime(vol, at + 0.02);
  g.gain.exponentialRampToValueAtTime(0.0001, at + dur);
  o.connect(g).connect(c.destination);
  o.start(at);
  o.stop(at + dur + 0.05);
}

// arm the autoplay-unlock listeners early (call once at app mount) so the
// first click anywhere unlocks audio before the first sound is needed
export function initAudio() {
  ensureCtx();
}

// Wellness reminder chime — a meditation singing-bowl strike: fundamental plus
// slightly-detuned partials with a long soft decay, then a gentle major-third
// echo. Deliberately calm and classy — nothing like the trading tones.
export function playWellnessChime() {
  try { window.dispatchEvent(new CustomEvent('vidura-wellness-chime')); } catch { /* ignore */ }
  const c = ensureCtx();
  if (!c || c.state !== 'running') return; // locked until first user gesture
  const t0 = c.currentTime + 0.02;
  const strike = (at, base, vol) => {
    [[1, vol], [2.01, vol * 0.42], [2.98, vol * 0.2], [4.16, vol * 0.09]].forEach(([m, v]) => {
      const o = c.createOscillator();
      const g = c.createGain();
      o.type = 'sine';
      o.frequency.setValueAtTime(base * m, at);
      g.gain.setValueAtTime(0.0001, at);
      g.gain.exponentialRampToValueAtTime(v, at + 0.03);
      g.gain.exponentialRampToValueAtTime(0.0001, at + 2.2);
      o.connect(g).connect(c.destination);
      o.start(at);
      o.stop(at + 2.3);
    });
  };
  strike(t0, 523.25, 0.14);        // C5 bowl strike
  strike(t0 + 0.55, 659.25, 0.08); // soft E5 echo shimmer
}

// Wealth-pot opening — a warm gong swell with a cascade of bright coin tings
// tumbling out (used when the Super-Signals live desk ignites).
export function playWealthPot() {
  try { window.dispatchEvent(new CustomEvent('vidura-wealth-pot')); } catch { /* ignore */ }
  if (!soundEnabled()) return;
  const c = ensureCtx();
  if (!c || c.state !== 'running') return;
  const t0 = c.currentTime + 0.02;
  // the pot: low golden gong swell (fundamental + detuned partial, slow decay)
  [[130.8, 0.22, 3.2], [196.0, 0.1, 2.6], [261.6, 0.06, 2.2]].forEach(([f, v, dur]) => {
    const o = c.createOscillator();
    const g = c.createGain();
    o.type = 'sine';
    o.frequency.setValueAtTime(f, t0);
    g.gain.setValueAtTime(0.0001, t0);
    g.gain.exponentialRampToValueAtTime(v, t0 + 0.25);
    g.gain.exponentialRampToValueAtTime(0.0001, t0 + dur);
    o.connect(g).connect(c.destination);
    o.start(t0); o.stop(t0 + dur + 0.1);
  });
  // the coins: ~14 bright tings tumbling out, dense then sparse
  const notes = [1568, 1760, 2093, 2349, 2637, 3136];
  for (let i = 0; i < 14; i++) {
    const at = t0 + 0.15 + Math.pow(i / 14, 1.6) * 2.0;
    const f = notes[Math.floor(Math.random() * notes.length)] * (0.98 + Math.random() * 0.04);
    tone(c, { freq: f, at, dur: 0.09 + Math.random() * 0.06, type: 'sine', vol: 0.05 + Math.random() * 0.05 });
  }
}

export function playSignalSound(dir) {
  if (!soundEnabled()) return;
  // observable hook for tests/extensions — fired whenever a play is attempted
  try { window.dispatchEvent(new CustomEvent('vidura-signal-sound', { detail: { dir } })); } catch { /* ignore */ }
  const c = ensureCtx();
  if (!c || c.state !== 'running') return; // locked until first user gesture
  const t = c.currentTime + 0.01;
  if (dir === 'SHORT') {
    tone(c, { freq: 392, to: 330, at: t, dur: 0.16, type: 'triangle', vol: 0.22 });
    tone(c, { freq: 294, to: 220, at: t + 0.17, dur: 0.24, type: 'triangle', vol: 0.22 });
  } else {
    tone(c, { freq: 523, at: t, dur: 0.12 });
    tone(c, { freq: 784, at: t + 0.13, dur: 0.18 });
  }
}

// Hot signal — an urgent klaxon for a signal that keeps repeating (fires more
// than twice within 20 min). Two rising three-blip alarm bursts (square waves)
// plus a bright sparkle flourish — deliberately more insistent than the normal
// signal chime so a persistent setup grabs attention.
export function playHotSignal() {
  if (!soundEnabled()) return;
  try { window.dispatchEvent(new CustomEvent('vidura-hot-signal')); } catch { /* ignore */ }
  const c = ensureCtx();
  if (!c || c.state !== 'running') return;
  const t0 = c.currentTime + 0.01;
  [880, 1174, 1568, 880, 1174, 1568].forEach((f, i) => {
    tone(c, { freq: f, at: t0 + i * 0.11, dur: 0.09, type: 'square', vol: 0.13 });
  });
  for (let i = 0; i < 6; i++) {
    tone(c, { freq: 2093 + Math.random() * 900, at: t0 + 0.68 + i * 0.05, dur: 0.06, type: 'sine', vol: 0.06 });
  }
}
