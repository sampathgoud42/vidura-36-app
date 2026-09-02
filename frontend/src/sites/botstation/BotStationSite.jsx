import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { ApiError, ensureUser, vidura } from '../../shared/viduraApi.js';
import SiteFooter from '../../shared/SiteFooter.jsx';
import WorldHeader from '../../shared/WorldHeader.jsx';
import { confirmDialog } from '../../shared/Dialog.jsx';
import LiveModeNotice, { useLiveLock } from '../../shared/LiveModeNotice.jsx';
import '../../shared/worldHeader.css';
import './botstation.css';

// /bot-station — BOT Prediction Station: the Kalshi bots' mission control.
// One canvas-rendered helios core (no R3F — pure 2D canvas, immune to this
// machine's fiber pitfalls) with the three bots orbiting it; clicking a bot
// opens its launch console. Visual language adapted from the HELIOS STATION
// reference. The existing BTC / Sports worlds are untouched — this world
// drives the same backend endpoints they do.

const BOTS = [
  { key: 'btc15', label: 'BTC-15', sub: '15 min breakout', accent: '#ffb347', chip: 'b15', meter: 'sun' },
  { key: 'btc60', label: 'BTC-60', sub: 'hourly committee', accent: '#4fd6e6', chip: 'b60', meter: 'cyan' },
  { key: 'sports', label: 'SPORTS', sub: 'tennis · baseball', accent: '#9085e9', chip: 'sp', meter: 'violet' },
  { key: 'parley', label: 'PARLEY', sub: 'live-leg combos', accent: '#f26fb8', chip: 'pl', meter: 'rose' },
  { key: 'gold15', label: 'GOLD-15', sub: '15 min gold breakout', accent: '#ffd700', chip: 'g15', meter: 'gold' },
  { key: 'silver15', label: 'SILVER-15', sub: '15 min silver breakout', accent: '#c0c0c0', chip: 's15', meter: 'silver' },
  { key: 'oil15', label: 'OIL-15', sub: '15 min WTI oil breakout', accent: '#8b5e3c', chip: 'o15', meter: 'brown' },
];
const BOT_BY_KEY = Object.fromEntries(BOTS.map((b) => [b.key, b]));

const ST_COLOR = { NA: '#525a6b', IDLE: '#fab219', PAPER: '#4fd6e6', LIVE: '#2fd35b' };

const CFG_KEY = 'vidura.botstation.cfg';   // per-bot launch forms (mode excluded)

// desk-wide launch defaults; anything the user typed (and cleared) wins
const NTT_DEFAULT = '17:00-19:30, 05:00-08:00';

// The sports the parlay bot draws legs from. These are Kalshi's OWN tag names
// on its Sports series, lowercased, so they match what the scan filters on --
// a pretty label here would silently match nothing. Deselecting all of them
// means every live sport rather than none, which is what the engine does with
// an empty list: an operator should not have to name a sport for the bot to
// notice a match happening in it.
const PARLEY_SPORTS = ['tennis', 'baseball', 'soccer', 'football',
  'basketball', 'esports'];
const NTT_RE = /^$|^\s*\d{1,2}:\d{2}\s*-\s*\d{1,2}:\d{2}(\s*,\s*\d{1,2}:\d{2}\s*-\s*\d{1,2}:\d{2})*\s*$/;

const BOT_DEFAULTS = {
  btc15: { bank: '50', contracts: '25', target_pct: '30', bank_sl_pct: '20', no_trade_times: NTT_DEFAULT },
  btc60: { bank: '50', contracts: '25', target_pct: '30', bank_sl_pct: '20', no_trade_times: NTT_DEFAULT },
  sports: {
    target_pct: '30', bank_sl_pct: '20', no_trade_times: '16:00-20:00',
    sports: {
      tennis: { contracts: '25', bank: '50' },
      baseball: { contracts: '25', bank: '50' },
    },
  },
  // the parlay bot's own knobs, in the cents and counts it actually reads —
  // its defaults, so an untouched form launches the documented engine
  parley: {
    bank: '100', stake_usd: '12', max_usd: '15.6', slippage_c: '5', max_per_event: '2', escalation_pct: '30', fill_wait_s: '60', daily_enabled: false, daily_at: '17:50', daily_stake_usd: '5', daily_min_legs: '5', daily_max_legs: '24', daily_min_c: '60', bank_sl_pct: '50',
    min_prob_c: '80', min_set: '2', lead_scope: 'current',
    min_legs: '2', max_legs: '0', max_open: '1', cooldown_min: '15',
    slippage_c: '3', max_price_c: '95', tp_ceiling_c: '97', stop_loss_c: '20',
  },
  gold15: { bank: '50', contracts: '25', target_pct: '30', bank_sl_pct: '20', no_trade_times: NTT_DEFAULT },
  silver15: { bank: '50', contracts: '25', target_pct: '30', bank_sl_pct: '20', no_trade_times: NTT_DEFAULT },
  oil15: { bank: '50', contracts: '25', target_pct: '30', bank_sl_pct: '20', no_trade_times: NTT_DEFAULT },
};

function loadCfg() {
  let stored = {};
  try {
    const j = JSON.parse(localStorage.getItem(CFG_KEY));
    if (j && typeof j === 'object') stored = j;
  } catch { /* corrupt — defaults */ }
  // empty-string saves are "unset", not choices — defaults fill them
  const clean = (o) => Object.fromEntries(
    Object.entries(o || {}).filter(([, v]) => v !== '')
  );
  const out = { ...stored };
  for (const key of Object.keys(BOT_DEFAULTS)) {
    out[key] = { ...BOT_DEFAULTS[key], ...clean(stored[key]) };
    if (key === 'sports') {
      const savedSports = (stored.sports || {}).sports || {};
      out.sports.sports = Object.fromEntries(
        Object.keys(BOT_DEFAULTS.sports.sports).map((sp) => [
          sp, { ...BOT_DEFAULTS.sports.sports[sp], ...clean(savedSports[sp]) },
        ])
      );
    }
  }
  return out;
}

function errText(e) {
  if (e instanceof ApiError) {
    const d = e.detail;
    if (typeof d === 'string' && d) return d;
    // FastAPI 422s carry a LIST of error objects — rendering that raw as a
    // JSX child would throw and unmount the whole app (no ErrorBoundary)
    if (Array.isArray(d)) {
      return d.map((x) => `${(x?.loc || []).slice(1).join('.') || 'request'}: `
        + (x?.msg || JSON.stringify(x))).join(' · ');
    }
    if (d && typeof d === 'object') return JSON.stringify(d);
    return e.message || `HTTP ${e.status}`;
  }
  return 'Backend unreachable — is the Vidura API running on :8791?';
}

