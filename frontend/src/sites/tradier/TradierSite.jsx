import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react'; // charts ungrouped
import { ApiError, ensureUser, vidura } from '../../shared/viduraApi.js';
import QuotePopup from '../../shared/QuotePopup.jsx';
import SiteFooter from '../../shared/SiteFooter.jsx';
import WorldHeader from '../../shared/WorldHeader.jsx';
import { confirmDialog } from '../../shared/Dialog.jsx';
import '../../shared/worldHeader.css';
import './tradier.css';

// /tradier-platform — the Tradier options executor desk.
// Not a prediction room: the operator picks symbol/side/risk, the backend
// picks the contract by delta, sizes by % of option buying power, buys,
// rests the TP on the venue and monitors the SL. Paper mode = Tradier's
// SANDBOX venue (its own token), so paper cannot touch live money.

function isMarketOpen() {
  const now = new Date();
  const cst = new Date(now.toLocaleString('en-US', { timeZone: 'America/Chicago' }));
  const day = cst.getDay(); // 0=Sun, 6=Sat
  if (day === 0 || day === 6) return false;
  const hhmm = cst.getHours() * 60 + cst.getMinutes();
  return hhmm >= 510 && hhmm < 900; // 8:30=510, 15:00=900
}

function errText(e) {
  if (typeof e === 'string') return e;
  if (e instanceof ApiError) return e.detail || e.message || `HTTP ${e.status}`;
  if (e && typeof e === 'object' && e.detail) return String(e.detail);
  return 'Backend unreachable — is the Vidura API running on :8790?';
}

// HTTP status kept alongside the text: 401 (keys), 429 (throttled) and 5xx
// (venue unwell) call for completely different reactions, and "an error
// occurred" on its own does not tell an operator which one they are in.
function errStatus(e) {
  return e instanceof ApiError ? (e.status ?? null) : null;
}

function errKind(status) {
  if (status == null) return 'offline';
  if (status === 401 || status === 403) return 'auth';
  if (status === 424) return 'config';
  if (status === 429) return 'throttled';
  if (status >= 500) return 'venue';
  if (status >= 400) return 'rejected';
  return 'error';
}

const ERR_HINT = {
  auth: 'the venue rejected the credentials for this account',
  config: 'credentials are missing or incomplete in the customer .env',
  throttled: 'Tradier is rate-limiting — it usually clears in a moment',
  venue: 'Tradier returned a server error; the desk did not change anything',
  rejected: 'the venue refused the request',
  offline: 'the Vidura API did not answer',
  error: '',
};

function usd(v) {
  if (v === null || v === undefined || Number.isNaN(Number(v))) return '—';
  const n = Number(v);
  return `${n < 0 ? '−' : ''}$${Math.abs(n).toLocaleString(undefined, {
    minimumFractionDigits: 2, maximumFractionDigits: 2,
  })}`;
}