function usd(v) {
  if (v === null || v === undefined || Number.isNaN(Number(v))) return '—';
  const n = Number(v);
  return `${n < 0 ? '−' : ''}$${Math.abs(n).toLocaleString(undefined, {
    minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

// run-time counter: naive-UTC start -> zero-padded HH:MM:SS elapsed
function fmtElapsed(iso, nowMs) {
  if (!iso) return null;
  const t = new Date(/Z$|[+-]\d\d:?\d\d$/.test(iso) ? iso : `${iso}Z`).getTime();
  if (Number.isNaN(t)) return null;
  let s = Math.max(0, Math.floor((nowMs - t) / 1000));
  const h = Math.floor(s / 3600); s -= h * 3600;
  const m = Math.floor(s / 60); s -= m * 60;
  const p = (n) => String(n).padStart(2, '0');
  return `${p(h)}:${p(m)}:${p(s)}`;
}

function utcTs(iso) {
  if (!iso) return '—';
  const d = new Date(/Z$|[+-]\d\d:?\d\d$/.test(iso) ? iso : `${iso}Z`);
  return Number.isNaN(d.getTime()) ? iso
    : d.toLocaleString([], { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
}

// ── the helios core: canvas sun + three orbiting bot nodes ─────────────────
// Adapted from the reference station's renderer: bloom, additive corona
// particles, prominence arcs, granulation, rotating sunspots, limb
// darkening — and one orbit per bot with trail, occlusion dimming behind
// the disc, a status line drawn to the core, and canvas hit-testing.
// The disc, relative to the layout base the orbits use.
const SUN_SCALE = 1.15;

function HeliosCanvas({ bots, neon, operator, onPick, onLogs, onSunDblClick }) {
  const hostRef = useRef(null);
  const botsRef = useRef(bots);
  useEffect(() => { botsRef.current = bots; }, [bots]);
  const neonRef = useRef(neon);
  useEffect(() => { neonRef.current = neon; }, [neon]);
  const operatorRef = useRef(operator);
  useEffect(() => { operatorRef.current = operator; }, [operator]);
  const onPickRef = useRef(onPick);
  useEffect(() => { onPickRef.current = onPick; }, [onPick]);
  const onLogsRef = useRef(onLogs);
  useEffect(() => { onLogsRef.current = onLogs; }, [onLogs]);
  const onSunDblClickRef = useRef(onSunDblClick);
  useEffect(() => { onSunDblClickRef.current = onSunDblClick; }, [onSunDblClick]);

  useEffect(() => {
    const host = hostRef.current;
    const canvas = document.createElement('canvas');
    host.appendChild(canvas);
    const ctx = canvas.getContext('2d');
    const DPR = Math.min(window.devicePixelRatio || 1, 2);
    let W = 0; let H = 0;
    const resize = () => {
      W = host.clientWidth; H = host.clientHeight;
      canvas.width = W * DPR; canvas.height = H * DPR;
      canvas.style.width = `${W}px`; canvas.style.height = `${H}px`;
      ctx.setTransform(DPR, 0, 0, DPR, 0, 0);
    };
    resize();
    const ro = new ResizeObserver(resize);
    ro.observe(host);

    // corona particles
    const N = 80;
    const parts = Array.from({ length: N }, () => ({
      angle: Math.random() * Math.PI * 2,
      life: Math.random(),
      maxr: 1.35 + Math.random() * 1.0,
      size: 0.5 + Math.random() * 1.3,
      hue: 18 + Math.random() * 24,
      speed: 0.002 + Math.random() * 0.004,
    }));
    const spots = Array.from({ length: 4 }, (_, i) => ({
      lat: (Math.random() - 0.5) * 1.2, off: i * 1.7, size: 0.05 + Math.random() * 0.06,
    }));
    // deep-space lucky charms: the home screen's talismans as far-away
    // planets — ~66% transparent, scattered on their own radii, revolving
    // around the core 4-13x slower than the slowest bot, drawn FIRST so
    // the sun, orbits and nodes all pass in front of them
    const CHARM_NAMES = ['ganesha', 'dragon', 'clover', 'seven', 'cornucopia',
      'om', 'maneki', 'coins', 'kubera', 'buddha', 'lotus'];
    const charms = CHARM_NAMES.map((n) => {
      const img = new Image();
      img.src = `/img/lucky-${n}-alpha.webp`;
      return {
        img,
        th: Math.random() * Math.PI * 2,
        arf: 0.45 + Math.random() * 0.85,          // radius: mid-field to beyond the edge
        size: 20 + Math.random() * 34,             // smaller = farther
        alpha: 0.28 + Math.random() * 0.12,        // ≈ 66% transparent
        spin: (0.00002 + Math.random() * 0.00004) * (Math.random() < 0.5 ? -1 : 1),
        bobA: 3 + Math.random() * 5,
        bobP: Math.random() * Math.PI * 2,
      };
    });
    // per-bot orbit state: angle + trail + user-adjustable radius offset
    // super-slow drift: a full lap takes ~4-6 minutes, the SAME lap for
    // every bot, so the gaps seeded here are the gaps for ever
    const orbits = BOTS.map((b, i) => ({
      key: b.key, accent: b.accent, label: b.label,
      ang: (i * Math.PI * 2) / BOTS.length + 0.6,
      speed: 0.00035,
      trail: [],
      rOff: 0,
    }));
    const nodePos = {};       // key -> {x, y} CSS px, for hit-testing
    let hover = null;
    let sunHover = false;     // pointer over the disc -> sun pops, name shows
    let pop = 0;              // eased 0..1 pop amount
    let dragKey = null;       // node being dragged along its orbit
    let dragMoved = 0;        // px travelled — beyond a few, it's not a click
    let R0 = 0;               // layout base radius, updated each frame
    let t = 0;
    let last = performance.now();
    let raf = 0;

    // nearest node within 26px — adjacent orbits pass closer than 52px near
    // 12 o'clock, so first-match would open the wrong bot's console there
    const hit = (mx, my) => {
      let best = null;
      let bestD = 32;
      for (const o of orbits) {
        const p = nodePos[o.key];
        if (!p) continue;
        const d = Math.hypot(mx - p.x, my - p.y);
        if (d < bestD) { bestD = d; best = o.key; }
      }
      return best;
    };
    const onMove = (e) => {
      const r = canvas.getBoundingClientRect();
      const mx = e.clientX - r.left; const my = e.clientY - r.top;
      if (dragKey) {
        const o = orbits.find((x) => x.key === dragKey);
        if (o) {
          const prev = o.ang;
          o.ang = Math.atan2(my - H * 0.5, mx - W / 2);
          dragMoved += Math.abs(o.ang - prev) * 100;
          const idx = orbits.indexOf(o);
          const baseR = R0 * (1.5 + idx * 0.26);
          const ptrR = Math.hypot(mx - W / 2, my - H * 0.5);
          o.rOff = Math.max(-baseR * 0.35, Math.min(baseR * 0.6, ptrR - baseR));
        }
        canvas.style.cursor = 'grabbing';
        return;
      }
      hover = hit(mx, my);
      // Tracks the drawn disc, with the same forgiving margin as before,
      // so the pointer target does not lag the sun it belongs to.
      sunHover = Math.hypot(mx - W / 2, my - H * 0.5)
        < Math.min(W, H) * 0.145 * SUN_SCALE * 1.15;
      canvas.style.cursor = hover ? 'grab' : sunHover ? 'pointer' : 'default';
    };
    const onLeave = () => { hover = null; sunHover = false; };
    canvas.addEventListener('pointerleave', onLeave);
    const onDown = (e) => {
      const r = canvas.getBoundingClientRect();
      const k = hit(e.clientX - r.left, e.clientY - r.top);
      if (k) {
        dragKey = k;
        dragMoved = 0;
        try { canvas.setPointerCapture(e.pointerId); } catch { /* older browsers */ }
        canvas.style.cursor = 'grabbing';
      }
    };
    const onUp = (e) => {
      if (dragKey) {
        try { canvas.releasePointerCapture(e.pointerId); } catch { /* ignore */ }
        dragKey = null;
        canvas.style.cursor = 'grab';
      }
    };
    // single click opens the console (deferred just long enough to see if a
    // second click lands); double click launches the sci-fi log feed
    let clickTimer = 0;
    const onClick = (e) => {
      if (dragMoved > 6) { dragMoved = 0; return; }   // a drag, not a click
      const r = canvas.getBoundingClientRect();
      const k = hit(e.clientX - r.left, e.clientY - r.top);
      if (!k) return;
      clearTimeout(clickTimer);
      clickTimer = setTimeout(() => onPickRef.current(k), 280);
    };
    const onDbl = (e) => {
      if (dragMoved > 6) { dragMoved = 0; return; }
      const r = canvas.getBoundingClientRect();
      const mx = e.clientX - r.left; const my = e.clientY - r.top;
      if (Math.hypot(mx - W / 2, my - H * 0.5) < Math.min(W, H) * 0.145 * 1.15) {
        clearTimeout(clickTimer);
        if (onSunDblClickRef.current) onSunDblClickRef.current();
        return;
      }
      const k = hit(mx, my);
      if (!k) return;
      clearTimeout(clickTimer);
      onLogsRef.current(k);
    };
    canvas.addEventListener('pointerdown', onDown);
    canvas.addEventListener('pointerup', onUp);
    canvas.addEventListener('pointermove', onMove);
    canvas.addEventListener('click', onClick);
    canvas.addEventListener('dblclick', onDbl);

    const draw = (now) => {
      raf = requestAnimationFrame(draw);
      const dt = Math.min(2, (now - last) / 16.67);
      last = now;
      if (document.hidden || W < 20 || H < 20) return;
      t += 0.016 * dt;

      const cx = W / 2; const cy = H * 0.5;
      // pop: eased toward 1 while the pointer rests on the disc — the sun
      // swells ~9% and the operator reticle fades in with it
      pop += ((sunHover ? 1 : 0) - pop) * Math.min(1, 0.12 * dt);
      R0 = Math.min(W, H) * 0.145;   // layout base: orbits stay put
      // The disc is scaled off R0 rather than R0 itself being raised, because
      // R0 also sets the orbit radii -- growing it would push every bot
      // outward by the same 15% and leave the composition unchanged. Only the
      // sun moves. The innermost orbit sits at 1.5 R0, so at 1.15 there is
      // still clear space between the limb and the first ring.
      const R = R0 * SUN_SCALE * (1 + pop * 0.09);   // popped: layers swell
      ctx.clearRect(0, 0, W, H);

      // palette: NEON GREEN when the past 3H P&L is positive, solar otherwise
      const neonNow = neonRef.current === true;
      const PAL = neonNow ? {
        bloom0: 'rgba(60,255,140,0.30)', bloom1: 'rgba(30,220,110,0.11)',
        bloom2: 'rgba(10,110,50,0.05)',
        hueShift: 105,                              // corona 18-42° -> 123-147° green
        disc: ['#eaffdc', '#b6ff9e', '#54f08c', '#1fd45f', '#0a7a35'],
        gran: '220,255,180', spotRim: 'rgba(30,180,80,0.35)',
        spotCore: 'rgba(10,40,20,0.75)', limb: '10,90,30',
      } : {
        bloom0: 'rgba(255,150,50,0.28)', bloom1: 'rgba(255,110,30,0.10)',
        bloom2: 'rgba(120,60,20,0.04)',
        hueShift: 0,
        disc: ['#fff2c8', '#ffd166', '#ff9a3c', '#ff6a1f', '#c23c10'],
        gran: '255,240,180', spotRim: 'rgba(200,80,20,0.35)',
        spotCore: 'rgba(90,20,0,0.75)', limb: '120,30,0',
      };

      // deep-space charm field (deepest layer)
      for (const ch of charms) {
        if (!ch.img.complete || !ch.img.naturalWidth) continue;
        ch.th += ch.spin * dt;
        const ar = ch.arf * Math.min(W, H) * 0.52;
        const px = cx + Math.cos(ch.th) * ar;
        const py = cy + Math.sin(ch.th) * ar * 0.9 + Math.sin(t * 0.25 + ch.bobP) * ch.bobA;
        if (px < -ch.size || px > W + ch.size || py < -ch.size || py > H + ch.size) continue;
        ctx.save();
        ctx.globalAlpha = ch.alpha;
        ctx.drawImage(ch.img, px - ch.size / 2, py - ch.size / 2, ch.size, ch.size);
        ctx.restore();
      }

      // bloom
      let g = ctx.createRadialGradient(cx, cy, R * 0.4, cx, cy, R * 3.0);
      g.addColorStop(0, PAL.bloom0);
      g.addColorStop(0.28, PAL.bloom1);
      g.addColorStop(0.6, PAL.bloom2);
      g.addColorStop(1, 'rgba(0,0,0,0)');
      ctx.fillStyle = g;
      ctx.fillRect(0, 0, W, H);

      // corona particles (additive)
      ctx.globalCompositeOperation = 'lighter';
      for (const p of parts) {
        p.life += p.speed * dt;
        if (p.life > 1) { p.life = 0; p.angle = Math.random() * Math.PI * 2; }
        const fade = Math.sin(p.life * Math.PI);
        const rr = R * (1 + p.life * (p.maxr - 1));
        const px = cx + Math.cos(p.angle) * rr;
        const py = cy + Math.sin(p.angle) * rr;
        ctx.fillStyle = `hsla(${p.hue + PAL.hueShift},100%,${60 + fade * 10}%,${fade * 0.45})`;
        ctx.beginPath();
        ctx.arc(px, py, p.size, 0, Math.PI * 2);
        ctx.fill();
      }
      ctx.globalCompositeOperation = 'source-over';

      // prominence arcs — one flare per bot, burning GREEN when that bot is
      // in profit (session P&L while running, 7d P&L when idle)
      for (let i = 0; i < 3; i++) {
        const inProfit = botsRef.current[i]?.profit === true;
        const a0 = t * 0.14 + i * 2.2;
        const fh = R * (0.42 + 0.18 * Math.sin(t * 0.6 + i * 2));
        const x0 = cx + Math.cos(a0) * R; const y0 = cy + Math.sin(a0) * R;
        const x1 = cx + Math.cos(a0 + 0.5) * R; const y1 = cy + Math.sin(a0 + 0.5) * R;
        const mxp = cx + Math.cos(a0 + 0.25) * (R + fh); const myp = cy + Math.sin(a0 + 0.25) * (R + fh);
        ctx.strokeStyle = inProfit ? 'rgba(47,211,91,0.55)' : 'rgba(255,120,40,0.35)';
        ctx.lineWidth = 1.6 + Math.sin(t * 3 + i);
        ctx.beginPath();
        ctx.moveTo(x0, y0);
        ctx.quadraticCurveTo(mxp, myp, x1, y1);
        ctx.stroke();
      }

      // disc
      g = ctx.createRadialGradient(cx - R * 0.25, cy - R * 0.25, R * 0.1, cx, cy, R);
      g.addColorStop(0, PAL.disc[0]);
      g.addColorStop(0.35, PAL.disc[1]);
      g.addColorStop(0.72, PAL.disc[2]);
      g.addColorStop(0.93, PAL.disc[3]);
      g.addColorStop(1, PAL.disc[4]);
      ctx.fillStyle = g;
      ctx.beginPath();
      ctx.arc(cx, cy, R, 0, Math.PI * 2);
      ctx.fill();

      // granulation + sunspots, clipped to disc
      ctx.save();
      ctx.beginPath();
      ctx.arc(cx, cy, R, 0, Math.PI * 2);
      ctx.clip();
      ctx.globalCompositeOperation = 'overlay';
      for (let i = 0; i < 18; i++) {
        const gx = cx + Math.cos(i * 2.4 + t * 0.05) * R * 0.7;
        const gy = cy + Math.sin(i * 1.7 + t * 0.04) * R * 0.7;
        const b = 0.10 + 0.10 * Math.sin(t * 0.8 + i * 2.6);
        const gg = ctx.createRadialGradient(gx, gy, 0, gx, gy, R * 0.16);
        gg.addColorStop(0, `rgba(${PAL.gran},${Math.max(0, b)})`);
        gg.addColorStop(1, `rgba(${PAL.gran},0)`);
        ctx.fillStyle = gg;
        ctx.fillRect(gx - R * 0.2, gy - R * 0.2, R * 0.4, R * 0.4);
      }
      ctx.globalCompositeOperation = 'source-over';
      for (const s of spots) {
        const rot = t * 0.12 + s.off;
        const front = Math.cos(rot);
        if (front < 0.05) continue;
        const sx = cx + Math.sin(rot) * R * 0.86 * Math.cos(s.lat * 1.2);
        const sy = cy + s.lat * R * 0.8;
        const sr = R * s.size * front;
        const sg = ctx.createRadialGradient(sx, sy, 0, sx, sy, sr * 2);
        sg.addColorStop(0, PAL.spotCore);
        sg.addColorStop(0.5, PAL.spotRim);
        sg.addColorStop(1, PAL.spotRim.replace(/[\d.]+\)$/, '0)'));
        ctx.fillStyle = sg;
        ctx.beginPath();
        ctx.arc(sx, sy, sr * 2, 0, Math.PI * 2);
        ctx.fill();
      }
      ctx.restore();

      // limb darkening
      g = ctx.createRadialGradient(cx, cy, R * 0.82, cx, cy, R);
      g.addColorStop(0, `rgba(${PAL.limb},0)`);
      g.addColorStop(1, `rgba(${PAL.limb},0.5)`);
      ctx.fillStyle = g;
      ctx.beginPath();
      ctx.arc(cx, cy, R, 0, Math.PI * 2);
      ctx.fill();

      // ── orbiting bot nodes ──────────────────────────────────────────────
      const live = botsRef.current;
      orbits.forEach((o, i) => {
        const meta = live.find((b) => b.key === o.key) || {};
        const status = meta.status || 'NA';
        const color = ST_COLOR[status] || ST_COLOR.NA;
        const running = status === 'LIVE' || status === 'PAPER';
        const orbR = R0 * (1.5 + i * 0.26) + o.rOff;
        const orbRy = orbR;

        // dashed guide circle
        ctx.strokeStyle = 'rgba(255,255,255,0.08)';
        ctx.setLineDash([3, 7]);
        ctx.beginPath();
        ctx.ellipse(cx, cy, orbR, orbRy, 0, 0, Math.PI * 2);
        ctx.stroke();
        ctx.setLineDash([]);

        // ONE angular speed for every bot, running or idle.
        //
        // Running bots used to advance 1.6x faster, so the nodes drifted
        // relative to each other and periodically bunched into the same arc
        // -- BTC-15 sitting on top of BTC-60, labels unreadable. With a
        // shared angular speed the gaps set at start-up are preserved for
        // ever: they are seeded 360/n apart and stay 360/n apart.
        //
        // Angular, not linear. Matching LINEAR speed would mean the inner
        // orbits sweep more degrees per second than the outer ones, which is
        // physically truer and brings the overlap straight back.
        if (o.key !== dragKey) o.ang += o.speed * dt;
        const nx = cx + Math.cos(o.ang) * orbR;
        const ny = cy + Math.sin(o.ang) * orbRy;
        nodePos[o.key] = { x: nx, y: ny };
        const dim = 1;   // nothing passes behind the disc on circular orbits

        // trail
        o.trail.push({ x: nx, y: ny });
        if (o.trail.length > 55) o.trail.shift();
        ctx.globalCompositeOperation = 'lighter';
        for (let k = 1; k < o.trail.length; k++) {
          const a = k / o.trail.length;
          ctx.strokeStyle = `${o.accent}${Math.round(a * 60).toString(16).padStart(2, '0')}`;
          ctx.lineWidth = a * 2.4;
          ctx.beginPath();
          ctx.moveTo(o.trail[k - 1].x, o.trail[k - 1].y);
          ctx.lineTo(o.trail[k].x, o.trail[k].y);
          ctx.stroke();
        }
        ctx.globalCompositeOperation = 'source-over';

        // status line: core -> node, pulsing when LIVE
        const dx = nx - cx; const dy = ny - cy;
        const dist = Math.hypot(dx, dy) || 1;
        const ux = dx / dist; const uy = dy / dist;
        const sx = cx + ux * (R * 1.04); const sy = cy + uy * (R * 1.04);
        const ex = nx - ux * 21; const ey = ny - uy * 21;
        const pulse = status === 'LIVE' ? 0.45 + 0.45 * Math.sin(t * 6) : 0.55;
        ctx.save();
        ctx.globalAlpha = pulse * dim;
        const lg = ctx.createLinearGradient(sx, sy, ex, ey);
        lg.addColorStop(0, 'rgba(255,255,255,0.02)');
        lg.addColorStop(1, color);
        ctx.strokeStyle = lg;
        ctx.lineWidth = status === 'LIVE' ? 1.6 : 1;
        ctx.beginPath();
        ctx.moveTo(sx, sy);
        ctx.lineTo(ex, ey);
        ctx.stroke();
        ctx.restore();

        // node
        ctx.save();
        ctx.globalAlpha = dim;
        ctx.shadowBlur = 18;
        ctx.shadowColor = o.accent;
        ctx.fillStyle = o.accent;
        ctx.beginPath();
        ctx.arc(nx, ny, hover === o.key ? 10.8 : 7.5, 0, Math.PI * 2);
        ctx.fill();
        ctx.shadowBlur = 0;
        ctx.strokeStyle = `${o.accent}66`;
        ctx.beginPath();
        ctx.arc(nx, ny, hover === o.key ? 20 : 15, 0, Math.PI * 2);
        ctx.stroke();

        // label chip: NAME · STATUS — the bank % renders on its own line below
        const pct = running ? meta.pct : null;
        const text = `${o.label} · ${status}`;
        ctx.font = '700 12.5px "JetBrains Mono", monospace';
        const tw = ctx.measureText(text).width;
        // clamp the chip inside the canvas — outer-orbit nodes reach the
        // edges at 3-column widths and the stage clips overflow
        let lx = nx + (nx > cx ? 21 : -21 - tw - 17);
        lx = Math.max(4, Math.min(lx, W - tw - 21));
        const ly = Math.max(19, Math.min(ny - 12,
          H - (meta.bankEvent ? 56 : pct !== null && pct !== undefined ? 34 : 10)));
        ctx.fillStyle = 'rgba(5,7,10,0.72)';
        ctx.strokeStyle = `${o.accent}44`;
        ctx.beginPath();
        if (ctx.roundRect) ctx.roundRect(lx, ly - 14, tw + 17, 22, 3);
        else ctx.rect(lx, ly - 14, tw + 17, 22);
        ctx.fill();
        ctx.stroke();
        ctx.fillStyle = o.accent;
        ctx.fillText(o.label, lx + 9, ly + 3);
        const lw = ctx.measureText(`${o.label} · `).width;
        ctx.fillStyle = color;
        if (status === 'LIVE') ctx.globalAlpha = dim * (0.5 + 0.5 * Math.sin(t * 6));
        ctx.fillText(text.slice(o.label.length), lx + 9 + lw - ctx.measureText(' · ').width, ly + 3);

        // bank P&L % on its own line under the chip: green +, red −
        if (pct !== null && pct !== undefined) {
          ctx.globalAlpha = dim;
          const pctText = `${pct >= 0 ? '+' : ''}${Number(pct).toFixed(2)}%`;
          ctx.font = '700 11px "JetBrains Mono", monospace';
          const ptw = ctx.measureText(pctText).width;
          ctx.fillStyle = 'rgba(5,7,10,0.72)';
          ctx.strokeStyle = `${o.accent}33`;
          ctx.beginPath();
          if (ctx.roundRect) ctx.roundRect(lx, ly + 11, ptw + 12, 19, 3);
          else ctx.rect(lx, ly + 11, ptw + 12, 19);
          ctx.fill();
          ctx.stroke();
          ctx.fillStyle = pct > 0 ? '#2fd35b' : pct < 0 ? '#ff4d4d' : '#7c8598';
          ctx.fillText(pctText, lx + 6, ly + 25);

          // bank halt banner: the session crossed its target / bank stop
          if (meta.bankEvent) {
            const halt = meta.bankEvent === 'tp';
            const haltText = halt ? 'TP hit on Bank' : 'SL hit on BANK';
            const haltColor = halt ? '#2fd35b' : '#ff4d4d';
            ctx.font = '800 10.5px "JetBrains Mono", monospace';
            const htw = ctx.measureText(haltText).width;
            ctx.fillStyle = 'rgba(5,7,10,0.8)';
            ctx.strokeStyle = `${haltColor}88`;
            ctx.beginPath();
            if (ctx.roundRect) ctx.roundRect(lx, ly + 33, htw + 12, 18, 3);
            else ctx.rect(lx, ly + 33, htw + 12, 18);
            ctx.fill();
            ctx.stroke();
            ctx.fillStyle = haltColor;
            // steady pulse so a halted bank is impossible to miss
            ctx.globalAlpha = dim * (0.65 + 0.35 * Math.sin(t * 4));
            ctx.fillText(haltText, lx + 6, ly + 46);
            ctx.globalAlpha = dim;
          }
        }
        ctx.restore();
      });

      // faint crosshair
      ctx.strokeStyle = 'rgba(255,255,255,0.05)';
      ctx.beginPath();
      ctx.moveTo(cx - R * 3.2, cy); ctx.lineTo(cx + R * 3.2, cy);
      ctx.moveTo(cx, cy - R * 2.2); ctx.lineTo(cx, cy + R * 2.2);
      ctx.stroke();

      // center reticle: the operator's name in HUD white — HIDDEN until the
      // helios is hovered, then it pops out along with the swelling sun
      if (operatorRef.current && pop > 0.02) {
        ctx.save();
        ctx.globalAlpha = Math.min(1, pop * 1.15);
        ctx.font = `700 ${(12 * (0.82 + 0.28 * pop)).toFixed(1)}px "JetBrains Mono", monospace`;
        ctx.textAlign = 'center';
        ctx.shadowColor = 'rgba(0,0,0,0.9)';
        ctx.shadowBlur = 7;
        ctx.fillStyle = 'rgba(255,255,255,0.94)';
        ctx.fillText(`+ ${String(operatorRef.current).toUpperCase()}`, cx, cy - 4);
        ctx.font = `700 ${(10 * (0.82 + 0.28 * pop)).toFixed(1)}px "JetBrains Mono", monospace`;
        ctx.fillStyle = '#ffd700';
        ctx.fillText('⚡ LAUNCH ALL', cx, cy + 14);
        ctx.restore();
      }
    };
    raf = requestAnimationFrame(draw);

    return () => {
      cancelAnimationFrame(raf);
      clearTimeout(clickTimer);
      ro.disconnect();
      canvas.removeEventListener('pointermove', onMove);
      canvas.removeEventListener('pointerleave', onLeave);
      canvas.removeEventListener('pointerdown', onDown);
      canvas.removeEventListener('pointerup', onUp);
      canvas.removeEventListener('click', onClick);
      canvas.removeEventListener('dblclick', onDbl);
      canvas.remove();
    };
  }, []);

  return <div ref={hostRef} className="bs-stage" data-testid="bs-stage" />;
}

// ── DMI strip: one row per instrument, 1m/2m/5m/10m DI-dominance readout ──
// Shared by the commodities and crypto panels. They ask the same question of
// different feeds and render the identical row, so this is written once —
// two copies of a signal readout drift the first time either is touched, and
// nothing on screen would show the disagreement.
//
// `load` is what differs, plus the title and how a row is labelled. Everything
// about how a reading is DISPLAYED is shared, which is the part that has to
// stay consistent across the desk.
function DmiStrip({ title, icon, load: loader, labelFor, decimals = 2 }) {
  const [snap, setSnap] = useState(null);
  const [err, setErr] = useState(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async (force = false) => {
    try {
      setSnap(await loader(force));
      setErr(null);
    } catch (e) { setErr(e.message || 'failed to load'); }
  }, [loader]);

  useEffect(() => { load(); }, [load]);
  useEffect(() => {
    const t = setInterval(() => { if (!document.hidden) load(); }, 60_000);
    return () => clearInterval(t);
  }, [load]);

  const doRefresh = async () => {
    if (busy) return;
    setBusy(true);
    await load(true);
    setBusy(false);
  };

  const rows = snap?.rows || [];
  const ago = (secs) => (secs < 60 ? `${secs}s`
    : secs < 3600 ? `${Math.floor(secs / 60)}m`
    : `${Math.floor(secs / 3600)}h`);
  const sideColor = (side) => (side === 'call' ? 'var(--bs-good, #2fd35b)'
    : side === 'put' ? 'var(--bs-crit, #ff4d4d)' : 'rgba(255,255,255,0.4)');
  const sideLabel = (side) => (side === 'call' ? 'CALL' : side === 'put' ? 'PUT' : '—');
  // Precision follows magnitude. Two decimals is right for gold at 4504 and
  // useless for DOGE at 0.085 or XRP at 1.3918 — both move in fractions of a
  // cent, and rounding them to 0.09 and 1.39 shows a price that never
  // changes. The break is at 10, not 100: HYPE at 82 and SOL at 104 are the
  // same kind of number, and showing 82.0800 beside 103.98 looked like two
  // different rules rather than one.
  const price = (v) => {
    if (v == null) return '—';
    const m = Math.abs(v);
    return v.toFixed(m >= 10 ? decimals : m >= 1 ? 4 : 5);
  };

  const tf = (r, key, label) => (
    <span className="tf" key={key}
      title={`${label}: ADX ${r[`${key}_adx`]?.toFixed(1) ?? '—'} · +DI ${r[`${key}_pdi`]?.toFixed(1) ?? '—'} · -DI ${r[`${key}_mdi`]?.toFixed(1) ?? '—'}`}>
      <b style={{ color: sideColor(r[`${key}_side`]) }}>{label}</b>{' '}
      {r[`${key}_adx`] != null ? Math.round(r[`${key}_adx`]) : '—'}
      {r[`${key}_slope`] != null && (
        <span className="slope">{r[`${key}_slope`] > 0 ? '↑' : '↓'}</span>
      )}
    </span>
  );

  return (
    <div className="bs-commodities">
      <div className="bs-commodities-hd">
        <span className="lbl">{icon} {title}</span>
        <span className="note">1m/2m/5m/10m DMI{snap?.meta?.source ? ` · ${snap.meta.source}` : ''}{err && ' · ⚠'}</span>
        {snap?.age_s != null && (
          <span className="note" title={`took ${snap.meta?.took_s ?? '—'}s · source ${snap.meta?.source ?? '—'}`}>
            {ago(snap.age_s)}
          </span>
        )}
        {/* How old the SPOT prices are, which is a different number from how
            old this response is: the board recomputes every minute from bars
            that may have been refreshed an hour ago. Only the on-demand
            source has one, so it appears only where it means something. */}
        {snap?.meta?.spot_polls_on_refresh_only && (
          <span className="note"
            title="API Ninjas spot prices are read only when you press refresh, never on a timer — the vendor is metered monthly">
            spot {snap.meta.spot_age_s == null ? 'not read' : ago(snap.meta.spot_age_s)}
          </span>
        )}
        <button type="button" className="bs-refresh" onClick={doRefresh} disabled={busy}
          title="force a fresh scan now">↻</button>
      </div>
      {err && <div className="bs-commodities-err">⚠ {err}</div>}
      <div className="bs-commodities-rows">
        {rows.map((r) => {
          const { label, accent } = labelFor(r);
          if (r.error) {
            return (
              <div key={r.bot} className="bs-commrow err"
                title={r.error /* why, not just a dash */}>
                <span className="tkr" style={{ color: accent }}>{label}</span>
                <span className="note">unavailable</span>
              </div>
            );
          }
          return (
            <div key={r.bot} className="bs-commrow">
              <span className="tkr" style={{ color: accent }}>{label}</span>
              <span className="last">{price(r.last)}</span>
              {tf(r, 'm1', '1m')}
              {tf(r, 'm2', '2m')}
              {tf(r, 'm5', '5m')}
              {tf(r, 'm10', '10m')}
              {/* The signal is 1m+2m agreement. 5m is shown beside it and
                  marked when it agrees, rather than folded into the rule —
                  widening what fires a trade is a trading change, not a
                  display one. */}
              <span className="sig" style={{ color: sideColor(r.signal) }}
                title={r.signal
                  ? `1m and 2m agree${r.m5_confirms ? '; 5m confirms' : '; 5m does not confirm'}`
                  : '1m and 2m disagree — no clear signal'}>
                {r.signal ? sideLabel(r.signal) : 'mixed'}
                {r.signal && r.m5_confirms && <span className="slope" title="5m confirms">✓</span>}
              </span>
            </div>
          );
        })}
        {rows.length === 0 && !err && <div className="bs-commodities-err" style={{ color: 'rgba(255,255,255,0.4)' }}>loading…</div>}
      </div>
    </div>
  );
}

// Gold / silver / oil, from Tradier in session and Coinbase-free spot outside
// it. Labelled from the bot registry so a row matches its core node.
// The luck bot. Not a launchable bot -- there is no process -- so it gets its
// own panel rather than a card with a Launch button that would mean nothing.
//
// Two steps on purpose. A long-shot ticket is twenty-odd legs chosen from
// forty thousand markets, and "place it" is not a thing anyone should confirm
// without seeing what "it" is. The preview spends nothing and creates nothing
// on the exchange; only the second button reaches the account.
// Luck parley. Not a launchable bot -- there is no process -- so it does not
// belong among the bot cards, and it is docked bottom-right out of the way:
// buying a lottery ticket is a deliberate act, not something to scan past.
//
// Three steps, each in its own place. The dock holds the numbers. Building
// scans the board and opens a SEPARATE sheet listing every leg, because
// choosing twenty legs out of forty thousand markets is the whole decision
// and it deserves the screen. Placing then happens without a second prompt --
// the sheet IS the confirmation, and a modal on top of a modal only teaches
// people to click through both.
function LuckPanel() {
  const [open, setOpen] = useState(false);
  const [sheet, setSheet] = useState(false);
  const [busy, setBusy] = useState('');
  const [elapsed, setElapsed] = useState(0);
  const [form, setForm] = useState({
    min_legs: '5', max_legs: '24', min_leg_c: '60', max_leg_c: '98',
    min_volume_usd: '5000', min_usd: '5', max_usd: '7.5',
  });
  const [preview, setPreview] = useState(null);
  const [keep, setKeep] = useState(() => new Set());
  const [result, setResult] = useState(null);
  const [error, setError] = useState('');

  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }));
  const n = (v, d) => { const x = Number(v); return Number.isFinite(x) ? x : d; };

  // The scan runs well past the tunnel's ~100s ceiling, so the server hands
  // back a job id and we poll rather than holding a request open.
  const awaitJob = async (jobId) => {
    for (let i = 0; i < 300; i += 1) {
      await new Promise((r) => setTimeout(r, 2000));
      const st = await vidura.luckJob(jobId);
      setElapsed(st.elapsed_s || 0);
      if (st.status === 'done') return st.result;
      if (st.status === 'failed') throw new Error(st.error || 'the job failed');
    }
    throw new Error('gave up waiting for the scan');
  };

  const build = async () => {
    setBusy('preview'); setError(''); setResult(null); setPreview(null);
    setElapsed(0);
    try {
      const job = await vidura.luckPreview({
        min_legs: n(form.min_legs, 5), max_legs: n(form.max_legs, 24),
        min_leg_c: n(form.min_leg_c, 60),
        max_leg_c: n(form.max_leg_c, 98),
        min_volume_usd: n(form.min_volume_usd, 0),
      });
      const out = await awaitJob(job.job_id);
      if (out && out.ok) {
        setPreview(out);
        setKeep(new Set(out.legs.map((l) => l.ticker)));
        setSheet(true);
      } else setError((out && out.detail) || 'no ticket could be built');
    } catch (e) {
      setError(String((e && e.message) || e));
    } finally { setBusy(''); }
  };

  const toggle = (ticker) => setKeep((prev) => {
    const next = new Set(prev);
    if (next.has(ticker)) next.delete(ticker); else next.add(ticker);
    return next;
  });
  const allOn = () => setKeep(new Set((preview ? preview.legs : []).map((l) => l.ticker)));
  const allOff = () => setKeep(new Set());

  // The odds of what is SELECTED, not of what was proposed. Deselect a leg
  // and this moves -- showing the preview's original number beside an edited
  // ticket would be a lie.
  const chosen = preview ? preview.legs.filter((l) => keep.has(l.ticker)) : [];
  const chosenOdds = chosen.reduce((acc, l) => acc * ((l.price_c || 0) / 100), 1);
  const enough = chosen.length >= n(form.min_legs, 5);

  const place = async () => {
    if (!preview || !enough) return;
    setBusy('place'); setError(''); setElapsed(0);
    try {
      const job = await vidura.luckPlace({
        token: preview.token,
        tickers: chosen.map((l) => l.ticker),
        min_usd: n(form.min_usd, 5), max_usd: n(form.max_usd, 7.5),
        min_legs: n(form.min_legs, 5),
      });
      const out = await awaitJob(job.job_id);
      setResult(out);
      if (out && out.placed) { setPreview(null); setSheet(false); }
      else setError((out && out.detail) || 'not placed');
    } catch (e) {
      setError(String((e && e.message) || e));
    } finally { setBusy(''); }
  };

  return (
    <>
      <section className={`bs-luckdock ${open ? 'open' : ''}`}>
        <header className="bs-luck-hd" onClick={() => setOpen((v) => !v)}>
          <h3>LUCK PARLEY</h3>
          <span className="bs-luck-toggle">{open ? '\u2212' : '+'}</span>
        </header>

        {!open ? null : (
          <div className="bs-luckdock-body">
            {/* Paired as ranges rather than six separate boxes: they ARE
                three ranges, and in a sidebar column six labelled fields wrap
                into a wall the panel cannot show without scrolling. */}
            <div className="bs-luckform">
              <label className="bs-luckrow">
                <span className="lbl">Legs</span>
                <input className="bs-input" type="number" min="2" max="24"
                  value={form.min_legs} onChange={set('min_legs')} />
                <i>–</i>
                <input className="bs-input" type="number" min="2" max="24"
                  value={form.max_legs} onChange={set('max_legs')} />
              </label>
              <label className="bs-luckrow">
                <span className="lbl">Spend $</span>
                <input className="bs-input" type="number" min="1" step="0.5"
                  value={form.min_usd} onChange={set('min_usd')} />
                <i>–</i>
                <input className="bs-input" type="number" min="1" step="0.5"
                  value={form.max_usd} onChange={set('max_usd')} />
              </label>
              {/* The leg price BAND, as a range like the two above it. The
                  ceiling was fixed at 98c and unstated: on a long shot built
                  from many legs, an already-decided one adds cost without
                  adding chance -- it only shortens the payout. */}
              <label className="bs-luckrow">
                <span className="lbl">Leg c</span>
                <input className="bs-input" type="number" min="5" max="98"
                  value={form.min_leg_c} onChange={set('min_leg_c')}
                  title="cheapest leg to accept, in cents" />
                <i>–</i>
                <input className="bs-input" type="number" min="6" max="99"
                  value={form.max_leg_c} onChange={set('max_leg_c')}
                  title="dearest leg to accept, in cents — above this the outcome is already decided" />
              </label>
              <label className="bs-luckrow">
                <span className="lbl">Min vol</span>
                <input className="bs-input" type="number" min="0" step="500"
                  value={form.min_volume_usd} onChange={set('min_volume_usd')}
                  title="minimum dollar volume per leg" />
                <i>$</i>
              </label>
            </div>

            <div className="bs-luck-actions">
              <button type="button" className="bs-btn" onClick={build}
                disabled={!!busy}>
                {busy === 'preview' ? 'SCANNING\u2026' : 'BUILD TICKET'}
              </button>
              {preview && !sheet ? (
                <button type="button" className="bs-btn"
                  onClick={() => setSheet(true)}>REOPEN LEGS</button>
              ) : null}
            </div>

            {busy === 'preview' ? (
              <p className="bs-luck-note">
                Reading every live market and its sub-events
                {elapsed ? ` \u00b7 ${Math.round(elapsed)}s` : ''}\u2026
                this takes a couple of minutes.
              </p>
            ) : null}
            {error && !sheet ? <p className="bs-luck-err">{error}</p> : null}
            {result && result.placed ? (
              <p className="bs-luck-ok">
                PLACED \u2014 {result.legs_used} legs, {result.contracts} contracts
                {result.filled_c != null ? ` at ${result.filled_c}c` : ''}
                {result.cost_usd != null ? ` \u00b7 $${result.cost_usd}` : ''}
                {result.contracts ? ` \u00b7 max payout $${Math.round(result.contracts).toLocaleString()}` : ''}
              </p>
            ) : null}
          </div>
        )}
      </section>

      {sheet && preview ? (
        <div className="bs-luck-scrim" onClick={() => { if (!busy) setSheet(false); }}>
          <div className="bs-luck-sheet" onClick={(e) => e.stopPropagation()}>
            <header className="bs-modal-hd">
              <h2>SELECT LEGS</h2>
              <button type="button" className="close"
                onClick={() => { if (!busy) setSheet(false); }}>\u00d7</button>
            </header>
            <p className="bs-luck-note">
              {chosen.length} of {preview.legs.length} kept
              {' \u00b7 '}chance {(chosenOdds * 100).toFixed(3)}%
              {' \u00b7 '}{preview.scanned.toLocaleString()} markets scanned
              {' \u00b7 '}buys at market, spending
              ${n(form.min_usd, 5).toFixed(2)}\u2013${n(form.max_usd, 7.5).toFixed(2)}
            </p>

            <div className="bs-luck-actions">
              <button type="button" className="bs-btn" onClick={allOn} disabled={!!busy}>ALL</button>
              <button type="button" className="bs-btn" onClick={allOff} disabled={!!busy}>NONE</button>
              <button type="button" className="bs-btn live" onClick={place}
                disabled={!!busy || !enough}>
                {busy === 'place'
                  ? `PLACING\u2026${elapsed ? ` ${Math.round(elapsed)}s` : ''}`
                  : `PLACE ORDER \u2014 ${chosen.length} LEGS`}
              </button>
            </div>
            {!enough ? (
              <p className="bs-luck-err">
                keep at least {n(form.min_legs, 5)} legs
              </p>
            ) : null}
            {error ? <p className="bs-luck-err">{error}</p> : null}

            <div className="bs-luck-legs">
              <table>
                <thead>
                  <tr><th>Keep</th><th>#</th><th>Market</th><th>Outcome</th>
                    <th>Sport</th>
                    <th className="num">Price</th><th className="num">Volume</th></tr>
                </thead>
                <tbody>
                  {preview.legs.map((l, i) => (
                    <tr key={l.ticker} className={keep.has(l.ticker) ? '' : 'off'}>
                      <td>
                        <input type="checkbox" checked={keep.has(l.ticker)}
                          disabled={!!busy}
                          onChange={() => toggle(l.ticker)} />
                      </td>
                      <td className="num">{i + 1}</td>
                      <td title={l.event}>{l.market}</td>
                      <td>{l.outcome}</td>
                      <td className="dim">{l.sport}</td>
                      <td className="num">{l.price_c}c</td>
                      <td className="num">${Math.round(l.volume_usd).toLocaleString()}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      ) : null}
    </>
  );
}


function CommoditiesStrip() {
  return (
    <DmiStrip
      title="COMMODITIES" icon="🛢"
      load={(force) => vidura.commodityDmiSignals(force)}
      labelFor={(r) => ({ label: BOT_BY_KEY[r.bot]?.label || r.label || r.bot,
                          accent: BOT_BY_KEY[r.bot]?.accent })}
    />
  );
}

// BTC / ETH / SOL / DOGE / XRP, from Coinbase. No credential and no session
// window — crypto never closes, so unlike commodities there is nothing to
// switch sources around.
const CRYPTO_ACCENT = {
  btc: '#f7931a', eth: '#8a92b2', sol: '#14f195',
  doge: '#c2a633', xrp: '#25a768',
};

function CryptoStrip() {
  return (
    <DmiStrip
      title="CRYPTO" icon="₿"
      load={(force) => vidura.cryptoDmiSignals(force)}
      labelFor={(r) => ({ label: r.label || r.bot.toUpperCase(),
                          accent: CRYPTO_ACCENT[r.bot] })}
    />
  );
}

// ── daily PV progress: one-layer pixel mountain, retro-scanline style ──────
// One column per calendar day since 08/01/2026 (start $60). Colors ramp
// progressively: deeper green the further above the start, deeper red the
// further below. Days with no capture are interpolated and drawn dim.
function pvColor(pct) {
  if (pct >= 0) {
    const t = Math.min(1, pct / 150);
    return `hsl(135, ${Math.round(45 + t * 25)}%, ${Math.round(54 - t * 22)}%)`;
  }
  const t = Math.min(1, -pct / 50);
  return `hsl(4, ${Math.round(55 + t * 20)}%, ${Math.round(52 - t * 18)}%)`;
}

function PixelPvGraph({ history, baseline }) {
  const hostRef = useRef(null);

  useEffect(() => {
    const host = hostRef.current;
    if (!host || !history || history.length === 0) return undefined;
    const canvas = document.createElement('canvas');
    host.appendChild(canvas);
    const ctx = canvas.getContext('2d');

    const draw = () => {
      const W = host.clientWidth; const H = host.clientHeight;
      const DPR = Math.min(window.devicePixelRatio || 1, 2);
      canvas.width = W * DPR; canvas.height = H * DPR;
      canvas.style.width = `${W}px`; canvas.style.height = `${H}px`;
      ctx.setTransform(DPR, 0, 0, DPR, 0, 0);
      ctx.clearRect(0, 0, W, H);
      ctx.imageSmoothingEnabled = false;

      // expand the captured series into a continuous day range
      const byDate = Object.fromEntries(history.map((r) => [r.date, r]));
      const first = new Date(`${history[0].date}T12:00:00Z`);
      const last = new Date(`${history[history.length - 1].date}T12:00:00Z`);
      const days = [];
      for (let d = new Date(first); d <= last; d.setUTCDate(d.getUTCDate() + 1)) {
        const key = d.toISOString().slice(0, 10);
        days.push({ date: key, row: byDate[key] || null });
      }
      // linear interpolation across capture gaps (drawn dim, marked ghost)
      for (let i = 0; i < days.length; i++) {
        if (days[i].row) { days[i].v = days[i].row.total_usd; continue; }
        let p = i - 1; while (p >= 0 && !days[p].row) p--;
        let n = i + 1; while (n < days.length && !days[n].row) n++;
        const pv = days[p]?.row?.total_usd; const nv = days[n]?.row?.total_usd;
        days[i].v = pv !== undefined && nv !== undefined
          ? pv + ((nv - pv) * (i - p)) / (n - p) : (pv ?? nv ?? baseline);
        days[i].ghost = true;
      }

      const vals = days.map((d) => d.v);
      const vMin = Math.min(baseline, ...vals) * 0.88;
      const vMax = Math.max(baseline, ...vals) * 1.06;
      const padB = 22; const padT = 14;
      const unit = 9;                                   // pixel block row height
      const rowsMax = Math.max(3, Math.floor((H - padB - padT) / unit));
      const colW = Math.max(12, Math.min(48, Math.floor(W / days.length)));
      const x0 = Math.max(0, Math.floor((W - colW * days.length) / 2));

      ctx.font = '700 9px "JetBrains Mono", monospace';
      days.forEach((d, i) => {
        const pct = ((d.v - baseline) / baseline) * 100;
        const rows = Math.max(1, Math.round(((d.v - vMin) / (vMax - vMin)) * rowsMax));
        const x = x0 + i * colW;
        ctx.globalAlpha = d.ghost ? 0.4 : 1;
        ctx.fillStyle = pvColor(pct);
        for (let r = 0; r < rows; r++) {              // chunky scanline blocks
          ctx.fillRect(x + 1, H - padB - (r + 1) * unit + 1, colW - 2, unit - 2);
        }
        ctx.globalAlpha = 1;
        // labels: value above the column, date below (when there is room)
        if (colW >= 24 && !d.ghost) {
          ctx.fillStyle = 'rgba(242,244,248,0.85)';
          ctx.textAlign = 'center';
          ctx.fillText(`$${Math.round(d.v)}`, x + colW / 2, H - padB - rows * unit - 4);
        }
        if (colW >= 22 || i % Math.ceil(22 / colW) === 0) {
          ctx.fillStyle = 'rgba(124,133,152,0.8)';
          ctx.textAlign = 'center';
          ctx.fillText(d.date.slice(5).replace('-', '/'), x + colW / 2, H - 8);
        }
      });

      // the $-start baseline, dashed across the field
      const by = H - padB - Math.max(1, Math.round(((baseline - vMin) / (vMax - vMin)) * rowsMax)) * unit;
      ctx.strokeStyle = 'rgba(255,255,255,0.22)';
      ctx.setLineDash([4, 5]);
      ctx.beginPath();
      ctx.moveTo(0, by); ctx.lineTo(W, by);
      ctx.stroke();
      ctx.setLineDash([]);
      ctx.fillStyle = 'rgba(255,255,255,0.45)';
      ctx.textAlign = 'left';
      ctx.fillText(`start $${baseline}`, 6, by - 4);
    };

    draw();
    const ro = new ResizeObserver(draw);
    ro.observe(host);
    return () => { ro.disconnect(); canvas.remove(); };
  }, [history, baseline]);

  return <div ref={hostRef} className="bs-pixelhost" />;
}

// ── sci-fi log feed: double-click a bot node — a translucent glass window
// floats over the desk streaming that bot's live tail ─────────────────────
function logLineClass(l) {
  if (/error|traceback|exception|fail/i.test(l)) return 'err';
  if (/\b(FILL|EXIT|WIN|TP|BUY|BET)\b/i.test(l)) return 'hot';
  if (/\b(SIGNAL|ENTRY|BREAKOUT|QUIET)\b/i.test(l)) return 'sig';
  return '';
}

function BotLogsOverlay({ botKey, user, onClose }) {
  const bot = BOT_BY_KEY[botKey];
  const [lines, setLines] = useState(null);
  const [err, setErr] = useState(null);
  const bodyRef = useRef(null);

  useEffect(() => {
    let alive = true;
    const load = async () => {
      try {
        const tail = { user_id: user.user_id, lines: 120 };
        const isCmdt = botKey === 'gold15' || botKey === 'silver15' || botKey === 'oil15';
        const r = botKey === 'sports' ? await vidura.sportsLogs(tail)
          : botKey === 'parley' ? await vidura.parleyLogs(tail)
            : isCmdt ? await vidura.commodityLogs({ bot: botKey, ...tail })
              : await vidura.btcLogs({ bot: botKey, ...tail });
        if (alive) { setLines(r.lines || []); setErr(null); }
      } catch (e) {
        if (!alive) return;
        if (e instanceof ApiError && e.status === 404) { setLines([]); setErr(null); }
        else setErr(errText(e));
      }
    };
    load();
    const t = setInterval(() => { if (!document.hidden) load(); }, 5000);
    return () => { alive = false; clearInterval(t); };
  }, [botKey, user]);

  useEffect(() => {   // stay glued to the newest line
    const el = bodyRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [lines]);

  useEffect(() => {
    const onKey = (e) => { if (e.key === 'Escape') onClose(); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  return (
    <div className="bs-logwin" style={{ '--bot-accent': bot.accent }} role="dialog"      aria-label={`${bot.label} live logs`}>
      <div className="bs-logwin-hd">
        <span className="sig" />
        <span className="ttl">◉ {bot.label} · LIVE FEED</span>
        <span className="sub">{bot.sub}</span>
        <button type="button" className="x" onClick={onClose} aria-label="close">✕</button>
      </div>
      <div className="bs-logwin-bd" ref={bodyRef}>
        {err && <div className="line err">✗ {err}</div>}
        {lines && lines.length === 0 && !err && (
          <div className="line dim">— no runs yet · the feed lights up when {bot.label} launches —</div>
        )}
        {!lines && !err && <div className="line dim">establishing uplink…</div>}
        {(lines || []).map((l, i) => (
          <div key={i} className={`line ${logLineClass(l)}`}>{l}</div>
        ))}
      </div>
      <div className="bs-logwin-ft">
        <span>TAIL 120 · REFRESH 5s</span>
        <span>ESC / ✕ TO DISMISS</span>
      </div>
    </div>
  );
}

// ── launch console modal (sci-fi pop-out) ──────────────────────────────────
function num(v) { const n = parseFloat(v); return Number.isFinite(n) ? n : undefined; }

function BotConsole({ botKey, meta, status, versions, cfg, onCfg, user, onClose, onChanged, onLogs }) {
  const bot = BOT_BY_KEY[botKey];
  const running = !!status?.running;
  const activeRun = (status?.runs || []).find((r) => r.status === 'running') || status?.runs?.[0];
  const isSports = botKey === 'sports';
  const isParley = botKey === 'parley';
  const isCommodity = botKey === 'gold15' || botKey === 'silver15' || botKey === 'oil15';
  const isBtc = !isSports && !isParley && !isCommodity;
  const f = cfg || {};
  const [mode, setMode] = useState('paper');   // NEVER persisted — safety
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState(null);
  const liveLock = useLiveLock(mode === 'live');
  const liveLocked = mode === 'live' && (!liveLock || liveLock.paperOnly);

  const vlist = versions || [];
  const defVersion = vlist.find((v) => v.default)?.version || vlist[0]?.version || '';
  const version = f.version ?? '';
  const set = (k) => (e) => onCfg(botKey, { ...f, [k]: e.target.value });
  const setSport = (sport, k) => (e) => onCfg(botKey, {
    ...f, sports: { ...(f.sports || {}), [sport]: { ...((f.sports || {})[sport] || {}), [k]: e.target.value } },
  });
  const defaultSel = isParley ? PARLEY_SPORTS : ['tennis', 'baseball'];
  const sportOn = (sport) => (f.sportsSel ?? defaultSel).includes(sport);
  const toggleSport = (sport) => () => {
    const sel = f.sportsSel ?? defaultSel;
    onCfg(botKey, { ...f, sportsSel: sel.includes(sport) ? sel.filter((s) => s !== sport) : [...sel, sport] });
  };
  const v5NoSl = (botKey === 'btc15' && (version || defVersion) === 'v5') || isCommodity;

  useEffect(() => {
    const onKey = (e) => {
      if (e.key !== 'Escape') return;
      if (busy) return;                                    // never unmount mid-request
      if (document.querySelector('.vwd-backdrop')) return; // confirmDialog owns Escape
      onClose();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose, busy]);

  const buildBody = () => {
    // No user_id. The session decides whose bot this is; sending an operator
    // in the body would be a cross-tenant selector, and the server strips it.
    const body = { mode, version: (version || undefined) };
    if (isBtc || isCommodity) {
      const contracts = parseInt(f.contracts, 10);
      if (contracts >= 1) body.contracts = contracts;
      if (num(f.bank) > 0) body.bankroll = num(f.bank);
      if (num(f.tp_pct) > 0) body.tp_pct = num(f.tp_pct);
      if (!v5NoSl && num(f.sl_pct) > 0 && num(f.sl_pct) < 100) body.sl_pct = num(f.sl_pct);
      if (num(f.target_pct) > 0) body.bank_tp_pct = num(f.target_pct);
      if (num(f.bank_sl_pct) > 0 && num(f.bank_sl_pct) < 100) body.bank_sl_pct = num(f.bank_sl_pct);
      // empty string is deliberate: it CLEARS the engine's own quiet hours
      if (typeof f.no_trade_times === 'string' && NTT_RE.test(f.no_trade_times.trim())) {
        body.no_trade_times = f.no_trade_times.trim();
      }
    } else if (isParley) {
      // Every selected sport, not just tennis. Tennis is the only one with a
      // leg qualifier (a set lead); the others are traded on price alone.
      // Posting ['tennis'] never actually narrowed anything -- the bot read
      // the list from argv, not from the form -- so the field described a
      // filter that did not exist. The reader is fixed in the v2 script;
      // this now means what it says.
      const chosenP = (f.sportsSel ?? PARLEY_SPORTS);
      if (chosenP.length) body.sports = chosenP;
      // A dollar budget per parlay, not a contract count: a combo's price
      // moves with its legs, so a fixed count spends a different amount every
      // pass. The engine buys as many as the budget covers, and none if it
      // cannot cover one.
      if (num(f.stake_usd) > 0) body.stake_usd = num(f.stake_usd);
      // The ceiling in dollars. The engine still escalates by a
      // percentage; it derives that from these two so the operator
      // never has to.
      if (num(f.max_usd) > 0) body.max_usd = num(f.max_usd);
      { const n = parseInt(f.max_per_event, 10);
        if (Number.isFinite(n) && n >= 1) body.max_per_event = n; }
      { const n = parseInt(f.fill_wait_s, 10);
        if (Number.isFinite(n) && n >= 5) body.fill_wait_s = n; }
      // The daily long-shot ticket. Sent only when it is switched on, so an
      // untouched form never quietly enables a second engine.
      body.daily_enabled = f.daily_enabled === true || f.daily_enabled === 'true';
      if (body.daily_enabled) {
        if (/^\d{1,2}:\d{2}$/.test((f.daily_at || '').trim())) body.daily_at = f.daily_at.trim();
        if (num(f.daily_stake_usd) > 0) body.daily_stake_usd = num(f.daily_stake_usd);
        { const n = parseInt(f.daily_min_legs, 10); if (Number.isFinite(n) && n >= 2) body.daily_min_legs = n; }
        { const n = parseInt(f.daily_max_legs, 10); if (Number.isFinite(n) && n >= 2) body.daily_max_legs = n; }
        { const n = parseInt(f.daily_min_c, 10); if (Number.isFinite(n) && n >= 5) body.daily_min_c = n; }
      }
      { const n = parseInt(f.slippage_c, 10);
        if (Number.isFinite(n) && n >= 0) body.slippage_c = n; }
      if (num(f.bank) > 0) body.bankroll = num(f.bank);
      if (num(f.bank_sl_pct) > 0 && num(f.bank_sl_pct) < 100) body.bank_sl_pct = num(f.bank_sl_pct);
      // cents and counts go straight through; blanks leave the engine default
      const p = {};
      const int_ = (k) => { const n = parseInt(f[k], 10); if (Number.isFinite(n)) p[k] = n; };
      ['min_prob_c', 'min_set', 'min_legs', 'max_legs', 'max_open',
        'slippage_c', 'max_price_c', 'tp_ceiling_c', 'stop_loss_c'].forEach(int_);
      if (num(f.cooldown_min) >= 0) p.cooldown_min = num(f.cooldown_min);
      if (f.lead_scope) p.lead_scope = f.lead_scope;
      if (f.limit_fallback !== undefined && f.limit_fallback !== '') {
        p.limit_fallback = f.limit_fallback === true || f.limit_fallback === 'true';
      }
      if (Object.keys(p).length) body.parley = p;
    } else {
      const chosen = (f.sportsSel ?? ['tennis', 'baseball']);
      body.sports = chosen;
      const settings = {};
      for (const sport of chosen) {
        const c = (f.sports || {})[sport] || {};
        const s = {};
        const contracts = parseInt(c.contracts, 10);
        if (contracts >= 1) s.contracts = contracts;
        if (num(c.bank) >= 0 && c.bank !== '' && c.bank !== undefined) s.bank = num(c.bank);
        if (sport === 'tennis' && c.model) s.model = c.model;
        if (Object.keys(s).length) settings[sport] = s;
      }
      if (Object.keys(settings).length) body.sport_settings = settings;
      if (num(f.target_pct) > 0) body.bank_tp_pct = num(f.target_pct);
      if (num(f.bank_sl_pct) > 0 && num(f.bank_sl_pct) < 100) body.bank_sl_pct = num(f.bank_sl_pct);
      // empty string deliberately CLEARS the engine's 16:00-20:00 default
      if (typeof f.no_trade_times === 'string' && NTT_RE.test(f.no_trade_times.trim())) {
        body.no_trade_times = f.no_trade_times.trim();
      }
    }
    return body;
  };

  const start = async () => {
    if (busy || !user) return;
    if (isSports && (f.sportsSel ?? ['tennis', 'baseball']).length === 0) {
      setErr('pick at least one sport'); return;
    }
    setErr(null);
    const ok = await confirmDialog({
      title: mode === 'live'
        ? `LAUNCH ${bot.label} — LIVE, real money?`
        : `Launch ${bot.label} in PAPER mode?`,
      body: mode === 'live'
        ? 'This bot will place REAL-MONEY Kalshi orders on its own. The server '
          + 'is unlocked (VIDURA_PAPER_ONLY=false) and the launch config below applies.'
        : 'Simulated fills, real signals — no money moves. The launch config below applies.',
      confirmText: mode === 'live' ? 'Launch LIVE' : 'Launch',
      cancelText: 'Cancel',
    });
    if (!ok) return;
    setBusy(true);
    const body = buildBody();
    const startWith = (b) => (isCommodity ? vidura.commodityStart(botKey, b)
      : isBtc ? vidura.btcStart(botKey, b)
      : isParley ? vidura.parleyStart(b) : vidura.sportsStart(b));
    const call = () => startWith(body);
    try {
      await call();
      onChanged();
      onClose();
    } catch (e) {
      if (e instanceof ApiError && e.status === 409 && /outside this API|already running/.test(e.detail || '')) {
        const kill = await confirmDialog({
          title: `A ${bot.label} bot is already running`,
          body: 'Kill the existing process(es) and start fresh with this config?',
          confirmText: 'Kill it and start fresh', cancelText: 'Leave it',
        });
        if (kill) {
          try {
            // Stop it, then start. kill_existing was never a field the API
            // accepted, so this retry was refused as an unknown option and
            // "Kill it and start fresh" could not work at all.
            const stopIt = isCommodity ? vidura.commodityStop(botKey, {})
              : isBtc ? vidura.btcStop(botKey, {})
                : isParley ? vidura.parleyStop({}) : vidura.sportsStop({});
            await stopIt.catch(() => { /* already gone is the outcome we want */ });
            await call();
            onChanged();
            onClose();
          } catch (e2) { setErr(errText(e2)); }
        }
      } else { setErr(errText(e)); }
    }
    setBusy(false);
  };

  const stop = async () => {
    if (busy) return;
    const ok = await confirmDialog({
      title: `Stop ${bot.label}?`,
      body: 'Stops the running bot process. Open positions stay as the bot left them.',
      confirmText: 'Stop bot', cancelText: 'Keep running',
    });
    if (!ok) return;
    setBusy(true);
    setErr(null);
    try {
      await (isCommodity ? vidura.commodityStop(botKey, { user_id: user.user_id })
        : isBtc ? vidura.btcStop(botKey, { user_id: user.user_id })
        : isParley ? vidura.parleyStop({ user_id: user.user_id })
          : vidura.sportsStop({ user_id: user.user_id }));
      onChanged();
      onClose();
    } catch (e) { setErr(errText(e)); }
    setBusy(false);
  };

  return (
    <div className="bs-modal-backdrop" role="dialog" aria-modal="true"      onMouseDown={(e) => { if (e.target === e.currentTarget) onClose(); }}
      aria-label={`${bot.label} console`}>
      <div className="bs-modal" style={{ '--bot-accent': bot.accent }}
        onClick={(e) => e.stopPropagation()}>
        <div className="bs-modal-hd">
          <span className="sig" />
          <h2>{bot.label} CONSOLE</h2>
          <button type="button" className="close" onClick={onClose} aria-label="close">✕</button>
        </div>
        <p className="bs-modal-sub">{bot.sub} · kalshi executor</p>

        {running && activeRun && (
          <>
            <div className="bs-runchips">
              <span className="bs-runchip">RUNNING · {activeRun.mode?.toUpperCase()}</span>
              <span className="bs-runchip">engine {activeRun.bot_version || '?'}</span>
              <span className="bs-runchip">pid {activeRun.pid ?? '—'}</span>
              <span className="bs-runchip">since {utcTs(activeRun.started_at)}</span>
              {status?.session && (
                <span className="bs-runchip">
                  session {usd(status.session.pnl_usd)} · {status.session.trades_closed} closed
                  {status.session.bankroll_pct !== null && status.session.bankroll_pct !== undefined
                    ? ` · bank ${status.session.bankroll_pct >= 0 ? '+' : ''}${status.session.bankroll_pct}%` : ''}
                </span>
              )}
            </div>
            <div className="bs-actions">
              <button type="button" className="bs-stopbtn" onClick={stop} disabled={busy}>
                {busy ? '…' : '■ STOP BOT'}
              </button>
              <button type="button" className="bs-logbtn" onClick={onLogs}>◉ VIEW LOGS</button>
              {err && <span className="bs-err">✗ {err}</span>}
            </div>
            {activeRun?.log_file && (
              <p className="bs-note log-path" title={activeRun.log_file} style={{ marginTop: 6 }}>
                log: {activeRun.log_file.replace(/^.*[/\\]/, '')}
              </p>
            )}
            <p className="bs-note" style={{ marginTop: 10 }}>
              To relaunch with a new config, stop it first — the form below is the next launch.
            </p>
          </>
        )}

        <div className="bs-form" style={{ marginTop: running ? 12 : 0 }}>
          <div className="bs-field">
            <span className="lbl">Engine version</span>
            <select className="bs-select" value={version} onChange={set('version')}>
              <option value="">{defVersion ? `${defVersion} · default` : 'default'}</option>
              {vlist.map((v) => (
                <option key={v.version} value={v.version} disabled={!v.exists}>
                  {v.version}{v.default ? ' · default' : ''}{v.exists ? '' : ' · missing'}
                </option>
              ))}
            </select>
          </div>

          {(isBtc || isCommodity) ? (
            <>
              <div className="bs-field">
                <span className="lbl">Contracts</span>
                <input className="bs-input" type="number" min="1" max="1000" value={f.contracts ?? ''}
                  placeholder="bot default" onChange={set('contracts')} />
              </div>
              <div className="bs-field">
                <span className="lbl">Bank $</span>
                <input className="bs-input" type="number" min="1" value={f.bank ?? ''}
                  placeholder="bot default" onChange={set('bank')} />
              </div>
              <div className="bs-field">
                <span className="lbl">TP % / trade</span>
                <input className="bs-input" type="number" min="1" max="500" value={f.tp_pct ?? ''}
                  placeholder="engine default" onChange={set('tp_pct')} />
              </div>
              <div className="bs-field">
                <span className="lbl">SL % / trade</span>
                <input className="bs-input" type="number" min="1" max="99" value={v5NoSl ? '' : (f.sl_pct ?? '')}
                  placeholder={v5NoSl ? 'v5: holds to settle' : 'engine default'}
                  disabled={v5NoSl} onChange={set('sl_pct')}
                  title={v5NoSl ? 'btc15 v5 has no stop loss — it holds to settlement by design' : ''} />
              </div>
              <div className="bs-field">
                <span className="lbl">Target % on bank</span>
                <input className="bs-input" type="number" min="0" step="0.5" value={f.target_pct ?? ''}
                  placeholder="off" onChange={set('target_pct')} />
              </div>
              <div className="bs-field">
                <span className="lbl">SL % on bank</span>
                <input className="bs-input" type="number" min="0" max="99" step="0.5" value={f.bank_sl_pct ?? ''}
                  placeholder="off" onChange={set('bank_sl_pct')} />
              </div>
              <div className="bs-field" style={{ gridColumn: '1 / -1' }}>
                <span className="lbl">No trade times (local)</span>
                <input className="bs-input" value={f.no_trade_times ?? NTT_DEFAULT}
                  placeholder={NTT_DEFAULT} onChange={set('no_trade_times')}
                  title="comma-separated HH:MM-HH:MM quiet windows on the machine's clock — clear the field to trade around the clock" />
              </div>
            </>
          ) : isParley ? (
            <>
              <div className="bs-field bs-field-wide">
                <span className="lbl">Sports</span>
                <div className="bs-checks">
                  {PARLEY_SPORTS.map((sport) => (
                    <label key={sport} className="bs-check">
                      <input type="checkbox" checked={sportOn(sport)}
                        onChange={toggleSport(sport)} />
                      {sport}
                    </label>
                  ))}
                </div>
              </div>
              <div className="bs-field bs-field-wide">
                <label className="bs-check">
                  <input type="checkbox"
                    checked={f.daily_enabled === true || f.daily_enabled === 'true'}
                    onChange={(e) => onCfg(botKey, { ...f, daily_enabled: e.target.checked })} />
                  Daily long-shot ticket — one a day, many legs, small stake
                </label>
              </div>
              <div className="bs-field">
                <span className="lbl">Daily at (HH:MM)</span>
                <input className="bs-input" value={f.daily_at ?? ''} placeholder="17:50"
                  disabled={!(f.daily_enabled === true || f.daily_enabled === 'true')}
                  onChange={set('daily_at')} />
              </div>
              <div className="bs-field">
                <span className="lbl">Daily $</span>
                <input className="bs-input" type="number" min="1" step="0.5"
                  value={f.daily_stake_usd ?? ''} placeholder="5"
                  disabled={!(f.daily_enabled === true || f.daily_enabled === 'true')}
                  onChange={set('daily_stake_usd')} />
              </div>
              <div className="bs-field">
                <span className="lbl">Daily legs (min–max)</span>
                <div style={{ display: 'flex', gap: '6px' }}>
                  <input className="bs-input" type="number" min="2" max="24"
                    value={f.daily_min_legs ?? ''} placeholder="5"
                    disabled={!(f.daily_enabled === true || f.daily_enabled === 'true')}
                    onChange={set('daily_min_legs')} />
                  <input className="bs-input" type="number" min="2" max="24"
                    value={f.daily_max_legs ?? ''} placeholder="24"
                    disabled={!(f.daily_enabled === true || f.daily_enabled === 'true')}
                    onChange={set('daily_max_legs')} />
                </div>
              </div>
              <div className="bs-field">
                <span className="lbl">Daily min leg (c)</span>
                <input className="bs-input" type="number" min="5" max="98"
                  value={f.daily_min_c ?? ''} placeholder="60"
                  disabled={!(f.daily_enabled === true || f.daily_enabled === 'true')}
                  onChange={set('daily_min_c')} />
              </div>
              <div className="bs-field">
                <span className="lbl">Wait before raising (s)</span>
                <input className="bs-input" type="number" min="5" max="600"
                  value={f.fill_wait_s ?? ''} placeholder="60" onChange={set('fill_wait_s')} />
              </div>
              <div className="bs-field">
                <span className="lbl">Max parlays / match</span>
                <input className="bs-input" type="number" min="1" max="5"
                  value={f.max_per_event ?? ''} placeholder="2" onChange={set('max_per_event')}
                  title="how many OPEN parlays may ride on the same match - they all win or lose together, so this is the dial on correlated risk" />
              </div>
              <div className="bs-field">
                <span className="lbl">Pay over fair (c)</span>
                <input className="bs-input" type="number" min="0" max="25"
                  value={f.slippage_c ?? ''} placeholder="5" onChange={set('slippage_c')}
                  title="how many cents above the parlay's theoretical price to pay - makers quote a combo above the product of its legs, so a ceiling at fair value never trades" />
              </div>
              <div className="bs-field">
                <span className="lbl">Spend at most ($)</span>
                <input className="bs-input" type="number" min="1" max="5000" step="0.5"
                  value={f.max_usd ?? ''} placeholder="15.6" onChange={set('max_usd')}
                  title="the most one parlay may cost — it starts at the figure below and is raised once, up to this, if nobody fills it" />
              </div>
              <div className="bs-field">
                <span className="lbl">Spend at least ($)</span>
                <input className="bs-input" type="number" min="1" max="5000" step="0.5"
                  value={f.stake_usd ?? ''} placeholder="5" onChange={set('stake_usd')}
                  title="what ONE parlay may spend - the engine buys as many contracts as this covers at the price it rests, and none if it cannot cover one" />
              </div>
              <div className="bs-field">
                <span className="lbl">Bank $ (0 = unlimited)</span>
                <input className="bs-input" type="number" min="0" value={f.bank ?? ''}
                  placeholder="100" onChange={set('bank')} />
              </div>
              <div className="bs-field">
                <span className="lbl">SL % on bank</span>
                <input className="bs-input" type="number" min="0" max="99" step="0.5" value={f.bank_sl_pct ?? ''}
                  placeholder="50" onChange={set('bank_sl_pct')}
                  title="realized session loss of this % of the bank halts NEW parlays; the open one keeps being managed" />
              </div>
              <div className="bs-field">
                <span className="lbl">Leg needs &gt; ¢</span>
                <input className="bs-input" type="number" min="50" max="99" value={f.min_prob_c ?? ''}
                  placeholder="80" onChange={set('min_prob_c')}
                  title="a leg only joins when one participant's YES price is strictly ABOVE this — 80 means 'odds > 80%'" />
              </div>
              <div className="bs-field">
                <span className="lbl">From set</span>
                <input className="bs-input" type="number" min="1" max="5" value={f.min_set ?? ''}
                  placeholder="2" onChange={set('min_set')}
                  title="the match must be at least this far in before it can be a leg" />
              </div>
              <div className="bs-field">
                <span className="lbl">Must lead</span>
                <select className="bs-select" value={f.lead_scope ?? ''} onChange={set('lead_scope')}>
                  <option value="current">current set</option>
                  <option value="second">second set</option>
                  <option value="off">off · price only</option>
                </select>
              </div>
              <div className="bs-field">
                <span className="lbl">Min legs</span>
                <input className="bs-input" type="number" min="2" max="12" value={f.min_legs ?? ''}
                  placeholder="2" onChange={set('min_legs')}
                  title="2 is also the exchange's own collection minimum" />
              </div>
              <div className="bs-field">
                <span className="lbl">Max legs (0 = all)</span>
                <input className="bs-input" type="number" min="0" max="12" value={f.max_legs ?? ''}
                  placeholder="0" onChange={set('max_legs')} />
              </div>
              <div className="bs-field">
                <span className="lbl">Max open parlays</span>
                <input className="bs-input" type="number" min="1" max="10" value={f.max_open ?? ''}
                  placeholder="1" onChange={set('max_open')} />
              </div>
              <div className="bs-field">
                <span className="lbl">Cooldown (min)</span>
                <input className="bs-input" type="number" min="0" step="1" value={f.cooldown_min ?? ''}
                  placeholder="15" onChange={set('cooldown_min')}
                  title="minimum gap between two parlays" />
              </div>
              <div className="bs-field">
                <span className="lbl">TP ceiling ¢</span>
                <input className="bs-input" type="number" min="2" max="99" value={f.tp_ceiling_c ?? ''}
                  placeholder="97" onChange={set('tp_ceiling_c')}
                  title="the resting take-profit sell, in cents — this bot prices in cents, not percent" />
              </div>
              <div className="bs-field">
                <span className="lbl">Stop ¢ under entry</span>
                <input className="bs-input" type="number" min="0" max="99" value={f.stop_loss_c ?? ''}
                  placeholder="20" onChange={set('stop_loss_c')}
                  title="exit once the bid falls this many cents below the entry (0 disables)" />
              </div>
              <div className="bs-field">
                <span className="lbl">Slippage ¢ over ask</span>
                <input className="bs-input" type="number" min="0" max="20" value={f.slippage_c ?? ''}
                  placeholder="3" onChange={set('slippage_c')}
                  title="the V2 API has no market-order type — a market order is sent as a marketable immediate-or-cancel at ask + this" />
              </div>
              <div className="bs-field">
                <span className="lbl">Max price ¢ / contract</span>
                <input className="bs-input" type="number" min="2" max="99" value={f.max_price_c ?? ''}
                  placeholder="95" onChange={set('max_price_c')} />
              </div>
              <div className="bs-field" style={{ gridColumn: '1 / -1' }}>
                <span className="lbl">Empty book</span>
                <select className="bs-select"                  value={(f.limit_fallback === true || f.limit_fallback === 'true') ? 'true' : 'false'}
                  onChange={(e) => onCfg(botKey, { ...f, limit_fallback: e.target.value })}>
                  <option value="false">take nothing · a market order into an empty book fills 0</option>
                  <option value="true">rest a maker buy at the theoretical price</option>
                </select>
              </div>
              <p className="bs-note" style={{ gridColumn: '1 / -1' }}>
                Legs are tennis only — set and lead state are sport-specific and the
                engine ships one qualifier. A freshly created combined market starts
                with an empty book, so the default outcome there is no position.
              </p>
            </>
          ) : (
            <>
              <div className="bs-field">
                <span className="lbl">Target % on bank</span>
                <input className="bs-input" type="number" min="0" step="0.5" value={f.target_pct ?? ''}
                  placeholder="off" onChange={set('target_pct')} />
              </div>
              <div className="bs-field">
                <span className="lbl">SL % on bank / sport</span>
                <input className="bs-input" type="number" min="0" max="99" step="0.5" value={f.bank_sl_pct ?? ''}
                  placeholder="off" onChange={set('bank_sl_pct')} />
              </div>
              <div className="bs-field" style={{ gridColumn: '1 / -1' }}>
                <span className="lbl">No trade times (local)</span>
                <input className="bs-input" value={f.no_trade_times ?? '16:00-20:00'}
                  placeholder="16:00-20:00" onChange={set('no_trade_times')}
                  title="comma-separated HH:MM-HH:MM quiet windows on the machine's clock — no NEW bets inside them (open positions keep being managed); clear to bet around the clock" />
              </div>
            </>
          )}
        </div>

        {isSports && ['tennis', 'baseball'].map((sport) => (
          <div key={sport} className={`bs-sport ${sportOn(sport) ? '' : 'off'}`}>
            <label className="head">
              <input type="checkbox" checked={sportOn(sport)} onChange={toggleSport(sport)} />
              {sport}
            </label>
            <div className="grid">
              <div className="bs-field">
                <span className="lbl">Contracts</span>
                <input className="bs-input" type="number" min="1" placeholder="bot default"                  value={((f.sports || {})[sport] || {}).contracts ?? ''}
                  disabled={!sportOn(sport)} onChange={setSport(sport, 'contracts')} />
              </div>
              <div className="bs-field">
                <span className="lbl">Bank $ (0 = unlimited)</span>
                <input className="bs-input" type="number" min="0" placeholder="bot default"                  value={((f.sports || {})[sport] || {}).bank ?? ''}
                  disabled={!sportOn(sport)} onChange={setSport(sport, 'bank')} />
              </div>
              {sport === 'tennis' && (
                <div className="bs-field">
                  <span className="lbl">Model</span>
                  <select className="bs-select" value={((f.sports || {})[sport] || {}).model ?? ''}
                    disabled={!sportOn(sport)} onChange={setSport(sport, 'model')}>
                    {/* Empty value = send no TENNIS_MODEL at all, which the
                        adapter resolves to v5. Keeping the default as "send
                        nothing" means a launch cannot pin a model that later
                        gets renamed or retired. */}
                    <option value="">v5 · default (50–62¢ whitelist)</option>
                    <option value="v6">v6 · favourite-only (v1 engine)</option>
                    <option value="v4">v4 · v3 + risk rules</option>
                    <option value="v3">v3 · + exits, favourite ladder</option>
                    <option value="v2">v2 · 07/06 snapshot</option>
                    <option value="v1">v1 · frozen weekend</option>
                  </select>
                </div>
              )}
            </div>
          </div>
        ))}

        <div className="bs-modeswitch">
          <button type="button" className={`bs-mode paper ${mode === 'paper' ? 'on' : ''}`}
            onClick={() => setMode('paper')} disabled={busy}>📝 PAPER</button>
          <button type="button" className={`bs-mode live ${mode === 'live' ? 'on' : ''}`}
            onClick={() => setMode('live')} disabled={busy}>🔴 LIVE</button>
        </div>
        {liveLocked && (
          <p className="bs-note warn">
            LIVE locked: the server runs VIDURA_PAPER_ONLY=true. Unlock it and restart the API,
            then re-toggle PAPER → LIVE here.
          </p>
        )}

        <div className="bs-actions">
          <button type="button" className="bs-launch" onClick={start}
            disabled={busy || !user || liveLocked}>
            {busy ? '…' : liveLocked ? '🔒 LIVE LOCKED' : `▶ LAUNCH ${mode.toUpperCase()}`}
          </button>
          <button type="button" className="bs-logbtn" onClick={onLogs}>◉ LOGS</button>
          <button type="button" className="bs-cancel" onClick={onClose}>Close</button>
          {!running && err && <span className="bs-err">✗ {err}</span>}
        </div>
        <p className="bs-note" style={{ marginTop: 8 }}>
          Config persists in this browser. Mode always resets to PAPER — a refresh can
          never come back silently armed to LIVE.
        </p>
      </div>
    </div>
  );
}

// ── launch-all modal: double-click the helios core to start every bot ─────
function LaunchAllModal({ user, statuses, onClose, onChanged, onGuard }) {
  const defaultBank = '50';
  const [bank, setBank] = useState(defaultBank);
  const [perBotBank, setPerBotBank] = useState(() => {
    const m = {};
    BOTS.forEach((b) => { m[b.key] = defaultBank; });
    return m;
  });
  const [perBotContracts, setPerBotContracts] = useState(() => {
    const m = {};
    BOTS.forEach((b) => { m[b.key] = String(BOT_DEFAULTS[b.key]?.contracts || 25); });
    return m;
  });
  const [selectedBots, setSelectedBots] = useState(() => {
    const m = {};
    BOTS.forEach((b) => { m[b.key] = true; });
    return m;
  });
  const [targetPct, setTargetPct] = useState('30');
  const [slPct, setSlPct] = useState('20');
  const [mode, setMode] = useState('paper');
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState(null);
  const [result, setResult] = useState(null);
  const liveLock = useLiveLock(mode === 'live');
  const liveLocked = mode === 'live' && (!liveLock || liveLock.paperOnly);

  const setAllBanks = (v) => {
    setBank(v);
    setPerBotBank((prev) => {
      const next = {};
      BOTS.forEach((b) => { next[b.key] = v; });
      return next;
    });
  };

  useEffect(() => {
    const onKey = (e) => {
      if (e.key === 'Escape' && !busy) onClose();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose, busy]);

  const selected = useMemo(() => BOTS.filter((b) => selectedBots[b.key]), [selectedBots]);
  const alreadyRunning = useMemo(() =>
    BOTS.filter((b) => statuses[b.key]?.running), [statuses]);

  const stopAll = async () => {
    if (busy) return;
    if (alreadyRunning.length === 0) return;
    const ok = await confirmDialog({
      title: `Stop all ${alreadyRunning.length} running bot${alreadyRunning.length > 1 ? 's' : ''}?`,
      body: `${alreadyRunning.map((b) => b.label).join(', ')} will be stopped immediately.`,
      confirmText: 'STOP ALL',
      cancelText: 'Cancel',
    });
    if (!ok) return;
    setBusy(true);
    setErr(null);
    setResult(null);
    const results = { ok: [], fail: [] };
    const stops = alreadyRunning.map(async (bot) => {
      const isCommodity = bot.key === 'gold15' || bot.key === 'silver15' || bot.key === 'oil15';
      const isBtc = bot.key === 'btc15' || bot.key === 'btc60';
      const isParley = bot.key === 'parley';
      const body = {};
      try {
        await (isCommodity ? vidura.commodityStop(bot.key, body)
          : isBtc ? vidura.btcStop(bot.key, body)
          : isParley ? vidura.parleyStop(body) : vidura.sportsStop(body));
        results.ok.push(bot.label);
      } catch (e) {
        results.fail.push(`${bot.label}: ${typeof e.detail === 'string' ? e.detail : typeof e.detail === 'object' ? JSON.stringify(e.detail) : e.message || 'error'}`);
      }
    });
    await Promise.allSettled(stops);
    setBusy(false);
    setResult({ ok: results.ok.map((l) => `${l} stopped`), fail: results.fail });
    onChanged();
    if (results.fail.length === 0) {
      setTimeout(() => onClose(), 1200);
    }
  };

  const startAll = async () => {
    if (busy) return;
    if (selected.length === 0) { setErr('Select at least one bot'); return; }
    const tgtNum = parseFloat(targetPct);
    const slNum = parseFloat(slPct);
    for (const b of selected) {
      const v = parseFloat(perBotBank[b.key]);
      if (!v || v <= 0) { setErr(`Bank for ${b.label} must be > 0`); return; }
    }
    if (!tgtNum || tgtNum <= 0) { setErr('Target % must be > 0'); return; }
    if (!slNum || slNum <= 0 || slNum >= 100) { setErr('Loss % must be 1-99'); return; }

    if (liveLocked) { setErr('Live mode is locked by VIDURA_PAPER_ONLY'); return; }

    const selRunning = selected.filter((b) => statuses[b.key]?.running);
    const totalBank = selected.reduce((s, b) => s + (parseFloat(perBotBank[b.key]) || 0), 0);
    const label = selected.length === BOTS.length ? `ALL ${BOTS.length} BOTS` : `${selected.length} BOT${selected.length > 1 ? 'S' : ''}`;
    const ok = await confirmDialog({
      title: mode === 'live'
        ? `LAUNCH ${label} — LIVE, real money?`
        : `Launch ${label} in PAPER mode?`,
      body: `${selected.map((b) => b.label).join(', ')}\nTotal bank $${totalBank} · Target +${tgtNum}% · Stop-loss −${slNum}%\n${selRunning.length > 0 ? selRunning.map((b) => b.label).join(', ') + ' will be killed & restarted.\n' : ''}Selected bots stop when combined session hits target or loss.`,
      confirmText: mode === 'live' ? 'YES, LAUNCH LIVE' : 'Launch',
      cancelText: 'Cancel',
    });
    if (!ok) return;

    setBusy(true);
    setErr(null);
    setResult(null);

    const results = { ok: [], fail: [] };

    // Stop what is already running before relaunching it. The confirmation
    // says these "will be killed & restarted", and the desk has to be the one
    // that does it: a start against a running bot is refused as BotBusy, so
    // without this the promise in the dialog was not kept.
    await Promise.allSettled(selRunning.map(async (bot) => {
      const c = bot.key === 'gold15' || bot.key === 'silver15' || bot.key === 'oil15';
      const b = bot.key === 'btc15' || bot.key === 'btc60';
      const pl = bot.key === 'parley';
      return (c ? vidura.commodityStop(bot.key, {})
        : b ? vidura.btcStop(bot.key, {})
          : pl ? vidura.parleyStop({}) : vidura.sportsStop({}));
    }));

    const launches = selected.map(async (bot) => {
      const botBank = parseFloat(perBotBank[bot.key]) || 0;
      const isCommodity = bot.key === 'gold15' || bot.key === 'silver15' || bot.key === 'oil15';
      const isBtc = bot.key === 'btc15' || bot.key === 'btc60';
      const isParley = bot.key === 'parley';
      // The numbers the operator actually typed. This sent a hardcoded 0 for
      // the target and never sent the stop-loss at all: both went only to the
      // station-level guard, so a form that validated "Target % must be > 0"
      // and a dialog that confirmed "Target +50%" still launched every bot
      // with no target of its own. It was silently accepted until the bot
      // schema began checking, which is when it surfaced as
      // "bank_tp_pct must be at least 1, got 0".
      //
      // kill_existing is gone with it: it was never a bot option, so it would
      // have been refused as an unknown field. Restarting a running bot is
      // something the DESK does, below, before launching.
      const body = {
        mode,
        bankroll: botBank,
        bank_tp_pct: tgtNum,
        bank_sl_pct: slNum,
        contracts: parseInt(perBotContracts[bot.key] || '25', 10),
      };
      if (isParley) {
        const pd = BOT_DEFAULTS.parley;
        body.min_prob_c = parseInt(pd.min_prob_c, 10);
        body.min_set = parseInt(pd.min_set, 10);
        body.lead_scope = pd.lead_scope;
        body.min_legs = parseInt(pd.min_legs, 10);
        body.max_legs = parseInt(pd.max_legs, 10);
        body.max_open = parseInt(pd.max_open, 10);
        body.cooldown_min = parseInt(pd.cooldown_min, 10);
        body.slippage_c = parseInt(pd.slippage_c, 10);
        body.max_price_c = parseInt(pd.max_price_c, 10);
        body.tp_ceiling_c = parseInt(pd.tp_ceiling_c, 10);
        body.stop_loss_c = parseInt(pd.stop_loss_c, 10);
      }
      if (!isParley && !isBtc && !isCommodity) {
        body.sport_settings = {};
        for (const sp of Object.keys(BOT_DEFAULTS.sports.sports)) {
          body.sport_settings[sp] = {
            contracts: parseInt(BOT_DEFAULTS.sports.sports[sp].contracts, 10),
            bank: botBank,
          };
        }
      }
      try {
        const startFn = isCommodity ? () => vidura.commodityStart(bot.key, body)
          : isBtc ? () => vidura.btcStart(bot.key, body)
          : isParley ? () => vidura.parleyStart(body)
          : () => vidura.sportsStart(body);
        await startFn();
        results.ok.push(bot.label);
      } catch (e) {
        results.fail.push(`${bot.label}: ${typeof e.detail === 'string' ? e.detail : typeof e.detail === 'object' ? JSON.stringify(e.detail) : e.message || 'error'}`);
      }
    });

    await Promise.allSettled(launches);
    setBusy(false);
    setResult(results);
    if (results.ok.length > 0) {
      onChanged();
      const avgBank = selected.reduce((s, b) => s + (parseFloat(perBotBank[b.key]) || 0), 0) / selected.length;
      onGuard({ bank: avgBank, target_pct: tgtNum, sl_pct: slNum });
    }
    if (results.fail.length === 0) {
      setTimeout(() => onClose(), 1200);
    }
  };

  return (
    <div className="bs-modal-backdrop"      onMouseDown={(e) => { if (e.target === e.currentTarget && !busy) onClose(); }}>
      <div className="bs-modal" style={{ maxWidth: 480 }}>
        <div className="bs-modal-hd">
          <h2>LAUNCH ALL BOTS</h2>
          <button type="button" className="close" onClick={onClose} disabled={busy}>x</button>
        </div>
        <div className="bs-modal-bd" style={{ padding: '16px 20px' }}>
          {alreadyRunning.length > 0 && (
            <div style={{ marginBottom: 14, padding: '10px 12px', background: 'rgba(255,179,71,0.1)',
              border: '1px solid rgba(255,179,71,0.3)', borderRadius: 6, display: 'flex', gap: 10, alignItems: 'flex-start' }}>
              <span style={{ fontSize: 18, lineHeight: 1 }}>&#9888;</span>
              <div style={{ fontFamily: '"JetBrains Mono", monospace', fontSize: 12, color: 'var(--bs-warn, #ffb347)' }}>
                <div style={{ fontWeight: 700, marginBottom: 2 }}>{alreadyRunning.length} bot{alreadyRunning.length > 1 ? 's' : ''} already running</div>
                <div style={{ color: 'rgba(255,255,255,0.6)' }}>{alreadyRunning.map((b) => b.label).join(', ')} will be killed and restarted.</div>
              </div>
            </div>
          )}

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px 16px', marginBottom: 16 }}>
            <div className="bs-field">
              <span className="lbl">Default bank ($)</span>
              <input className="bs-input" type="number" min="1" step="1" value={bank}
                onChange={(e) => setAllBanks(e.target.value)} disabled={busy} />
            </div>
            <div className="bs-field">
              <span className="lbl">Mode</span>
              <select className="bs-input" value={mode}
                onChange={(e) => setMode(e.target.value)} disabled={busy}>
                <option value="paper">PAPER</option>
                <option value="live" disabled={liveLocked}>LIVE</option>
              </select>
            </div>
            <LiveModeNotice mode={mode} accent="#f87171" />
            <div className="bs-field">
              <span className="lbl">Target % on bank</span>
              <input className="bs-input" type="number" min="1" max="999" step="0.5" value={targetPct}
                onChange={(e) => setTargetPct(e.target.value)} disabled={busy} />
            </div>
            <div className="bs-field">
              <span className="lbl">Stop-loss % on bank</span>
              <input className="bs-input" type="number" min="1" max="99" step="0.5" value={slPct}
                onChange={(e) => setSlPct(e.target.value)} disabled={busy} />
            </div>
          </div>

          <div style={{ marginBottom: 16, padding: '10px 12px', background: 'rgba(255,255,255,0.04)',
            border: '1px solid rgba(255,255,255,0.08)', borderRadius: 6 }}>
            <div style={{ fontFamily: '"JetBrains Mono", monospace', fontSize: 12, color: 'rgba(255,255,255,0.7)' }}>
              <div style={{ display: 'grid', gridTemplateColumns: '24px 1fr 80px 70px auto', gap: '4px 8px', alignItems: 'center',
                marginBottom: 6, paddingBottom: 4, borderBottom: '1px solid rgba(255,255,255,0.1)',
                fontSize: 10, textTransform: 'uppercase', color: 'rgba(255,255,255,0.4)' }}>
                <input type="checkbox" checked={selected.length === BOTS.length} disabled={busy}
                  onChange={(e) => {
                    const v = e.target.checked;
                    setSelectedBots(() => {
                      const m = {};
                      BOTS.forEach((b) => { m[b.key] = v; });
                      return m;
                    });
                  }}
                  style={{ width: 14, height: 14, accentColor: '#ffd700', cursor: 'pointer' }} />
                <span>Bot</span><span>Bank ($)</span><span>Contracts</span><span>Status</span>
              </div>
              {BOTS.map((b) => {
                const isRunning = statuses[b.key]?.running;
                const checked = !!selectedBots[b.key];
                return (
                  <div key={b.key} style={{ display: 'grid', gridTemplateColumns: '24px 1fr 80px 70px auto', gap: '4px 8px',
                    alignItems: 'center', padding: '3px 0', opacity: checked ? 1 : 0.4 }}>
                    <input type="checkbox" checked={checked} disabled={busy}
                      onChange={(e) => setSelectedBots((p) => ({ ...p, [b.key]: e.target.checked }))}
                      style={{ width: 14, height: 14, accentColor: b.accent, cursor: 'pointer' }} />
                    <span style={{ color: b.accent }}>{b.label}</span>
                    <input className="bs-input" type="number" min="1" step="1"
                      value={perBotBank[b.key] || ''} disabled={busy || !checked}
                      onChange={(e) => setPerBotBank((p) => ({ ...p, [b.key]: e.target.value }))}
                      style={{ height: 24, fontSize: 12, padding: '2px 6px' }} />
                    <input className="bs-input" type="number" min="1" step="1"
                      value={perBotContracts[b.key] || ''} disabled={busy || !checked}
                      onChange={(e) => setPerBotContracts((p) => ({ ...p, [b.key]: e.target.value }))}
                      style={{ height: 24, fontSize: 12, padding: '2px 6px', textAlign: 'center' }} />
                    <span style={{ fontSize: 10, fontWeight: 700,
                      color: isRunning ? 'var(--bs-warn, #ffb347)' : 'var(--bs-ok, #4caf50)' }}>
                      {isRunning ? 'RUNNING' : 'IDLE'}
                    </span>
                  </div>
                );
              })}
              <div style={{ borderTop: '1px solid rgba(255,255,255,0.1)', marginTop: 6, paddingTop: 6,
                display: 'flex', justifyContent: 'space-between', fontWeight: 700 }}>
                <span>Total bank ({selected.length}/{BOTS.length} bots)</span>
                <span>{'$'}{selected.reduce((s, b) => s + (parseFloat(perBotBank[b.key]) || 0), 0)}</span>
              </div>
            </div>
          </div>

          {err && <p className="bs-note" style={{ color: 'var(--bs-crit, #ff5c5c)', marginBottom: 8 }}>{err}</p>}

          {result && (
            <div style={{ marginBottom: 12, fontFamily: '"JetBrains Mono", monospace', fontSize: 12 }}>
              {result.ok.length > 0 && (
                <p style={{ color: 'var(--bs-ok, #4caf50)', margin: '4px 0' }}>
                  Launched: {result.ok.join(', ')}
                </p>
              )}
              {result.fail.length > 0 && result.fail.map((f, i) => (
                <p key={i} style={{ color: 'var(--bs-crit, #ff5c5c)', margin: '4px 0' }}>{f}</p>
              ))}
            </div>
          )}

          <div style={{ display: 'flex', gap: 12, justifyContent: 'flex-end' }}>
            {alreadyRunning.length > 0 && (
              <button type="button" className="bs-btn" onClick={stopAll} disabled={busy}
                style={{ background: 'var(--bs-crit, #ff5c5c)', color: '#fff', fontWeight: 700, marginRight: 'auto' }}>
                {busy ? 'Stopping...' : `STOP ALL ${alreadyRunning.length} BOTS`}
              </button>
            )}
            <button type="button" className="bs-btn" onClick={onClose} disabled={busy}
              style={{ background: 'rgba(255,255,255,0.08)' }}>Cancel</button>
            <button type="button" className="bs-btn" onClick={startAll} disabled={busy}
              style={{ background: mode === 'live' ? 'var(--bs-crit, #ff5c5c)' : '#ffd700',
                color: '#000', fontWeight: 700 }}>
              {busy ? 'Launching...' : selected.length === BOTS.length ? `LAUNCH ALL ${BOTS.length} BOTS` : `LAUNCH ${selected.length} BOT${selected.length !== 1 ? 'S' : ''}`}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

// ── the world ──────────────────────────────────────────────────────────────
export default function BotStationSite() {
  const [user, setUser] = useState(null);
  const [userErr, setUserErr] = useState(false);
  const [statuses, setStatuses] = useState({});   // key -> BotStatusOut
  const [pv, setPv] = useState(null);
  const [bots, setBots] = useState([]);           // /bots registry (versions)
  const [feed, setFeed] = useState(null);         // merged recent trades
  const [feedFilter, setFeedFilter] = useState('all');   // all | btc15 | btc60 | sports
  const [perf, setPerf] = useState({});           // key -> {trades,wins,losses,pnl}
  const [pnlWin, setPnlWin] = useState(null);     // {d1, d7, d30} rolling P&L
  const [pvHist, setPvHist] = useState(null);     // daily PV snapshots (graph)
  // the PV graph ships collapsed; the choice sticks per browser
  const [pvOpen, setPvOpen] = useState(() => {
    try { return localStorage.getItem('vidura.botstation.pvopen') === '1'; } catch { return false; }
  });
  const togglePvOpen = () => setPvOpen((o) => {
    try { localStorage.setItem('vidura.botstation.pvopen', o ? '0' : '1'); } catch { /* ignore */ }
    return !o;
  });
  const [console_, setConsole] = useState(null);  // botKey | null
  const [logsFor, setLogsFor] = useState(null);   // botKey | null — dbl-click feed
  const [launchAll, setLaunchAll] = useState(false);
  const [stationGuard, setStationGuard] = useState(null); // { bank, target_pct, sl_pct, pv_at_launch, draining } | null
  const stationHaltedRef = useRef(false);
  // Launch/stop history from the DB. It used to live in localStorage,
  // appended whenever a tab happened to see a status change -- so it was
  // empty on a new machine, wrong after a reload, and silent about anything
  // that happened while nobody was watching. A bot exiting on its own at 3am
  // is exactly the event this panel is for, and exactly the one a
  // browser-side list could never record.
  const [botStopLog, setBotStopLog] = useState([]);
  const [showAllStopLog, setShowAllStopLog] = useState(false);
  const [cfg, setCfg] = useState(loadCfg);
  const [clock, setClock] = useState(() => new Date());

  useEffect(() => {
    try { localStorage.setItem(CFG_KEY, JSON.stringify(cfg)); } catch { /* ignore */ }
  }, [cfg]);
  const onCfg = useCallback((k, v) => setCfg((p) => ({ ...p, [k]: v })), []);

  useEffect(() => {
    let alive = true;
    ensureUser().then((u) => { if (alive) { setUser(u); setUserErr(false); } })
      .catch(() => { if (alive) setUserErr(true); });
    return () => { alive = false; };
  }, []);

  // One request per bot, keyed by the bot it asked about.
  //
  // This used to make four family calls and iterate two of the responses as
  // lists — but each returns ONE status object, so `for (const s of btcList)`
  // threw "not iterable". The throw landed in the catch below, setStatuses was
  // never reached, and `statuses` stayed empty: every tile rendered IDLE
  // while the bots were running, and the swallowed error said nothing.
  //
  // The four calls also only ever asked about btc15, sports, parley and
  // gold15, so btc60, silver15 and oil15 could not have had a status at all.
  // Asking per bot means the station shows what is actually running, and a
  // new bot appears with no change here.
  const loadStatuses = useCallback(async () => {
    if (!user) return;
    try {
      // ONE request for all seven. This polled each bot separately every ten
      // seconds — seven requests and seven database sessions per tick, which
      // was most of the desk's steady-state load and part of what exhausted
      // the server's connection pool.
      const all = await vidura.botStatuses();
      if (all && Object.keys(all).length) setStatuses(all);
    } catch {
      // Keep the last good picture rather than blanking every tile on one
      // failed poll. A stale status reads as stale; an empty one reads as
      // "nothing is running", which is a different and worse claim.
    }
  }, [user]);

  // ONE call, one table. This used to be eight requests against four
  // per-family CSV endpoints, whose numbers the v2/v6 engines never wrote --
  // which is why every P&L window read $0.00 while real money was moving.
  // bot_trade is now written at entry by every bot, so the desk reads that
  // and nothing else.
  const loadFeed = useCallback(async () => {
    if (!user) return;
    try {
      const [out, runs] = await Promise.all([
        vidura.tradeEventLog({ limit: 500 }),
        vidura.botRuns({ limit: 60 }).catch(() => ({ runs: [] })),
      ]);
      setFeed(out.trades || []);
      setBotStopLog(runs.runs || []);

      // The windows arrive already computed, over the WHOLE ledger rather
      // than over the page on screen, and banded on when a trade CLOSED.
      const w = out.windows || {};
      const at = (k) => (w[k] ? w[k].pnl : 0);
      setPnlWin({
        h3: at('3h'), h6: at('6h'), d1: at('24h'),
        d7: at('7d'), d30: at('30d'), d60: at('60d'),
      });

      // Per-bot 7d record, from the same rows.
      const closedMs = (x) => {
        const iso = x.closed_at || x.opened_at || '';
        return new Date(/Z$|[+-]\d\d:?\d\d$/.test(iso) ? iso : `${iso}Z`).getTime();
      };
      const cutoff7 = Date.now() - 7 * 86400e3;
      const p = {};
      for (const key of BOTS.map((b) => b.key)) {
        const rows = (out.trades || []).filter(
          (x) => (x.bot || '').toLowerCase() === key && closedMs(x) >= cutoff7);
        p[key] = {
          trades: rows.length,
          wins: rows.filter((x) => x.status === 'WON').length,
          losses: rows.filter((x) => x.status === 'LOST').length,
          pnl: rows.reduce((sum, x) => sum + (x.pnl || 0), 0),
        };
      }
      setPerf(p);
    } catch { /* keep last */ }
  }, [user]);

  // event-log sync: pull the bots' freshest CSV rows into the DB, then settle
  // every stale-open row's P&L from Kalshi fills+settlements, refreshing the
  // UI after each stage so corrections appear iteratively
  const [feedSync, setFeedSync] = useState({ busy: false, note: null });
  const syncFeed = useCallback(async () => {
    if (!user || feedSync.busy) return;
    setFeedSync({ busy: true, note: 'pulling bot ledgers…' });
    try {
      // No CSV pull any more. Bots write to bot_trade the moment they enter,
      // so there is nothing to import -- this only asks Kalshi what became of
      // the rows that are still open.
      setFeedSync({ busy: true, note: 'settling P&L from Kalshi…' });
      const rec = await vidura.botsReconcile(user.user_id, 1, true);
      await loadFeed();
      const tu = rec.true_up || {};
      setFeedSync({
        busy: false,
        note: `${rec.updated} settled · `
          + `${tu.corrected || 0} fee-trued of ${tu.checked || 0} checked`,
      });
    } catch (e) {
      setFeedSync({ busy: false, note: `sync failed: ${errText(e)}` });
    }
  }, [user, feedSync.busy, loadFeed]);

  const loadPv = useCallback(async () => {
    if (!user) return;
    try { setPv(await vidura.portfolio(user.user_id)); } catch { /* creds missing */ }
    try {
      const h = await vidura.portfolioHistory(user.user_id);
      setPvHist((h.items || []).filter((x) => x.total_usd !== null && x.total_usd !== undefined));
    } catch { /* endpoint down — panel hides */ }
  }, [user]);

  useEffect(() => {
    if (!user) return undefined;
    vidura.bots().then(setBots).catch(() => {});
    loadStatuses();
    loadFeed();
    loadPv();
    const t1 = setInterval(() => { if (!document.hidden) loadStatuses(); }, 10_000);
    const t2 = setInterval(() => { if (!document.hidden) loadFeed(); }, 60_000);
    // async PV refresh: cheap (server caches ~30s/user), keeps the cell live
    const t3 = setInterval(() => { if (!document.hidden) loadPv(); }, 60_000);
    return () => { clearInterval(t1); clearInterval(t2); clearInterval(t3); };
  }, [user, loadStatuses, loadFeed, loadPv]);

  useEffect(() => {
    const t = setInterval(() => setClock(new Date()), 1000);
    return () => clearInterval(t);
  }, []);

  useEffect(() => {
    if (!stationGuard?.draining) return;
    const t = setInterval(() => { if (!document.hidden) loadPv(); }, 10_000);
    return () => clearInterval(t);
  }, [stationGuard?.draining, loadPv]);

  useEffect(() => {
    const onKey = (e) => {
      if (e.key === 'L' && e.shiftKey && !e.ctrlKey && !e.metaKey) {
        setLaunchAll(true);
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  // canvas + tiles view-model: key/status/pct/profit (profit colors the
  // bot's solar flare green — session P&L while running, 7d P&L when idle)
  const botStates = useMemo(() => BOTS.map((b) => {
    const idleProfit = perf[b.key] ? perf[b.key].pnl > 0 : null;
    if (!user) return { ...b, status: 'NA', pct: null, profit: null };
    const st = statuses[b.key];
    if (!st || !st.running) return { ...b, status: 'IDLE', pct: null, profit: idleProfit };
    const run = (st.runs || []).find((r) => r.status === 'running') || st.runs?.[0];
    // bank % of the session; a bank-less launch (bankroll_pct null) falls
    // back to % of portfolio value at launch — the bots' own PV baseline
    let pct = st.session?.bankroll_pct ?? null;
    if (pct === null && st.session?.pnl_usd !== null && st.session?.pnl_usd !== undefined) {
      const pv0 = run?.extra?.config?.pv_at_start?.total_usd;
      if (pv0 > 0) pct = Math.round((st.session.pnl_usd / pv0) * 10000) / 100;
    }
    // bank halt detection: session bank % vs the launch's target / bank-SL
    const targetPct = st.session?.target_pct ?? run?.extra?.config?.target_pct ?? null;
    const bankSlPct = run?.extra?.config?.bank_sl_pct ?? null;
    let bankEvent = null;
    if (pct !== null) {
      if (targetPct > 0 && pct >= targetPct) bankEvent = 'tp';
      else if (bankSlPct > 0 && pct <= -bankSlPct) bankEvent = 'sl';
    }
    return {
      ...b,
      status: run?.mode === 'live' ? 'LIVE' : 'PAPER',
      pct,
      bankEvent,
      startedAt: run?.started_at || null,
      profit: st.session?.pnl_usd !== null && st.session?.pnl_usd !== undefined
        ? st.session.pnl_usd > 0 : idleProfit,
    };
  }), [user, statuses, perf]);

  // station-level PV guard: monitors portfolio value growth from launch.
  // Phase 1 (active): PV rises by TP% → stop all bots (no new orders), enter draining.
  // Phase 2 (draining): wait for positions_usd to reach 0, then finalize.
  // SL: immediate stop at any phase.
  useEffect(() => {
    if (!stationGuard || !user || stationHaltedRef.current) return;
    if (!pv) return;
    const currentPv = (Number(pv.cash_usd) || 0) + (Number(pv.positions_usd) || 0);
    const positionsUsd = Number(pv.positions_usd) || 0;
    const pvAtLaunch = stationGuard.pv_at_launch || 0;

    if (stationGuard.draining) {
      if (positionsUsd <= 0.01) {
        stationHaltedRef.current = true;
        const pvGain = currentPv - pvAtLaunch;
        const pvPct = pvAtLaunch > 0 ? (pvGain / pvAtLaunch) * 100 : 0;
        alert(`STATION DRAIN COMPLETE\n\nAll positions closed.\nPortfolio: $${pvAtLaunch.toFixed(2)} → $${currentPv.toFixed(2)} (${pvPct >= 0 ? '+' : ''}${pvPct.toFixed(1)}%)`);
        setStationGuard(null);
        stationHaltedRef.current = false;
        loadStatuses();
        loadFeed();
        loadPv();
      }
      return;
    }

    if (pvAtLaunch <= 0) return;
    const pvGainPct = ((currentPv - pvAtLaunch) / pvAtLaunch) * 100;
    const running = BOTS.filter((b) => statuses[b.key]?.running);
    if (running.length === 0) return;

    const hitTarget = stationGuard.target_pct > 0 && pvGainPct >= stationGuard.target_pct;
    const hitSl = stationGuard.sl_pct > 0 && pvGainPct <= -stationGuard.sl_pct;
    if (!hitTarget && !hitSl) return;

    stationHaltedRef.current = true;
    const reason = hitTarget ? 'TARGET' : 'STOP-LOSS';
    (async () => {
      const stops = running.map(async (bot) => {
        const isCommodity = bot.key === 'gold15' || bot.key === 'silver15' || bot.key === 'oil15';
        const isBtc = bot.key === 'btc15' || bot.key === 'btc60';
        const isParley = bot.key === 'parley';
        const body = {};
        try {
          await (isCommodity ? vidura.commodityStop(bot.key, body)
            : isBtc ? vidura.btcStop(bot.key, body)
            : isParley ? vidura.parleyStop(body) : vidura.sportsStop(body));
        } catch { /* best-effort */ }
      });
      await Promise.allSettled(stops);
      loadStatuses();
      loadFeed();
      loadPv();

      if (hitTarget && positionsUsd > 0.01) {
        setStationGuard((g) => g ? { ...g, draining: true } : null);
        stationHaltedRef.current = false;
        alert(`STATION ${reason} HIT — DRAINING\n\nPortfolio: $${pvAtLaunch.toFixed(2)} → $${currentPv.toFixed(2)} (+${pvGainPct.toFixed(1)}%)\n\nAll bots stopped. Waiting for $${positionsUsd.toFixed(2)} in open positions to close...`);
      } else {
        const pvGain = currentPv - pvAtLaunch;
        alert(`STATION ${reason} HIT\n\nPortfolio: $${pvAtLaunch.toFixed(2)} → $${currentPv.toFixed(2)} (${pvGainPct >= 0 ? '+' : ''}${pvGainPct.toFixed(1)}%)\nP&L: ${pvGain >= 0 ? '+' : ''}$${pvGain.toFixed(2)}\n\nAll ${running.length} bots stopped.`);
        setStationGuard(null);
        stationHaltedRef.current = false;
      }
    })();
  }, [statuses, stationGuard, user, pv, loadStatuses, loadFeed, loadPv]);

  // The stop detector that used to live here is gone. It compared this
  // tab's previous statuses to the current ones and appended to a
  // localStorage list, which meant the Bots Log only ever knew about
  // events this browser was awake for. bot_run records every launch and
  // stop as it happens, so the panel reads that instead -- see loadFeed.

  const runningCount = botStates.filter((b) => b.status === 'LIVE' || b.status === 'PAPER').length;
  const anyLive = botStates.some((b) => b.status === 'LIVE');
  const plColor = (v) => (v > 0 ? 'var(--bs-good)' : v < 0 ? 'var(--bs-crit)' : undefined);
  // PV is CASH + POSITIONS, summed here — never the backend's total field
  const pvTotal = pv ? (Number(pv.cash_usd) || 0) + (Number(pv.positions_usd) || 0) : null;

  const versionsFor = (key) => (bots.find((b) => b.key === key)?.versions) || [];

  const chipFor = (k) => BOT_BY_KEY[k]?.chip || 'sp';

  const stationPnl = useMemo(() => {
    if (!stationGuard || !pv) return null;
    const pvAtLaunch = stationGuard.pv_at_launch || 0;
    const currentPv = (Number(pv.cash_usd) || 0) + (Number(pv.positions_usd) || 0);
    const positionsUsd = Number(pv.positions_usd) || 0;
    const gain = currentPv - pvAtLaunch;
    const pct = pvAtLaunch > 0 ? (gain / pvAtLaunch) * 100 : 0;
    return { pnl: gain, pct, pvAtLaunch, currentPv, positionsUsd, draining: !!stationGuard.draining };
  }, [stationGuard, pv]);

  const tickerItems = [
    `STATION ${anyLive ? 'LIVE TRADING' : runningCount ? 'PAPER OPS' : 'IDLE'}`,
    `BOTS RUNNING ${runningCount}/${BOTS.length}`,
    `PV ${pvTotal !== null ? usd(pvTotal) : '—'}`,
    `P&L 3H ${pnlWin ? usd(pnlWin.h3) : '—'} · 6H ${pnlWin ? usd(pnlWin.h6) : '—'} · 24H ${pnlWin ? usd(pnlWin.d1) : '—'} · 7D ${pnlWin ? usd(pnlWin.d7) : '—'} · 30D ${pnlWin ? usd(pnlWin.d30) : '—'} · 60D ${pnlWin ? usd(pnlWin.d60) : '—'}`,
    ...BOTS.map((b) => {
      const p = perf[b.key];
      return `${b.label} W${p?.wins ?? 0}/L${p?.losses ?? 0} · ${usd(p?.pnl ?? 0)}`;
    }),
    `OPERATOR ${user ? user.username.toUpperCase() : 'NOT FOUND'}`,
    ...(stationPnl ? [`GUARD PV $${stationPnl.pvAtLaunch.toFixed(0)}→$${stationPnl.currentPv.toFixed(0)} (${stationPnl.pct >= 0 ? '+' : ''}${stationPnl.pct.toFixed(1)}%) · TP +${stationGuard.target_pct}% SL -${stationGuard.sl_pct}%${stationPnl.draining ? ' · DRAINING $' + stationPnl.positionsUsd.toFixed(2) : ''}`] : []),
  ];

  return (
    <div className="bs-root">
      <WorldHeader accent="#ffb347" title="BOT Prediction Station" showSound={false}
        right={(
          <span className={`bs-user ${user ? '' : 'na'}`}
            title={user ? `operator ${user.username} · ${user.user_id}` : 'no user found — bots read NA'}>
            <span className="dot" />
            {user ? user.username.charAt(0).toUpperCase() + user.username.slice(1) : 'NO OPERATOR'}
          </span>
        )} />
      <div className="bs-content">

        {/* status strip */}
        <div className="bs-bar">
          <div className="bs-cell">
            <div className="bs-brand">
              <svg className="glyph" viewBox="0 0 24 24" aria-hidden="true">
                <circle cx="12" cy="12" r="5" fill="#ffb347" />
                {Array.from({ length: 8 }, (_, i) => (
                  <line key={i} x1="12" y1="2" x2="12" y2="5" stroke="#ff8a2b" strokeWidth="1.6"                    transform={`rotate(${i * 45} 12 12)`} />
                ))}
              </svg>
              <div>
                <div className="t1">BOT PREDICTION STATION</div>
                <div className="t2">KALSHI BOTS · MISSION CONTROL</div>
              </div>
            </div>
          </div>
          <div className="bs-cell"><span className="k">CST · bot clock</span>
            <span className="v sun">
              {clock.toLocaleTimeString('en-US', { timeZone: 'America/Chicago', hour12: true })}
            </span></div>
          <div className="bs-cell"><span className="k">Portfolio value</span>
            <span className="v cyan" title={pv ? `cash ${usd(pv.cash_usd)} + positions ${usd(pv.positions_usd)}` : ''}>
              {pvTotal !== null ? usd(pvTotal) : '—'}</span></div>
          <div className="bs-cell"><span className="k">Cash / Positions</span>
            <span className="v">{pv ? `${usd(pv.cash_usd)} · ${usd(pv.positions_usd)}` : '—'}</span></div>
          <div className="bs-cell"><span className="k">3H P&L</span>
            <span className="v" style={{ color: plColor(pnlWin?.h3) }}>{pnlWin ? usd(pnlWin.h3) : '—'}</span></div>
          <div className="bs-cell"><span className="k">6H P&L</span>
            <span className="v" style={{ color: plColor(pnlWin?.h6) }}>{pnlWin ? usd(pnlWin.h6) : '—'}</span></div>
          <div className="bs-cell"><span className="k">24H P&L</span>
            <span className="v" style={{ color: plColor(pnlWin?.d1) }}>{pnlWin ? usd(pnlWin.d1) : '—'}</span></div>
          <div className="bs-cell"><span className="k">7D P&L</span>
            <span className="v" style={{ color: plColor(pnlWin?.d7) }}>{pnlWin ? usd(pnlWin.d7) : '—'}</span></div>
          <div className="bs-cell"><span className="k">30D P&L</span>
            <span className="v" style={{ color: plColor(pnlWin?.d30) }}>{pnlWin ? usd(pnlWin.d30) : '—'}</span></div>
          <div className="bs-cell grow"><span className="k">60D P&L</span>
            <span className="v" style={{ color: plColor(pnlWin?.d60) }}>{pnlWin ? usd(pnlWin.d60) : '—'}</span></div>
          <div className="bs-cell"><span className="k">Station status</span>
            <span className={`v bs-st-${anyLive ? 'LIVE' : runningCount ? 'PAPER' : 'IDLE'}`}>
              {anyLive ? 'LIVE' : runningCount ? 'PAPER OPS' : 'IDLE'}</span>
            {stationGuard && <span className="v" style={{ fontSize: 10, color: stationGuard.draining ? '#ff9800' : '#ffd700', display: 'block', marginTop: 2 }}>
              {stationGuard.draining ? 'DRAINING' : 'GUARD'} +{stationGuard.target_pct}% / -{stationGuard.sl_pct}%
              {stationPnl && <span style={{ display: 'block', fontSize: 9, color: 'rgba(255,255,255,0.5)' }}>
                PV ${stationPnl.pvAtLaunch.toFixed(0)} → ${stationPnl.currentPv.toFixed(0)}
                {stationGuard.draining && ` · pos $${stationPnl.positionsUsd.toFixed(2)}`}
              </span>}
            </span>}
          </div>
        </div>

        <div className="bs-grid">
          {/* left: telemetry */}
          <div className="bs-col">
            <div className="bs-panel">
              <div className="bs-panel-hd"><h3>Bot Cores</h3><span className="idx">BOT·01</span></div>
              <div className="bs-bots">
                {botStates.map((b) => (
                  <button type="button" key={b.key} className="bs-bot" onClick={() => setConsole(b.key)}>
                    <span className={`dot bs-dot-${b.status}`} />
                    <span>
                      <span className="name" style={{ color: b.accent }}>{b.label}</span>
                      <span className="sub"> · {b.sub}</span>
                    </span>
                    <span className="st">
                      <span className={`bs-st-${b.status}`}>{b.status}</span>
                      {(b.status === 'LIVE' || b.status === 'PAPER') && b.startedAt && (
                        <span className="pct uptime" title="run time">⏱ {fmtElapsed(b.startedAt, clock.getTime())}</span>
                      )}
                    </span>
                  </button>
                ))}
              </div>
            </div>

            <div className="bs-panel">
              <div className="bs-panel-hd"><h3>Session Telemetry</h3><span className="idx">TEL·02</span></div>
              <div className="bs-panel-bd">
                {BOTS.map((b) => {
                  const st = statuses[b.key];
                  const s = st?.session;
                  // contracts of the RUNNING bot, from its recorded launch
                  // config (btc: one number; sports: per enabled sport)
                  const run = st?.running
                    ? (st.runs || []).find((r) => r.status === 'running') : null;
                  let contracts = null;
                  if (run) {
                    if (b.key === 'sports') {
                      const ss = run.extra?.sport_settings || {};
                      const parts = (run.extra?.sports || Object.keys(ss))
                        .map((sp) => `${sp.slice(0, 3)} ${ss[sp]?.contracts != null ? `${ss[sp].contracts}c` : 'def'}`);
                      contracts = parts.length ? parts.join(' · ') : 'default c';
                    } else {
                      const n = run.extra?.config?.contracts;
                      contracts = n != null ? `${n}c` : 'default c';
                    }
                  }
                  return (
                    <div className="bs-ro" key={b.key}>
                      <span className="l" style={{ color: b.accent }}>{b.label}</span>
                      <span className={`r ${s ? (s.pnl_usd > 0 ? 'good' : s.pnl_usd < 0 ? 'crit' : '') : 'dim'}`}>
                        {s ? `${usd(s.pnl_usd)} ` : '— '}
                        <span className="u">
                          {s
                            ? `${s.trades_open ?? 0} open · ${s.won ?? 0}W ${s.lost ?? 0}L`
                            : 'no session'}
                          {s && s.staked_usd ? ` · ${usd(s.staked_usd)} in` : ''}
                          {contracts !== null && ` · ${contracts}`}
                        </span>
                      </span>
                    </div>
                  );
                })}
                <div className="bs-ro">
                  <span className="l">Operator</span>
                  <span className={`r ${user ? 'sun' : 'dim'}`}>{user ? user.username : 'NOT FOUND'}</span>
                </div>
              </div>
            </div>

            <div className="bs-panel">
              <div className="bs-panel-hd"><h3>7d Win Record</h3><span className="idx">REC·03</span></div>
              <div className="bs-panel-bd">
                {BOTS.map((b) => {
                  const p = perf[b.key] || { wins: 0, losses: 0, trades: 0 };
                  const settled = p.wins + p.losses;
                  const rate = settled ? (p.wins / settled) * 100 : null;
                  const cls = b.meter;
                  return (
                    <div className="bs-meter" key={b.key}>
                      <div className="row">
                        <span style={{ color: b.accent }}>{b.label}</span>
                        <b>{rate === null ? '—' : `${rate.toFixed(0)}% win`} · {usd(p.pnl || 0)}</b>
                      </div>
                      <div className="track">
                        <div className={`fill ${cls}`} style={{ width: `${rate ?? 0}%` }} />
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          </div>

          {/* center: helios core */}
          <div className="bs-stagewrap bs-panel">
            <div className="bs-hud tl">
              <h2>HELIOS BOT CORE</h2>
              <span className="tag">CLICK A BOT NODE TO OPEN ITS CONSOLE · LIVE FEED</span>
            </div>
            <div className="bs-legend">
              {BOTS.map((b) => (
                <span key={b.key}><i style={{ background: b.accent, boxShadow: `0 0 6px ${b.accent}` }} />{b.label}</span>
              ))}
            </div>
            <div className="bs-hud br">
              <span className="frame">{runningCount}/{BOTS.length} CORES ACTIVE · POLL 10s</span>
            </div>
            <HeliosCanvas bots={botStates} neon={(pnlWin?.h3 ?? 0) > 0}
              operator={user?.username} onPick={setConsole} onLogs={setLogsFor}
              onSunDblClick={() => setLaunchAll(true)} />
            <div className="bs-strips">
              <CommoditiesStrip />
              <CryptoStrip />
            </div>
          </div>

          {/* right: event feed */}
          <div className="bs-col">
            <div className="bs-panel">
              <div className="bs-panel-hd">
                <h3>Bots Log</h3>
                <span className="idx">STOP·LOG</span>
              </div>
              <div className="bs-panel-bd" style={{ maxHeight: showAllStopLog ? 400 : 220, overflowY: 'auto' }}>
                {botStopLog.length === 0 && (
                  <div className="bs-feed-empty">no runs recorded yet</div>
                )}
                {botStopLog.slice(0, showAllStopLog ? 60 : 10).map((r) => {
                  const meta = BOT_BY_KEY[r.bot_key];
                  const live = r.status === 'running';
                  return (
                    <div key={r.run_id} className="bs-runrow">
                      <span className="who" style={{ color: meta?.accent }}>{r.bot}</span>
                      <span className="ts">{utcTs(r.stopped_at || r.started_at)}</span>
                      {/* what the run WAS, and how it ended -- a bot the
                          operator stopped is different news from one that
                          exited by itself. */}
                      <span className={`bs-st ${live ? 'open' : r.exited_on_its_own ? 'lost' : 'closed'}`}>
                        {live ? (r.mode === 'live' ? 'LIVE' : 'PAPER')
                          : r.exited_on_its_own ? 'EXITED' : 'STOPPED'}
                      </span>
                      <span className="dim">{r.version}</span>
                      <span className="dim">{r.trades}t</span>
                      <b className={r.pnl > 0 ? 'win' : r.pnl < 0 ? 'loss' : ''}>
                        {r.pnl ? `${r.pnl > 0 ? '+' : ''}${usd(r.pnl)}` : '—'}
                      </b>
                    </div>
                  );
                })}
                {botStopLog.length > 10 && (
                  <button type="button" onClick={() => setShowAllStopLog((v) => !v)}
                    style={{ marginTop: 6, background: 'none', border: 'none', color: 'var(--bs-cyan, #00e5ff)',
                      cursor: 'pointer', fontFamily: '"JetBrains Mono", monospace', fontSize: 11, padding: 0 }}>
                    {showAllStopLog ? 'Show less' : `Load history (${botStopLog.length} runs)`}
                  </button>
                )}
              </div>
            </div>

            <div className="bs-panel">
              <div className="bs-panel-hd">
                <h3>Trade Event Log</h3>
                <button type="button" className={`bs-syncbtn ${feedSync.busy ? 'busy' : ''}`}
                  onClick={syncFeed} disabled={feedSync.busy || !user}
                  title="pull the bots' ledgers, then settle every stale-open row's P&L from Kalshi fills + settlements">
                  ⟳
                </button>
                <select className="bs-fsel" value={feedFilter} aria-label="filter by bot"                  style={{ color: BOT_BY_KEY[feedFilter]?.accent }}
                  onChange={(e) => setFeedFilter(e.target.value)}>
                  <option value="all">ALL BOTS</option>
                  {BOTS.map((b) => <option key={b.key} value={b.key}>{b.label}</option>)}
                </select>
                <span className="idx">
                  {feed ? `${(feedFilter === 'all' ? feed : feed.filter((t) => (t.bot || '').toLowerCase() === feedFilter)).length} EVT` : '…'}
                </span>
              </div>
              <div className="bs-panel-bd">
                {feedSync.note && (
                  <p className={`bs-note ${/failed/.test(feedSync.note) ? '' : ''}`}
                    style={{ marginBottom: 6, color: /failed/.test(feedSync.note) ? 'var(--bs-crit)' : undefined }}>
                    {feedSync.busy ? '⟳ ' : ''}{feedSync.note}
                  </p>
                )}
                <div className="bs-feed">
                  {feed && feed.length === 0 && (
                    <div className="bs-feed-empty">no trades recorded yet — launch a core</div>
                  )}
                  {feed && feed.length > 0
                    && feed.every((t) => feedFilter !== 'all' && (t.bot || '').toLowerCase() !== feedFilter) && (
                    <div className="bs-feed-empty">no recent trades from {BOT_BY_KEY[feedFilter]?.label || feedFilter}</div>
                  )}
                  {(feed || [])
                    .filter((t) => feedFilter === 'all' || (t.bot || '').toLowerCase() === feedFilter)
                    .slice(0, 30)
                    .map((tr) => (
                    <div key={tr.id} className={`bs-evt st-${(tr.status || '').toLowerCase()}`}>
                      <span className="rail" />
                      <div className="bd">
                        <div className="top">
                          <span className={`chip ${chipFor((tr.bot || '').toLowerCase())}`}>{tr.bot}</span>
                          {tr.is_live === false && <span className="chip" style={{ color: 'var(--bs-ink-3)', background: 'rgba(255,255,255,0.06)' }}>PAPER</span>}
                          <span className={`bs-st ${(tr.status || '').toLowerCase()}`}>{tr.status}</span>
                          <span className="ts">{utcTs(tr.closed_at || tr.opened_at)}</span>
                        </div>
                        {/* market, side, and the cash: in USD both ends, so
                            exit minus entry IS the result. */}
                        <div className="msg" title={tr.ticker}>
                          {tr.market}{tr.outcome ? ` · ${tr.outcome}` : ''}
                        </div>
                        <div className="msg">
                          {tr.entry != null ? usd(tr.entry) : '—'}
                          {' → '}
                          {tr.status === 'OPEN' ? 'TBD' : (tr.exit != null ? usd(tr.exit) : '—')}
                          {tr.pnl != null
                            ? <> · <b className={tr.pnl >= 0 ? 'win' : 'loss'}>{usd(tr.pnl)}</b></>
                            : null}
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </div>

            <LuckPanel />

          </div>
        </div>

        {/* portfolio progress: daily PV as a one-layer pixel mountain */}
        {pvHist && pvHist.length > 0 && (
          <div className="bs-panel bs-pvpanel">
            <button type="button" className="bs-panel-hd bs-pvtoggle" onClick={togglePvOpen}
              aria-expanded={pvOpen} title={pvOpen ? 'collapse the graph' : 'expand the graph'}>
              <h3>Portfolio Progress · Daily</h3>
              <span className="bs-pvlegend tr-mono">
                {(() => {
                  const startV = 60;
                  const first = pvHist[0];
                  const last = pvHist[pvHist.length - 1];
                  const lastV = last.total_usd;
                  const pct = ((lastV - startV) / startV) * 100;
                  // compound-growth projection: daily rate r =
                  // (V/start)^(1/days) − 1; days-to-target = ln(T/V)/ln(1+r).
                  // A straight extrapolation of the run so far, nothing more.
                  const elapsed = Math.max(1, Math.round(
                    (new Date(`${last.date}T12:00:00Z`) - new Date(`${first.date}T12:00:00Z`)) / 86400e3));
                  const r = (lastV / startV) ** (1 / elapsed) - 1;
                  const daysTo = (T) => (lastV >= T ? '✓'
                    : (() => { const d = Math.ceil(Math.log(T / lastV) / Math.log(1 + r)); return d > 3650 ? '>10y' : `${d}d`; })());
                  return (
                    <>
                      <span>start {usd(startV)}</span>
                      <span>·</span>
                      <b style={{ color: pct >= 0 ? 'var(--bs-good)' : 'var(--bs-crit)' }}>
                        {usd(lastV)} ({pct >= 0 ? '+' : ''}{pct.toFixed(1)}%)
                      </b>
                      {r > 0 && lastV > 0 && (
                        <span className="bs-pvpredict"                          title={`at ${(r * 100).toFixed(1)}%/day — straight extrapolation of the ${elapsed}-day run so far, not a promise`}>
                          🔮 $1K {daysTo(1000)} · $10K {daysTo(10000)} · $100K {daysTo(100000)} · $1M {daysTo(1000000)}
                        </span>
                      )}
                    </>
                  );
                })()}
              </span>
              <span className="idx">PV·05 <i className={`bs-pvchev ${pvOpen ? 'up' : ''}`}>▾</i></span>
            </button>
            {pvOpen && <PixelPvGraph history={pvHist} baseline={60} />}
          </div>
        )}

        {/* ticker */}
        <div className="bs-ticker">
          <div className="inner">
            {[...tickerItems, ...tickerItems].map((s, i) => (
              <span key={i}><b>{s}</b>{'  ◦  '}</span>
            ))}
          </div>
        </div>

        {logsFor && user && (
          <BotLogsOverlay botKey={logsFor} user={user} onClose={() => setLogsFor(null)} />
        )}
        {console_ && user && (
          <BotConsole
            botKey={console_}
            meta={BOT_BY_KEY[console_]}
            status={statuses[console_]}
            versions={versionsFor(console_)}
            cfg={cfg[console_]}
            onCfg={onCfg}
            user={user}
            onClose={() => setConsole(null)}
            onChanged={() => { loadStatuses(); loadPv(); loadFeed(); }}
            onLogs={() => setLogsFor(console_)}
          />
        )}
        {console_ && !user && (
          <div className="bs-modal-backdrop"
            onMouseDown={(e) => { if (e.target === e.currentTarget) setConsole(null); }}>
            <div className="bs-modal">
              <div className="bs-modal-hd"><h2>NO OPERATOR</h2>
                <button type="button" className="close" onClick={() => setConsole(null)}>✕</button></div>
              <p className="bs-note">No user found (status NA) — the API on :8791 must be
                reachable and the default operator "sampath" must exist. The station retries
                automatically.</p>
            </div>
          </div>
        )}
        {launchAll && user && (
          <LaunchAllModal
            user={user}
            statuses={statuses}
            onClose={() => setLaunchAll(false)}
            onChanged={() => { loadStatuses(); loadPv(); loadFeed(); }}
            onGuard={(g) => {
              stationHaltedRef.current = false;
              const currentPv = pv ? (Number(pv.cash_usd) || 0) + (Number(pv.positions_usd) || 0) : 0;
              setStationGuard({ ...g, pv_at_launch: currentPv, draining: false });
            }}
          />
        )}
        <SiteFooter />
      </div>
    </div>
  );
}