function when(iso) {
  if (!iso) return '—';
  const d = new Date(/Z$|[+-]\d\d:?\d\d$/.test(iso) ? iso : `${iso}Z`);
  return Number.isNaN(d.getTime())
    ? iso
    : d.toLocaleString([], { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
}

// ── lucky charm blessing: ONE random charm from the home screen's gallery,
// receding into the deep and fading — shown when a trade is confirmed ──────
const CHARM_IMGS = ['ganesha', 'dragon', 'clover', 'seven', 'cornucopia', 'om',
  'maneki', 'coins', 'kubera', 'buddha', 'lotus'];

function LuckyCharm({ charm, onDone }) {
  // animationend is the normal exit; the timer covers throttled/frozen tabs
  // where the animation never runs, so a charm can never get stuck on screen
  useEffect(() => {
    if (!charm) return undefined;
    const t = setTimeout(onDone, 4300);
    return () => clearTimeout(t);
  }, [charm, onDone]);
  if (!charm) return null;
  return (
    <div className="tr-charm" aria-hidden="true">
      <img src={charm.src} alt="" onAnimationEnd={onDone} />
    </div>
  );
}

// ── fresh-arrival blink: rows pulse until clicked away or 5 minutes old ────
// Give it the CURRENT list of stable row keys; anything not seen before
// (after the first load, which is baseline) starts blinking. A click/tap
// anywhere on the screen clears every blink at once.
const NEW_BLINK_MS = 5 * 60 * 1000;

function useNewBlink(keys) {
  const seen = useRef(null);
  const [fresh, setFresh] = useState({});   // key -> arrivedAt ms

  useEffect(() => {
    if (!keys) return;
    if (seen.current === null) {            // first page: baseline, no blink
      seen.current = new Set(keys);
      return;
    }
    const arrivals = keys.filter((k) => !seen.current.has(k));
    keys.forEach((k) => seen.current.add(k));
    if (arrivals.length) {
      const now = Date.now();
      setFresh((p) => {
        const n = { ...p };
        arrivals.forEach((k) => { n[k] = now; });
        return n;
      });
    }
  }, [keys]);

  useEffect(() => {
    const clearAll = () => setFresh((p) => (Object.keys(p).length ? {} : p));
    const sweep = setInterval(() => setFresh((p) => {
      const now = Date.now();
      const kept = Object.fromEntries(
        Object.entries(p).filter(([, at]) => now - at < NEW_BLINK_MS)
      );
      return Object.keys(kept).length === Object.keys(p).length ? p : kept;
    }), 15_000);
    window.addEventListener('pointerdown', clearAll);
    return () => {
      clearInterval(sweep);
      window.removeEventListener('pointerdown', clearAll);
    };
  }, []);

  return fresh;
}

// "0.25-0.45" → [0.25, 0.45]; tolerant of spaces/–/to, ordered, 0<δ≤1
function parseDeltaRange(text) {
  const nums = (String(text).match(/\d*\.?\d+/g) || [])
    .map(Number).filter((n) => n > 0 && n <= 1);
  if (nums.length < 2) return [0.25, 0.45];
  return [Math.min(nums[0], nums[1]), Math.max(nums[0], nums[1])];
}

// A delta band is typed as a magnitude, because that is how it is spoken, but
// it is searched signed: a call's delta runs 0..+1 and a put's runs 0..-1. So
// "0.25-0.45" is +0.25..+0.45 on a call and -0.45..-0.25 on a put, and the
// desk shows which one it is about to use rather than leaving it implied.
function signedBandLabel(side, text) {
  const [lo, hi] = parseDeltaRange(text);
  const f = (n) => (n > 0 ? `+${n}` : String(n));
  return side === 'put' ? `${f(-hi)}..${f(-lo)}` : `${f(lo)}..${f(hi)}`;
}

const STATUS_FILTERS = [
  ['active', 'ACTIVE'], ['all', 'ALL'], ['tp_filled', 'TP WINS'],
  ['sl_sold', 'SL STOPS'], ['closed', 'CLOSED'],
];

const VENUE_FILTERS = [['all', 'ALL'], ['sandbox', 'SANDBOX'], ['live', 'LIVE']];

// chart granularity — a display preference, so unlike the LIVE venue it is
// safe to remember across reloads
const CHART_INTERVALS = [['1min', '1m'], ['5min', '5m'], ['15min', '15m']];
const CHART_IV_KEY = 'tradier.chart.interval';   // + '.SYMBOL'

// Remembered per symbol: SPY and QQQ are often watched at different
// speeds, and that choice should survive a reload.
function loadChartInterval(symbol) {
  try {
    const v = localStorage.getItem(`${CHART_IV_KEY}.${symbol}`);
    if (CHART_INTERVALS.some(([k]) => k === v)) return v;
  } catch { /* private mode — fall through */ }
  return '15min';
}

const CHART_SYM_KEY = 'tradier.chart.symbol';    // + '.SLOT'

// The desk's tiles, in groups. Slots are stable ids; the ticker in each
// is editable and remembered, so this table is only ever the starting
// Row 1: 2 charts, rows 2-5: 4 each, row 6: 1 — 19 slots total.
const CHART_SLOTS = [
  ['a', 'SPY'], ['b', 'QQQ'],
  ['c', 'SPX'], ['d', 'IWM'], ['e', 'SMH'], ['f', 'VIX'],
  ['g', 'MSFT'], ['h', 'TSLA'], ['i', 'AAPL'], ['j', 'AMZN'],
  ['k', 'NVDA'], ['l', 'META'], ['m', 'NFLX'], ['n', 'GOOG'],
  ['o', 'MU'], ['p', 'AMD'], ['q', 'CRM'], ['r', 'AVGO'],
  ['s', ''],
];
const CHART_ROWS = [2, 4, 4, 4, 4, 1];

// Keyed by SLOT, not symbol: the slot is the thing that persists, the
// symbol in it is what the operator swaps.
function loadChartSymbol(slot, fallback) {
  try {
    const v = localStorage.getItem(`${CHART_SYM_KEY}.${slot}`);
    if (v && /^[A-Z0-9.\-]{1,10}$/.test(v)) return v;
  } catch { /* private mode — fall through */ }
  return fallback;
}

function saveChartSymbol(slot, v) {
  try { localStorage.setItem(`${CHART_SYM_KEY}.${slot}`, v); }
  catch { /* nothing to do */ }
}

function saveChartInterval(symbol, v) {
  try { localStorage.setItem(`${CHART_IV_KEY}.${symbol}`, v); }
  catch { /* nothing to do */ }
}


/* ── index strip: Tradier WebSocket market stream ──────────────────────────
   Streaming is production-only (the sandbox token has no stream scope), so
   this shows REAL index prices even while the desk is placing mock orders —
   which is what you want when paper-trading a real strategy. The session id
   the server hands back is market-data-only and cannot touch the account.

   Tradier gives the session five minutes to CONNECT, so a dropped socket has
   to fetch a fresh one rather than reuse the old id. */
function useIndexStream(user, live, extras = []) {
  const [ticks, setTicks] = useState([]);
  // whatever the charts are showing rides the same socket — a symbol the
  // strip does not carry would otherwise never tick
  const extraKey = extras.join(',');
  const extrasRef = useRef(extras);
  extrasRef.current = extras;
  const [state, setState] = useState('off');    // off|connecting|live|retry|error
  const [err, setErr] = useState(null);
  const sockRef = useRef(null);
  const timerRef = useRef(null);
  const bySymbol = useRef({});
  const sessRef = useRef(null);
  const aliveRef = useRef(true);
  const triesRef = useRef(0);
  // strip entries Tradier cannot stream (BTC) — the server names them, and
  // they are refreshed here on a timer instead of by a tick
  const polledRef = useRef([]);

  const paint = useCallback(() => {
    setTicks(Object.values(bySymbol.current).filter((t) => !t.extra));
  }, []);

  const connect = useCallback(async () => {
    // Streaming only exists on production, so it runs only when the desk is
    // actually on the live venue — no production socket open behind a
    // sandbox session.
    if (!user || !aliveRef.current || !live) return;
    setState('connecting');
    let sess;
    try {
      sess = await vidura.tradierStreamSession(user.user_id);
      setErr(null);
    } catch (e) {
      setErr(errText(e));
      setState('error');
      timerRef.current = setTimeout(connect, 15 * 60_000);
      return;
    }
    if (!aliveRef.current) return;
    sessRef.current = sess;
    polledRef.current = sess.polled || [];

    // seed so the strip reads immediately, and outside market hours when no
    // tick will ever arrive
    (sess.seed || []).forEach((s) => {
      const prev = bySymbol.current[s.symbol] || {};
      bySymbol.current[s.symbol] = {
        ...prev, label: s.label, symbol: s.symbol,
        price: s.price ?? prev.price ?? null,
        prevClose: s.prev_close ?? prev.prevClose ?? null,
        changePct: s.change_pct ?? prev.changePct ?? null,
      };
    });
    paint();

    let ws;
    try {
      ws = new WebSocket(sess.ws_url);
    } catch (e) {
      setState('error');
      setErr('stream unreachable');
      timerRef.current = setTimeout(connect, 15 * 60_000);
      return;
    }
    sockRef.current = ws;

    ws.onopen = () => {
      triesRef.current = 0;
      setState('live');
      ws.send(JSON.stringify({
        symbols: [...new Set([...(sess.symbols || []).map((s) => s.symbol),
          ...extrasRef.current])],
        sessionid: sess.sessionid,
        filter: ['quote', 'trade', 'summary'],
        linebreak: true,
        validOnly: true,
      }));
    };

    ws.onmessage = (ev) => {
      // linebreak:true can pack several JSON objects into one frame
      String(ev.data).split('\n').forEach((line) => {
        const raw = line.trim();
        if (!raw) return;
        let m;
        try { m = JSON.parse(raw); } catch { return; }
        const sym = (m.symbol || '').toUpperCase();
        if (!sym) return;
        // seeded rows belong to the strip; a chart's own symbol arrives
        // unseeded and is created on first tick, flagged so the strip
        // does not grow a tile for it
        if (!bySymbol.current[sym]) {
          if (!extrasRef.current.includes(sym)) return;
          bySymbol.current[sym] = { symbol: sym, label: sym, extra: true };
        }
        const row = { ...bySymbol.current[sym] };
        const num = (v) => { const n = Number(v); return Number.isFinite(n) ? n : null; };
        if (m.type === 'trade' || m.type === 'tradex') {
          row.price = num(m.price) ?? num(m.last) ?? row.price;
          row.beat = Date.now();
        } else if (m.type === 'quote') {
          row.bid = num(m.bid) ?? row.bid;
          row.ask = num(m.ask) ?? row.ask;
          // Indices never print a trade — their mid IS the quote.
          if (row.price == null && row.bid != null && row.ask != null) {
            row.price = (row.bid + row.ask) / 2;
          }
          row.beat = Date.now();
        } else if (m.type === 'summary') {
          row.prevClose = num(m.prevClose) ?? row.prevClose;
        } else { return; }
        if (row.price != null && row.prevClose) {
          row.changePct = ((row.price - row.prevClose) / row.prevClose) * 100;
        }
        bySymbol.current[sym] = row;
      });
      paint();
    };

    const retry = () => {
      if (!aliveRef.current) return;
      sockRef.current = null;
      triesRef.current += 1;
      if (triesRef.current <= 2) {
        setState('retry');
        timerRef.current = setTimeout(connect, 3_000);
      } else {
        setState('error');
        setErr('stream unreachable');
        timerRef.current = setTimeout(connect, 15 * 60_000);
      }
    };
    ws.onclose = retry;
    ws.onerror = () => { try { ws.close(); } catch { /* onclose retries */ } };
  }, [user, live, paint]);

  // a live socket can be re-pointed by resending the payload
  useEffect(() => {
    const ws = sockRef.current;
    if (!ws || ws.readyState !== 1 || !sessRef.current) return;
    ws.send(JSON.stringify({
      symbols: [...new Set([...(sessRef.current.symbols || [])
        .map((s) => s.symbol), ...extras])],
      sessionid: sessRef.current.sessionid,
      filter: ['quote', 'trade', 'summary'],
      linebreak: true,
      validOnly: true,
    }));
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [extraKey]);

  useEffect(() => {
    aliveRef.current = true;
    if (live) {
      connect();
    } else {
      // Leaving stale numbers on screen would read as live prices.
      bySymbol.current = {};
      triesRef.current = 0;
      setTicks([]);
      setErr(null);
      setState('off');
    }
    return () => {
      aliveRef.current = false;
      clearTimeout(timerRef.current);
      const s = sockRef.current;
      sockRef.current = null;
      if (s) { s.onclose = null; try { s.close(); } catch { /* closing */ } }
    };
  }, [connect, live]);

  // The entries the socket cannot carry. BTC is not a Tradier instrument, so
  // no subscription will ever tick it — it is refreshed on its own timer from
  // the keyless quotes service. A minute is right for a strip: fast enough
  // that the number is current, slow enough that it is one request.
  useEffect(() => {
    if (!user || !live) return undefined;
    let alive = true;
    const pull = async () => {
      for (const sym of polledRef.current) {
        try {
          const q = await vidura.superQuote(sym);
          if (!alive) return;
          const prev = bySymbol.current[sym] || { symbol: sym, label: sym };
          bySymbol.current[sym] = {
            ...prev,
            price: q.price ?? prev.price ?? null,
            prevClose: q.prev_close ?? prev.prevClose ?? null,
            changePct: q.change_pct ?? prev.changePct ?? null,
          };
        } catch { /* the strip shows its last good number */ }
      }
      if (alive) paint();
    };
    pull();
    const t = setInterval(() => { if (!document.hidden) pull(); }, 60_000);
    return () => { alive = false; clearInterval(t); };
  }, [user, live, state, paint]);

  const dotTitle = {
    live: 'streaming from Tradier (production market data)',
    connecting: 'opening the market stream…',
    retry: 'stream dropped — reconnecting',
    error: err || 'stream unavailable',
    off: 'stopped — Tradier only streams on production, so the strip runs '
       + 'while the desk is LIVE',
  }[state];

  return { ticks, state, err, dotTitle, bySymbol };
}

function StreamStrip({ stream, movers, onPick }) {
  const { ticks, state, err, dotTitle } = stream;
  // Reached for = held still. A price you are trying to read should not be
  // walking away from the cursor, and a tap is the touch equivalent of the
  // same intent.
  const [held, setHeld] = useState(false);

  // Stopped: the venue control right above says why, so one short hint beats
  // a state chip plus a sentence.
  if (state === 'off') {
    return <span className="tr-note" title={dotTitle}>index stream runs on LIVE</span>;
  }

  const item = (t, key) => (
    <button key={key} type="button" className="tr-strip-item"
      onClick={(e) => { e.stopPropagation(); onPick?.(t.symbol); }}
      title={`${t.symbol} — click for levels & buy`}>
      <span className="tr-strip-sym">
        {t.label}
      </span>
      <b className="tr-strip-px" style={{ color: pctColor(t.changePct) }}>
        {t.price != null ? Number(t.price).toFixed(2) : '—'}
      </b>
      {t.changePct != null && (
        <span className="tr-strip-chg" style={{ color: pctColor(t.changePct) }}>
          {t.changePct >= 0 ? '+' : ''}{Number(t.changePct).toFixed(2)}%
        </span>
      )}
    </button>
  );

  const pipe = (key) => <span key={key} className="tr-strip-pipe">|</span>;

  const moverItems = movers ? [
    pipe('p1'),
    ...movers.up.map((q, i) => item({ label: q.symbol, symbol: q.symbol,
      price: q.price, changePct: q.change_pct }, `u${i}`)),
    pipe('p2'),
    ...movers.down.map((q, i) => item({ label: q.symbol, symbol: q.symbol,
      price: q.price, changePct: q.change_pct }, `d${i}`)),
  ] : [];

  const run = [
    <span key="st" className={`tr-strip-state ${state}`} title={dotTitle}>
      {state === 'live'
        ? <span style={{ display: 'inline-block', width: 6, height: 6, borderRadius: '50%', background: 'var(--tr-green)', boxShadow: '0 0 6px var(--tr-green)' }} />
        : <span style={{ fontSize: 11, color: '#d4d44a' }}>&#9888;</span>}
    </span>,
    ...(ticks.length === 0
      ? [<span key="w" className="tr-note">{err ? `⚠ ${err}` : 'waiting for the first tick…'}</span>]
      : ticks.map((t) => item(t, t.symbol))),
    ...moverItems,
  ];

  return (
    <div className={`tr-strip-wrap ${held ? 'held' : ''}`}
      role="group" aria-label="index prices"
      onMouseEnter={() => setHeld(true)}
      onMouseLeave={() => setHeld(false)}
      onClick={() => setHeld((v) => !v)}
      title={held ? 'paused — move away or click to resume' : 'hover or click to hold it still'}>
      <div className="tr-strip-track">
        <div className="tr-strip-run">{run}</div>
        <div className="tr-strip-run" aria-hidden="true">
          {run.map((el) => React.cloneElement(el, { key: `dup-${el.key}` }))}
        </div>
      </div>
    </div>
  );
}


/* ── ADX / DMI (Wilder, 14) ────────────────────────────────────────────────
   Only the crossovers are wanted on the chart, but they cannot be found
   without the whole calculation: +DI and -DI say which side is in control,
   ADX says whether anything is in control at all. A cross with ADX under the
   floor is two flat lines touching — the filter is the point.

   Wilder's smoothing, not a simple average: the first value seeds from a sum
   of `period` terms and every later one decays by 1/period. An SMA here
   produces visibly different numbers from every charting package. */
// A level only matters when it is in reach. Anything outside the frame is
// noise until price comes within this much of it, at which point it is the
// most interesting line on the chart.
const PIVOT_NEAR_PCT = 0.15;

const ADX_PERIOD = 14;
const ADX_FLOOR = 20;

function adxCompute(bars, { period = ADX_PERIOD, floor = ADX_FLOOR } = {}) {
  const n = bars.length;
  const empty = { marks: [], byT: new Map() };
  if (n < period * 2 + 2) return empty;

  const tr = [], plusDM = [], minusDM = [];
  for (let i = 1; i < n; i += 1) {
    const h = bars[i].h, l = bars[i].l, pc = bars[i - 1].c;
    const ph = bars[i - 1].h, pl = bars[i - 1].l;
    tr.push(Math.max(h - l, Math.abs(h - pc), Math.abs(l - pc)));
    const up = h - ph;
    const down = pl - l;
    plusDM.push(up > down && up > 0 ? up : 0);
    minusDM.push(down > up && down > 0 ? down : 0);
  }

  // Wilder smoothing: seed with a sum, then decay by 1/period
  const smooth = (src) => {
    const out = [];
    let acc = 0;
    for (let i = 0; i < src.length; i += 1) {
      if (i < period) { acc += src[i]; out.push(i === period - 1 ? acc : null); }
      else { acc = acc - acc / period + src[i]; out.push(acc); }
    }
    return out;
  };
  const sTR = smooth(tr), sP = smooth(plusDM), sM = smooth(minusDM);

  const plusDI = [], minusDI = [], dx = [];
  for (let i = 0; i < tr.length; i += 1) {
    if (sTR[i] == null || sTR[i] === 0) { plusDI.push(null); minusDI.push(null); dx.push(null); continue; }
    const pdi = 100 * (sP[i] / sTR[i]);
    const mdi = 100 * (sM[i] / sTR[i]);
    plusDI.push(pdi);
    minusDI.push(mdi);
    const sum = pdi + mdi;
    dx.push(sum === 0 ? 0 : 100 * (Math.abs(pdi - mdi) / sum));
  }

  // ADX is Wilder's average of DX, seeded by the mean of the first `period`
  const adx = new Array(dx.length).fill(null);
  const firstDX = dx.findIndex((v) => v != null);
  if (firstDX < 0 || firstDX + period > dx.length) return empty;
  let acc = 0;
  for (let i = firstDX; i < firstDX + period; i += 1) acc += dx[i];
  adx[firstDX + period - 1] = acc / period;
  for (let i = firstDX + period; i < dx.length; i += 1) {
    adx[i] = (adx[i - 1] * (period - 1) + dx[i]) / period;
  }

  // index j maps to bar j+1 — the reading BELONGS to that bar
  const marks = [];
  const byT = new Map();
  for (let j = 0; j < plusDI.length; j += 1) {
    const bar = bars[j + 1];
    if (!bar) continue;
    if (plusDI[j] != null && minusDI[j] != null) {
      byT.set(bar.t, { pdi: plusDI[j], mdi: minusDI[j], adx: adx[j] });
    }
    if (j < 1) continue;
    const a = adx[j];
    if (a == null || a < floor) continue;
    const p0 = plusDI[j - 1], m0 = minusDI[j - 1];
    const p1 = plusDI[j], m1 = minusDI[j];
    if (p0 == null || m0 == null || p1 == null || m1 == null) continue;
    if (p0 <= m0 && p1 > m1) marks.push({ t: bar.t, dir: 'up', adx: a });
    else if (m0 <= p0 && m1 > p1) marks.push({ t: bar.t, dir: 'down', adx: a });
  }
  return { marks, byT };
}

// Regular session only (09:30-16:00 ET). Overnight bars are thin enough to
// invent directional moves that never happened in the book.
function regularSession(bars) {
  return bars.filter((b) => {
    const hm = String(b.time || '').slice(11, 16);
    return hm >= '09:30' && hm <= '16:00';
  });
}

/* ── intraday candles: 15-minute bars from Tradier, live-updated ────────────
   Seeded from timesales because a socket only produces from the moment it
   connects. Streamed ticks do NOT append points — on a candle chart the live
   price belongs to the bar in progress, so it extends that candle's high/low
   and moves its close. The next re-seed rolls it into a settled bar. */
// Exported so other boards can render the same chart rather than growing a
// second one that drifts: the pivot lines, the ADX/DI markers and the
// interval memory all live here.
export function MiniChart({ user, live, symbol, onSymbol, stream, onError, onBuy, blocked,
  height = 210 }) {
  const [interval, setInterval_] = useState(() => loadChartInterval(symbol));
  const pickInterval = (v) => { setInterval_(v); saveChartInterval(symbol, v); };
  const [pivots, setPivots] = useState(null);
  const [editSym, setEditSym] = useState(false);
  // pending single-click on the header symbol, cancelled by a double click
  const symTapRef = useRef(null);
  useEffect(() => () => clearTimeout(symTapRef.current), []);
  const [symDraft, setSymDraft] = useState(symbol);
  // a new symbol brings its own remembered granularity
  useEffect(() => { setInterval_(loadChartInterval(symbol)); }, [symbol]);
  const commitSym = () => {
    setEditSym(false);
    const v = (symDraft || '').trim().toUpperCase();
    if (!v || v === symbol || !/^[A-Z0-9.\-]{1,10}$/.test(v)) {
      setSymDraft(symbol);
      return;
    }
    onSymbol?.(v);
  };
  const [seed, setSeed] = useState(null);
  const [err, setErr] = useState(null);
  const [hover, setHover] = useState(null);
  const hoverRef = useRef(null);
  const [cursor, setCursor] = useState(null);   // {x, y} in CSS px
  const [expanded, setExpanded] = useState(false);
  // The canvas's REAL laid-out size. Guessing it from window.innerHeight
  // drew a 510px plot into a 605px box and stretched everything: the
  // backing store and the CSS box have to agree, so measure the element
  // and let the layout decide.
  const [box, setBox] = useState({ w: 0, h: 0 });
  useEffect(() => {
    const cv = canvasRef.current;
    if (!cv) return undefined;
    const read = () => setBox((prev) => (
      prev.w === cv.clientWidth && prev.h === cv.clientHeight
        ? prev : { w: cv.clientWidth, h: cv.clientHeight }));
    read();
    if (typeof ResizeObserver === 'undefined') return undefined;
    const ro = new ResizeObserver(read);
    ro.observe(cv);
    return () => ro.disconnect();
  }, [expanded]);
  const canvasRef = useRef(null);
  const geomRef = useRef(null);          // candle hit-boxes for the crosshair

  const retryRef = useRef(null);
  const load = useCallback(async () => {
    if (!user) return;
    try {
      setSeed(await vidura.tradierTimesales(user.user_id, symbol, interval,
        live, interval === '1min' ? 1 : 5));
      setErr(null);
    } catch (e) {
      const msg = errText(e);
      if (/timed?\s*out|unreachable|ECONNREFUSED|network/i.test(msg)) {
        setErr('disconnected');
        clearTimeout(retryRef.current);
        retryRef.current = setTimeout(load, 10 * 60_000);
      } else {
        setSeed(null);
        setErr(msg);
        onError?.(`${symbol} bars`, e);
      }
    }
  }, [user, symbol, interval, live, onError]);

  useEffect(() => {
    setSeed(null);
    load();
    return () => clearTimeout(retryRef.current);
  }, [load]);

  useEffect(() => {
    if (!expanded) return undefined;
    const onKey = (e) => { if (e.key === 'Escape') setExpanded(false); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [expanded]);

  // Pivots come from the prior completed session, so once per symbol is
  // enough — they do not move while the chart is open.
  useEffect(() => {
    let alive = true;
    setPivots(null);
    vidura.superQuote(symbol)
      .then((q) => { if (alive) setPivots(q?.pivots || null); })
      .catch(() => { if (alive) setPivots(null); });
    return () => { alive = false; };
  }, [symbol]);
  usePolling(load, 60_000, { enabled: !!user && isMarketOpen(), blocked });

  // everything fetched feeds the indicator; only the latest session is drawn
  const allBars = useMemo(() => regularSession(seed?.bars || []), [seed]);
  const bars = useMemo(() => {
    if (!allBars.length) return [];
    const day = String(allBars[allBars.length - 1].time || '').slice(0, 10);
    return allBars.filter((b) => String(b.time || '').startsWith(day));
  }, [allBars]);
  // Signals are found across the whole warmup window but only the ones on
  // the drawn session are marked — and the badge counts those, not the
  // window's, or it would advertise letters that are nowhere on the chart.
  const dmi = useMemo(() => adxCompute(allBars), [allBars]);
  const marks = useMemo(
    () => new Map(dmi.marks.map((s) => [s.t, s])), [dmi]);
  const shownMarks = useMemo(
    () => bars.reduce((n, b) => n + (marks.has(b.t) ? 1 : 0), 0), [bars, marks]);
  const prevClose = seed?.prev_close ?? null;
  const livePx = stream?.bySymbol?.current?.[symbol]?.price ?? null;

  // the bar in progress carries the live price
  const candles = useMemo(() => {
    const out = bars
      .filter((b) => Number.isFinite(b.o) && b.o > 0 && Number.isFinite(b.c) && b.c > 0)
      .map((b) => ({ ...b }));
    if (livePx != null && out.length) {
      const last = out[out.length - 1];
      last.c = livePx;
      last.h = Math.max(last.h, livePx);
      last.l = Math.min(last.l, livePx);
      last.hot = true;
    }
    return out;
  }, [bars, livePx]);

  const last = candles.length ? candles[candles.length - 1].c : null;
  const changePct = (last != null && prevClose)
    ? ((last - prevClose) / prevClose) * 100 : null;

  useEffect(() => {
    const cv = canvasRef.current;
    if (!cv) return;
    const dpr = window.devicePixelRatio || 1;
    const w = box.w || cv.clientWidth || 320;
    const h = box.h || cv.clientHeight || height;
    cv.width = Math.round(w * dpr);
    cv.height = Math.round(h * dpr);
    const ctx = cv.getContext('2d');
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, w, h);
    geomRef.current = null;
    if (candles.length < 1) return;

    const padL = 4;
    const padR = 46;                     // price axis
    const padT = 8;
    const padB = 20;                     // time axis
    const plotW = w - padL - padR;
    const plotH = h - padT - padB;

    const highs = candles.map((c) => c.h);
    const lows = candles.map((c) => c.l);
    let hi = Math.max(...highs, prevClose ?? -Infinity);
    let lo = Math.min(...lows, prevClose ?? Infinity);

    // Which pivots earn a line: the ones already inside the frame, plus
    // any the price has come within PIVOT_NEAR_PCT of. A near level just
    // outside the frame stretches it rather than being clipped away —
    // hiding the level you are about to test would be exactly backwards.
    const shownPivots = [];
    if (pivots && last != null) {
      Object.entries(pivots).forEach(([name, raw]) => {
        const v = Number(raw);
        if (!Number.isFinite(v) || v <= 0) return;
        const inView = v >= lo && v <= hi;
        const near = Math.abs(v - last) / last * 100 <= PIVOT_NEAR_PCT;
        if (inView || near) shownPivots.push({ name, v, near });
      });
      shownPivots.forEach(({ v }) => { hi = Math.max(hi, v); lo = Math.min(lo, v); });
    }

    const padSpan = (hi - lo) * 0.08 || 0.5;
    hi += padSpan; lo -= padSpan;
    const span = hi - lo || 1;
    const y = (v) => padT + (1 - (v - lo) / span) * plotH;
    const slot = plotW / candles.length;
    const body = Math.max(1.5, Math.min(11, slot * 0.62));
    const cx = (i) => padL + slot * (i + 0.5);

    const css = getComputedStyle(document.querySelector('.tr-root') || document.body);
    const GREEN = css.getPropertyValue('--tr-green').trim() || '#34d399';
    const RED = css.getPropertyValue('--tr-red').trim() || '#ff6b5e';
    const FAINT = css.getPropertyValue('--tr-faint').trim() || '#5f679b';
    const GRID = 'rgba(91, 106, 240, 0.13)';

    ctx.font = '9px ui-monospace, Consolas, monospace';
    ctx.textBaseline = 'middle';

    // ── price axis: gridlines + labels on the right
    const ticks = 4;
    ctx.strokeStyle = GRID;
    ctx.lineWidth = 1;
    ctx.fillStyle = FAINT;
    ctx.textAlign = 'left';
    for (let i = 0; i <= ticks; i += 1) {
      const v = lo + (span * i) / ticks;
      const yy = Math.round(y(v)) + 0.5;
      ctx.beginPath();
      ctx.moveTo(padL, yy);
      ctx.lineTo(padL + plotW, yy);
      ctx.stroke();
      ctx.fillText(v.toFixed(2), padL + plotW + 5, y(v));
    }

    // prior close — the level the day's percent is measured from
    if (prevClose && prevClose > lo && prevClose < hi) {
      ctx.strokeStyle = 'rgba(154, 163, 208, 0.5)';
      ctx.setLineDash([3, 3]);
      ctx.beginPath();
      ctx.moveTo(padL, y(prevClose));
      ctx.lineTo(padL + plotW, y(prevClose));
      ctx.stroke();
      ctx.setLineDash([]);
    }

    // ── time axis: label every Nth candle, enough to stay readable
    const every = Math.max(1, Math.ceil(candles.length / Math.max(2, Math.floor(plotW / 62))));
    ctx.textAlign = 'center';
    ctx.fillStyle = FAINT;
    candles.forEach((c, i) => {
      if (i % every !== 0 && i !== candles.length - 1) return;
      const hhmm = String(c.time || '').slice(11, 16);
      if (!hhmm) return;
      ctx.fillText(hhmm, cx(i), h - padB / 2);
    });

    // ── pivots: blue, under the candles so price stays legible
    const PIVOT = css.getPropertyValue('--tr-accent').trim() || '#5b6af0';
    shownPivots.forEach(({ name, v, near }) => {
      const yy = Math.round(y(v)) + 0.5;
      ctx.strokeStyle = PIVOT;
      ctx.globalAlpha = near ? 0.95 : 0.5;
      ctx.lineWidth = near ? 1.4 : 1;
      ctx.beginPath();
      ctx.moveTo(padL, yy);
      ctx.lineTo(padL + plotW, yy);
      ctx.stroke();
      ctx.globalAlpha = 1;
      ctx.fillStyle = PIVOT;
      ctx.font = `${near ? 'bold ' : ''}9px ui-monospace, Consolas, monospace`;
      ctx.textAlign = 'left';
      ctx.textBaseline = 'bottom';
      ctx.fillText(name, padL + 2, yy - 1);
    });
    ctx.textBaseline = 'middle';
    ctx.font = '9px ui-monospace, Consolas, monospace';

    // ── candles
    candles.forEach((c, i) => {
      const up = c.c >= c.o;
      const color = up ? GREEN : RED;
      const x = cx(i);
      ctx.strokeStyle = color;
      ctx.fillStyle = color;
      ctx.lineWidth = 1;
      // wick
      ctx.beginPath();
      ctx.moveTo(Math.round(x) + 0.5, y(c.h));
      ctx.lineTo(Math.round(x) + 0.5, y(c.l));
      ctx.stroke();
      // body: hollow on up bars, filled on down — the classic read
      const yo = y(c.o);
      const yc = y(c.c);
      const top = Math.min(yo, yc);
      const hgt = Math.max(1, Math.abs(yc - yo));
      if (up) {
        ctx.globalAlpha = c.hot ? 0.55 : 0.28;
        ctx.fillRect(x - body / 2, top, body, hgt);
        ctx.globalAlpha = 1;
        ctx.strokeRect(Math.round(x - body / 2) + 0.5, Math.round(top) + 0.5,
                       Math.round(body), Math.round(hgt));
      } else {
        ctx.fillRect(x - body / 2, top, body, hgt);
      }
    });

    // ── the DMI reading itself, top-right of the plot
    const readBar = hoverRef.current
      ? candles.find((c) => c.t === hoverRef.current)
      : candles[candles.length - 1];
    const read = readBar ? dmi.byT.get(readBar.t) : null;
    if (read) {
      const parts = [
        [`+DI ${read.pdi.toFixed(1)}`, GREEN],
        [`-DI ${read.mdi.toFixed(1)}`, RED],
        [`ADX ${read.adx == null ? '—' : read.adx.toFixed(1)}`,
          (read.adx ?? 0) >= ADX_FLOOR ? '#fbbf24' : FAINT],
      ];
      ctx.font = '10px ui-monospace, Consolas, monospace';
      ctx.textAlign = 'right';
      ctx.textBaseline = 'top';
      let x = padL + plotW - 2;
      for (let i = parts.length - 1; i >= 0; i -= 1) {
        const [label, colour] = parts[i];
        ctx.fillStyle = colour;
        ctx.fillText(label, x, padT + 1);
        x -= ctx.measureText(label).width + 9;
      }
      ctx.textBaseline = 'middle';
      ctx.font = '9px ui-monospace, Consolas, monospace';
    }

    // ── ADX/DMI crossovers: a letter at the bar, nothing else
    candles.forEach((c, i) => {
      const sig = marks.get(c.t);
      if (!sig) return;
      const up = sig.dir === 'up';
      ctx.fillStyle = up ? GREEN : RED;
      ctx.font = 'bold 11px ui-monospace, Consolas, monospace';
      ctx.textAlign = 'center';
      ctx.textBaseline = up ? 'top' : 'bottom';
      ctx.fillText('B', cx(i), up ? y(c.l) + 5 : y(c.h) - 5);
    });
    ctx.textBaseline = 'middle';
    ctx.font = '9px ui-monospace, Consolas, monospace';

    // the live bar's close, carried to the price axis
    if (last != null) {
      const yy = y(last);
      const col = changePct == null || changePct >= 0 ? GREEN : RED;
      ctx.fillStyle = col;
      ctx.fillRect(padL + plotW + 2, yy - 7, padR - 4, 14);
      ctx.fillStyle = '#04061a';
      ctx.textAlign = 'left';
      ctx.fillText(last.toFixed(2), padL + plotW + 5, yy);
    }

    // ── crosshair: dotted, snapped to the bar under the pointer
    if (cursor && candles.length) {
      const i = Math.max(0, Math.min(candles.length - 1,
        Math.floor((cursor.x - padL) / slot)));
      const cxi = cx(i);
      const cy = Math.max(padT, Math.min(padT + plotH, cursor.y));
      ctx.save();
      ctx.setLineDash([2, 3]);
      ctx.strokeStyle = 'rgba(154, 163, 208, 0.75)';
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.moveTo(Math.round(cxi) + 0.5, padT);
      ctx.lineTo(Math.round(cxi) + 0.5, padT + plotH);
      ctx.moveTo(padL, Math.round(cy) + 0.5);
      ctx.lineTo(padL + plotW, Math.round(cy) + 0.5);
      ctx.stroke();
      ctx.restore();

      // the price the pointer is actually on, against the axis
      const priceAt = lo + (1 - (cy - padT) / plotH) * span;
      ctx.fillStyle = 'rgba(154, 163, 208, 0.92)';
      ctx.fillRect(padL + plotW + 2, cy - 7, padR - 4, 14);
      ctx.fillStyle = '#04061a';
      ctx.font = '9px ui-monospace, Consolas, monospace';
      ctx.textAlign = 'left';
      ctx.textBaseline = 'middle';
      ctx.fillText(priceAt.toFixed(2), padL + plotW + 5, cy);

      // and the bar's time, against the time axis
      const hhmm = String(candles[i].time || '').slice(11, 16);
      if (hhmm) {
        ctx.font = '9px ui-monospace, Consolas, monospace';
        const tw = ctx.measureText(hhmm).width + 8;
        ctx.fillStyle = 'rgba(154, 163, 208, 0.92)';
        ctx.fillRect(cxi - tw / 2, h - padB, tw, padB - 2);
        ctx.fillStyle = '#04061a';
        ctx.textAlign = 'center';
        ctx.fillText(hhmm, cxi, h - padB / 2 - 1);
      }
      ctx.textAlign = 'left';
    }

    geomRef.current = { padL, slot, candles };
  }, [candles, prevClose, changePct, box, height, last, marks, dmi, hover,
      pivots, cursor]);

  const onMove = (e) => {
    const g = geomRef.current;
    const cv = canvasRef.current;
    if (!g || !cv) return;
    const r = cv.getBoundingClientRect();
    setCursor({ x: e.clientX - r.left, y: e.clientY - r.top });
    const i = Math.floor((e.clientX - r.left - g.padL) / g.slot);
    const c = i >= 0 && i < g.candles.length ? g.candles[i] : null;
    hoverRef.current = c ? c.t : null;
    setHover(c);
  };

  const streaming = stream?.state === 'live';
  const shown = hover || (candles.length ? candles[candles.length - 1] : null);

  const chart = (
    <div className={`tr-chart ${expanded ? 'fs' : ''}`}>
      <div className="tr-charthd">
        {editSym ? (
          <input className="tr-syminput" value={symDraft} autoFocus maxLength={10}
            onChange={(e) => setSymDraft(e.target.value.toUpperCase())}
            onBlur={commitSym}
            onKeyDown={(e) => {
              if (e.key === 'Enter') commitSym();
              if (e.key === 'Escape') { setSymDraft(symbol); setEditSym(false); }
            }} />
        ) : (
          // One control, two intents: a click renames the tile, a double
          // click buys it. A double click delivers its two single clicks
          // first, so the rename is DEFERRED by a beat and cancelled if the
          // second click lands — otherwise every buy would first drop the
          // header into an edit box. The same event covers a double tap.
          <button type="button" className="tr-chartsym"
            onClick={() => {
              clearTimeout(symTapRef.current);
              symTapRef.current = setTimeout(() => {
                setSymDraft(symbol);
                setEditSym(true);
              }, 260);
            }}
            onDoubleClick={() => {
              clearTimeout(symTapRef.current);
              setEditSym(false);
              onBuy?.(symbol);
            }}
            title={`${symbol} — click to chart a different ticker, double-click to buy`}>
            {symbol}
          </button>
        )}
        <span className="tr-ivchips">
          {CHART_INTERVALS.map(([v, label]) => (
            <button key={v} type="button"
              className={`tr-ivchip ${interval === v ? 'on' : ''}`}
              onClick={() => pickInterval(v)}
              title={`${label} candles for ${symbol}`}>{label}</button>
          ))}
        </span>
        {/* Percent only. The absolute price is already on the axis, on the
            last-bar readout and in the ticker strip; repeating it here cost
            header width that the interval chips and the expand control need
            on a phone. The move is what the eye is actually scanning for. */}
        {changePct != null && (
          <span className="tr-chartchg" style={{ color: pctColor(changePct) }}
            title={last != null ? `${symbol} ${last.toFixed(2)}` : undefined}>
            {changePct >= 0 ? '+' : ''}{changePct.toFixed(2)}%
          </span>
        )}
        {/* Sits beside the percent rather than pinned to the far edge: on a
            narrow screen the spacer pushed it off the end of the row. */}
        <button type="button" className="tr-chartfs-btn"
          onClick={() => setExpanded((v) => !v)}
          title={expanded ? 'back to the tile (Esc)' : 'expand to full screen'}>
          {expanded ? '⤡' : '⤢'}
        </button>
        <span className="ml-auto" />
        {shownMarks > 0 && (
          <span className="tr-note" title={`ADX(${ADX_PERIOD}) > ${ADX_FLOOR}: green B where +DI crosses above -DI, red B where -DI crosses above +DI`}>
            {shownMarks}B
          </span>
        )}
        <span className="tr-note" title={streaming
          ? `${bars.length} ${interval} bars · live price on the open bar`
          : `${bars.length} ${interval} bars · ${seed?.venue || ''} (stream runs on LIVE)`}>
          {streaming ? 'live' : (seed?.venue || '')}
        </span>
      </div>

      {/* the hovered candle, or the newest one */}
      <div className="tr-chartohlc tr-note">
        {shown ? (
          <>
            <span>{String(shown.time || '').replace('T', ' ').slice(0, 16)}</span>
            {' · '}O {shown.o?.toFixed(2)} H {shown.h?.toFixed(2)}
            {' '}L {shown.l?.toFixed(2)}{' '}
            <span style={{ color: shown.c >= shown.o ? 'var(--tr-green)' : 'var(--tr-red)' }}>
              C {shown.c?.toFixed(2)}
            </span>
          </>
        ) : <span>&nbsp;</span>}
      </div>

      {err && err === 'disconnected'
        ? <span className="tr-chart-warn" title="Tradier unreachable — retrying in 10 min">⚠</span>
        : err && <p className="tr-err" style={{ fontSize: 11 }}>⚠ {err}</p>}
      {!err && candles.length === 0 && (
        <p className="tr-note">no intraday bars yet — the session may not have opened</p>
      )}
      <canvas ref={canvasRef}
        style={expanded ? { width: '100%' } : { width: '100%', height }}
        onMouseMove={onMove}
        onMouseLeave={() => {
          hoverRef.current = null; setHover(null); setCursor(null);
        }} />
    </div>
  );

  if (!expanded) return chart;
  return (
    <div className="tr-chartfs" role="dialog" aria-modal="true"
      onMouseDown={(e) => { if (e.target === e.currentTarget) setExpanded(false); }}>
      {chart}
    </div>
  );
}

// ── left rail: live ticker prices, default display order ───────────────────
const RAIL_TICKERS = ['SPX', 'SPY', 'QQQ', 'VIX', 'IWM', 'GLD', 'AAPL', 'TSLA',
  'NVDA', 'MSFT', 'AMZN', 'MU', 'SNDK', 'AVGO', 'META', 'GOOGL', 'LLY', 'JPM',
  'ORCL', 'IBM', 'ONDS', 'IONQ', 'QBTS'];
const RAIL_KEY = 'tradier.rail.tickers';   // user's customized list, per browser

function loadRailTickers() {
  try {
    const j = JSON.parse(localStorage.getItem(RAIL_KEY));
    if (Array.isArray(j) && j.length && j.every((s) => typeof s === 'string')) return j;
  } catch { /* fall through to default */ }
  return RAIL_TICKERS;
}

function px(v) {
  if (v === null || v === undefined || Number.isNaN(Number(v))) return '—';
  const n = Number(v);
  return n.toLocaleString(undefined, {
    minimumFractionDigits: 2, maximumFractionDigits: 2,
  });
}

// progressive % color: flat = muted gray, ramping to BRIGHT green/red as the
// move grows — full brightness at ±3% and beyond
function pctColor(pct) {
  const v = Number(pct);
  if (!Number.isFinite(v)) return 'var(--tr-faint)';
  const t = Math.min(1, Math.abs(v) / 3);
  const dim = [122, 116, 144];                        // near-flat: muted
  const hot = v >= 0 ? [0, 255, 128] : [255, 120, 100]; // bright green / coral
  const c = dim.map((d, i) => Math.round(d + (hot[i] - d) * t));
  return `rgb(${c[0]}, ${c[1]}, ${c[2]})`;
}

/* ── HOT: the top-100 names in a strong, one-sided uptrend ──────────────────
   Three gates on Wilder DMI/ADX, all of which must hold:

       +DI  >  25        the up-move is substantial on its own
       +DI >= -DI x 2    and it DOMINATES rather than merely leads
       ADX  >  34        and the whole thing is a trend, not a range

   The middle gate is the point. A +DI/-DI crossover happens constantly and
   reverses just as often; twice -DI says the buyers are not being answered.

   Served from a background bar sweep — 100 timesales calls — so this polls a
   snapshot rather than waiting on the venue. */
// The server re-sweeps once its snapshot passes this age; shown here so the
// panel can say so rather than leaving the cadence a mystery.
const HOT_REFRESH_MIN = 15;

// No thousands separator here. In a 232px rail the comma is a whole
// character's width spent on decoration, and 1027.15 is not less legible than
// 1,027.15 in a column of prices.
function hotPx(v) {
  if (v === null || v === undefined || Number.isNaN(Number(v))) return '—';
  return Number(v).toLocaleString(undefined, {
    minimumFractionDigits: 2, maximumFractionDigits: 2, useGrouping: false,
  });
}

// Price width, in steps. 78.22 is five characters, 379.20 is six, 1234.56 is
// seven — and each extra one eats into the space the buy button needs, so the
// price steps down a size rather than pushing the row wider.
function lastSizeClass(text) {
  const n = String(text).length;
  if (n >= 8) return 'sm3';
  if (n >= 7) return 'sm2';     // 1234.56
  if (n >= 6) return 'sm1';     // 379.20
  return '';                    // 78.22 and shorter — full size
}
/* ── the buy ticket ────────────────────────────────────────────────────────
   Every buy on this desk opens this, prefilled: the charts, the HOT list, the
   flow board, the A/B rail. There is no longer a standing composer to type
   into — the ticket IS the composer, opened against whatever you clicked.

   Two shapes, because the desk has two kinds of buy. Given a ticker and a
   side, the backend picks the contract from the delta band. Given a contract
   the board already chose, there is nothing to search: the delta band and
   0DTE are not just irrelevant then, they would be a lie about what happens
   next, so they are not shown.

   Whatever you change here becomes the next ticket's defaults. 0DTE is the
   exception — it resets every time, because a same-day expiry left armed from
   the last order is exactly the trade nobody meant to place. */
const DESK_KEY = 'vidura.tradier.desk';
const DESK_DEFAULTS = {
  buy_pct: '50', size_tol: '25', delta: '0.25-0.45', tp_pct: '15', sl_pct: '30',
};
function loadDeskDefaults() {
  try {
    const j = JSON.parse(localStorage.getItem(DESK_KEY));
    if (j && typeof j === 'object') return { ...DESK_DEFAULTS, ...j };
  } catch { /* first run */ }
  return { ...DESK_DEFAULTS };
}

const DISCOUNT_OPTIONS = [5, 10, 20, 40];

function BuyTicket({ open, desk, onDesk, live, bal, busy, err, onErr, onPlace, onClose }) {
  const named = !!open?.occ_symbol;
  const [side, setSide] = useState(open?.side === 'put' ? 'put' : 'call');
  const [zeroDte, setZeroDte] = useState(false);
  const [manualSym, setManualSym] = useState('');
  const [market, setMarket] = useState(true);
  const [discount, setDiscount] = useState(10);
  const [midDayWarn, setMidDayWarn] = useState(false);
  useEffect(() => {
    setSide(open?.side === 'put' ? 'put' : 'call');
    setZeroDte(false);
    setManualSym(open?.symbol || '');
    setMidDayWarn(false);
  }, [open]);

  // Editing a refused ticket clears the refusal: the message described the
  // numbers as they were, and leaving it up over new ones makes it a lie.
  const set = (k) => (e) => { onErr?.(null); onDesk({ ...desk, [k]: e.target.value }); };

  useEffect(() => {
    const onKey = (e) => { if (e.key === 'Escape' && !busy) onClose(); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose, busy]);

  if (!open) return null;
  const sym = open.symbol || manualSym.trim().toUpperCase();

  const isMidDay = () => {
    const now = new Date();
    const cst = new Date(now.toLocaleString('en-US', { timeZone: 'America/Chicago' }));
    return cst.getHours() * 60 + cst.getMinutes() >= 675; // 11:15 AM = 675
  };

  const doPlace = () => onPlace({
    symbol: sym,
    occ_symbol: open.occ_symbol,
    side,
    zero_dte: zeroDte,
    discount_pct: market ? 0 : discount,
    ...desk,
  });

  const place = () => {
    if (isMidDay() && !midDayWarn) { setMidDayWarn(true); return; }
    setMidDayWarn(false);
    doPlace();
  };

  return (
    <div className="tr-modal-backdrop" role="dialog" aria-modal="true"
      aria-label={`buy ${open.symbol}`}
      onMouseDown={(e) => { if (e.target === e.currentTarget && !busy) onClose(); }}>
      <div className={`tr-ticket ${live ? 'live' : ''}`} onClick={(e) => e.stopPropagation()}>
        <div className="tr-ticket-hd">
          <span className="tr-eyebrow" style={{ display: 'inline' }}>buy</span>
          {open.symbol
            ? <b className="tr-ticket-sym">{open.symbol}</b>
            : <input className="tr-input tr-ticket-sym-input" value={manualSym}
                onChange={(e) => { onErr?.(null); setManualSym(e.target.value.toUpperCase()); }}
                placeholder="TICKER" autoFocus spellCheck={false} />}
          <span className={`tr-venue-pill ${live ? 'live' : ''}`}>
            {live ? 'LIVE' : 'SANDBOX'}
          </span>
          <span className="ml-auto" />
          <button type="button" className="tr-ticket-x" onClick={onClose}
            disabled={busy} aria-label="close">✕</button>
        </div>

        {open.why && <p className="tr-note tr-ticket-why">{open.why}</p>}
        {named && (
          <p className="tr-note tr-mono tr-ticket-why">
            {open.occ_symbol} — chosen already, so no delta search
          </p>
        )}

        <div className="tr-ticket-grid">
          {!named && (
            <div><span className="tr-label">Side</span>
              <select className="tr-select" value={side}
                onChange={(e) => setSide(e.target.value)}>
                <option value="call">CALL</option><option value="put">PUT</option>
              </select></div>
          )}
          <div><span className="tr-label">Buy % of balance</span>
            <input className="tr-input" type="number" min="1" max="100" value={desk.buy_pct}
              onWheel={(e) => e.currentTarget.blur()} onChange={set('buy_pct')} /></div>
          <div><span className="tr-label">Size ± %</span>
            <input className="tr-input" type="number" min="0" max="100" value={desk.size_tol}
              onWheel={(e) => e.currentTarget.blur()} onChange={set('size_tol')}
              title={'How far either side of the Buy % budget the total may land. '
                + 'Contracts are indivisible, so Buy % is a target: at 50% of $100 '
                + 'with ±25% the window is $37.50–$62.50. 0 makes it a hard cap.'} /></div>
          {!named && (
            <div><span className="tr-label">Delta range</span>
              <input className="tr-input" value={desk.delta} placeholder="0.25-0.45"
                onChange={set('delta')}
                title={'Typed as a magnitude and searched signed — a CALL runs 0..+1 '
                  + `and a PUT runs 0..-1, so this ${side.toUpperCase()} searches `
                  + `${signedBandLabel(side, desk.delta)}.`} /></div>
          )}
          <div><span className="tr-label">TP % over entry</span>
            <input className="tr-input" type="number" min="1" max="500" value={desk.tp_pct}
              onWheel={(e) => e.currentTarget.blur()} onChange={set('tp_pct')} /></div>
          <div><span className="tr-label">SL % below entry</span>
            <input className="tr-input" type="number" min="1" max="99" value={desk.sl_pct}
              onWheel={(e) => e.currentTarget.blur()} onChange={set('sl_pct')} /></div>
          <div><span className="tr-label">Order type</span>
            <div className="tr-market-toggle">
              <button type="button"
                className={`tr-chip ${market ? 'on' : ''}`}
                onClick={() => setMarket(true)}>MKT</button>
              <button type="button"
                className={`tr-chip ${!market ? 'on' : ''}`}
                onClick={() => setMarket(false)}>LIMIT</button>
            </div>
            {!market && (
              <div className="tr-discount-row">
                {DISCOUNT_OPTIONS.map((d) => (
                  <button key={d} type="button"
                    className={`tr-chip sm ${discount === d ? 'on' : ''}`}
                    onClick={() => setDiscount(d)}>
                    −{d}%
                  </button>
                ))}
              </div>
            )}
          </div>
        </div>

        {midDayWarn && (
          <div className="tr-ticket-err" role="alert" style={{ background: '#78350f', borderColor: '#f59e0b' }}>
            <span className="x">⚠</span>
            <span className="msg">You lost many trades in MID DAY, AVOID!!!</span>
            <span className="ml-auto" />
            <button type="button" className="tr-btn sm" onClick={() => setMidDayWarn(false)}
              style={{ marginRight: 6 }}>Cancel</button>
            <button type="button" className="tr-btn sm buy" onClick={() => { setMidDayWarn(false); doPlace(); }}>
              Continue anyway
            </button>
          </div>
        )}

        {err && (
          <div className="tr-ticket-err" role="alert">
            <span className="x">✗</span>
            <span className="msg">{err}</span>
            <button type="button" className="dismiss" onClick={() => onErr?.(null)}
              aria-label="dismiss">✕</button>
          </div>
        )}

        <div className="tr-ticket-ft">
          {!named && (
            <button type="button" className={`tr-chip tr-0dte ${zeroDte ? 'on' : ''}`}
              aria-pressed={zeroDte} onClick={() => setZeroDte((v) => !v)}
              title={zeroDte
                ? 'same-day expiries allowed — the nearest expiry, today included'
                : 'same-day expiries skipped — the nearest expiry after today'}>
              0DTE {zeroDte ? 'ON' : 'OFF'}
            </button>
          )}
          <span className="tr-note">
            {named
              ? `${desk.buy_pct}% ±${desk.size_tol}% · TP ${desk.tp_pct}% · SL ${desk.sl_pct}%`
              : `delta ${signedBandLabel(side, desk.delta)} · ${desk.buy_pct}% ±${desk.size_tol}%`
                + ` · TP ${desk.tp_pct}% · SL ${desk.sl_pct}%`}
            {!market && ` · LIMIT −${discount}%`}
          </span>
          <span className="ml-auto" />
          <button type="button" className="tr-btn sm" onClick={onClose} disabled={busy}>
            Cancel
          </button>
          <button type="button" className={`tr-btn sm ${side === 'put' ? 'sell' : 'buy'}`}
            onClick={place} disabled={busy || !bal || !sym}>
            {busy ? 'Placing…'
              : live ? `▶ Buy ${side.toUpperCase()} — REAL money`
                : `▶ Buy ${side.toUpperCase()}`}
          </button>
        </div>
        {live && (
          <p className="tr-note warn tr-ticket-why">
            LIVE account{bal?.account_id ? ` ${bal.account_id}` : ''} — this spends real money.
          </p>
        )}
      </div>
    </div>
  );
}

/* ── the day's movers ──────────────────────────────────────────────────────
   Top 3 up and top 3 down across the megacaps, for the header strip. One
   quotes call for the whole list on a slow timer: this is context, not a
   signal, and it moves on the scale of the session rather than the tick. */
const MEGACAPS = ('AAPL,MSFT,NVDA,AMZN,GOOGL,META,TSLA,AVGO,LLY,JPM,V,UNH,'
  + 'XOM,MA,COST,HD,PG,JNJ,ABBV,WMT,NFLX,BAC,CRM,AMD,ORCL,QCOM,ADBE,INTC').split(',');

// `minPct` is the notability floor: the strip only wants movers worth
// looking at, so a flat day shows none rather than a list of noise. Pass 0
// to get a straight ranking instead — which is what a "top 5" list wants,
// where the answer is still the top 5 on a quiet day.
export function useMovers(user, top = 3, minPct = 0.99) {
  const [movers, setMovers] = useState(null);

  useEffect(() => {
    if (!user) return undefined;
    let alive = true;
    const load = async () => {
      try {
        const d = await vidura.tradierQuotes(user.user_id, MEGACAPS.join(','));
        if (!alive) return;
        const rows = (d.quotes || [])
          .filter((q) => q.change_pct !== null && q.change_pct !== undefined)
          .sort((a, b) => Number(b.change_pct) - Number(a.change_pct));
        if (rows.length < 2) { setMovers(null); return; }
        // the losers come back worst-first, so the two ends read outward
        // from flat in both directions
        setMovers({
          up: rows.slice(0, top).filter((q) => Number(q.change_pct) >= minPct),
          down: rows.slice(-top).reverse().filter((q) => Number(q.change_pct) <= -minPct),
        });
      } catch { /* the strip simply carries no movers */ }
    };
    load();
    const t = setInterval(() => { if (!document.hidden) load(); }, 60_000);
    return () => { alive = false; clearInterval(t); };
  }, [user, top, minPct]);

  return movers;
}

const HOT_INTERVALS = ['5min', '15min', '30min', '1h'];
const HOT_IV_KEY = 'vidura.tradier.hot.interval';
const loadHotInterval = () => {
  try {
    const v = localStorage.getItem(HOT_IV_KEY);
    if (HOT_INTERVALS.includes(v)) return v;
  } catch { /* first run */ }
  return '5min';
};

// Exported alongside MiniChart so another board can show the SAME scan —
// same gates, same granularity chips, same cached snapshot — rather than a
// second copy that quietly disagrees with this one.
export function HotScan({ user, live, onPick, onError, onBuy, buying, blocked, slotAfterSuperhot }) {
  const [snap, setSnap] = useState(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState(null);
  const [interval_, setInterval_] = useState(loadHotInterval);
  const pickInterval = (v) => {
    setInterval_(v);
    try { localStorage.setItem(HOT_IV_KEY, v); } catch { /* ignore */ }
  };

  const load = useCallback(async (force = false) => {
    if (!user) return;
    try {
      setSnap(await vidura.tradierHot(user.user_id, live, interval_, force));
      setErr(null);
    } catch (e) { setErr(errText(e)); onError?.('hot scan', e); }
  }, [user, live, interval_, onError]);

  useEffect(() => { load(); }, [load]);
  // The SWEEP runs every 15 minutes; this poll is not the sweep, it is the
  // heartbeat that lets the server notice its snapshot has aged out. So it
  // stays at a minute rather than matching the cadence: poll every 15 and a
  // sweep would only start on the first tick AFTER the snapshot went stale,
  // leaving the list up to 30 minutes old. Each call is a cached dict.
  // While a sweep is IN FLIGHT it tightens to a few seconds — a granularity
  // switch starts a fresh one, and waiting out a full tick to see the result
  // makes the switch feel broken.
  usePolling(load, snap?.refreshing ? 3_000 : 60_000, { enabled: !!user && isMarketOpen(), blocked });

  const doRefresh = async () => {
    if (busy) return;
    setBusy(true);
    await load(true);
    setTimeout(() => { load(); setBusy(false); }, 6000);
  };

  const rows = snap?.rows || [];
  const superhotRows = snap?.superhot || [];
  const meta = snap?.meta || {};
  const g = meta.gates || {};
  const shg = meta.sh_gates || {};

  // Track when each symbol first appeared so new arrivals can be highlighted
  // for 30 min. The ref persists across renders; entries older than 30 min are
  // pruned every cycle. A timeout re-renders at the EARLIEST expiration so the
  // highlight drops precisely when each symbol's 30 min are up.
  const NEW_TTL = 30 * 60_000;
  const seenRef = useRef({ hot: {}, superhot: {} });
  const [newTick, bumpNew] = useState(0);

  const shDayRef = useRef({ day: null, times: {} });
  const [shTick, bumpSh] = useState(0);
  useEffect(() => {
    const now = Date.now();
    const today = new Date().toDateString();
    if (shDayRef.current.day !== today) {
      shDayRef.current = { day: today, times: {} };
    }
    const m = shDayRef.current.times;
    superhotRows.forEach((r) => { if (!(r.symbol in m)) m[r.symbol] = now; });
    const tid = setTimeout(() => bumpSh((v) => v + 1), 60_000);
    return () => clearTimeout(tid);
  }, [snap, shTick]);  // eslint-disable-line react-hooks/exhaustive-deps
  const shAge = (sym) => {
    const t = shDayRef.current.times[sym];
    if (t == null) return '';
    const mins = Math.floor((Date.now() - t) / 60_000);
    if (mins < 1) return '<1m';
    if (mins < 60) return `${mins}m`;
    const hrs = mins / 60;
    return `${hrs.toFixed(1)}h`;
  };

  useEffect(() => {
    const now = Date.now();
    const tag = (map, syms) => {
      syms.forEach((s) => { if (!(s in map)) map[s] = now; });
      for (const k of Object.keys(map)) {
        if (now - map[k] > NEW_TTL) delete map[k];
      }
    };
    tag(seenRef.current.hot, rows.map((r) => r.symbol));
    tag(seenRef.current.superhot, superhotRows.map((r) => r.symbol));
    const allTimes = [
      ...Object.values(seenRef.current.hot),
      ...Object.values(seenRef.current.superhot),
    ];
    if (allTimes.length > 0) {
      const earliest = Math.min(...allTimes);
      const remaining = NEW_TTL - (now - earliest);
      if (remaining > 0) {
        const tid = setTimeout(() => bumpNew((v) => v + 1), remaining + 200);
        return () => clearTimeout(tid);
      }
    }
  }, [snap, newTick]);  // eslint-disable-line react-hooks/exhaustive-deps
  const isNew = (kind, sym) => {
    const t = seenRef.current[kind]?.[sym];
    return t != null && Date.now() - t < NEW_TTL;
  };

  return (
    <>
    {/* ── SUPERHOT: the tighter tier, period-9 DMI with slope + DXS ──────
       Collapses to nothing when no names qualify — unlike HOT, which always
       has its chrome. The section appears only when there is something to
       show, so the panel space goes entirely to the list. */}
    {superhotRows.length > 0 && (
      <div className="tr-panel tr-superhot mb-4">
        <div className="flex items-center gap-2 mb-1">
          <span className="tr-eyebrow" style={{ display: 'inline' }}>⚡ superhot{err && ' ⚠'}</span>
          <span className="tr-note"
            title={`period-${shg.di_period ?? 9} DMI · ADX ${shg.min_adx ?? 20}–${shg.max_adx ?? 50}`
              + ` · slope > 0 · |DXS| ≥ ${shg.min_dxs ?? 0.35}`
              + ' — trend onset with directional efficiency'}>
            {superhotRows.length}
            {meta.sh_calls != null
              ? ` · ${meta.sh_calls}C ${meta.sh_puts}P`
              : ''}
          </span>
          <button type="button" className="tr-chip" onClick={doRefresh} disabled={busy}
            title="force a fresh scan now">↻</button>
        </div>
        <div className="tr-hotlist tr-mono">
          {superhotRows.map((r) => {
            const side = r.sh_side || r.side || 'call';
            return (
              <div key={r.symbol} className={`tr-hotrow tr-shrow ${side}`}>
                <button type="button" className={`tr-tkr${isNew('superhot', r.symbol) ? ' tr-new' : ''}`}
                  onClick={() => onPick?.(r.symbol)}
                  onDoubleClick={() => onBuy?.({ symbol: r.symbol, side })}
                  title={`${r.symbol} — tap: chart · double-tap: buy`}>{r.symbol}</button>
                <span className={`last ${lastSizeClass(hotPx(r.last))}`}
                  title={`last ${px(r.last)}`}>{hotPx(r.last)}</span>
                <span className="tr-hotdi tr-note">
                  <span className="tr-shadx" title={`ADX(${shg.di_period ?? 9}) ${r.sh_adx} · slope ${r.sh_slope > 0 ? '+' : ''}${r.sh_slope}`}>
                    {Math.round(r.sh_adx)}
                  </span>
                  <span className="tr-shdxs"
                    title={`DXS ${r.sh_dxs > 0 ? '+' : ''}${r.sh_dxs} — directional efficiency`}>
                    {r.sh_dxs > 0 ? '+' : ''}{(r.sh_dxs * 100).toFixed(0)}%
                  </span>
                </span>
                {shAge(r.symbol) && (
                  <span className="tr-note" style={{ fontSize: '0.75em', minWidth: '2.5em', textAlign: 'right' }}
                    title={`in superhot list for ${shAge(r.symbol)} today`}>{shAge(r.symbol)}</span>
                )}
                <span className="tr-shslope"
                  title={`ADX slope over ${shg.slope_lb ?? 3} bars — positive means the trend is strengthening`}>
                  {r.sh_slope > 0 ? '↑' : '↓'}
                </span>
              </div>
            );
          })}
        </div>
      </div>
    )}

    {slotAfterSuperhot}

    <div className="tr-panel tr-hot mb-4">
      <div className="flex items-center gap-2 mb-1">
        <span className="tr-eyebrow" style={{ display: 'inline' }}>🔥 hot{err && ' ⚠'}</span>
        <span className="tr-note"
          title={'of the top 100, on ' + (meta.interval || '5min') + ' bars: a '
            + 'CALL when +DI is above ' + (g.min_di ?? 25) + ' and at least '
            + (g.di_ratio ?? 2) + '× -DI, a PUT when -DI is, and ADX above '
            + (g.min_adx ?? 34) + ' either way — a trend that is strong AND '
            + 'one-sided'}>
          {rows.length
            ? `${rows.length}/${meta.scanned || 100}`
            + (meta.calls != null ? ` · ${meta.calls}C ${meta.puts}P` : '')
            : ''}
        </span>
      </div>

      {/* Granularity. Each choice is a fresh 100-name sweep on that bar size —
          the switch IS the regenerate control. All four come from Tradier
          natively, each with its own lookback so every one lands on a
          comparable number of bars. Remembered per browser. */}
      <div className="tr-hotivs mb-2">
        {HOT_INTERVALS.map((iv) => (
          <button type="button" key={iv}
            className={`tr-chip ${interval_ === iv ? 'on' : ''}`}
            onClick={() => pickInterval(iv)} disabled={busy}
            title={`recompute the DMI on ${iv} bars`}>
            {iv === '1h' ? '1H' : iv.replace('min', 'm')}
          </button>
        ))}
        <span className="ml-auto" />
        {(snap?.refreshing || busy) && <span className="tr-note">scanning…</span>}
        {/* Age, not wall-clock: on a 15-minute cadence "is this current?" is
            the only question the timestamp is asked, and "09:54" makes you
            do the subtraction. The exact time is in the title. */}
        {!snap?.refreshing && !busy && meta.at && (
          <span className="tr-note"
            title={`swept ${meta.at} · ${meta.scanned} scanned · `
              + `${meta.with_readings} with readings · ${meta.took_s}s · `
              + `${meta.venue} · ${meta.interval} bars · `
              + `re-sweeps every ${HOT_REFRESH_MIN} min`}>
            {snap?.age_s == null ? meta.at : `${Math.floor(snap.age_s / 60)}m`}
          </span>
        )}
        <button type="button" className="tr-chip" onClick={doRefresh} disabled={busy}
          title={`sweep the 100 names now — otherwise it re-runs by itself every ${HOT_REFRESH_MIN} min`}>↻</button>
      </div>

      {err && <p className="tr-err">⚠ {err}</p>}
      {!err && rows.length === 0 && (
        <p className="tr-note">
          {snap?.refreshing || busy
            ? 'scanning 100 tickers…'
            : `nothing clears DI>${g.min_di ?? 25}, ${g.di_ratio ?? 2}× the other side and ADX>${g.min_adx ?? 34} right now`}
        </p>
      )}

      <div className="tr-hotlist tr-mono">
        {rows.map((r) => (
          <div key={r.symbol} className={`tr-hotrow ${r.side}`}>
            {/* the desk's shared ticker link: same look and same popup as the
                watchlist and the flow board — live price, pivot levels and an
                external TradingView link */}
            <button type="button" className={`tr-tkr${isNew('hot', r.symbol) ? ' tr-new' : ''}`}
              onClick={() => onPick?.(r.symbol)}
              onDoubleClick={() => onBuy?.(r)}
              title={`${r.symbol} — tap: chart · double-tap: buy`}>{r.symbol}</button>
            {/* A four-figure price is two characters wider than a two-figure
                one, and in a rail this narrow those two characters are what
                push the buy button off the row. The price gives them back by
                setting a step smaller — it is the only field here whose width
                varies, and the least harmed by losing a point of size. */}
            <span className={`last ${lastSizeClass(hotPx(r.last))}`}
              title={`last ${px(r.last)}`}>{hotPx(r.last)}</span>
            {/* ADX:+DI:-DI as whole numbers — on a 0-100 scale the decimals
                were noise, and the row is read at a glance. The dominant side
                is the one carrying the colour. */}
            {/* A three-digit reading — ADX or a DI at 100 — makes this group
                nine characters and it would clip. It steps down like the
                price does rather than eat the buy button's column. */}
            <span className={'tr-hotdi tr-note'
              + (`${Math.round(r.adx)}${Math.round(r.plus_di)}${Math.round(r.minus_di)}`.length >= 7
                ? ' sm' : '')}>
              <span className="tr-hotadx" title={`ADX ${r.adx} — trend strength`}>
                {Math.round(r.adx)}
              </span>
              :
              <b style={{ color: 'var(--tr-green)' }} title={`+DI ${r.plus_di}`}>
                {Math.round(r.plus_di)}
              </b>
              :
              <b style={{ color: 'var(--tr-red)' }} title={`-DI ${r.minus_di}`}>
                {Math.round(r.minus_di)}
              </b>
            </span>
            <span className="tr-hotratio"
              title={r.side === 'put'
                ? '-DI ÷ +DI — how far past the 2× gate the sellers are unanswered'
                : '+DI ÷ -DI — how far past the 2× gate the buyers are unanswered'}>
              {r.di_ratio == null ? '∞' : `${Math.round(r.di_ratio)}x`}
            </span>
          </div>
        ))}
      </div>
    </div>
    </>
  );
}

export function CommoditiesPanel({ user, live, onPick, onError, onBuy, blocked }) {
  const [snap, setSnap] = useState(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState(null);

  const load = useCallback(async (force = false) => {
    if (!user) return;
    try {
      setSnap(await vidura.tradierCommodities(user.user_id, live, force));
      setErr(null);
    } catch (e) { setErr(errText(e)); onError?.('commodities', e); }
  }, [user, live, onError]);

  useEffect(() => { load(); }, [load]);
  usePolling(load, 60_000, { enabled: !!user, blocked });

  const doRefresh = async () => {
    if (busy) return;
    setBusy(true);
    await load(true);
    setTimeout(() => { load(); setBusy(false); }, 3000);
  };

  const rows = snap?.rows || [];
  const meta = snap?.meta || {};

  const sideColor = (side) => side === 'call' ? 'var(--tr-green)' : side === 'put' ? 'var(--tr-red)' : 'var(--tr-muted)';
  const sideLabel = (side) => side === 'call' ? 'C' : side === 'put' ? 'P' : '—';

  return (
    <div className="tr-panel tr-commodities mb-4">
      <div className="flex items-center gap-2 mb-1">
        <span className="tr-eyebrow" style={{ display: 'inline' }}>CMDTS{err && ' ⚠'}</span>
        <span className="tr-note">
          {meta.source && <span title={meta.source === 'tradier' ? 'market hours — Tradier bars' : 'off-hours — API Ninjas live prices'}>{meta.source === 'tradier' ? '📊 tradier' : '🌙 ninja-api'}</span>}
        </span>
        {meta.at && (
          <span className="tr-note" title={`scanned ${meta.at} · ${meta.took_s}s · ${meta.venue}`}>
            {snap?.age_s == null ? meta.at : `${Math.floor(snap.age_s / 60)}m`}
          </span>
        )}
        <button type="button" className="tr-chip" onClick={doRefresh} disabled={busy}
          title="force a fresh commodity scan now">↻</button>
      </div>

      {err && <p className="tr-err">⚠ {err}</p>}

      <div className="tr-hotlist tr-mono">
        {rows.map((r) => {
          const signal = r.signal || r.m1_side || r.m2_side || r.m5_side;
          return (
            <div key={r.symbol} className={`tr-hotrow ${signal || ''}`}
              style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
              <button type="button" className="tr-tkr"
                onClick={() => onPick?.(r.symbol)}
                onDoubleClick={() => onBuy?.({ symbol: r.symbol, side: signal || 'call' })}
                title={`${r.label} — tap: chart · double-tap: buy · ${r.bars_1m ?? 0} bars · source: ${r.source ?? 'tradier'}`}
                style={{ minWidth: '2.5em' }}>{r.symbol}</button>
              <span className={`last ${lastSizeClass(hotPx(r.last))}`}
                title={`last ${px(r.last)}`}>{hotPx(r.last)}</span>
              <span className="tr-note" style={{ fontSize: '0.7em', minWidth: '3.5em' }}
                title={`1m: ADX ${r.m1_adx ?? '—'} · +DI ${r.m1_pdi ?? '—'} · -DI ${r.m1_mdi ?? '—'} · slope ${r.m1_slope ?? '—'}`}>
                <span style={{ color: sideColor(r.m1_side), fontWeight: 600 }}>1m</span>
                {' '}{r.m1_adx != null ? Math.round(r.m1_adx) : '—'}
                {r.m1_slope != null && <span style={{ fontSize: '0.9em' }}>{r.m1_slope > 0 ? '↑' : '↓'}</span>}
              </span>
              <span className="tr-note" style={{ fontSize: '0.7em', minWidth: '3.5em' }}
                title={`2m: ADX ${r.m2_adx ?? '—'} · +DI ${r.m2_pdi ?? '—'} · -DI ${r.m2_mdi ?? '—'} · slope ${r.m2_slope ?? '—'}`}>
                <span style={{ color: sideColor(r.m2_side), fontWeight: 600 }}>2m</span>
                {' '}{r.m2_adx != null ? Math.round(r.m2_adx) : '—'}
                {r.m2_slope != null && <span style={{ fontSize: '0.9em' }}>{r.m2_slope > 0 ? '↑' : '↓'}</span>}
              </span>
              <span className="tr-note" style={{ fontSize: '0.7em', minWidth: '3.5em' }}
                title={`5m: ADX ${r.m5_adx ?? '—'} · +DI ${r.m5_pdi ?? '—'} · -DI ${r.m5_mdi ?? '—'} · slope ${r.m5_slope ?? '—'}`}>
                <span style={{ color: sideColor(r.m5_side), fontWeight: 600 }}>5m</span>
                {' '}{r.m5_adx != null ? Math.round(r.m5_adx) : '—'}
                {r.m5_slope != null && <span style={{ fontSize: '0.9em' }}>{r.m5_slope > 0 ? '↑' : '↓'}</span>}
              </span>
              {/* The signal is 1m+2m agreement — the same rule the commodity
                  bots trade on, so the board and the bot never disagree. This
                  read "1m/2m/5m agree", which was never what it meant. 5m is
                  reported separately as confirmation. */}
              {r.signal ? (
                <span style={{ color: sideColor(r.signal), fontWeight: 700, fontSize: '0.75em' }}
                  title={`1m and 2m agree: ${sideLabel(r.signal)}${r.m5_confirms ? ' · 5m confirms' : ' · 5m does not confirm'}`}>
                  {sideLabel(r.signal)}{r.m5_confirms ? '✓' : ''}
                </span>
              ) : (
                <span style={{ color: '#888', fontWeight: 700, fontSize: '0.75em' }}
                  title="1m and 2m disagree — no clear signal">M</span>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

function TickerRail({ user, onPick }) {
  const [data, setData] = useState(null);
  const [err, setErr] = useState(null);
  const [symbols, setSymbols] = useState(loadRailTickers);
  const [draft, setDraft] = useState('');

  useEffect(() => {
    try { localStorage.setItem(RAIL_KEY, JSON.stringify(symbols)); } catch { /* ignore */ }
  }, [symbols]);

  useEffect(() => {
    if (!user) return undefined;
    let alive = true;
    const load = async () => {
      try {
        const d = await vidura.tradierQuotes(user.user_id, symbols.join(','));
        if (alive) { setData(d); setErr(null); }
      } catch (e) { if (alive) setErr(errText(e)); }
    };
    load();
    const t = setInterval(load, 15_000);
    return () => { alive = false; clearInterval(t); };
  }, [user, symbols]);

  const addSymbol = async () => {
    const s = draft.trim().toUpperCase();
    if (!/^[A-Z0-9^.\-]{1,10}$/.test(s) || symbols.includes(s)) return;
    const ok = await confirmDialog({
      title: `Add ${s} to the ticker rail?`,
      body: `${s} gets a live-quote row (Tradier, yfinance fallback) with the `
        + 'pivot popup, and stays on the rail in this browser until removed.',
      confirmText: 'Add ticker', cancelText: 'Cancel',
    });
    if (!ok) return;
    setSymbols((prev) => (prev.includes(s) ? prev : [...prev, s]));
    setDraft('');
  };
  const removeSymbol = async (s) => {
    const ok = await confirmDialog({
      title: `Remove ${s} from the ticker rail?`,
      body: `${s} disappears from the rail in this browser. You can add it back `
        + 'any time with the + symbol box.',
      confirmText: 'Remove ticker', cancelText: 'Keep it',
    });
    if (!ok) return;
    setSymbols((prev) => prev.filter((x) => x !== s));
  };

  // drag & drop reorder: drop inserts the dragged row BEFORE the target row;
  // the new order persists through the same localStorage effect as add/remove
  const dragFrom = useRef(null);
  const [dragging, setDragging] = useState(null);
  const [dropAt, setDropAt] = useState(null);
  const onDrop = (target) => {
    const from = dragFrom.current;
    dragFrom.current = null;
    setDragging(null);
    setDropAt(null);
    if (!from || from === target) return;
    setSymbols((prev) => {
      const arr = prev.filter((x) => x !== from);
      arr.splice(arr.indexOf(target), 0, from);
      return arr;
    });
  };

  return (
    <div className="tr-panel tr-rail">
      <span className="tr-eyebrow mb-2" style={{ display: 'block' }}>live tickers</span>
      {err && !data && <p className="tr-err">⚠ {err}</p>}
      {!err && !data && <p className="tr-note">loading quotes…</p>}
      {data && (
        <div className="tr-ticklist tr-mono">
          {(() => {
            const qmap = {};
            for (const q of data.quotes) qmap[q.symbol] = q;
            return symbols.map((s) => {
              const q = qmap[s] || { symbol: s, price: null, change_pct: null };
              const up = Number(q.change_pct) > 0;
              return (
                <div key={s}
                  className={`tr-tick ${dragging === s ? 'dragging' : ''} ${dropAt === s ? 'dragover' : ''}`}
                  draggable
                  onDragStart={(e) => {
                    dragFrom.current = s;
                    setDragging(s);
                    e.dataTransfer.effectAllowed = 'move';
                    try { e.dataTransfer.setData('text/plain', s); } catch { /* ignore */ }
                  }}
                  onDragOver={(e) => {
                    e.preventDefault();
                    e.dataTransfer.dropEffect = 'move';
                    if (dropAt !== s) setDropAt(s);
                  }}
                  onDragLeave={() => { if (dropAt === s) setDropAt(null); }}
                  onDrop={(e) => { e.preventDefault(); onDrop(s); }}
                  onDragEnd={() => { dragFrom.current = null; setDragging(null); setDropAt(null); }}
                >
                  <button type="button" className="sym tr-tkr"
                    title={`${s} — live price, pivot points, TradingView · drag to reorder`}
                    onClick={() => onPick(s)}>{s}</button>
                  <span className="last">{px(q.price)}</span>
                  <span className="chg" style={{ color: pctColor(q.change_pct) }}>
                    {q.change_pct === null || q.change_pct === undefined
                      ? '—' : `${up ? '+' : ''}${Number(q.change_pct).toFixed(2)}%`}
                  </span>
                  <button type="button" className="rm" title={`remove ${s} from the rail`}
                    onClick={() => removeSymbol(s)}>✕</button>
                </div>
              );
            });
          })()}
          <div className="tr-tick-add">
            <input className="tr-input" value={draft} placeholder="+ symbol"
              maxLength={10} title="add a ticker to the rail (Enter)"
              onChange={(e) => setDraft(e.target.value.toUpperCase())}
              onKeyDown={(e) => { if (e.key === 'Enter') addSymbol(); }} />
            <button type="button" className="tr-chip" onClick={addSymbol}
              disabled={!draft.trim()}>＋ add</button>
          </div>
          <p className="tr-note mt-2">source: {data.source} · 15s refresh</p>
        </div>
      )}
    </div>
  );
}

// ── level crosses · latest per level (SPY/QQQ/SPX) — the intraday desk's
// LevelsPanel, fed by levels_watcher.py through the API. A new cross of the
// same level overrides the previous one, so each level shows its freshest
// cross. Small start/stop control drives the watcher process itself. ───────
function LevelCrosses({ maxPerTicker = Infinity }) {
  const [data, setData] = useState(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState(null);

  const load = useCallback(async () => {
    try { setData(await vidura.levelsStatus()); setErr(null); }
    catch (e) { setErr(errText(e)); }
  }, []);

  useEffect(() => {
    load();
    const t = setInterval(load, 30_000);
    return () => clearInterval(t);
  }, [load]);

  const fmtSignal = (s) => {
    let t = s.replace(/^(above|below)_/, '');
    t = t.replace('postmarket', 'PM').replace('yesterday', 'YD');
    return t.toUpperCase();
  };

  const toggle = async () => {
    if (busy) return;
    setBusy(true);
    try {
      if (data?.running) await vidura.levelsStop();
      else await vidura.levelsStart();
      await load();
    } catch (e) { setErr(errText(e)); }
    setBusy(false);
  };

  const snap = data?.status;
  const COLS = ['SPY', 'QQQ', 'SPX'];
  // fresh crosses pulse until acknowledged (any click) or 5 min old
  const crossKeys = useMemo(() => {
    if (!snap?.tickers) return null;
    const keys = [];
    for (const tkr of COLS) {
      const latest = (snap.tickers[tkr] || {}).latest || {};
      for (const [lvl, s] of Object.entries(latest)) keys.push(`${tkr}|${lvl}|${s?.time || ''}|${s?.signal || ''}`);
    }
    return keys;
  }, [snap]);
  const freshCrosses = useNewBlink(crossKeys);
  const cols = COLS.map((tkr) => {
    const t = snap?.tickers?.[tkr] || {};
    const marked = Object.entries(t.levels || {})
      .map(([k, v]) => `${k.replace('yesterday_', 'yd_').replace('postmarket_', 'pm_')} ${v}`)
      .join(' · ');
    // one entry per level, freshest cross wins (the watcher overrides in
    // place) — newest at the top of the column
    const rows = Object.entries(t.latest || {})
      .map(([lvl, s]) => ({ lvl, ...s }))
      .sort((a, b) => (a.time < b.time ? 1 : -1))
      .slice(0, maxPerTicker);
    return { tkr, marked, rows };
  });

  return (
    <div className="tr-levels">
      <div className="tr-levels-head">
        <span className={`dot ${data?.running ? 'on' : ''}`}
          title={data?.running ? `levels_watcher.py running (pid ${data.pid})` : 'watcher not running'} />
        <span className="tr-levels-tag">⚑ LVL CROSS</span>
        {snap?.updated && <span className="tr-levels-ts">{snap.updated.replace(/^\d{4}-/, '').replace(/-/, '/').replace(' ', ' ').replace(/ CST$/, '')}</span>}
        <button type="button" className="tr-chip" onClick={toggle} disabled={busy || !data}>
          {busy ? '…' : data?.running ? '■ stop' : '▶ start'}
        </button>
      </div>
      {err && !snap && <p className="tr-err" style={{ fontSize: 11 }}>⚠ {err}</p>}
      {!err && snap === null && data && (
        <p className="tr-note">no levels snapshot yet — start the watcher</p>
      )}
      {snap?.tickers && (
        <div className="tr-levels-cols tr-mono">
          {cols.map(({ tkr, marked, rows }) => (
            <div key={tkr} className="col">
              <div className="col-head" title={marked ? `${tkr} marked levels (CST): ${marked}` : `${tkr} — waiting for data`}>
                {tkr}
              </div>
              {rows.length === 0 && <p className="none">no crosses yet</p>}
              {rows.map((e) => (
                <p key={e.lvl}
                  className={freshCrosses[`${tkr}|${e.lvl}|${e.time}|${e.signal}`] ? 'tr-newblink' : ''}
                  style={{ color: e.dir === 'LONG' ? 'var(--tr-green)' : 'var(--tr-red)' }}
                  title={`${tkr} ${e.signal} @ ${e.time} CST (${e.dir})`}>
                  {fmtSignal(e.signal)} {e.time}
                </p>
              ))}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}



/* ── error tray ────────────────────────────────────────────────────────────
   Every venue failure lands here — 4xx, 5xx, rejections, and the silent ones
   the panels used to swallow. Trading errors do not time out on their own:
   they stay until dismissed, because an order that did not go through is not
   something to find out about from a toast that already faded. */
function ErrorTray({ errors, onDismiss, onClear }) {
  if (!errors.length) return null;
  return (
    <div className="tr-errtray" role="alert" aria-label="desk errors">
      <div className="tr-errtray-hd">
        <span className="tr-eyebrow" style={{ display: 'inline' }}>
          {errors.length} error{errors.length > 1 ? 's' : ''}
        </span>
        <span className="ml-auto" />
        <button type="button" className="tr-chip" onClick={onClear}>clear all</button>
      </div>
      {errors.map((e) => (
        <div key={e.id} className={`tr-errcard ${e.kind}`}>
          <div className="tr-errcard-top">
            <span className="tr-errbadge">{e.status ?? 'offline'}</span>
            {/* every caller that hit this same fault, on the one card */}
            <span className="tr-errsrc" title={e.sources.join(', ')}>
              {e.sources.length > 3
                ? `${e.sources.slice(0, 3).join(', ')} +${e.sources.length - 3}`
                : e.sources.join(', ')}
            </span>
            <span className="tr-note">{e.at}</span>
            {e.count > 1 && <span className="tr-errcount">x{e.count}</span>}
            <span className="ml-auto" />
            <button type="button" className="tr-errx" onClick={() => onDismiss(e.id)}
              aria-label="dismiss and resume">✕</button>
          </div>
          <div className="tr-errmsg">{e.message}</div>
          {ERR_HINT[e.kind] && <div className="tr-note">{ERR_HINT[e.kind]}</div>}
          {/* the dismiss button is the retry button — say so, or a paused
              desk looks like a broken one */}
          <div className="tr-note">
            {e.sources.length > 1 ? 'those panels have' : 'that panel has'} stopped
            polling — close this to retry
          </div>
        </div>
      ))}
    </div>
  );
}

/* A poll that stops while its error card is up.

   The dismiss button IS the retry button: a blocked poll drops its timer
   entirely, and fires once the moment it is unblocked — so closing the card
   refreshes straight away instead of waiting out the interval. */
function usePolling(fn, everyMs, { enabled = true, blocked = false } = {}) {
  const wasBlocked = useRef(false);
  useEffect(() => {
    if (!enabled) return undefined;
    if (blocked) { wasBlocked.current = true; return undefined; }
    if (wasBlocked.current) { wasBlocked.current = false; fn(); }
    const t = setInterval(fn, everyMs);
    return () => clearInterval(t);
  }, [fn, everyMs, enabled, blocked]);
}

/* Collects desk errors, folding repeats of the same failure into one card
   with a count — a poll that fails every 6s must not bury the screen — and
   pausing the callers that raised it until the card is dismissed. */
function useDeskErrors() {
  const [errors, setErrors] = useState([]);
  const seq = useRef(0);

  // One card per DISTINCT FAULT, not per caller. When the API is down every
  // poller notices the same thing within a second or two — balance, positions,
  // the sweep, options flow, one per chart — and keying by caller filled the
  // tray with ten copies of "Backend unreachable" (user 08/17). A repeat now
  // replaces its card in place: same slot, latest time, the callers that hit
  // it listed on it.
  const push = useCallback((source, e) => {
    const status = errStatus(e);
    const message = errText(e);
    // a venue outcome arrives as plain text, not a failed HTTP call
    const kind = typeof e === 'string' ? 'rejected' : errKind(status);
    const at = new Date().toLocaleTimeString();
    setErrors((prev) => {
      const i = prev.findIndex((x) => x.message === message && x.kind === kind);
      if (i >= 0) {
        const hit = prev[i];
        const next = prev.slice();
        next[i] = {
          ...hit,
          at,
          count: hit.count + 1,
          sources: hit.sources.includes(source) ? hit.sources : [...hit.sources, source],
        };
        return next;                       // replaced, never appended
      }
      seq.current += 1;
      return [{ id: seq.current, sources: [source], message, status, kind, at, count: 1 },
        ...prev].slice(0, 12);
    });
  }, []);

  // Everything a live error is blocking. Polling against a backend that just
  // refused is noise that buries the first, real failure — so the callers on
  // a card stop retrying, and dismissing the card is what resumes them.
  //
  // Derived during render rather than stashed in a ref by an effect: an
  // effect lands AFTER paint, so the render that first shows the error would
  // still read "not blocked" and let one more round of polls go out.
  const blocked = useMemo(
    () => new Set(errors.flatMap((e) => e.sources)), [errors]);
  const isBlocked = useCallback((source) => blocked.has(source), [blocked]);

  const dismiss = useCallback((id) => {
    setErrors((prev) => prev.filter((e) => e.id !== id));
  }, []);
  const clear = useCallback(() => setErrors([]), []);
  return { errors, push, dismiss, clear, isBlocked };
}


/* ── rearrangeable sections ────────────────────────────────────────────────
   Desks are personal: whichever panel you look at most belongs at the top.
   Order is per column and remembered, and an unknown id (a panel added in a
   later build) is appended rather than dropped, so a saved order can never
   make a section disappear.

   Dragging is armed from the grip only — a table full of buttons and inputs
   inside a draggable container is otherwise unusable. */
function useSectionOrder(storageKey, defaultIds) {
  const [order, setOrder] = useState(() => {
    try {
      const saved = JSON.parse(localStorage.getItem(storageKey));
      if (Array.isArray(saved)) {
        const known = saved.filter((id) => defaultIds.includes(id));
        return [...known, ...defaultIds.filter((id) => !known.includes(id))];
      }
    } catch { /* fall through to the shipped order */ }
    return defaultIds;
  });
  const move = useCallback((from, to) => {
    setOrder((prev) => {
      if (from === to) return prev;
      const next = prev.filter((id) => id !== from);
      const at = next.indexOf(to);
      next.splice(at < 0 ? next.length : at, 0, from);
      try { localStorage.setItem(storageKey, JSON.stringify(next)); }
      catch { /* nothing to do */ }
      return next;
    });
  }, [storageKey]);
  const reset = useCallback(() => {
    setOrder(defaultIds);
    try { localStorage.removeItem(storageKey); } catch { /* nothing to do */ }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [storageKey]);
  const dirty = order.join() !== defaultIds.join();
  return { order, move, reset, dirty };
}

function Section({ id, label, drag, variant = '', children }) {
  const [armed, setArmed] = useState(false);
  const isOver = drag.over === id && drag.from && drag.from !== id;
  return (
    <div
      className={`tr-sec ${variant} ${drag.from === id ? 'dragging' : ''} ${isOver ? 'over' : ''}`}
      draggable={armed}
      onDragStart={(e) => { e.dataTransfer.effectAllowed = 'move'; drag.start(id); }}
      onDragEnd={() => { setArmed(false); drag.end(); }}
      onDragOver={(e) => { e.preventDefault(); drag.hover(id); }}
      onDrop={(e) => { e.preventDefault(); drag.drop(id); }}
    >
      <button type="button" className="tr-grip"
        title={`drag to move ${label}`}
        aria-label={`drag to move ${label}`}
        onMouseDown={() => setArmed(true)}
        onMouseUp={() => setArmed(false)}
        onBlur={() => setArmed(false)}>⠿</button>
      {children}
    </div>
  );
}

function useDrag(move) {
  // The dragged id lives in a ref as well as state: state drives the styling,
  // but `drop` must read the CURRENT id, not the one captured when its
  // handler was bound — dragstart and drop can land in the same batch, and
  // then the closure still says nothing is being dragged.
  const fromRef = useRef(null);
  const [from, setFrom] = useState(null);
  const [over, setOver] = useState(null);
  const reset = () => { fromRef.current = null; setFrom(null); setOver(null); };
  return {
    from,
    over,
    start: (id) => { fromRef.current = id; setFrom(id); },
    hover: setOver,
    end: reset,
    drop: (to) => {
      const id = fromRef.current;
      if (id) move(id, to);
      reset();
    },
  };
}

const COL_STORAGE_KEY = 'tradier.colWidths';

function useColumnResize(defaultLeft = 232, defaultRight = 232) {
  const [left, setLeft] = useState(() => {
    try { const s = JSON.parse(localStorage.getItem(COL_STORAGE_KEY)); return s?.left ?? defaultLeft; } catch { return defaultLeft; }
  });
  const [right, setRight] = useState(() => {
    try { const s = JSON.parse(localStorage.getItem(COL_STORAGE_KEY)); return s?.right ?? defaultRight; } catch { return defaultRight; }
  });
  const [dragging, setDragging] = useState(null);
  const startX = useRef(0);
  const startW = useRef(0);

  const onMouseDown = useCallback((side, e) => {
    e.preventDefault();
    setDragging(side);
    startX.current = e.clientX;
    startW.current = side === 'left' ? left : right;
  }, [left, right]);

  useEffect(() => {
    if (!dragging) return;
    const onMove = (e) => {
      const dx = e.clientX - startX.current;
      const delta = dragging === 'left' ? dx : -dx;
      const next = Math.max(160, Math.min(500, startW.current + delta));
      if (dragging === 'left') setLeft(next);
      else setRight(next);
    };
    const onUp = () => setDragging(null);
    window.addEventListener('mousemove', onMove);
    window.addEventListener('mouseup', onUp);
    return () => {
      window.removeEventListener('mousemove', onMove);
      window.removeEventListener('mouseup', onUp);
    };
  }, [dragging]);

  useEffect(() => {
    if (dragging) return;
    try { localStorage.setItem(COL_STORAGE_KEY, JSON.stringify({ left, right })); } catch {}
  }, [left, right, dragging]);

  return { left, right, dragging, onMouseDown };
}

// statuses a position can still be managed in
const ACTIVE = new Set(['pending', 'open']);

/* ── editable take-profit ──────────────────────────────────────────────────
   Click the target to change it. Committing re-rests the sell on the venue,
   so the exit keeps working whether or not the desk is open. */
function TargetCell({ pos, busy, onSave }) {
  const [editing, setEditing] = useState(false);
  const [val, setVal] = useState('');
  const inputRef = useRef(null);

  const begin = () => {
    setVal(pos.tp_price != null ? pos.tp_price.toFixed(2) : '');
    setEditing(true);
  };
  useEffect(() => {
    if (editing && inputRef.current) inputRef.current.select();
  }, [editing]);

  const commit = async () => {
    const px = parseFloat(val);
    setEditing(false);
    if (!Number.isFinite(px) || px <= 0) return;
    if (pos.tp_price != null && Math.abs(px - pos.tp_price) < 0.005) return;
    await onSave(px);
  };

  if (busy) return <span className="tr-note">saving…</span>;
  if (editing) {
    return (
      <input ref={inputRef} className="tr-tpinput" type="number" step="0.01" min="0.01"
        value={val} autoFocus
        onChange={(e) => setVal(e.target.value)}
        onBlur={commit}
        onWheel={(e) => e.currentTarget.blur()}
        onKeyDown={(e) => {
          if (e.key === 'Enter') commit();
          if (e.key === 'Escape') { e.stopPropagation(); setEditing(false); }
        }} />
    );
  }
  return (
    <button type="button" className="tr-tpbtn" onClick={begin}
      title="click to move the take-profit — the resting sell is replaced on the venue">
      {pos.tp_price != null ? pos.tp_price.toFixed(2) : '—'}
      <span className="tr-tppen">✎</span>
    </button>
  );
}

// ── auto-trade arm form: strategy / tickers / CST window / sizing ──────────
// Exported with the rest, so another board arms the auto-trader through
// the SAME form and the same knobs rather than a second one that drifts.
const AUTO_DISCOUNT_OPTIONS = [10, 20, 40];

export function AutoTradeForm({ defaults, seed, paper, busy, onArm, onClose }) {
  const [f, setF] = useState({
    strategy: defaults?.strategy || '10min_intraday_move',
    tickers: defaults?.tickers || 'SPY,QQQ,SPX',
    window_open: defaults?.window_open || '08:30',
    window_close: defaults?.window_close || '09:30',
    buy_pct: seed.buy_pct, tolerance_pct: seed.tolerance_pct,
    tp_pct: seed.tp_pct, sl_pct: seed.sl_pct,
    min_contracts: String(defaults?.min_contracts ?? 1),
    delta: seed.delta || '0.12-0.30',
    books: defaults?.books || 'A,B',
    dte_max: String(defaults?.dte_max ?? 6),
    zero_dte_cutoff: defaults?.zero_dte_cutoff || '13:00',
    cooldown_min: String(defaults?.cooldown_min ?? 60),
    top_n: String(defaults?.top_n ?? 3),
  });
  const [market, setMarket] = useState(true);
  const [discount, setDiscount] = useState(10);
  const [zeroDte, setZeroDte] = useState(true);
  const set = (k) => (e) => setF((p) => ({ ...p, [k]: e.target.value }));
  const isHot = f.strategy === 'hot_tickers';
  const isSuperHot = f.strategy === 'super_hot_tickers';
  const isAutoScan = isHot || isSuperHot;

  useEffect(() => {
    if (isHot) {
      setMarket(false); setDiscount(10);
      setF((p) => ({ ...p, delta: '0.30-0.50' }));
    }
    if (isSuperHot) {
      setMarket(false); setDiscount(10);
      setF((p) => ({ ...p, buy_pct: 30, delta: '0.30-0.50' }));
    }
  }, [f.strategy]);

  useEffect(() => {
    const onKey = (e) => { if (e.key === 'Escape') onClose(); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  return (
    <div className="tr-modal-backdrop" onClick={onClose} role="dialog" aria-modal="true"
      aria-label="arm auto-trade">
      <div className="tr-modal tr-panel" onClick={(e) => e.stopPropagation()}>
        <span className="tr-eyebrow mb-3" style={{ display: 'block' }}>arm auto trade</span>
        <div className="tr-modal-grid">
          <div><span className="tr-label">Strategy</span>
            <select className="tr-select" value={f.strategy} onChange={set('strategy')}>
              {(defaults?.strategies || [f.strategy]).map((s) => (
                <option key={s} value={s}>{s}</option>
              ))}
            </select></div>
          <div><span className="tr-label">Tickers</span>
            <input className="tr-input"
              value={isHot ? '(auto from HOT scan)' : isSuperHot ? '(auto from SUPERHOT scan)' : f.tickers}
              onChange={set('tickers')} placeholder="SPY,QQQ,SPX"
              disabled={isAutoScan} style={isAutoScan ? { opacity: 0.45 } : undefined}
              title={isHot ? 'HOT tickers strategy auto-picks from 5min+15min scan intersection'
                : isSuperHot ? 'SUPERHOT strategy auto-picks top N from the superhot scan'
                : undefined} /></div>
          {isSuperHot && (
            <div><span className="tr-label">Top N tickers</span>
              <input className="tr-input" type="number" min="1" max="20" value={f.top_n}
                onWheel={(e) => e.currentTarget.blur()} onChange={set('top_n')}
                title="how many top superhot tickers to trade (ranked by DXS * ADX slope)" /></div>
          )}
          <div><span className="tr-label">Time range (CST)</span>
            <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
              <input className="tr-input" value={f.window_open} onChange={set('window_open')}
                placeholder="08:30" maxLength={5} />
              <span className="tr-note">to</span>
              <input className="tr-input" value={f.window_close} onChange={set('window_close')}
                placeholder="09:30" maxLength={5} />
            </div></div>
          <div><span className="tr-label">Delta range</span>
            <input className="tr-input" value={f.delta}
              onChange={set('delta')} placeholder="0.12-0.30"
              title="delta band for contract selection, e.g. 0.12-0.30" /></div>
          <div><span className="tr-label">Buy % of balance</span>
            <input className="tr-input" type="number" min="1" max="100" value={f.buy_pct}
              onWheel={(e) => e.currentTarget.blur()} onChange={set('buy_pct')}
              title={isSuperHot ? 'per-ticker allocation — e.g. 30% means each of the top N gets 30% of buying power' : undefined} /></div>
          <div><span className="tr-label">Size &plusmn; %</span>
            <input className="tr-input" type="number" min="0" max="100" value={f.tolerance_pct}
              onWheel={(e) => e.currentTarget.blur()} onChange={set('tolerance_pct')}
              title="how far either side of the Buy % budget a total may land - contracts are indivisible, so Buy % is a target rather than a cap (0 makes it a cap)" /></div>
          <div><span className="tr-label">TP % over entry</span>
            <input className="tr-input" type="number" min="1" max="500" value={f.tp_pct}
              onWheel={(e) => e.currentTarget.blur()} onChange={set('tp_pct')} /></div>
          <div><span className="tr-label">SL % below entry</span>
            <input className="tr-input" type="number" min="1" max="99" value={f.sl_pct}
              onWheel={(e) => e.currentTarget.blur()} onChange={set('sl_pct')} /></div>
          <div><span className="tr-label">Min contracts</span>
            <input className="tr-input" type="number" min="1" max="1000" value={f.min_contracts}
              onWheel={(e) => e.currentTarget.blur()} onChange={set('min_contracts')}
              title="the Buy % sizing must reach this many contracts, or the trade is skipped" /></div>
          <div><span className="tr-label">Order type</span>
            <div className="tr-market-toggle">
              <button type="button"
                className={`tr-chip ${market ? 'on' : ''}`}
                onClick={() => setMarket(true)}>MKT</button>
              <button type="button"
                className={`tr-chip ${!market ? 'on' : ''}`}
                onClick={() => setMarket(false)}>LIMIT</button>
            </div>
            {!market && (
              <div className="tr-discount-row">
                {AUTO_DISCOUNT_OPTIONS.map((d) => (
                  <button key={d} type="button"
                    className={`tr-chip sm ${discount === d ? 'on' : ''}`}
                    onClick={() => setDiscount(d)}>
                    −{d}%
                  </button>
                ))}
              </div>
            )}
          </div>
          <div><span className="tr-label">Expiration</span>
            <button type="button" className={`tr-chip tr-0dte ${zeroDte ? 'on' : ''}`}
              aria-pressed={zeroDte} onClick={() => setZeroDte((v) => !v)}
              title={zeroDte
                ? "same-day expiries allowed — the nearest expiry, today included"
                : "same-day expiries skipped — the nearest expiry after today"}>
              0DTE {zeroDte ? 'ON' : 'OFF'}
            </button>
          </div>
        </div>
        <p className="tr-note mt-3">
          {isSuperHot ? (
            <>
              Picks the top {f.top_n} tickers from the SUPERHOT scan (period-9 DMI/ADX,
              directional efficiency, trend acceleration). Each gets a {market ? 'market' : `LIMIT −${discount}%`} buy,
              delta {f.delta}, {f.buy_pct}% of buying power per ticker.
              {!market && ' Unfilled limit orders cancel after 30 min and retry if the signal persists.'}
              {' '}Tickers are auto-discovered — no manual input needed. Each ticker is traded
              at most once per day.
            </>
          ) : isHot ? (
            <>
              Picks tickers appearing in BOTH the 5min and 15min HOT scan lists (strong
              DMI/ADX trend on two time-frames). Each qualifying ticker gets a {market ? 'market' : `LIMIT −${discount}%`} buy,
              delta {f.delta}, using the side (CALL/PUT) from the scan.
              {!market && ' Unfilled limit orders cancel after 30 min and retry if the signal persists.'}
              {' '}Tickers are auto-discovered from the HOT scan — no manual input needed.
              Each ticker is traded at most once per day.
            </>
          ) : (
            <>
              New above_10min_high → CALL / below_10min_low → PUT crosses inside the window,
              confirmed after {Math.round((defaults?.confirm_s ?? 300) / 60)} min, open a managed
              0DTE position sized by Buy % — sized below min contracts, the trade is skipped.
            </>
          )}{' '}
          {paper === false ? 'LIVE account — this spends real money on its own.'
            : 'SANDBOX venue — paper money, real order flow.'}
        </p>
        <div className="mt-4 flex flex-wrap items-center gap-3">
          <button type="button" className="tr-btn sm auto" disabled={busy}
            onClick={() => onArm({ ...f, discount_pct: market ? 0 : discount, zero_dte: zeroDte })}>{busy ? '…' : '🤖 Arm auto-trade'}</button>
          <button type="button" className="tr-btn sm" onClick={onClose}>Cancel</button>
        </div>
      </div>
    </div>
  );
}

// ── SPY 0DTE GEX trend, past 24h — the Super world's hourly net-gamma
// history (08:00–16:00 CST slots) chained oldest → newest ─────────────────
function gexAge(sec) {
  if (sec === null || sec === undefined) return null;
  const min = Math.round(sec / 60);
  if (min < 60) return `${min}m`;
  return `${Math.round(min / 60)}h`;
}

// signed compact dollars, matching the backend's fmt_signed (+4.2B / -820M)
function fmtNet(n) {
  const v = Number(n);
  if (n === null || n === undefined || Number.isNaN(v)) return null;
  const a = Math.abs(v);
  const s = v < 0 ? '-' : '+';
  for (const [cut, suf] of [[1e12, 'T'], [1e9, 'B'], [1e6, 'M'], [1e3, 'K']]) {
    if (a >= cut) return `${s}${a / cut >= 100 ? (a / cut).toFixed(0) : (a / cut).toFixed(1)}${suf}`;
  }
  return `${s}${a.toFixed(0)}`;
}

// the live-update window, on the CHICAGO clock wherever the browser is:
// 08:00 through 15:15 CST — outside it the feed is idle, so polls stop
function gexWindowOpen(now = new Date()) {
  const p = new Intl.DateTimeFormat('en-US', {
    timeZone: 'America/Chicago', hour: '2-digit', minute: '2-digit', hour12: false,
  }).formatToParts(now);
  const g = (t) => Number(p.find((x) => x.type === t)?.value ?? 0);
  const mins = (g('hour') % 24) * 60 + g('minute');
  return mins >= 8 * 60 && mins <= 15 * 60 + 15;
}

const GEX_MINS_KEY = 'tradier.gex.mins';   // browser-cached minute tape
const GEX_MINS_KEEP = 10;                  // the past 10 pushes, no more

function loadGexMins() {
  try {
    const j = JSON.parse(localStorage.getItem(GEX_MINS_KEY));
    if (Array.isArray(j)) {
      const cutoff = Date.now() - 24 * 3600e3;   // same window as the box
      return j.filter((m) => m && m.at && m.text
        && new Date(m.at).getTime() >= cutoff).slice(0, GEX_MINS_KEEP);
    }
  } catch { /* corrupt cache — start clean */ }
  return [];
}

// Exported so another board shows the SAME gamma reading: the same hourly
// history, the same cache, the same formatting. A second implementation
// would eventually disagree with this one about the same number.
export function GexInline() {
  const [slots, setSlots] = useState(null);
  const [live, setLive] = useState(null);
  const [mins, setMins] = useState(loadGexMins);
  const [showHistory, setShowHistory] = useState(false);

  useEffect(() => {
    try { localStorage.setItem(GEX_MINS_KEY, JSON.stringify(mins)); } catch {}
  }, [mins]);

  useEffect(() => {
    let alive = true;
    const cst = (ms) => new Date(ms).toLocaleString('sv-SE', { timeZone: 'America/Chicago' });
    const load = async () => {
      try {
        const today = await vidura.superGex0dteHistory();
        const dates = (await vidura.superGex0dteHistoryDates().catch(() => ({ dates: [] }))).dates || [];
        const prevDate = dates.find((d) => d < today.date);
        const prev = prevDate ? await vidura.superGex0dteHistory(prevDate).catch(() => null) : null;
        if (!alive) return;
        const nowCst = cst(Date.now());
        const cutoff = cst(Date.now() - 24 * 3600e3);
        const captured = [prev, today].filter(Boolean).flatMap((d) =>
          d.hours.filter((h) => h.captured).map((h) => ({
            ...h, date: d.date,
            key: `${d.date} ${String(h.hour_cst).padStart(2, '0')}:00`,
          }))
        ).filter((s) => s.key <= nowCst);
        const within = captured.filter((s) => s.key >= cutoff);
        setSlots(within.length ? within : captured.slice(-9));
      } catch { if (alive) setSlots([]); }
      try {
        const cur = await vidura.superGex0dte();
        if (!alive) return;
        setLive(cur);
        const text = fmtNet(cur?.net_gex);
        if (cur?.fetched_at && text) {
          setMins((prev) => {
            if (prev[0]?.at === cur.fetched_at) return prev;
            const hm = new Date(cur.fetched_at).toLocaleTimeString('en-GB', {
              timeZone: 'America/Chicago', hour: '2-digit', minute: '2-digit',
            });
            return [{ at: cur.fetched_at, hm, text }, ...prev].slice(0, GEX_MINS_KEEP);
          });
        }
      } catch {}
    };
    load();
    const t = setInterval(() => { if (gexWindowOpen()) load(); }, 60_000);
    return () => { alive = false; clearInterval(t); };
  }, []);

  if (!slots || slots.length === 0) return null;
  const liveText = fmtNet(live?.net_gex) ?? slots[slots.length - 1].text;
  const liveNeg = liveText.startsWith('-');
  const age = gexAge(live?.age_seconds);
  return (
    <div className="tr-stat">
      <div className="k">
        SPY 0DTE GEX
        <button type="button" className="tr-gex-toggle"
          onClick={() => setShowHistory((v) => !v)}
          title={showHistory ? 'hide GEX history' : 'show GEX history'}>
          {showHistory ? '▾' : '▸'}
        </button>
      </div>
      <div className="v tr-mono" style={{ color: liveNeg ? 'var(--tr-red)' : 'var(--tr-green)' }}
        title={live ? `${live.regime || '—'} · spot ${live.spot ?? '—'} · flip ${live.flip ?? '—'}` : ''}>
        {liveText}
        {age && <span className="tr-gex-age" style={{ fontSize: '0.65em', marginLeft: 4 }}>({age})</span>}
      </div>
      {showHistory && (
        <div className="tr-gex-hist tr-mono">
          <div className="tr-gex-list">
            {[...slots].reverse().map((s, i) => (
              <span key={s.key} className="row">
                {i > 0 && <span className="sep">&raquo;</span>}
                <span className={`val ${s.sign === 'pos' ? 'pos' : s.sign === 'neg' ? 'neg' : 'flat'}`}
                  title={`${s.date} ${s.label} · net ${s.text} · ${s.regime || '—'}`}>
                  {s.text}
                </span>
              </span>
            ))}
          </div>
          {mins.length > 0 && (
            <div className="tr-gex-mins" title="minute-by-minute pushes">
              {mins.map((m, i) => (
                <span key={m.at} className="row">
                  {i > 0 && <span className="sep">&raquo;</span>}
                  <span className={`val ${m.text.startsWith('-') ? 'neg' : 'pos'}`}
                    title={`${m.hm} CST · net ${m.text}`}>{m.text}</span>
                </span>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ── right rail: A/B super signals from the central ledgers, past 48h ───────
function sigWhen(iso) {
  if (!iso) return '';
  const d = new Date(/Z$|[+-]\d\d:?\d\d$/.test(iso) ? iso : `${iso}Z`);
  return Number.isNaN(d.getTime())
    ? iso
    : d.toLocaleString([], { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' });
}


/* ── options flow: heaviest contracts across the large caps ────────────────
   Served from a background chain sweep, so this polls a snapshot rather than
   waiting on the venue. Open interest is a prior-close figure and cannot
   stream, which is why vol/OI carries the "is this OPENING positions?"
   signal until tomorrow's OI lands and oi_chg becomes real. */
function compactNum(n) {
  const v = Number(n);
  if (!Number.isFinite(v)) return '—';
  if (Math.abs(v) >= 1e6) return `${(v / 1e6).toFixed(1)}M`;
  if (Math.abs(v) >= 1e3) return `${(v / 1e3).toFixed(1)}K`;
  return String(Math.round(v));
}

// Exported with HotScan and MiniChart, for the same reason: one flow board,
// one cached sweep, no second ranking that disagrees with this one.
export function OptionsFlow({ user, live, onPick, onError, onBuy, buying, blocked }) {
  const [snap, setSnap] = useState(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState(null);

  const load = useCallback(async (force = false) => {
    if (!user) return;
    try {
      setSnap(await vidura.tradierFlow(user.user_id, live, force));
      setErr(null);
    } catch (e) { setErr(errText(e)); onError?.('options flow', e); }
  }, [user, live, onError]);

  useEffect(() => { load(); }, [load]);
  // The sweep itself is on a 5-minute TTL server-side; polling faster just
  // picks up a finished refresh sooner.
  usePolling(load, 60_000, { enabled: !!user && isMarketOpen(), blocked });

  const doRefresh = async () => {
    if (busy) return;
    setBusy(true);
    await load(true);
    // the sweep runs in the background — pick the result up shortly after
    setTimeout(() => { load(); setBusy(false); }, 6000);
  };

  const rows = snap?.rows || [];
  const meta = snap?.meta || {};

  return (
    <div className="tr-panel tr-flow mb-4">
      <div className="flex flex-wrap items-center gap-2 mb-2">
        <span className="tr-eyebrow" style={{ display: 'inline' }}>options flow{err && ' ⚠'}</span>
        <span className="tr-note" title="contracts ranked by today's volume across the large-cap universe">
          top {rows.length || ''}
        </span>
        <span className="ml-auto" />
        {(snap?.refreshing || busy) && <span className="tr-note">sweeping…</span>}
        {!snap?.refreshing && !busy && meta.at && (
          <span className="tr-note" title={`${meta.symbols} symbols · ${meta.contracts_seen} contracts · ${meta.took_s}s · ${meta.venue}`}>
            {meta.at}
          </span>
        )}
        <button type="button" className="tr-chip" onClick={doRefresh} disabled={busy}
          title="run the chain sweep now">↻</button>
      </div>

      {err && <p className="tr-err">⚠ {err}</p>}
      {!err && rows.length === 0 && (
        <p className="tr-note">{snap?.refreshing ? 'scanning the chains…' : 'no flow yet'}</p>
      )}

      <div className="tr-flowlist">
        {rows.map((r) => (
          <div key={r.occ_symbol} className="tr-flowrow">
            <div className="l1">
              <button type="button" className="tr-flowsym" onClick={() => onPick?.(r.symbol)}
                onDoubleClick={() => onBuy?.(r)}
                title={`${r.symbol} — tap: chart · double-tap: buy`}>{r.symbol}</button>
              <span className={`tr-flowcp ${r.type}`}>{r.type === 'call' ? 'C' : 'P'}</span>
              <span className="tr-flowstrike">{r.strike}</span>
              <span className="tr-note tr-flowexp">{String(r.expiration || '').slice(5)}</span>
              <span className="ml-auto" />
              <b className="tr-flowvol" title="contracts traded today">{compactNum(r.volume)}</b>
              <button type="button" className="tr-flowbuy"
                disabled={buying === r.occ_symbol}
                onClick={() => onBuy?.(r)}
                title={`buy ${r.occ_symbol} with the desk's Buy% / TP% / SL%`}>
                {buying === r.occ_symbol ? <span className="tr-note">…</span> : 'buy'}
              </button>
            </div>
            <div className="l2 tr-note">
              OI {compactNum(r.open_interest)}
              {r.oi_chg != null && (
                <span style={{ color: r.oi_chg >= 0 ? 'var(--tr-green)' : 'var(--tr-red)' }}>
                  {' '}({r.oi_chg >= 0 ? '+' : ''}{compactNum(r.oi_chg)})
                </span>
              )}
              {r.vol_oi != null && (
                <>
                  {' · '}
                  <span className={r.vol_oi >= 1 ? 'tr-flowhot' : ''}
                    title="volume ÷ open interest — above 1x today's trade exceeds everything already open">
                    {r.vol_oi}x
                  </span>
                </>
              )}
              {r.last != null && <>{' · '}last {Number(r.last).toFixed(2)}</>}
              {(r.low != null || r.high != null) && (
                <span className="tr-flowrange"
                  title="the contract's own low and high today">
                  {'; '}L:{r.low != null ? Number(r.low).toFixed(2) : '—'}
                  {', '}H:{r.high != null ? Number(r.high).toFixed(2) : '—'}
                </span>
              )}
            </div>
          </div>
        ))}
      </div>

      {rows.length > 0 && (
        <p className="tr-note mt-2" style={{ fontSize: 10 }}>
          {meta.oi_baseline_date
            ? `OI change vs ${meta.oi_baseline_date}`
            : 'OI change starts once a prior session is on file — vol/OI meanwhile'}
        </p>
      )}
    </div>
  );
}

// The band the operator wants for signal-driven entries — deliberately
// tighter than the composer's default.
const SIGNAL_DELTA = [0.25, 0.40];

/* The universal power glyph — a ring broken at the top with a stem through
   it, drawn rather than typed so it is crisp at chip size and needs no emoji
   support. Same mark as the Super-Signals world's power button, because it is
   the same action. */
function PowerGlyph() {
  return (
    <svg className="tr-powerglyph" viewBox="0 0 100 100" aria-hidden="true" focusable="false">
      <path d="M28 26a34 34 0 1 0 44 0" />
      <line x1="50" y1="12" x2="50" y2="48" />
    </svg>
  );
}

function SignalRail({ onPick, onBuy, buying }) {
  const [items, setItems] = useState(null);
  const [err, setErr] = useState(null);
  // the signal watcher (super_research supervisors) — same backend action as
  // the Super Signals site's start button, minus the splash theatrics
  const [watcher, setWatcher] = useState(null);   // {live, cats[]} | null
  const [starting, setStarting] = useState(false);
  const [offBusy, setOffBusy] = useState(false);

  const checkWatcher = useCallback(async () => {
    try {
      const st = await vidura.superState();
      const cats = st?.categories || [];
      setWatcher({
        live: cats.some((c) => c.live),
        cats: cats.filter((c) => c.live).map((c) => c.key || c.label || '?'),
      });
    } catch { /* backend down — signals fetch shows the error */ }
  }, []);

  useEffect(() => {
    checkWatcher();
    const t = setInterval(checkWatcher, 60_000);
    return () => clearInterval(t);
  }, [checkWatcher]);

  const startWatcher = async () => {
    if (starting) return;
    setStarting(true);
    try { await vidura.superOn(); } catch (e) { setErr(errText(e)); }
    await checkWatcher();
    setStarting(false);
  };

  // ⏻ off — the Super-Signals world's power-down, reachable from here. Same
  // call, same confirmation, same scope: every category supervisor, not just
  // the ones feeding this rail. The desk could already START the watcher, so
  // being unable to stop it was the asymmetry (user 08/17).
  const stopWatcher = async () => {
    if (offBusy) return;
    const sure = await confirmDialog({
      title: 'Power down the Super-Signals desk?',
      body: 'This stops all category supervisor bots. Workers finish their cycle and exit.',
      notes: watcher?.cats?.length
        ? [`running now: ${watcher.cats.join(', ')}`,
          'the A/B signals on this rail stop updating until it is started again']
        : undefined,
      confirmText: 'Power down',
      tone: 'danger',
    });
    if (!sure) return;
    setOffBusy(true);
    try { await vidura.superOff(); } catch (e) { setErr(errText(e)); }
    await checkWatcher();
    setOffBusy(false);
  };

  useEffect(() => {
    let alive = true;
    const load = async () => {
      try {
        const page = await vidura.superSignals({ days: 2, central: 1, limit: 200 });
        if (!alive) return;
        const cutoff = Date.now() - 48 * 3600 * 1000;
        setItems((page.items || []).filter((s) => {
          if (!s.logged_at) return false;
          const t = new Date(/Z$/.test(s.logged_at) ? s.logged_at : `${s.logged_at}Z`).getTime();
          return t >= cutoff;
        }));
        setErr(null);
      } catch (e) { if (alive) setErr(errText(e)); }
    };
    load();
    const t = setInterval(load, 60_000);
    return () => { alive = false; clearInterval(t); };
  }, []);

  // 48h outcome tally for the header: target / stop / deadline-timeout
  const tally = { target: 0, stop: 0, timeout: 0 };
  for (const s of items || []) {
    const o = s.raw?.outcome;
    if (o in tally) tally[o] += 1;
  }

  // brand-new signals pulse until acknowledged (any click) or 5 min old
  const sigKeys = useMemo(() => (items ? items.map((s) => String(s.id)) : null), [items]);
  const freshSigs = useNewBlink(sigKeys);

  return (
    <div className="tr-panel tr-rail">
      <div className="tr-sighead mb-2">
        <span className="tr-eyebrow" style={{ display: 'inline' }}>signals · 48h</span>
        {watcher && (watcher.live ? (
          <button type="button" className="tr-chip on tr-power"
            style={{ marginRight: 'auto' }}
            onClick={stopWatcher} disabled={offBusy}
            aria-label="Power down the Super-Signals supervisors"
            title={`signal watcher live: ${watcher.cats.join(', ')}`
              + ' — click to power down every category supervisor'}>
            {offBusy ? '…' : <><PowerGlyph /> live</>}
          </button>
        ) : (
          <button type="button" className="tr-chip" style={{ marginRight: 'auto' }}
            onClick={startWatcher} disabled={starting}
            title="start the signal watcher on the backend (same as the Super Signals start button)">
            {starting ? '…' : '▶ start'}
          </button>
        ))}
        {items && items.length > 0 && (
          <span className="tr-sigstats tr-mono"
            title="settled outcomes of the signals below (past 48h): take-profit / stop-loss / timeout">
            <b style={{ color: 'var(--tr-green)' }}>TP: {tally.target}</b>
            <b style={{ color: 'var(--tr-red)' }}>SL: {tally.stop}</b>
            <b style={{ color: 'var(--tr-faint)' }}>TO: {tally.timeout}</b>
          </span>
        )}
      </div>
      {err && !items && <p className="tr-err">⚠ {err}</p>}
      {!err && !items && <p className="tr-note">loading signals…</p>}
      {items && items.length === 0 && <p className="tr-note">no A/B signals in the past 48 hours</p>}
      {items && items.length > 0 && (
        <div className="tr-siglist tr-mono">
          {items.map((s) => {
            const r = s.raw || {};
            const short = (s.direction || '').toUpperCase() === 'SHORT';
            return (
              <div key={s.id}
                className={`tr-sig ${(s.book || '').toLowerCase()} ${freshSigs[String(s.id)] ? 'tr-newblink' : ''}`}>
                <span className="ts">{sigWhen(s.logged_at)}</span>
                <span className="line">
                  <b className={`bk ${(s.book || '').toLowerCase()}`}>{s.book}-book</b>{' '}
                  <b style={{ color: short ? 'var(--tr-red)' : 'var(--tr-green)' }}>
                    {(s.direction || '?').toUpperCase()}
                  </b>{' '}
                  <button type="button" className="tr-tkr"
                    title={`${s.ticker} — live price, pivot points, TradingView`}
                    onClick={() => onPick(s.ticker)}>{s.ticker}</button>
                  {' '}px {px(s.price)} → {px(r.target_price)} / {px(r.stop_price)}{' '}
                  SL/TP ≤{r.stop_deadline_cst || '—'}
                  {r.eng_hot && <span className="hot"> ·{'🔥'.repeat(Math.max(0, Number(r.eng_hot) - 1))}</span>}
                  {r.outcome && (
                    <span className={`oc ${r.outcome}`}> {r.outcome}</span>
                  )}
                </span>
                {onBuy && (
                  <button type="button" className="tr-sigbuy"
                    disabled={!!buying}
                    onClick={() => onBuy(s)}
                    title={`find the ${SIGNAL_DELTA[0]}-${SIGNAL_DELTA[1]} delta `
                      + `${short ? 'put' : 'call'} on ${s.ticker}`}>
                    {buying === s.id ? '…' : 'buy'}
                  </button>
                )}
              </div>
            );
          })}
          <p className="tr-note mt-2">A + B books · merged ledger rows · 60s refresh</p>
        </div>
      )}
    </div>
  );
}

export default function TradierSite() {
  // First: every loader below reports into this tray, and asks it whether it
  // is still allowed to poll. Declared here so the const is initialized before
  // any of them close over isBlocked.
  const { errors: deskErrors, push: pushErr, dismiss: dismissErr,
    clear: clearErrs, isBlocked } = useDeskErrors();
  const [user, setUser] = useState(null);
  const [bal, setBal] = useState(null);
  const [balErr, setBalErr] = useState(null);
  const [positions, setPositions] = useState(null);
  const [filter, setFilter] = useState('active');
  const [venueFilter, setVenueFilter] = useState('all');
  // The desk opens on LIVE (user 08/18). It used to land on the sandbox every
  // reload, on the Kalshi bots' rule that a paper/live mode should never be
  // inherited — but this desk is used live, and starting every session one
  // click away from the wrong account was its own kind of wrong.
  //
  // The reversal is real and worth being plain about: a refresh now arms the
  // production account, and the venue button is red while it is. The one
  // guard kept is below — if this operator has no live keys, or the server is
  // paper-locked, it falls back rather than sitting on a venue it cannot use.
  const [live, setLive] = useState(true);
  const [venueInfo, setVenueInfo] = useState(null);
  const [posAt, setPosAt] = useState(null);
  // one socket for the whole desk: the strip and the charts share it
  const [chartSyms, setChartSyms] = useState(() => Object.fromEntries(
    CHART_SLOTS.map(([slot, fallback]) => [slot, loadChartSymbol(slot, fallback)]),
  ));
  const setChartSym = useCallback((slot, v) => {
    setChartSyms((prev) => ({ ...prev, [slot]: v }));
    saveChartSymbol(slot, v);
  }, []);
  // every tile's symbol rides the one socket
  const chartTickers = useMemo(
    () => [...new Set(Object.values(chartSyms).filter(Boolean))], [chartSyms]);
  const stream = useIndexStream(user, live, chartTickers);
  const movers = useMovers(user, 5);
  const [events, setEvents] = useState([]);
  const [busy, setBusy] = useState(false);
  const [openErr, setOpenErr] = useState(null);

  // market-hours gate: at 15:00 stop auto-trade + levels, at 15:30 stop all polling
  const [marketOffline, setMarketOffline] = useState(false);
  const [showOfflinePopup, setShowOfflinePopup] = useState(false);
  const eodShutdownDone = useRef(false);
  useEffect(() => {
    const check = async () => {
      const cst = new Date(new Date().toLocaleString('en-US', { timeZone: 'America/Chicago' }));
      const hhmm = `${String(cst.getHours()).padStart(2, '0')}:${String(cst.getMinutes()).padStart(2, '0')}`;
      if (hhmm >= '15:00' && !eodShutdownDone.current && user) {
        eodShutdownDone.current = true;
        try { await vidura.autoTradeStop(user.user_id); } catch { /* ignore */ }
        try { await vidura.levelsStop(); } catch { /* ignore */ }
      }
      if (hhmm >= '15:30' && !marketOffline) setShowOfflinePopup(true);
    };
    check();
    const t = setInterval(check, 30_000);
    return () => clearInterval(t);
  }, [marketOffline, user]);

  // composer — the defaults the user specified for the executor
  // The desk's standing risk settings. They used to live in a composer panel
  // that was always on screen; now they ride in the buy ticket, so they are
  // remembered between orders instead of being re-typed. Buy % is a target
  // rather than a cap — contracts are indivisible, so the total is allowed
  // size_tol either side of it, and without that band a contract priced just
  // over the budget sizes to zero and the delta band's own pick never trades.
  const [desk, setDesk] = useState(loadDeskDefaults);
  useEffect(() => {
    try { localStorage.setItem(DESK_KEY, JSON.stringify(desk)); } catch { /* ignore */ }
  }, [desk]);
  // aliases: the auto-trade form and the confirmations read these
  const buyPct = desk.buy_pct;
  const sizeTol = desk.size_tol;
  const deltaRange = desk.delta;
  const tpPct = desk.tp_pct;
  const slPct = desk.sl_pct;
  // ticker clicked in either rail — opens the shared quote + pivots popup
  const [quoteTicker, setQuoteTicker] = useState(null);
  // opening-range auto-trader (backend watcher; survives tab close)
  const [autoST, setAutoST] = useState(null);
  const [autoBusy, setAutoBusy] = useState(false);
  const [autoFormOpen, setAutoFormOpen] = useState(false);
  useEffect(() => {
    if (!user || marketOffline) return undefined;
    let alive = true;
    const poll = () => vidura.autoTradeStatus(user.user_id)
      .then((s) => { if (alive) setAutoST(s); })
      .catch(() => {});
    poll();
    const t = setInterval(poll, 15_000);
    return () => { alive = false; clearInterval(t); };
  }, [user, marketOffline]);

  const toggleAutoTrade = async () => {
    if (!user || autoBusy) return;
    setOpenErr(null);
    if (!autoST?.active) { setAutoFormOpen(true); return; }
    setAutoBusy(true);
    try {
      const ok = await confirmDialog({
        title: 'Disarm the auto-trader?',
        body: 'Stops watching for new signals, and abandons any contract whose '
          + 'bid it is still observing. Positions it already opened stay managed '
          + 'by the desk (TP/SL) as usual.',
        confirmText: 'Disarm', cancelText: 'Keep armed',
      });
      if (ok) setAutoST(await vidura.autoTradeStop(user.user_id));
    } catch (e) { setOpenErr(errText(e)); pushErr('auto-trade', e); }
    setAutoBusy(false);
  };

  const armAutoTrade = async (f) => {
    if (!user || autoBusy) return;
    setAutoBusy(true);
    setOpenErr(null);
    try {
      const [dMin, dMax] = parseDeltaRange(f.delta || deltaRange);
      setAutoST(await vidura.autoTradeStart({
        user_id: user.user_id,
        strategy: f.strategy,
        tickers: f.tickers,
        window_open: f.window_open.trim(),
        window_close: f.window_close.trim(),
        buy_pct: parseFloat(f.buy_pct),
        tolerance_pct: parseFloat(f.tolerance_pct),
        tp_pct: parseFloat(f.tp_pct),
        sl_pct: parseFloat(f.sl_pct),
        min_contracts: parseInt(f.min_contracts, 10) || 1,
        delta_min: dMin, delta_max: dMax,
        books: f.books,
        dte_max: parseInt(f.dte_max, 10),
        zero_dte_cutoff: (f.zero_dte_cutoff || '').trim(),
        cooldown_min: parseInt(f.cooldown_min, 10),
        discount_pct: parseFloat(f.discount_pct) || 0,
        top_n: parseInt(f.top_n, 10) || 3,
        zero_dte: f.zero_dte !== false,
        live,
      }));
      setAutoFormOpen(false);
      showCharm();
    } catch (e) { setOpenErr(errText(e)); pushErr('auto-trade', e); }
    setAutoBusy(false);
  };

  useEffect(() => {
    let alive = true;
    ensureUser().then((u) => { if (alive) setUser(u); }).catch(() => {});
    return () => { alive = false; };
  }, []);

  const loadBalance = useCallback(async (uid, isLive) => {
    try {
      setBal(await vidura.tradierBalance(uid, isLive));
      setBalErr(null);
    } catch (e) { setBalErr(errText(e)); setBal(null); pushErr('balance', e); }
  }, []);

  // which venues this operator actually has keys for — drives the toggle
  useEffect(() => {
    if (!user) return;
    vidura.tradierVenue(user.user_id).then((v) => {
      setVenueInfo(v);
      // The desk opens LIVE, but only where LIVE is actually reachable.
      // Without this it would sit on a venue with no keys, every call 4xx-ing
      // into the error tray, and read as a broken desk rather than a
      // misconfigured one.
      if (!v?.live?.configured || v?.paper_only_server) setLive(false);
    }).catch(() => setVenueInfo(null));
  }, [user]);

  const toggleLive = async () => {
    if (live) { setLive(false); return; }        // stepping back to paper is free
    const acct = venueInfo?.live?.account_id;
    const ok = await confirmDialog({
      title: 'Switch the desk to the LIVE account?',
      body: 'Every order placed while LIVE is on spends real money on the '
        + 'production Tradier account. Balance, chain prices and new orders all '
        + 'move to the production venue.',
      notes: [
        acct ? `Production account ${acct}.` : 'Production credentials from the customer .env.',
        'LIVE is never remembered — reloading the desk returns it to SANDBOX.',
      ],
      confirmText: 'Go LIVE',
      cancelText: 'Stay on sandbox',
    });
    if (ok) setLive(true);
  };

  // one random lucky charm, blessed onto every confirmed trade / new position
  // (one at a time: triggers while a charm is mid-dive are absorbed)
  const [charm, setCharm] = useState(null);
  const showCharm = useCallback(() => {
    const pick = CHARM_IMGS[Math.floor(Math.random() * CHARM_IMGS.length)];
    setCharm((prev) => prev || { src: `/img/lucky-${pick}-alpha.webp`, key: Date.now() });
  }, []);

  // new row in managed positions -> lucky charm dive. Compared by max id
  // within the SAME filter, so switching filters never false-triggers.
  // Tracks both the newest id (new position -> charm) and each row's status,
  // so a fill or an exit lands in the event strip the moment it happens.
  const posSeen = useRef({ filter: null, max: null, statuses: null });
  const loadPositions = useCallback(async (uid, st, vn) => {
    try {
      const page = await vidura.tradierPositions(uid, st, vn, true);
      setPositions(page);
      const items = page.items || [];
      const max = items.reduce((m, p) => Math.max(m, p.id || 0), 0);
      const statuses = Object.fromEntries(items.map((p) => [p.id, p.status]));
      const key = `${st}:${vn}`;
      const prev = posSeen.current;
      if (prev.filter === key) {
        if (prev.max !== null && max > prev.max) showCharm();
        if (prev.statuses) {
          const moved = items
            .filter((p) => prev.statuses[p.id] && prev.statuses[p.id] !== p.status)
            .map((p) => `#${p.id} ${p.occ_symbol} ${prev.statuses[p.id]} → ${p.status}`);
          if (moved.length) setEvents((old) => [...moved, ...old].slice(0, 30));
        }
      }
      posSeen.current = { filter: key, max, statuses };
      setPosAt(Date.now());
    } catch (e) { pushErr('positions', e); }
  }, [showCharm]);

  // sweep + refresh: the sweep runs the SAME monitor pass as the backend
  // loop, so what renders is the venue's current truth, not the last tick
  const refresh = useCallback(async () => {
    if (!user) return;
    try {
      const s = await vidura.tradierSweep(user.user_id);
      if (s?.events?.length) {
        setEvents((old) => [...s.events, ...old].slice(0, 30));
        // venue outcomes that are failures, not progress
        s.events
          .filter((ev) => /reject|expired|venue error|failed|cancell?ed/i.test(ev))
          .forEach((ev) => pushErr('venue', ev));
      }
    } catch (e) { pushErr('sweep', e); }
    loadBalance(user.user_id, live);
    loadPositions(user.user_id, filter, venueFilter);
  }, [user, filter, venueFilter, live, loadBalance, loadPositions]);

  useEffect(() => { refresh(); }, [refresh]);
  // Two cadences. The heavy pass (sweep + balance) every 30s, and the table
  // itself every 6s so an open, a fill, an exit and the live mark all land
  // without the operator touching anything. The sweep is the expensive half:
  // it places and cancels orders, and the API runs its own monitor loop
  // anyway, so polling the table faster costs one batched quote call.
  // The heavy pass drives three calls, so any one of them failing pauses it —
  // otherwise a dead balance endpoint keeps being asked every 30s while its
  // card sits on screen.
  const deskBlocked = isBlocked('sweep') || isBlocked('balance') || isBlocked('positions');
  usePolling(refresh, 30_000, { enabled: !!user && !marketOffline && isMarketOpen(), blocked: deskBlocked });

  const pollPositions = useCallback(() => {
    if (user) loadPositions(user.user_id, filter, venueFilter);
  }, [user, filter, venueFilter, loadPositions]);
  usePolling(pollPositions, 6_000, {
    enabled: !!user && !marketOffline && isMarketOpen(), blocked: isBlocked('positions'),
  });

  // ── the one buy path ──────────────────────────────────────────────────
  // Every buy control on the desk opens the ticket; the ticket is the only
  // thing that places. Before, each call site built its own order and its own
  // confirmation, which is several places for the risk settings to drift
  // apart from one another.
  const [ticket, setTicket] = useState(null);
  // A rejected buy belongs where the buy was pressed. It used to go to the
  // desk's error tray and the header line — both of which sit BEHIND the
  // open ticket, so the order appeared to do nothing while the reason for it
  // scrolled past out of sight (user 08/18). The tray keeps what it is for:
  // background polls and sweeps, which have nowhere else to surface.
  const [ticketErr, setTicketErr] = useState(null);
  const openTicket = useCallback((t) => {
    setOpenErr(null);
    setTicketErr(null);
    setTicket(t);
  }, []);

  const placeTicket = async (t) => {
    if (!user || busy) return;
    setBusy(true);
    setOpenErr(null);
    try {
      const common = {
        user_id: user.user_id,
        live,
        buy_pct: parseFloat(t.buy_pct),
        tolerance_pct: parseFloat(t.size_tol),
        tp_pct: parseFloat(t.tp_pct),
        sl_pct: parseFloat(t.sl_pct),
        discount_pct: t.discount_pct || 0,
      };
      if (t.occ_symbol) {
        await vidura.tradierBuyContract({ ...common, occ_symbol: t.occ_symbol });
      } else {
        const [dMin, dMax] = parseDeltaRange(t.delta);
        await vidura.tradierOpen({
          ...common,
          symbol: t.symbol, side: t.side,
          zero_dte: t.zero_dte,
          delta_min: dMin, delta_max: dMax,
        });
      }
      setTicket(null);
      showCharm();
      await refresh();
    } catch (e) {
      // the ticket stays open holding the numbers that were refused, so the
      // fix is one edit away rather than a re-open and a re-type
      setTicketErr(errText(e));
    }
    setBusy(false);
  };

  // rearrangeable panels, per column
  const mainOrder = useSectionOrder('tradier.order.main2',
    ['charts-top', 'positions', 'charts-mid', 'charts-bottom']);
  const railOrder = useSectionOrder('tradier.order.rail2', ['flow']);
  const mainDrag = useDrag(mainOrder.move);
  const railDrag = useDrag(railOrder.move);
  const colResize = useColumnResize(232, 232);
  // Same-day expiries are opt-in and NOT remembered: a 0DTE left armed
  // from yesterday is exactly the trade nobody meant to place.
  const [zeroDte, setZeroDte] = useState(false);
  const [targetBusy, setTargetBusy] = useState(null);
  const saveTarget = async (p, px) => {
    if (!user) return;
    setTargetBusy(p.id);
    setOpenErr(null);
    try {
      await vidura.tradierSetTarget(user.user_id, p.id, px);
      await loadPositions(user.user_id, filter, venueFilter);
    } catch (e) { setOpenErr(errText(e)); pushErr('target', e); }
    setTargetBusy(null);
  };

  // buy a contract straight off the flow board, on the composer's terms
  // HOT: the scan names a ticker and a direction, so the ticket opens on the
  // delta search with that side preselected.
  const buyHot = (r) => {
    const side = (r.sh_side || r.side || 'call') === 'put' ? 'put' : 'call';
    const adx = r.sh_adx ?? r.adx;
    const why = adx != null
      ? `ADX ${Math.round(adx)} · +DI ${r.sh_pdi ?? r.plus_di ?? '—'} / -DI ${r.sh_mdi ?? r.minus_di ?? '—'}`
      : undefined;
    openTicket({ symbol: r.symbol, side, why });
  };

  const buyFlowContract = (r) => openTicket({
    symbol: r.symbol,
    side: r.type === 'put' ? 'put' : 'call',
    occ_symbol: r.occ_symbol,
    why: `${r.type === 'call' ? 'CALL' : 'PUT'} ${r.strike} · today last `
      + `${r.last ?? '—'} · low ${r.low ?? '—'} · high ${r.high ?? '—'}`,
  });

  // A/B signal -> the contract that signal implies. The pick is SHOWN
  // before anything is placed: a delta band is a rule, and the operator
  // still wants to see which strike it landed on.

  const doClose = async (p) => {
    const ok = await confirmDialog({
      title: `Close #${p.id} ${p.occ_symbol}?`,
      body: 'Cancels any resting orders for it and sells the position at market.',
      confirmText: 'Close position', cancelText: 'Keep it',
    });
    if (!ok) return;
    try {
      await vidura.tradierClose(user.user_id, p.id);
      await refresh();
    } catch (e) {
      const msg = errText(e);
      setOpenErr(msg);
      pushErr('close', e);
      // The venue can refuse a cancel while cheerfully serving the same
      // order on GET (Tradier's sandbox 500s on DELETE). On paper that
      // leaves a row nobody can clear, so offer to stop tracking it —
      // never offered on the live account, where an abandoned working
      // order would mean a position nobody is watching.
      if (p.sandbox && p.status === 'pending') {
        const forced = await confirmDialog({
          title: `Stop tracking #${p.id}?`,
          body: 'The venue refused to cancel this order. It is a sandbox '
            + 'paper order, so the desk can stop tracking it — the order may '
            + 'still rest at Tradier until it expires at the close.',
          notes: [msg],
          confirmText: 'Stop tracking', cancelText: 'Leave it',
        });
        if (forced) {
          try {
            await vidura.tradierClose(user.user_id, p.id, true);
            setOpenErr(null);
            await refresh();
          } catch (e2) { setOpenErr(errText(e2)); pushErr('close (force)', e2); }
        }
      }
    }
  };

  const doCarryOver = async (p) => {
    const enabling = !p.carry_over;
    const ok = await confirmDialog({
      title: enabling
        ? `Carry over #${p.id} ${p.occ_symbol}?`
        : `Remove carry-over from #${p.id}?`,
      body: enabling
        ? 'Stop-loss will be removed and the position will NOT be closed at the EOD cut-off. '
          + 'The take-profit order stays active on the venue.'
        : 'SL monitoring and EOD auto-close will be re-enabled for this position.',
      confirmText: enabling ? 'Carry over' : 'Remove carry-over',
      cancelText: 'Cancel',
    });
    if (!ok) return;
    try {
      await vidura.tradierCarryOver(user.user_id, p.id, enabling);
      await refresh();
    } catch (e) { setOpenErr(errText(e)); pushErr('carry-over', e); }
  };

  const items = positions?.items || [];

  return (
    <div className="tr-root">
      <WorldHeader accent="#5b6af0" title="Tradier Platform" showSound={false} />
      <div className="tr-content tr-wide">
        <ErrorTray errors={deskErrors} onDismiss={dismissErr}
          onClear={clearErrs} />

        <header className="mt-8 mb-6 tr-head">
          <div className="tr-head-left">
            <span className="tr-eyebrow">tradier · options executor</span>
            <h1 className="tr-title">Tradier <span className="vio">Options&nbsp;Desk</span><span className="tr-cursor">_</span></h1>
            <p className="mt-2 text-sm" style={{ color: 'var(--tr-dim)', maxWidth: '46rem' }}>
              Every position is managed until it exits.
              {user?.user_root_folder && bal && (
                <span className="tr-mono" style={{ marginLeft: 8, color: 'var(--tr-faint)', fontSize: '11px' }}>
                  {user.user_root_folder.replace(/\\/g, '/').split('/').filter(Boolean).pop()}
                  {bal.account_id ? ` · ${bal.account_id}` : ''}
                </span>
              )}
            </p>
          </div>

          {/* balance — lives in the header's right half so the desk starts
              one full row higher */}
          <div className="tr-panel tr-head-right">
            {bal ? (
              <div className="tr-kv">
                <div className="tr-stat"><div className="k">buying power</div>
                  <div className="v" style={{ color: 'var(--tr-accent-hi)' }}>{usd(bal.option_buying_power)}</div></div>
                <div className="tr-stat"><div className="k">total equity</div>
                  <div className="v">{usd(bal.total_equity)}</div></div>
                <div className="tr-stat"><div className="k">open P&L</div>
                  <div className="v" style={{ color: Number(bal.open_pl) >= 0 ? 'var(--tr-green)' : 'var(--tr-red)' }}>
                    {usd(bal.open_pl)}</div></div>
                {/* Today = realized (close_pl) + unrealized (open_pl). The
                    percent is against what the account was WORTH this
                    morning — equity now already contains the move. */}
                <div className="tr-stat"><div className="k">today P&L</div>
                  {(() => {
                    const fees = Number(bal.fees_today) || 0;
                    const day = Number(bal.day_pl_net ?? bal.day_pl) ;
                    const start = Number(bal.total_equity) - Number(bal.day_pl);
                    const pct = start > 0 ? (day / start) * 100 : null;
                    const col = day > 0 ? 'var(--tr-green)'
                      : day < 0 ? 'var(--tr-red)' : 'var(--tr-faint)';
                    return (
                      <div className="v" style={{ color: col }}
                        title={`realized ${usd(bal.close_pl)} + open ${usd(bal.open_pl)}`
                          + (fees ? ` − fees ${usd(fees)}` : '')
                          + (start > 0 ? ` · from ${usd(start)} at the open` : '')}>
                        {day > 0 ? '+' : ''}{usd(day)}
                        {pct != null && (
                          <span className="tr-daypct">
                            {' '}{pct >= 0 ? '+' : ''}{pct.toFixed(2)}%
                          </span>
                        )}
                        {fees > 0 && (
                          <span className="tr-dayfees"> (−{usd(fees)} fees)</span>
                        )}
                      </div>
                    );
                  })()}
                </div>
                <GexInline />
                <div className="tr-stat">
                  <div className="tr-venuectl">
                    <button type="button"
                      className={`tr-venue-btn ${live ? 'on' : ''}`}
                      onClick={toggleLive} aria-pressed={live}
                      title={live
                        ? 'Trading the PRODUCTION account — click to return to sandbox'
                        : 'Mock orders on the Tradier sandbox — click to arm the live account'}>
                      <span className="tr-venue-dot" />
                      {bal.sandbox ? 'SANDBOX' : 'LIVE'}
                    </button>
                    <button type="button"
                      className={`tr-autobtn ${autoST?.active ? 'on' : ''}`}
                      onClick={toggleAutoTrade} disabled={autoBusy}
                      title={autoST?.active
                        ? 'auto-trader ARMED on this venue — click to open its form'
                        : 'arm the auto-trader on this venue'}>
                      {autoBusy ? '…' : '🤖 AUTO'}
                    </button>
                    <button type="button" className="tr-buybtn"
                      onClick={() => openTicket({ symbol: '' })}
                      title="open manual buy ticket">
                      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>
                      {' '}BUY
                    </button>
                  </div>
                </div>
              </div>
            ) : (
              <div>
                <p className="tr-err">⚠ {balErr || 'connecting to Tradier…'}</p>
                {balErr && /TRADIER/.test(balErr) && (
                  <p className="tr-note mt-1">
                    Add the keys to your customer folder&apos;s <span className="tr-mono">.env</span>:{' '}
                    <span className="tr-mono">TRADIER_SANDBOX_URI/_TOKEN/_ACCOUNT_ID</span> for paper
                    (free at tradier.com developer portal), or the{' '}
                    <span className="tr-mono">TRADIER_PROD_*</span> trio for the real account.
                  </p>
                )}
              </div>
            )}
          </div>
        </header>

        <div className="tr-streamrow">
          {venueInfo && !venueInfo.live?.configured && !live && (
            <span className="tr-note">live keys not configured</span>
          )}
          {venueInfo?.paper_only_server && (
            <span className="tr-note">server paper-locked</span>
          )}
          <StreamStrip stream={stream} movers={movers} onPick={setQuoteTicker} />
        </div>

        <div className={`tr-layout${colResize.dragging ? ' tr-resizing' : ''}`}
          style={{ gridTemplateColumns: `${colResize.left}px 4px minmax(0,1fr) 4px ${colResize.right}px` }}>
        <aside className="tr-col side"
          style={colResize.left > 232 ? { fontSize: `${Math.min(12, 9 * (colResize.left / 232))}px` } : undefined}>
          <HotScan user={user} live={live} onPick={setQuoteTicker}
            onError={pushErr} onBuy={buyHot}
            blocked={isBlocked('hot scan')}
            slotAfterSuperhot={
              <CommoditiesPanel user={user} live={live} onPick={setQuoteTicker}
                onError={pushErr} onBuy={buyHot}
                blocked={isBlocked('commodities')} />
            } />
          <TickerRail user={user} onPick={setQuoteTicker} />
        </aside>
        <div className="tr-resize-handle" onMouseDown={(e) => colResize.onMouseDown('left', e)} />
        <div className="tr-col main">

        {mainOrder.order.map((sid) => {
          if (sid === 'positions') return (
            <Section key="positions" id="positions" label="managed positions" drag={mainDrag}>
        {/* positions */}
        <div className="tr-panel">
          <div className="flex flex-wrap items-center gap-2 mb-3">
            <span className="tr-eyebrow" style={{ display: 'inline' }}>managed positions</span>
            <span className="tr-livedot" title={posAt
              ? `auto-refreshing every 6s · last ${new Date(posAt).toLocaleTimeString()}`
              : 'auto-refreshing every 6s'} />
            <span className="ml-auto" />
            {VENUE_FILTERS.map(([v, label]) => (
              <button key={v} type="button"
                className={`tr-chip ${venueFilter === v ? 'on' : ''} ${v === 'live' ? 'tr-chip-live' : ''}`}
                onClick={() => setVenueFilter(v)}>{label}</button>
            ))}
            <span className="tr-chip-sep" />
            {STATUS_FILTERS.map(([v, label]) => (
              <button key={v} type="button" className={`tr-chip ${filter === v ? 'on' : ''}`}
                onClick={() => setFilter(v)}>{label}</button>
            ))}
            <button type="button" className="tr-chip" onClick={refresh}>↻ sweep now</button>
          </div>
          {/* Venue outcomes, newest first. Dismissing one reveals the next
              rather than clearing the lot: they are separate events, and a
              rejection you have not read yet should not vanish with the one
              you have. */}
          {events.length > 0 && (
            <div className="tr-banner mb-3 tr-mono" style={{ fontSize: 11.5 }}>
              <span style={{ flex: 1 }}>{events[0]}</span>
              {events.length > 1 && (
                <span className="tr-note">+{events.length - 1} more</span>
              )}
              <button type="button" className="tr-errx"
                title={events.length > 1 ? 'dismiss — the next one follows' : 'dismiss'}
                aria-label="dismiss this event"
                onClick={() => setEvents((old) => old.slice(1))}>✕</button>
              {events.length > 1 && (
                <button type="button" className="tr-chip"
                  onClick={() => setEvents([])}>clear all</button>
              )}
            </div>
          )}
          <div className="tr-tablewrap">
            <table className="tr-table">
              <thead><tr>
                <th>#</th><th>venue</th><th>contract</th><th>strategy</th><th>Δ</th><th>qty</th><th>entry</th>
                <th>tp</th><th>sl</th><th>mark</th><th>p&l</th><th>status</th>
                <th>opened</th><th></th>
              </tr></thead>
              <tbody>
                {items.length === 0 && (
                  <tr><td colSpan={14} style={{ color: 'var(--tr-faint)' }}>
                    {positions ? 'no positions under this filter' : 'loading…'}
                  </td></tr>
                )}
                {items.map((p) => (
                  <tr key={p.id}>
                    <td>{p.id}</td>
                    <td>
                      <span className={`tr-venue ${p.sandbox ? 'sbx' : 'live'}`}>
                        {p.sandbox ? 'SANDBOX' : 'LIVE'}
                      </span>
                    </td>
                    <td className="tr-mono" title={p.note || ''}>{p.occ_symbol}</td>
                    <td>
                      <span className={`tr-tag ${p.strategy === 'Manual' ? 'closed' : 'open'}`}>
                        {p.strategy || 'Manual'}
                      </span>
                    </td>
                    <td>{p.delta_at_entry != null ? p.delta_at_entry.toFixed(2) : '—'}</td>
                    {/* the count is the one thing the ± band changes, so it
                        carries the arithmetic that produced it */}
                    <td title={p.sizing
                      ? `${p.contracts} × $${p.sizing.cost_per_contract_usd.toFixed(2)} `
                        + `= $${p.sizing.total_usd.toFixed(2)} against a `
                        + `$${p.sizing.budget_usd.toFixed(2)} budget `
                        + `(±${p.sizing.tolerance_pct}% → $${p.sizing.band_low_usd.toFixed(2)}`
                        + `–$${p.sizing.band_high_usd.toFixed(2)})`
                      : undefined}>{p.contracts}</td>
                    <td title={p.entry_price == null && p.limit_price != null
                      ? `buy working at ${p.limit_price.toFixed(2)} limit — not filled yet`
                      : undefined}>
                      {p.entry_price != null ? p.entry_price.toFixed(2)
                        : p.limit_price != null
                          ? <span className="tr-prov">@{p.limit_price.toFixed(2)}</span>
                          : '—'}</td>
                    {/* TP is editable while the position is live: the target
                        is the thing an operator actually changes mid-trade */}
                    <td className={p.exits_provisional ? 'tr-prov' : ''}
                      title={p.exits_provisional
                        ? 'provisional — computed from the working limit; set on fill'
                        : undefined}>
                      {ACTIVE.has(p.status) ? (
                        <TargetCell pos={p} busy={targetBusy === p.id}
                          onSave={(px) => saveTarget(p, px)} />
                      ) : (p.tp_price != null ? p.tp_price.toFixed(2) : '—')}
                    </td>
                    <td className={p.exits_provisional ? 'tr-prov' : ''}
                      title={p.exits_provisional
                        ? 'provisional — computed from the working limit; set on fill'
                        : undefined}>
                      {p.sl_price != null ? p.sl_price.toFixed(2) : '—'}
                    </td>
                    {/* mark: the exit price once realized, otherwise what the
                        position is worth right now (the bid) */}
                    <td className={p.exit_price == null && p.live_bid != null ? 'tr-livecell' : ''}>
                      {p.exit_price != null ? p.exit_price.toFixed(2)
                        : p.live_bid != null ? p.live_bid.toFixed(2) : '—'}</td>
                    {(() => {
                      const realized = p.pnl_usd != null;
                      const val = realized ? p.pnl_usd : p.live_pnl_usd;
                      return (
                        <td className={!realized && val != null ? 'tr-livecell' : ''}
                          title={realized ? 'realized' : 'unrealized, at the current bid'}
                          style={{ color: val > 0 ? 'var(--tr-green)' : val < 0 ? 'var(--tr-red)' : undefined }}>
                          {val != null ? usd(val) : '—'}</td>
                      );
                    })()}
                    <td><span className={`tr-tag ${p.status}`}>{p.status}</span></td>
                    <td className="tr-note">{when(p.opened_at)}</td>
                    <td style={{ whiteSpace: 'nowrap' }}>
                      {p.status === 'open' && (
                        <button type="button"
                          className={`tr-chip${p.carry_over ? ' on' : ''}`}
                          onClick={() => doCarryOver(p)}
                          title={p.carry_over
                            ? 'Carry-over ON — no SL, no EOD close; TP still active. Click to remove.'
                            : 'Carry over overnight — removes SL and EOD auto-close, keeps TP'}>
                          {p.carry_over ? '🌙 carrying' : '🌙 carry'}
                        </button>
                      )}
                      {(p.status === 'open' || p.status === 'pending') && (
                        <button type="button" className="tr-chip" onClick={() => doClose(p)}>✕ close</button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="tr-note mt-3">
            The take-profit rests on the venue and survives restarts; the stop-loss is the
            API&apos;s 10-second monitor — it cancels the TP before selling, so two sells can
            never stack. Multiple positions run side by side.
          </p>
        </div>
            </Section>
          );
          const chartRange =
            sid === 'charts-top' ? [0, 1] :
            sid === 'charts-mid' ? [1, 5] :
            sid === 'charts-bottom' ? [5, 6] : null;
          if (chartRange) {
            const [fromRow, toRow] = chartRange;
            let idx = CHART_ROWS.slice(0, fromRow).reduce((a, b) => a + b, 0);
            return (
              <Section key={sid} id={sid} label={sid} drag={mainDrag}>
                {CHART_ROWS.slice(fromRow, toRow).map((cols, ri) => {
                  const row = fromRow + ri;
                  const slots = CHART_SLOTS.slice(idx, idx + cols);
                  idx += cols;
                  return (
                    <div key={row} className="tr-chartrow" style={{
                      gridTemplateColumns: `repeat(${cols}, 1fr)` }}>
                      {slots.map(([slot]) => {
                        const sym = chartSyms[slot];
                        if (!sym) return (
                          <div key={slot} className="tr-chart tr-chart-empty">
                            <button type="button" className="tr-chart-add"
                              onClick={() => {
                                const t = prompt('Ticker symbol:');
                                if (t && /^[A-Z0-9.\-]{1,10}$/i.test(t))
                                  setChartSym(slot, t.toUpperCase());
                              }}>+ add ticker</button>
                          </div>
                        );
                        return (
                          <MiniChart key={slot} user={user} live={live} symbol={sym}
                            onSymbol={(v) => setChartSym(slot, v)}
                            stream={stream} onError={pushErr}
                            onBuy={(s) => openTicket({ symbol: s })}
                            blocked={isBlocked(`${sym} bars`)}
                            height={row === 0 ? 200 : 168} />
                        );
                      })}
                    </div>
                  );
                })}
              </Section>
            );
          }
          return null;
        })}
        </div>
        <div className="tr-resize-handle" onMouseDown={(e) => colResize.onMouseDown('right', e)} />
        <aside className="tr-col side"
          style={colResize.right > 232 ? { fontSize: `${Math.min(12, 9 * (colResize.right / 232))}px` } : undefined}>
          <LevelCrosses maxPerTicker={3} />
          {railOrder.order.map((sid) => (sid === 'flow' ? (
            <Section key="flow" id="flow" label="options flow" drag={railDrag}>
              <OptionsFlow user={user} live={live} onPick={setQuoteTicker}
                onError={pushErr} onBuy={buyFlowContract}
                blocked={isBlocked('options flow')} />
            </Section>
          ) : null))}
        </aside>
        </div>

        {(mainOrder.dirty || railOrder.dirty) && (
          <div className="tr-layoutreset">
            <span className="tr-note">panels rearranged</span>
            <button type="button" className="tr-chip"
              onClick={() => { mainOrder.reset(); railOrder.reset(); }}>
              reset layout
            </button>
          </div>
        )}

        {quoteTicker && (
          <QuotePopup ticker={quoteTicker} accent="#5b6af0"
            onClose={() => setQuoteTicker(null)}
            onBuy={(sym, side) => openTicket({ symbol: sym, side })} />
        )}
        <LuckyCharm key={charm?.key} charm={charm} onDone={() => setCharm(null)} />
        {autoFormOpen && (
          <AutoTradeForm
            defaults={autoST?.defaults}
            seed={{ buy_pct: buyPct, tolerance_pct: sizeTol, tp_pct: tpPct, sl_pct: slPct, delta: deltaRange }}
            paper={bal ? bal.sandbox : autoST?.paper}
            busy={autoBusy}
            onArm={armAutoTrade}
            onClose={() => setAutoFormOpen(false)}
          />
        )}
        <BuyTicket open={ticket} desk={desk} onDesk={setDesk} live={live} bal={bal}
          busy={busy} err={ticketErr} onErr={setTicketErr}
          onPlace={placeTicket} onClose={() => { setTicketErr(null); setTicket(null); }} />
        {showOfflinePopup && (
          <div className="tr-modal-backdrop" role="dialog" aria-modal="true"
            aria-label="market offline">
            <div className="tr-modal tr-panel" onClick={(e) => e.stopPropagation()}>
              <span className="tr-eyebrow mb-3" style={{ display: 'block' }}>market closed</span>
              <p className="tr-note" style={{ fontSize: 12, lineHeight: 1.5 }}>
                System is <strong>OFFLINE</strong> — market is closed (after 3:30 PM CST).
                All Tradier API polling has been paused to save resources.
              </p>
              <div className="mt-4 flex flex-wrap items-center gap-3">
                <button type="button" className="tr-btn sm"
                  onClick={() => { setMarketOffline(true); setShowOfflinePopup(false); }}>
                  OK
                </button>
                <button type="button" className="tr-btn sm auto"
                  onClick={() => { setMarketOffline(false); setShowOfflinePopup(false); }}>
                  Stay Online
                </button>
              </div>
            </div>
          </div>
        )}
        {marketOffline && (
          <div className="tr-offline-banner">
            SYSTEM OFFLINE — market closed
            <button type="button" className="tr-chip" style={{ marginLeft: 8 }}
              onClick={() => setMarketOffline(false)}>
              Go Online
            </button>
          </div>
        )}
        <SiteFooter />
      </div>
    </div>
  );
}
