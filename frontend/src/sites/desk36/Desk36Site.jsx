import React, {
  useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState,
} from 'react';
import { Link } from 'react-router-dom';
import { api, auth, ensureUser, vidura } from '../../shared/viduraApi.js';
import QuotePopup from '../../shared/QuotePopup.jsx';
import {
  AutoTradeForm, CommoditiesPanel, HotScan, MiniChart, OptionsFlow, useMovers,
} from '../tradier/TradierSite.jsx';
import '../../shared/quotePopup.css';
import './desk36.css';

// 36 Trade Desk — the market snapshot board.
//
// One diverging bar per ticker: green right for up, red left for down, every
// row sharing a centre spine so the symbols line up and the eye can read the
// column as a single distribution rather than fourteen separate widths.
//
// Nothing here re-implements the desk. Quotes come from /tradier/quotes, the
// contract preview from /tradier/chain and the order from POST
// /tradier/positions — the same three calls the Tradier desk makes, so a
// trade placed here is the same trade with the same TP/SL management.
// The only new endpoint is /desk36/dmi, which exists because the HOT scan
// only reports names inside its own top-100 universe and this board shows
// whatever the operator typed.

// MAIN is the pair that is always on screen and cannot be removed or
// renamed; everything after it is the watchlist, which is yours to edit.
const LOCKED = ['SPY', 'QQQ'];
// Order matters and it is append-only: a ticker added to the board goes on
// the END, never into the middle. IWM and USO were spliced in at positions
// three and four when they were introduced, which put them somewhere
// different from where the same two land for anyone who already had a saved
// list — the board read differently depending on when you first opened it.
const DEFAULT_EXTRA = ['SPX', 'VIX', 'SMH', 'GLD', 'TSLA', 'AAPL', 'MSFT',
  'NVDA', 'LLY', 'AMZN', 'IWM', 'USO'];
const STORE_KEY = 'desk36.tickers.v2';
const STORE_KEY_V1 = 'desk36.tickers';
const MAX_TICKERS = 24;

const QUOTE_MS = 15000;      // prices move constantly
const DMI_MS = 300000;       // a DMI reading cannot change until a bar closes

// How long a source has to be failing CONTINUOUSLY before the board says so.
// A poller that fails once has not failed: the API restarts, a tunnel
// hiccups, a phone changes network. Printing that immediately put an error
// over the board every few minutes, and doing it while someone is filling in
// an order ticket is noise at the worst possible moment.
const FAIL_GRACE_MS = 5 * 60 * 1000;
// The desk panels report failures but never recoveries, so a clock that stops
// being fed IS the recovery. Three minutes is longer than any of their poll
// intervals (charts 60s, hot 60s, flow 60s, positions 20s).
const RECOVERED_MS = 3 * 60 * 1000;

// The desk's own ladder, kept identical so the two tickets offer the same
// rungs. The backend caps discount_pct at 50.
const DISCOUNT_OPTIONS = [5, 10, 20, 40];

const VENUE_KEY = 'desk36.venue';
// The venue survives a refresh, because forgetting it silently is how a paper
// order becomes a real one. Nothing stored means this browser has never opened
// the board, and that first load is LIVE.
const loadVenue = () => {
  try {
    const v = localStorage.getItem(VENUE_KEY);
    if (v === 'paper') return false;
    if (v === 'live') return true;
  } catch { /* private mode */ }
  return true;
};
const saveVenue = (live) => {
  try { localStorage.setItem(VENUE_KEY, live ? 'live' : 'paper'); } catch { /* ignore */ }
};

// MiniChart remembers its granularity per symbol under this key and falls
// back to 15m. On this board the tiles open at 5m: fourteen of them at once
// is a scan, and 5m is the resolution a scan is read at.
//
// Two rules, because "default" has to mean both things. A one-time pass moves
// every tile on a board that already exists; after that only a symbol with no
// remembered choice is seeded, so a tile deliberately switched to 1m or 15m
// stays where it was put.
const CHART_IV_KEY = 'tradier.chart.interval';   // + '.SYMBOL', MiniChart's own
const CHART_5M_FLAG = 'desk36.chart5m.v1';
const seedChartIntervals = (symbols) => {
  try {
    const first = localStorage.getItem(CHART_5M_FLAG) !== '1';
    symbols.forEach((sym) => {
      const k = `${CHART_IV_KEY}.${sym}`;
      if (first || !localStorage.getItem(k)) localStorage.setItem(k, '5min');
    });
    if (first) localStorage.setItem(CHART_5M_FLAG, '1');
  } catch { /* private mode: the tiles open at their own default */ }
};

// Everything that can reach the screen goes through here first.
//
// FastAPI answers a validation failure with a LIST OF OBJECTS, not a string:
// detail = [{type, loc, msg, input, ctx}]. Dropping that straight into JSX
// throws "objects are not valid as a React child", which is not a caught
// error -- it unmounts the whole board and leaves a blank page. Typing the
// leading 0 of "0.35" into the delta field did exactly that, because 0 fails
// the endpoint's own gt=0 guard.
const errMsg = (e) => {
  const raw = typeof e === 'string' ? e : (e?.detail ?? e?.message ?? e);
  const one = (x) => {
    if (x == null) return '';
    if (typeof x === 'string') return x;
    if (typeof x === 'object') return x.msg || x.detail || x.message || JSON.stringify(x);
    return String(x);
  };
  const out = Array.isArray(raw) ? raw.map(one).filter(Boolean).join('; ') : one(raw);
  return out.slice(0, 200);
};

/* The desk's panels, memoised.
 *
 * Each of them builds its fetcher with useCallback over a dependency list
 * that ENDS IN onError, and then runs it from an effect keyed on that
 * fetcher; MiniChart's copy blanks the tile first. An inline arrow passed as
 * onError is a new function on every parent render, so a quote tick every
 * fifteen seconds re-armed all four: fourteen charts blanked and refetched,
 * the hot scan restarted, the flow board restarted, the positions poll lost
 * its timer. That is the board reloading itself under an open order ticket.
 * Stable callbacks stop the refetch and memo stops the render.
 */
const Chart = React.memo(MiniChart);
const Hot = React.memo(HotScan);
const Commodities = React.memo(CommoditiesPanel);
const Flow = React.memo(OptionsFlow);

// One tile. Renaming is per-symbol, so that handler has to be per-symbol too
// — this is where the closure gets a stable identity, instead of the grid
// minting fourteen new ones on every render.
const ChartCell = React.memo(function ChartCell(
  { user, live, sym, blocked, onRename, onError, onBuy },
) {
  const rename = useCallback((next) => onRename(sym, next), [sym, onRename]);
  return (
    <Chart user={user} live={live} symbol={sym} blocked={blocked}
      onSymbol={rename} onError={onError} onBuy={onBuy} height={170} />
  );
});

// Tickers added to the board after people already had a saved list, with
// the flag that marks each batch as applied. Adding to DEFAULT_EXTRA alone
// would not reach them: an existing list never falls through to the
// defaults. The flag is what stops a ticker the operator later removes from
// reappearing on every load.
const ADDITIONS = [{ flag: 'desk36.added.iwm_uso', symbols: ['IWM', 'USO'] }];

// The board's running order, and the order of the tabs that filter it —
// one list so the two can never disagree.
const SECTIONS = [
  ['main', 'main'],
  ['watch', 'watchlist'],
  ['positions', 'positions'],
  ['commodities', 'commodities'],
  ['hot', 'hot'],
  ['charts', 'charts'],
  ['flow', 'contracts'],
  ['top5', 'top 5'],
];

function applyAdditions(list) {
  let out = list;
  ADDITIONS.forEach(({ flag, symbols }) => {
    try {
      if (localStorage.getItem(flag)) return;
      out = [...out, ...symbols.filter((s) => !out.includes(s))];
      localStorage.setItem(flag, '1');
    } catch { /* private mode: the board still works, just without the add */ }
  });
  return out.slice(0, MAX_TICKERS);
}

function loadTickers() {
  try {
    const raw = JSON.parse(localStorage.getItem(STORE_KEY));
    if (Array.isArray(raw) && raw.length) {
      // MAIN is prepended unconditionally: a stored list from an older build
      // (or a hand-edited one) must never be able to drop it.
      const extra = raw.filter((t) => !LOCKED.includes(t));
      return applyAdditions([...LOCKED, ...extra]);
    }
  } catch { /* fall through */ }

  // One-time migration. v1 locked four tickers, so SPX and VIX were never
  // written into the stored list — reading a v1 list under the new rules
  // would silently lose them. Rebuild instead: MAIN, then the two that were
  // locked, then whatever else was on the board.
  try {
    const old = JSON.parse(localStorage.getItem(STORE_KEY_V1));
    if (Array.isArray(old) && old.length) {
      const kept = old.filter((t) => !LOCKED.includes(t) && t !== 'SPX' && t !== 'VIX');
      return applyAdditions([...LOCKED, 'SPX', 'VIX', ...kept]);
    }
  } catch { /* fall through to the default board */ }

  return [...LOCKED, ...DEFAULT_EXTRA];
}

function saveTickers(list) {
  try { localStorage.setItem(STORE_KEY, JSON.stringify(list)); } catch { /* ignore */ }
}

// IBM Plex Mono's advance width, in ems. Measured against the live board:
// a 13-character label at 11px renders 84.4px wide -> 84.4/(13*11) = 0.59.
const ADVANCE = 0.6;

// Compact money for the header: $68.53, $1.2K, $468K. Buying power can run
// to six figures, and the full number would not fit beside the title.
const usd = (v) => {
  if (v == null || !Number.isFinite(v)) return '—';
  const a = Math.abs(v);
  if (a >= 1e6) return `$${(v / 1e6).toFixed(2)}M`;
  if (a >= 1e4) return `$${(v / 1e3).toFixed(1)}K`;
  return `$${v.toFixed(2)}`;
};

const fmtMoney = (v) => `${v >= 0 ? '+' : '-'}$${Math.abs(v).toFixed(2)}`;
const fmtPct = (v) => `${v >= 0 ? '+' : ''}${v.toFixed(2)}%`;

/** Shrink a bar's label until it fits, and report when even the floor does not.
 *
 * Measured rather than estimated: the label is proportional-width digits in a
 * monospace face at a size that changes per row, so no character-count rule
 * gets this right. ResizeObserver re-runs it on rotation and on every width
 * change, which is what makes the board survive an iPhone turning sideways.
 */
function useFitText(text, { max = 11, min = 7 } = {}) {
  const boxRef = useRef(null);
  const textRef = useRef(null);
  const [size, setSize] = useState(max);
  const [fits, setFits] = useState(true);

  useLayoutEffect(() => {
    const box = boxRef.current;
    const el = textRef.current;
    if (!box || !el) return undefined;

    // Derived, not measured. Measuring the text meant reading its width
    // while the bar was still animating toward its final width, so the
    // answer was computed against a box that no longer existed by the time
    // it was applied — labels stayed at 11px inside a 79px bar.
    //
    // The label is monospace, which makes the width exactly
    // chars x ADVANCE x fontSize, so the size that fits can be solved for
    // directly from the ONE thing that has to be read from layout: how much
    // room the bar actually has. No second measurement, nothing to race.
    const measure = () => {
      const cs = getComputedStyle(box);
      const avail = box.clientWidth
        - parseFloat(cs.paddingLeft) - parseFloat(cs.paddingRight);
      if (!Number.isFinite(avail) || avail <= 0) { setFits(false); return; }

      const chars = text.length || 1;
      // A pixel of slack. ADVANCE is accurate to about half a percent, and a
      // measurement can still be read a frame before the width settles, so
      // sizing to the exact available width leaves a label one rounding
      // error away from being clipped. One pixel here is invisible and makes
      // the fit hold through rotation and resize.
      const ideal = Math.max(0, avail - 1) / (chars * ADVANCE);
      // Half-pixel steps: whole pixels waste up to 9% of the width at these
      // sizes, and WebKit renders fractional sizes cleanly.
      const stepped = Math.floor(Math.min(max, ideal) * 2) / 2;
      setSize(Math.max(min, stepped));
      setFits(stepped >= min);
    };

    measure();
    const ro = new ResizeObserver(measure);
    ro.observe(box);

    // The bar animates its width, and ResizeObserver's callbacks land DURING
    // that animation — the last one can arrive a frame before the final
    // width, which is how labels ended up clipped again after a rotation or
    // a window resize. transitionend is the only signal that the width has
    // actually settled, so it gets the final say.
    const settle = (e) => { if (!e || e.propertyName === 'width') measure(); };
    box.addEventListener('transitionend', settle);

    // Belt and braces on the viewport. ResizeObserver is the right tool and
    // usually the only one that fires, but it did NOT fire for these bars
    // when the viewport itself changed size — the bar resized and the label
    // kept its old font, clipped. window resize and orientationchange always
    // fire, and measure() is idempotent, so the overlap costs nothing.
    const onViewport = () => {
      measure();
      // Once more after the width transition has had time to land.
      setTimeout(measure, 400);
    };
    window.addEventListener('resize', onViewport);
    window.addEventListener('orientationchange', onViewport);

    return () => {
      ro.disconnect();
      box.removeEventListener('transitionend', settle);
      window.removeEventListener('resize', onViewport);
      window.removeEventListener('orientationchange', onViewport);
    };
  }, [text, max, min]);

  return { boxRef, textRef, size, fits };
}

// SPY 0DTE net gamma, hour by hour, newest first and reading backwards in
// time to the right. It rides on the SPY row because that is whose gamma it
// is — a market-wide number repeated on fourteen rows would say nothing new
// thirteen times.
const GEX_HOURS = 8;

const fmtGex = (v) => {
  if (v == null || !Number.isFinite(v)) return '—';
  const a = Math.abs(v);
  const sign = v >= 0 ? '+' : '-';
  if (a >= 1e9) return `${sign}${(a / 1e9).toFixed(1)}B`;
  if (a >= 1e6) return `${sign}${Math.round(a / 1e6)}M`;
  return `${sign}${Math.round(a / 1e3)}K`;
};

function useGexSeries() {
  const [state, setState] = useState({ rows: [], date: null, stale: false });

  useEffect(() => {
    let dead = false;

    const captured = (d) => (d?.hours || [])
      .filter((h) => h.captured && Number.isFinite(h.net_gex))
      .sort((a, b) => b.hour_cst - a.hour_cst)       // newest first
      .slice(0, GEX_HOURS);

    const pull = async () => {
      try {
        const today = await vidura.superGex0dteHistory();
        let rows = captured(today);
        let date = today?.date || null;
        let stale = false;

        // Nothing today yet. That is the normal state before the market
        // opens, and every day until the getgamma pusher has run — showing
        // an empty space then reads as a bug rather than as "no data yet",
        // so the last session with data is shown instead, labelled.
        if (rows.length === 0) {
          const { dates = [] } = await vidura.superGex0dteHistoryDates()
            .catch(() => ({ dates: [] }));
          const prev = dates.find((d) => d !== date);
          if (prev) {
            const back = await vidura.superGex0dteHistory(prev).catch(() => null);
            const backRows = captured(back);
            if (backRows.length) { rows = backRows; date = prev; stale = true; }
          }
        }
        if (!dead) setState({ rows, date, stale });
      } catch { /* the row simply carries no gamma strip */ }
    };

    pull();
    // A slot fills once an hour, so there is nothing to gain from asking
    // more often than that.
    const id = setInterval(pull, 10 * 60 * 1000);
    return () => { dead = true; clearInterval(id); };
  }, []);

  return state;
}

function GexStrip({ series, date, stale }) {
  // Say so rather than showing a gap: an empty space where a number lives
  // is indistinguishable from something being broken.
  if (!series.length) {
    return (
      <span className="d36-gexstrip"
        title="No 0DTE gamma captured yet. Run the getgamma bookmarklet to push today's.">
        <span className="d36-gexnone">gex — no data yet</span>
      </span>
    );
  }
  return (
    <span className="d36-gexstrip"
      title={`SPY 0DTE net gamma, newest first, one value per hour (CST)`
        + (date ? ` · ${date}` : '')
        + (stale ? ' · last session, nothing pushed today yet' : '')}>
      {stale && <span className="d36-gexstale">{date?.slice(5)}</span>}
      {series.map((h, i) => (
        <React.Fragment key={h.hour_cst}>
          {i > 0 && <span className="d36-gexarrow">←</span>}
          {/* The current reading is at full size and every earlier one is
              at 60% of it — one step, not a gradient. The history reads as
              a single band the eye can scan across, rather than eight
              values each asking to be weighed differently. */}
          <span className={`d36-gexv ${h.net_gex >= 0 ? 'up' : 'down'} ${i === 0 ? 'now' : 'prev'}`}
            title={`${String(h.hour_cst).padStart(2, '0')}:00 CST`}>
            {fmtGex(h.net_gex)}
          </span>
        </React.Fragment>
      ))}
    </span>
  );
}

function DiReadout({ r }) {
  if (!r || r.plus_di == null) return <span className="d36-di" />;
  const strong = r.adx >= 34;
  return (
    <span className={`d36-di ${strong ? 'strong' : ''}`}
      title={`Wilder DMI · +DI ${r.plus_di} · ADX ${r.adx} · -DI ${r.minus_di}`}>
      <span className="pdi">+DI<b> {r.plus_di.toFixed(0)}</b></span>
      <span className="adx">ADX<b> {r.adx.toFixed(0)}</b></span>
      <span className="mdi">-DI<b> {r.minus_di.toFixed(0)}</b></span>
    </span>
  );
}

// Monospace, so a character count is an exact width rather than a guess:
// IBM Plex Mono advances 0.6em. This is the floor a bar may not shrink below,
// because the label lives inside it.
const MIN_FONT = 7;
const CHAR_W = MIN_FONT * ADVANCE;
const BAR_PAD = 12;
const minBarPx = (label) => Math.ceil(label.length * CHAR_W) + BAR_PAD;

function Bar({ pct, label, dir, scale }) {
  const { boxRef, textRef, size, fits } = useFitText(label);
  if (pct == null) return <span className="d36-di" />;
  // Grow from "just fits the label" to the full field, so one outlier (VIX on
  // a spike day) cannot flatten every other bar to an unreadable stub. calc
  // does the mixing, so nothing has to measure the container in JS.
  const floor = minBarPx(label);
  const width = `calc(${floor}px + (100% - ${floor}px) * ${scale.toFixed(4)})`;
  return (
    <>
      {/* Outside-the-bar fallback, on the far side so it never overlaps the
          symbol column. */}
      {!fits && dir === 'down' && (
        <span className={`d36-out down`} style={{ fontSize: 8 }}>{label}</span>
      )}
      <span ref={boxRef} className={`d36-bar ${dir}`} style={{ width }}>
        <span ref={textRef} className="d36-bar-label"
          style={{ fontSize: size, visibility: fits ? 'visible' : 'hidden' }}>
          {label}
        </span>
      </span>
      {!fits && dir === 'up' && (
        <span className={`d36-out up`} style={{ fontSize: 8 }}>{label}</span>
      )}
    </>
  );
}

function BuySheet({ user, symbol: initialSymbol, side: initialSide, live, onClose, onDone }) {
  // Opened from a row it already knows the ticker; opened from the header's
  // BUY it does not, so the ticket asks.
  // Coerced, not trusted. The board normalises what the panels hand it, but
  // this is the value that gets rendered as a child and a non-string here
  // blanks the page rather than showing a wrong ticket -- so it is worth the
  // belt as well as the braces.
  const [symbol, setSymbol] = useState(() => String(initialSymbol || ''));
  const [side, setSide] = useState(initialSide === 'put' ? 'put' : 'call');
  const [pick, setPick] = useState(null);
  // The ticket keeps its OWN error. A refused order belongs beside the
  // button that would place it again, not in the board's tray at the top of
  // a page you would have to scroll to.
  const [err, setErr] = useState('');
  const [busy, setBusy] = useState(false);
  const [f, setF] = useState({ buy_pct: 50, delta_min: 0.25, delta_max: 0.5, tp_pct: 15, sl_pct: 30 });
  // Same-day expiries are off unless they are asked for, every time the
  // ticket opens. 0DTE is not a preference to remember, it is a decision to
  // take on the trade in front of you — and the backend defaults zero_dte
  // false on both /tradier/chain and POST /tradier/positions, so this asks
  // for them rather than being the only thing preventing them.
  const [zeroDte, setZeroDte] = useState(false);
  // Market, or a limit below it. discount_pct = 0 IS the market order as far
  // as the backend is concerned -- it rests a smart_limit at the going price.
  // Anything above 0 becomes a limit at market x (1 - pct/100) which the
  // server cancels after fifteen minutes if it has not filled. Ten is the
  // rung the desk preselects, so switching to LIMIT lands on something
  // sensible rather than on nothing.
  const [market, setMarket] = useState(true);
  const [discount, setDiscount] = useState(10);
  const [midDayWarn, setMidDayWarn] = useState(false);

  // Prefill from the desk's own configured defaults rather than hard-coding a
  // second set that could drift from the one the auto-traders use.
  useEffect(() => {
    let dead = false;
    vidura.autoTradeStatus(user.user_id).then((s) => {
      const d = s?.defaults;
      if (dead || !d) return;
      setF((p) => ({
        ...p,
        buy_pct: d.buy_pct ?? p.buy_pct,
        tp_pct: d.tp_pct ?? p.tp_pct,
        sl_pct: d.sl_pct ?? p.sl_pct,
      }));
    }).catch(() => { /* defaults above are fine */ });
    return () => { dead = true; };
  }, [user.user_id]);

  // A delta band is typed one character at a time, and most of those
  // intermediate values are not a band: clearing the field and typing the
  // leading 0 of "0.35" asks for delta_min=0, which the endpoint refuses
  // (gt=0). So the ticket works out whether it has something askable before
  // it asks, rather than sending every keystroke and rendering whatever
  // comes back.
  const bandInput = useMemo(() => {
    const rawLo = String(f.delta_min ?? '').trim();
    const rawHi = String(f.delta_max ?? '').trim();
    if (!rawLo || !rawHi) return null;
    const lo = Number(rawLo);
    const hi = Number(rawHi);
    if (!Number.isFinite(lo) || !Number.isFinite(hi)) return null;
    if (!(lo > 0 && hi <= 1 && lo <= hi)) return null;
    return { lo, hi };
  }, [f.delta_min, f.delta_max]);

  // Which contract this would actually buy, before it is bought.
  useEffect(() => {
    if (!symbol) { setPick(null); return undefined; }
    if (!bandInput) {
      setPick(null);
      setErr('delta band must be between 0 and 1, lower value first');
      return undefined;
    }
    let dead = false;
    setPick(null); setErr('');
    // Debounced, so a four-character delta is one request rather than four.
    const id = setTimeout(() => {
      vidura.tradierChain(user.user_id, {
        symbol, side, delta_min: bandInput.lo, delta_max: bandInput.hi, live,
        zero_dte: zeroDte,
      }).then((r) => { if (!dead) setPick(r); })
        .catch((e) => { if (!dead) setErr(errMsg(e) || 'no contract in that delta band'); });
    }, 350);
    return () => { dead = true; clearTimeout(id); };
  }, [user.user_id, symbol, side, bandInput, live, zeroDte]);

  // iOS keeps scrolling the page behind a fixed overlay; freezing the body is
  // the only reliable way to stop it there.
  useEffect(() => {
    const prev = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => { document.body.style.overflow = prev; };
  }, []);

  // Escape is the keyboard way out, since the backdrop no longer is one.
  useEffect(() => {
    const onKey = (e) => { if (e.key === 'Escape') onClose(); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  const isMidDay = () => {
    const now = new Date();
    const cst = new Date(now.toLocaleString('en-US', { timeZone: 'America/Chicago' }));
    return cst.getHours() * 60 + cst.getMinutes() >= 675; // 11:15 AM = 675
  };

  const doSubmit = async () => {
    setBusy(true); setErr('');
    try {
      const row = await vidura.tradierOpen({
        user_id: user.user_id, symbol, side, live, zero_dte: zeroDte,
        discount_pct: market ? 0 : discount,
        buy_pct: Number(f.buy_pct),
        delta_min: bandInput.lo, delta_max: bandInput.hi,
        tp_pct: Number(f.tp_pct), sl_pct: Number(f.sl_pct),
      });
      onDone(`${side.toUpperCase()} ${symbol} · ${row.contracts ?? ''} contract(s) · ${row.status}`);
      onClose();
    } catch (e) {
      setErr(errMsg(e) || 'order refused');
    } finally {
      setBusy(false);
    }
  };

  const submit = () => {
    if (isMidDay() && !midDayWarn) { setMidDayWarn(true); return; }
    setMidDayWarn(false);
    doSubmit();
  };

  // /tradier/chain returns `pick` as the chosen OCC symbol and `band` as the
  // candidates it was chosen from; the strike, delta and quote live on the
  // band row, not at the top level.
  const chosen = useMemo(
    () => (pick?.band || []).find((c) => c.occ_symbol === pick.pick) || null,
    [pick],
  );

  const num = (k, label, step) => (
    <div className="d36-fld">
      <label htmlFor={`d36-${k}`}>{label}</label>
      <input id={`d36-${k}`} type="number" inputMode="decimal" step={step}
        value={f[k]} onChange={(e) => setF({ ...f, [k]: e.target.value })} />
    </div>
  );

  return (
    // A tap on the backdrop does NOT close this one. Every other overlay on
    // the board is a view; this is a half-filled order, and the sections
    // behind it were relaying out underneath while it was open, which turned
    // a mistimed tap into a lost ticket. The x and Escape close it.
    <div className="d36-scrim">
      <div className="d36-sheet" role="dialog" aria-modal="true" aria-label={`Buy ${symbol} ${side}`}>
        <div className="d36-sheet-hd">
          {initialSymbol ? (
            <span className="d36-sheet-sym">{symbol}</span>
          ) : (
            <input className="d36-symfield" value={symbol} autoFocus
              placeholder="TICKER" maxLength={10}
              inputMode="text" autoCapitalize="characters" autoCorrect="off"
              spellCheck={false}
              onChange={(e) => setSymbol(e.target.value.toUpperCase().trim())} />
          )}
          <button type="button" className={`d36-sheet-side ${side}`}
            onClick={() => setSide((v) => (v === 'call' ? 'put' : 'call'))}
            title="switch side">{side}</button>
          <button type="button" className="d36-sheet-x" onClick={onClose} aria-label="close">×</button>
        </div>

        <div className="d36-pick">
          {err && !chosen ? <span style={{ color: '#ffc9d2' }}>{err}</span>
            : pick ? (
              <>
                <b>{pick.pick || '—'}</b><br />
                strike <b>{chosen?.strike ?? '—'}</b> · exp <b>{pick.expiration ?? '—'}</b><br />
                delta <b>{chosen?.delta != null ? chosen.delta.toFixed(3) : '—'}</b>
                {' · '}bid <b>{chosen?.bid ?? '—'}</b> · ask <b>{chosen?.ask ?? '—'}</b>
                {chosen?.open_interest != null && <><br />OI <b>{chosen.open_interest.toLocaleString()}</b> · vol <b>{chosen.volume?.toLocaleString() ?? '—'}</b></>}
              </>
            ) : 'finding a contract in the delta band…'}
        </div>

        <button type="button" className={`d36-dte ${zeroDte ? 'on' : ''}`}
          aria-pressed={zeroDte} onClick={() => setZeroDte((v) => !v)}>
          <span className="d36-dtebox" aria-hidden="true">{zeroDte ? '\u2713' : ''}</span>
          <span>0DTE {zeroDte ? 'on \u00b7 today\u2019s expiry allowed'
            : 'off \u00b7 nearest expiry after today'}</span>
        </button>

        <div className="d36-otype">
          <div className="d36-chiprow">
            <button type="button" className={`d36-chip ${market ? 'on' : ''}`}
              aria-pressed={market} onClick={() => setMarket(true)}>MKT</button>
            <button type="button" className={`d36-chip ${!market ? 'on' : ''}`}
              aria-pressed={!market} onClick={() => setMarket(false)}>LIMIT</button>
          </div>
          {!market && (
            <div className="d36-chiprow">
              {DISCOUNT_OPTIONS.map((d) => (
                <button key={d} type="button"
                  className={`d36-chip sm ${discount === d ? 'on' : ''}`}
                  aria-pressed={discount === d}
                  onClick={() => setDiscount(d)}>&minus;{d}%</button>
              ))}
            </div>
          )}
          {/* What the choice actually does, in the terms the server acts on.
              A limit that never fills is a position you did not take, so the
              fifteen minutes is the part worth saying out loud. */}
          <div className="d36-otnote">
            {market
              ? 'market · fills at the going price'
              : `limit −${discount}% · cancels after 15 min if unfilled`}
          </div>
        </div>

        <div className="d36-grid">
          {num('buy_pct', '% of buying power', '1')}
          {num('tp_pct', 'take profit %', '1')}
          {num('delta_min', 'delta min', '0.05')}
          {num('delta_max', 'delta max', '0.05')}
          {num('sl_pct', 'stop loss %', '1')}
        </div>

        {err && pick && <div className="d36-err">{err}</div>}

        {midDayWarn && (
          <div className="d36-err" style={{ background: '#78350f', borderColor: '#f59e0b', padding: '10px 12px' }}>
            <span style={{ fontWeight: 700 }}>⚠ You lost many trades in MID DAY, AVOID!!!</span>
            <div style={{ marginTop: 8, display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
              <button type="button" className="d36-go put" style={{ flex: 'none', padding: '6px 16px' }}
                onClick={() => setMidDayWarn(false)}>Cancel</button>
              <button type="button" className="d36-go call" style={{ flex: 'none', padding: '6px 16px' }}
                onClick={() => { setMidDayWarn(false); doSubmit(); }}>Continue</button>
            </div>
          </div>
        )}

        <button type="button" className={`d36-go ${side}`}
          disabled={busy || !pick || !symbol} onClick={submit}>
          {busy ? 'placing…' : `Buy ${side}`}
        </button>
        <div className={`d36-warn ${live ? 'live' : 'paper'}`}>
          {live ? '● live — this places a real order' : '○ paper — sandbox venue'}
          {!market && ` · limit −${discount}%`}
        </div>
      </div>
    </div>
  );
}

/** Top 5 gainers and top 5 losers, as a list.
 *
 * Same source the desk's mover strip reads — one quotes call over the
 * megacap universe — but ranked rather than filtered: the strip only wants
 * movers past a notability floor, and a "top 5" that shows three names on a
 * quiet day is not a top 5. Passing minPct 0 turns the shared hook from a
 * filter into a ranking.
 */
function TopFive({ user, onPick, onBuy }) {
  const movers = useMovers(user, 5, 0);
  if (!movers) return <div className="d36-posempty">loading…</div>;

  const col = (rows, dir, label) => (
    <div className="d36-t5col">
      <div className={`d36-t5hd ${dir}`}>{label}</div>
      {rows.length === 0 ? <div className="d36-t5empty">—</div> : rows.map((q) => (
        <div className="d36-t5row" key={q.symbol}>
          <button type="button" className="d36-t5sym" onClick={() => onPick(q.symbol)}
            title={`${q.symbol} — levels, TradingView, buy`}>{q.symbol}</button>
          <span className="d36-t5px">{q.price?.toFixed(2)}</span>
          <span className={`d36-t5pct ${dir}`}>
            {q.change_pct >= 0 ? '+' : ''}{Number(q.change_pct).toFixed(2)}%
          </span>
          <span className="d36-t5pc">
            <button type="button" className="d36-pc put"
              onClick={() => onBuy(q.symbol, 'put')} aria-label={`buy a put on ${q.symbol}`}>p</button>
            <button type="button" className="d36-pc call"
              onClick={() => onBuy(q.symbol, 'call')} aria-label={`buy a call on ${q.symbol}`}>c</button>
          </span>
        </div>
      ))}
    </div>
  );

  return (
    <div className="d36-t5">
      {col(movers.up, 'up', '▲ top 5 gainers')}
      {col(movers.down, 'down', '▼ top 5 losers')}
    </div>
  );
}

// The board reports one of five states and nothing else. The ledger has
// more (tp_filled and sl_sold both mean the position is done), but the
// distinction belongs in the P&L column, not in a status that then needs a
// sentence to explain it.
const STATUS = {
  pending: ['PENDING', 'pending'],
  open: ['OPEN', 'open'],
  tp_filled: ['CLOSED', 'closed'],
  sl_sold: ['CLOSED', 'closed'],
  closed: ['CLOSED', 'closed'],
  failed: ['CANCELLED', 'cancelled'],
  cancelled: ['CANCELLED', 'cancelled'],
  timeout: ['TIMEOUT', 'timeout'],
};

const POS_FILTERS = [['active', 'active'], ['', 'all'], ['tp_filled', 'tp wins'],
  ['sl_sold', 'sl stops'], ['closed', 'closed']];

/** Managed positions.
 *
 * The one panel here that is NOT the desk's own component. The desk renders
 * its table inline, sharing state with the lucky-charm trigger and the
 * auto-trade form, so lifting it out means refactoring the close / sweep /
 * set-target handlers that manage live money. That is a change worth making
 * deliberately, not as the last step of a long session — so this owns its
 * own state and calls the SAME endpoints
 * (/tradier/positions, /positions/sweep, /positions/{id}/close), which keeps
 * the two views showing the same rows and the same actions.
 */
function PositionsPanel({ user, live, onError, onOk, blocked }) {
  const [page, setPage] = useState(null);
  const [status, setStatus] = useState('active');
  const [busy, setBusy] = useState(null);

  const venue = live ? 'live' : 'sandbox';
  // Reports its source by name, so the board's five-minute clock can tell a
  // positions outage from a chart outage, and reports success too — this is
  // the one panel the desk owns, so it is the one that can.
  const load = useCallback(async () => {
    try {
      setPage(await vidura.tradierPositions(user.user_id, status, venue, true));
      onOk?.('positions');
    } catch (e) { onError?.('positions', e); }
  }, [user.user_id, status, venue, onError, onOk]);

  // blocked is a ref, not a dep: making it one would tear the timer down and
  // rebuild it every time a sheet opened or closed.
  const blockedRef = useRef(blocked);
  useEffect(() => { blockedRef.current = blocked; }, [blocked]);

  useEffect(() => {
    let dead = false;
    load();
    const id = setInterval(() => {
      if (!dead && !blockedRef.current) load();
    }, 20000);
    return () => { dead = true; clearInterval(id); };
  }, [load]);

  const act = async (fn, key) => {
    setBusy(key);
    try { await fn(); await load(); }
    catch (e) { onError?.('positions', e); }
    finally { setBusy(null); }
  };

  const items = page?.items || [];
  return (
    <div className="d36-pos">
      <div className="d36-posbar">
        <span className="d36-poschips">
          {POS_FILTERS.map(([v, label]) => (
            <button key={label} type="button"
              className={`d36-poschip ${status === v ? 'on' : ''}`}
              onClick={() => setStatus(v)}>{label}</button>
          ))}
        </span>
        <button type="button" className="d36-posrefresh" disabled={busy === 'sweep'}
          onClick={() => act(() => vidura.tradierSweep(user.user_id), 'sweep')}>
          {busy === 'sweep' ? '…' : '↻ sweep'}
        </button>
      </div>

      {items.length === 0 ? <div className="d36-posempty" /> : items.map((p) => {
        const pl = p.live_pnl_usd ?? p.pnl_usd;
        return (
          <div className="d36-posrow" key={p.id}>
            <div className="d36-posmain">
              <b>{p.underlying}</b>
              <span className={`d36-postag ${p.option_type}`}>{p.option_type}</span>
              <span className="d36-posstrike">{p.strike} · {p.expiration?.slice(5)}</span>
              <span className={`d36-posstatus ${STATUS[p.status]?.[1] || ''}`}>
                {STATUS[p.status]?.[0] || String(p.status || '').toUpperCase()}
              </span>
              {!p.sandbox && <span className="d36-poslive">live</span>}
            </div>
            <div className="d36-posnums">
              <span>{p.contracts}x</span>
              <span>in {p.entry_price ?? '—'}</span>
              <span>tp {p.tp_price ?? '—'}</span>
              <span>sl {p.sl_price ?? '—'}</span>
              {p.live_bid != null && <span>bid {p.live_bid}</span>}
              {pl != null && (
                <span className={pl >= 0 ? 'up' : 'down'}>
                  {pl >= 0 ? '+' : '-'}${Math.abs(pl).toFixed(2)}
                </span>
              )}
              {['pending', 'open'].includes(p.status) && (
                <button type="button" className="d36-posclose"
                  disabled={busy === p.id}
                  onClick={() => act(() => vidura.tradierClose(user.user_id, p.id), p.id)}>
                  {busy === p.id ? '…' : 'close'}
                </button>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}

export default function Desk36Site() {
  const [user, setUser] = useState(null);
  const [tickers, setTickers] = useState(loadTickers);
  const [quotes, setQuotes] = useState({});
  const [dmi, setDmi] = useState({});
  const [live, setLive] = useState(loadVenue);
  const [editing, setEditing] = useState(null);
  const [draft, setDraft] = useState('');
  const [adding, setAdding] = useState('');
  // A list, not a string: several panels can fail at once, and the same
  // failure arriving from three pollers should still read as one line.
  //
  // Nothing reaches that list on a first failure. Each source gets a clock:
  // the first failure starts it, later failures keep it running, a success
  // stops it, and only a clock that runs past FAIL_GRACE_MS puts a line on
  // screen. Everything shorter than five continuous minutes is a blip the
  // next tick clears, and the board says nothing about it.
  const [errs, setErrs] = useState([]);
  const failing = useRef(new Map());   // source -> { at, last, msg }

  // Shown at once, no clock: without a user nothing on this board works, so
  // waiting five minutes to say so would just look broken.
  const failNow = useCallback((e) => {
    const msg = errMsg(e);
    if (!msg) return;
    setErrs((prev) => (prev.includes(msg) ? prev : [...prev, msg]));
  }, []);

  const fail = useCallback((src, e) => {
    const msg = errMsg(e);
    if (!msg) return;
    const now = Date.now();
    const open = failing.current.get(src);
    if (!open) { failing.current.set(src, { at: now, last: now, msg }); return; }
    open.last = now;
    open.msg = msg;
    if (now - open.at < FAIL_GRACE_MS) return;
    setErrs((prev) => (prev.includes(msg) ? prev : [...prev, msg]));
  }, []);

  const ok = useCallback((src) => {
    const open = failing.current.get(src);
    if (!open) return;
    failing.current.delete(src);
    setErrs((prev) => (prev.includes(open.msg) ? prev.filter((m) => m !== open.msg) : prev));
  }, []);

  // Recovery, for the panels that can only report the bad news. A source
  // that has not failed again in RECOVERED_MS has outlived its own poll
  // interval without complaining, which is the only recovery signal they
  // give. A message another live clock still holds stays up.
  useEffect(() => {
    const id = setInterval(() => {
      const now = Date.now();
      const gone = [];
      failing.current.forEach((v, k) => {
        if (now - v.last > RECOVERED_MS) { gone.push(v.msg); failing.current.delete(k); }
      });
      if (!gone.length) return;
      const held = new Set();
      failing.current.forEach((v) => held.add(v.msg));
      const drop = gone.filter((m) => !held.has(m));
      if (drop.length) setErrs((prev) => prev.filter((m) => !drop.includes(m)));
    }, 60000);
    return () => clearInterval(id);
  }, []);

  // Dismissing restarts the clock instead of only clearing the line: the
  // source is still down, and a message that returns on the next tick is not
  // dismissable.
  const dismissErr = useCallback((msg) => {
    const now = Date.now();
    failing.current.forEach((v) => { if (v.msg === msg) v.at = now; });
    setErrs((prev) => prev.filter((m) => m !== msg));
  }, []);
  const clearErrs = useCallback(() => {
    const now = Date.now();
    failing.current.forEach((v) => { v.at = now; });
    setErrs([]);
  }, []);

  // What the imported panels call. MiniChart reports as ('SPY bars', e), the
  // hot scan as ('hot scan', e), the flow board as ('options flow', e) — that
  // label is exactly the per-source key the clocks want. Stable identity is
  // the point: this prop is what was re-arming their fetchers.
  const onPanelErr = useCallback((src, e) => fail(String(src), e), [fail]);
  const onPanelOk = useCallback((src) => ok(String(src)), [ok]);
  const sectionHasErr = (prefix) => {
    let found = false;
    failing.current.forEach((_, k) => { if (k.startsWith(prefix)) found = true; });
    return found;
  };
  const [toast, setToast] = useState('');
  const [buy, setBuy] = useState(null);
  const [manage, setManage] = useState(false);
  const [popup, setPopup] = useState(null);      // ticker levels / TV / buy
  const [bal, setBal] = useState(null);
  const gexSeries = useGexSeries();
  const [logout, setLogout] = useState(false);
  const [venueAsk, setVenueAsk] = useState(false);
  // Both account ids, so the confirmation can name the one it is switching
  // TO. `bal` only ever holds the venue currently selected, so using it
  // named the sandbox account in a dialog about going live — precisely the
  // number that has to be right.
  const [venues, setVenues] = useState(null);
  const [autoOpen, setAutoOpen] = useState(false);
  const [autoST, setAutoST] = useState(null);
  const [autoBusy, setAutoBusy] = useState(false);
  const [picked, setPicked] = useState(() => new Set());

  const togglePick = (id) => setPicked((prev) => {
    const next = new Set(prev);
    if (next.has(id)) next.delete(id); else next.add(id);
    return next;
  });
  // Empty selection is the default, and it means everything.
  const shows = (id) => picked.size === 0 || picked.has(id);
  const [charts, setCharts] = useState(true);
  const [snapOpen, setSnapOpen] = useState(true);
  const [mainOpen, setMainOpen] = useState(true);
  const [hotOpen, setHotOpen] = useState(false);
  const [commOpen, setCommOpen] = useState(false);
  const [posOpen, setPosOpen] = useState(false);
  const [flowOpen, setFlowOpen] = useState(false);
  const [top5Open, setTop5Open] = useState(true);

  // While any overlay is up, background refreshes stop. They are all cheap
  // and none of them is worth a relayout under a sheet someone is typing
  // into; the tick is skipped rather than the timer rebuilt, so nothing
  // restarts when the sheet closes and the next tick is on schedule.
  // Transient dialogs only. Manage mode is deliberately NOT here: it is a
  // toggle someone can leave on, and a board that stops quoting for as long
  // as the edit pencil is lit is a board showing stale prices.
  const busy = !!buy || !!popup || autoOpen || logout || venueAsk;
  const busyRef = useRef(busy);
  useEffect(() => { busyRef.current = busy; }, [busy]);

  // Stable for the same reason onPanelErr is: these go to memoised panels.
  //
  // They also NORMALISE, because the panels do not agree on what onBuy takes.
  // MiniChart, TopFive and the ticker popup call it with (symbol, side); the
  // hot scan and the flow board call it with their whole ROW. Both contracts
  // are long-standing and neither is going to change here -- TradierSite is
  // mirrored from upstream and any edit to it is overwritten by the next
  // sync -- so the two shapes get reconciled at the one point they both
  // arrive at.
  //
  // Passing a row straight through put an OBJECT in the ticket's symbol, and
  // React will not render an object as a child. It threw, and because the
  // throw happens during render there is nothing to catch it: the buy button
  // on a HOT row or a flow contract took the entire board down to a blank
  // page.
  const symOf = (v) => String(
    (v && typeof v === 'object' ? v.symbol : v) || '',
  ).toUpperCase().trim();

  const pickSym = useCallback((v) => {
    const sym = symOf(v);
    if (sym) setPopup(sym);
  }, []);

  const buySym = useCallback((v, side) => {
    const sym = symOf(v);
    if (!sym) return;
    // A hot row carries its side as `side`, a flow contract as `type`.
    const raw = (v && typeof v === 'object' ? (v.side || v.type) : side) || 'call';
    setBuy({ symbol: sym, side: String(raw).toLowerCase() === 'put' ? 'put' : 'call' });
  }, []);
  const closeBuy = useCallback(() => setBuy(null), []);
  const renameTicker = useCallback((sym, next) => {
    // Recharting a tile renames that ticker on the board too, so the two
    // halves never disagree. Functional form, so this closure does not have
    // to capture the list and can stay stable across renders.
    const up = (next || '').toUpperCase();
    if (!up) return;
    setTickers((prev) => (prev.includes(up) ? prev : prev.map((t) => (t === sym ? up : t))));
  }, []);


  useEffect(() => { ensureUser().then(setUser).catch(failNow); }, [failNow]);
  useEffect(() => { saveTickers(tickers); }, [tickers]);
  useEffect(() => { saveVenue(live); }, [live]);

  const symbols = useMemo(() => tickers.join(','), [tickers]);

  // Seeded in the render body, not an effect, and that is deliberate:
  // MiniChart reads the stored granularity in a useState initializer, which
  // runs while the tile is rendering. Every effect this component could use
  // -- including a layout effect -- fires after that, so a tile mounted in
  // the same commit would already have read the old value. The ref keeps it
  // to once per change of the ticker list.
  const seededFor = useRef(null);
  if (seededFor.current !== symbols) {
    seededFor.current = symbols;
    seedChartIntervals(tickers);
  }

  // Prices: frequent and cheap.
  useEffect(() => {
    if (!user) return undefined;
    let dead = false;
    const pull = () => vidura.tradierQuotes(user.user_id, symbols)
      .then((r) => {
        if (dead) return;
        const m = {};
        (r.quotes || []).forEach((q) => { m[q.symbol] = q; });
        setQuotes(m);
        ok('quotes');
      })
      .catch((e) => { if (!dead) fail('quotes', e?.detail || e?.message || 'quotes unavailable'); });
    pull();
    const id = setInterval(() => { if (!busyRef.current) pull(); }, QUOTE_MS);
    return () => { dead = true; clearInterval(id); };
  }, [user, symbols, fail, ok]);

  // DMI: one timesales call per new symbol, so rarely.
  useEffect(() => {
    if (!user) return undefined;
    let dead = false;
    const pull = () => api.get('/desk36/dmi', {
      params: { user_id: user.user_id, symbols, live }, timeout: 120000,
    }).then((r) => {
      if (dead) return;
      const m = {};
      (r.rows || []).forEach((x) => { m[x.symbol] = x; });
      setDmi(m);
    }).catch(() => { /* the board is still useful without readings */ });
    pull();
    const id = setInterval(() => { if (!busyRef.current) pull(); }, DMI_MS);
    return () => { dead = true; clearInterval(id); };
  }, [user, symbols, live]);

  // Balance follows the venue toggle, so the header always reports the
  // account a trade from this board would actually hit.
  useEffect(() => {
    if (!user) return undefined;
    let dead = false;
    const pull = () => vidura.tradierBalance(user.user_id, live)
      .then((b) => { if (!dead) setBal(b); })
      .catch(() => { if (!dead) setBal(null); });
    pull();
    const id = setInterval(() => { if (!busyRef.current) pull(); }, 30000);
    return () => { dead = true; clearInterval(id); };
  }, [user, live]);

  useEffect(() => {
    if (!user) return;
    vidura.tradierVenue(user.user_id)
      .then(setVenues)
      .catch(() => { /* the confirmation falls back to naming no account */ });
  }, [user]);

  // Whether the auto-trader is already armed, so the button can say so.
  useEffect(() => {
    if (!user) return undefined;
    let dead = false;
    const pull = () => vidura.autoTradeStatus(user.user_id)
      .then((st) => { if (!dead) setAutoST(st); })
      .catch(() => { /* the button simply reads as unarmed */ });
    pull();
    const id = setInterval(() => { if (!busyRef.current) pull(); }, 30000);
    return () => { dead = true; clearInterval(id); };
  }, [user]);
  const autoOn = !!autoST?.active;

  // day_pl_net is the fee-adjusted figure the desk added; fall back to the
  // raw day_pl on an account (or a build) that does not report it.
  const dayPl = bal ? (bal.day_pl_net ?? bal.day_pl ?? null) : null;
  // The desk's own formula, copied deliberately: the percentage is against
  // what the account was worth AT THE OPEN, which is today's equity less
  // today's move — equity now already contains it. Any other base makes the
  // two boards disagree about the same account.
  const dayPct = (() => {
    if (!bal || dayPl == null) return null;
    const start = Number(bal.total_equity) - Number(bal.day_pl);
    return start > 0 ? (dayPl / start) * 100 : null;
  })();

  useEffect(() => {
    if (!toast) return undefined;
    const id = setTimeout(() => setToast(''), 5000);
    return () => clearTimeout(id);
  }, [toast]);

  // Bars are scaled to the biggest absolute move on the board, so the widest
  // bar is always full and the rest are readable against it. A fixed scale
  // would flatten every row on a quiet day.
  const maxAbs = useMemo(() => {
    const vals = tickers
      .map((t) => Math.abs(quotes[t]?.change_pct ?? 0))
      .filter((v) => Number.isFinite(v));
    return Math.max(0.25, ...vals);
  }, [tickers, quotes]);

  // Keyed by symbol rather than index: the board renders as two lists now,
  // so an index into the combined array is no longer a stable identity.
  const commitEdit = (sym) => {
    const next = draft.trim().toUpperCase();
    setEditing(null);
    if (!next || next === sym) return;
    if (tickers.includes(next)) { failNow(`${next} is already on the board`); return; }
    setTickers(tickers.map((t) => (t === sym ? next : t)));
  };

  const mainList = tickers.filter((t) => LOCKED.includes(t));
  const watchList = tickers.filter((t) => !LOCKED.includes(t));

  const add = () => {
    const next = adding.trim().toUpperCase();
    if (!next) return;
    if (tickers.includes(next)) { failNow(`${next} is already on the board`); setAdding(''); return; }
    if (tickers.length >= MAX_TICKERS) { failNow(`the board holds ${MAX_TICKERS} tickers`); return; }
    setTickers([...tickers, next]);
    setAdding('');
  };

  // One row, rendered into either list. Both groups share it so MAIN and
  // the watchlist can never drift into looking like different things.
  const renderRow = (sym) => {
          const q = quotes[sym];
          const pct = q?.change_pct;
          const chg = q?.change;
          const up = (pct ?? 0) >= 0;
          // Square root, not linear: a 7% VIX day next to a 0.3% ETF would
          // otherwise leave every other bar at its floor and the board would
          // stop saying anything about the differences that matter.
          const scale = pct == null ? 0
            : Math.min(1, Math.sqrt(Math.abs(pct) / maxAbs));
          const label = pct == null ? ''
            : `${chg != null ? `${fmtMoney(chg)} ` : ''}${fmtPct(pct)}`;
          const locked = LOCKED.includes(sym);
          const r = dmi[sym];
          const isGexRow = sym === 'SPY';

    return (
            <div className="d36-row" key={sym}>
              <button type="button" className="d36-pc put"
                onClick={() => user && setBuy({ symbol: sym, side: 'put' })}
                aria-label={`buy a put on ${sym}`}>put</button>

              <span className="d36-field left">
                {/* The DI readout takes whichever side the bar left empty. */}
                {pct == null ? null : up ? (
                  <><DiReadout r={r} />{isGexRow && <GexStrip series={gexSeries.rows} date={gexSeries.date} stale={gexSeries.stale} />}</>
                )
                  : <Bar pct={pct} label={label} dir="down" scale={scale} />}
              </span>

              {editing === sym ? (
                <input className="d36-syminput" value={draft} autoFocus
                  inputMode="text" autoCapitalize="characters" autoCorrect="off"
                  spellCheck={false} maxLength={10}
                  onChange={(e) => setDraft(e.target.value.toUpperCase())}
                  onBlur={() => commitEdit(sym)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') e.currentTarget.blur();
                    if (e.key === 'Escape') setEditing(null);
                  }} />
              ) : (
                <button type="button"
                  className={`d36-sym ${manage && !locked ? 'editable' : 'locked'}`}
                  onClick={() => {
                    // In manage mode the symbol becomes an edit field.
                    // Otherwise a tap opens the ticker's levels / TradingView
                    // / buy popup, which is what a tap on a price row should
                    // do once the board is set up the way you want it.
                    if (manage && !locked) { setDraft(sym); setEditing(sym); }
                    else setPopup(sym);
                  }}
                  title={manage && !locked
                    ? `${sym} — tap to rename`
                    : `${sym} — levels, TradingView, buy`}>
                  {sym}
                </button>
              )}

              <span className="d36-field right">
                {pct == null ? null : up
                  ? <Bar pct={pct} label={label} dir="up" scale={scale} />
                  : (
                    <><DiReadout r={r} />{isGexRow && <GexStrip series={gexSeries.rows} date={gexSeries.date} stale={gexSeries.stale} />}</>
                  )}
                {manage && !locked && (
                  <button type="button" className="d36-del"
                    onClick={() => setTickers(tickers.filter((t) => t !== sym))}
                    title={`remove ${sym} from the board`}
                    aria-label={`remove ${sym}`}>remove</button>
                )}
              </span>

              <button type="button" className="d36-pc call"
                onClick={() => user && setBuy({ symbol: sym, side: 'call' })}
                aria-label={`buy a call on ${sym}`}>call</button>
            </div>
    );
  };

  return (
    <div className="d36">
      <header className="d36-hd">
        {/* The mark is the way back to the Tradier desk — the same role it
            plays as the home button in the shared world header. */}
        <Link to="/tradier-platform" className="d36-mark"
          title="Tradier Platform" aria-label="back to the Tradier Platform">
          <img src="/vidura-logo.svg" alt="" width="26" height="26" />
        </Link>
        {/* The third world, reachable from here directly. There is no room
            for the shared world switcher at 393px, so the two worlds this
            desk needs get one mark each rather than a menu.

            A broadcast mark, NOT the robot: 🤖 is already the auto-trader
            two buttons along, and two robots in one 393px header meaning
            different things is worse than no icon at all. */}
        <Link to="/bot-station" className="d36-mark d36-bots"
          title="Bot Station" aria-label="open the Bot Station">
          <svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true"
            fill="none" stroke="currentColor" strokeWidth="1.9"
            strokeLinecap="round">
            <circle cx="12" cy="12" r="2.2" fill="currentColor" stroke="none" />
            <path d="M8.2 8.2a5.4 5.4 0 0 0 0 7.6M15.8 8.2a5.4 5.4 0 0 1 0 7.6" />
            <path d="M5.4 5.4a9.4 9.4 0 0 0 0 13.2M18.6 5.4a9.4 9.4 0 0 1 0 13.2"
              opacity="0.55" />
          </svg>
        </Link>
        <h1 className="d36-title">
          36 Trade Desk
        </h1>
        {user && <span className="d36-who">- {user.username}</span>}
        <div className="d36-hd-right">
          {/* Same two actions the desk carries, in the same order, before
              the venue toggle they apply to. */}
          {/* Icon-only: two words plus a venue toggle plus the edit control
              is more text than a 393px header has room for, and both of
              these read faster as marks than as labels. The title attribute
              carries the name for anyone who needs it. */}
          <button type="button" className="d36-act buy"
            onClick={() => setBuy({ symbol: '', side: 'call' })}
            aria-label="manual buy ticket" title="manual buy ticket">
            {/* Two arrows circling a dollar — money going round, which is
                what a trade is. Inline SVG rather than an emoji so it takes
                the button's colour and renders identically everywhere. */}
            <svg viewBox="0 0 24 24" width="15" height="15" aria-hidden="true"
              fill="none" stroke="currentColor" strokeWidth="2"
              strokeLinecap="round" strokeLinejoin="round">
              <path d="M3.5 12a8.5 8.5 0 0 1 8.5-8.5c2.6 0 5 1.2 6.5 3.1" />
              <polyline points="18.5 2.6 18.5 7 14.1 7" />
              <path d="M20.5 12a8.5 8.5 0 0 1-8.5 8.5c-2.6 0-5-1.2-6.5-3.1" />
              <polyline points="5.5 21.4 5.5 17 9.9 17" />
              <path d="M14 9.4a2.2 2.2 0 0 0-2-1.1c-1.2 0-2.1.7-2.1 1.7 0 2.3 4.4 1.2 4.4 3.6 0 1.1-1 1.8-2.3 1.8a2.4 2.4 0 0 1-2.2-1.2" />
              <path d="M12 7.1v1.2M12 15.6v1.3" />
            </svg>
          </button>
          <button type="button" className={`d36-act auto ${autoOn ? 'on' : ''}`}
            onClick={() => setAutoOpen(true)}
            aria-label={autoOn ? 'auto-trader armed' : 'arm the auto-trader'}
            title={autoOn ? 'auto-trader ARMED on this venue' : 'arm the auto-trader'}>
            <span aria-hidden="true">🤖</span>
          </button>
          {/* Paper shows the paper-trading mark: a sheet of candles and the
              pencil you are drawing them with. Live shows a filled dot,
              because "you are spending real money" should not be a picture
              of practising. Either way the switch is confirmed, never a
              stray tap. */}
          <button type="button" className={`d36-venue ${live ? 'live' : 'paper'}`}
            onClick={() => setVenueAsk(true)}
            aria-label={live ? 'live venue' : 'paper venue'}
            title={live
              ? 'LIVE — orders from this board are real. Tap to switch.'
              : 'Paper — orders go to the Tradier sandbox. Tap to switch.'}>
            {live ? (
              <span className="d36-venue-live" aria-hidden="true">●<span> live</span></span>
            ) : (
              <svg viewBox="0 0 24 24" width="16" height="16" aria-hidden="true"
                fill="none" stroke="currentColor" strokeWidth="1.7"
                strokeLinecap="round" strokeLinejoin="round">
                {/* the sheet, with its curled corner */}
                <path d="M6 3h9.5v18H5.2A2.2 2.2 0 0 1 3 18.8V6a3 3 0 0 1 3-3Z" />
                <path d="M6 3a3 3 0 0 0-3 3h3V3Z" />
                {/* three candles */}
                <path d="M7.6 8.6v6.8M7.6 10.1h0M10.9 7v9.4M13.9 9.2v6" />
                <rect x="6.3" y="10.1" width="2.6" height="3.6" rx="0.5" />
                <rect x="9.6" y="8.8" width="2.6" height="4.6" rx="0.5" />
                <rect x="12.6" y="10.6" width="2.6" height="3.4" rx="0.5" />
                {/* the pencil */}
                <path d="M19.4 4.6l1.8 1.4-6.1 0V5.6l4.3-1Z" transform="rotate(90 19 6)" />
                <path d="M18.2 5.2h2.2v12.4l-1.1 2.4-1.1-2.4V5.2Z" />
              </svg>
            )}
          </button>
          {/* Sign out. The same door-and-arrow the shared world header uses,
              so the control reads identically in all three worlds. */}
          <button type="button" className="d36-iconbtn signout"
            onClick={() => setLogout(true)}
            aria-label="sign out of every world" title="sign out (all worlds)">
            <svg viewBox="0 0 24 24" width="15" height="15" aria-hidden="true"
              fill="none" stroke="currentColor" strokeWidth="1.9"
              strokeLinecap="round" strokeLinejoin="round">
              <path d="M14 4.5 H6.5 a1.5 1.5 0 0 0 -1.5 1.5 v12 a1.5 1.5 0 0 0 1.5 1.5 H14" />
              <path d="M12.5 12 H21 M18 8.6 L21.4 12 L18 15.4" />
            </svg>
          </button>
          <button type="button" className={`d36-iconbtn ${manage ? 'on' : ''}`}
            onClick={() => setManage((v) => !v)} aria-label="edit tickers"
            title="add or remove tickers">✎</button>
        </div>
        {/* Buying power and today's P&L, on their own line inside the sticky
            header. Two numbers only — they are what you check before every
            trade, and any more of them would push the title off a 393px
            screen. */}
        <div className="d36-stats">
          <span className="d36-stat">
            <span className="d36-statk">bp</span>
            <b className="d36-statv bp">
              {bal ? usd(bal.option_buying_power) : '—'}
            </b>
          </span>
          <span className="d36-stat">
            <span className="d36-statk">today</span>
            <b className={`d36-statv ${dayPl == null ? '' : dayPl >= 0 ? 'up' : 'down'}`}
              title={bal ? `from ${usd(Number(bal.total_equity) - Number(bal.day_pl))} at the open` : undefined}>
              {dayPl == null ? '—'
                : `${dayPl >= 0 ? '+' : '-'}$${Math.abs(dayPl).toFixed(2)}`}
              {dayPct != null && (
                <span className="d36-statpct">
                  {dayPct >= 0 ? '+' : ''}{dayPct.toFixed(2)}%
                </span>
              )}
            </b>
          </span>

          {/* Section tabs. Multi-select, and none selected means all — a
              filter that can be emptied into "show nothing" is a way to
              make the board look broken. */}
          <span className="d36-tabs">
            {SECTIONS.map(([id, label]) => (
              <button key={id} type="button"
                className={`d36-tab ${picked.has(id) ? 'on' : ''}`}
                onClick={() => togglePick(id)}
                aria-pressed={picked.has(id)}
                title={picked.size
                  ? `${picked.has(id) ? 'hide' : 'also show'} ${label}`
                  : `show only ${label}`}>
                {label}
              </button>
            ))}
          </span>
        </div>
      </header>

      {/* Every section collapses the same way, so the board can be cut down
          to just the part being watched — which is the difference between
          usable and endless scrolling on a phone. */}

      {/* One tray, at the top, deduped. Panels report failures upward
          rather than printing their own, so three pollers failing on the
          same outage read as one line with a way to dismiss it. Nothing
          appears here until its source has been failing for five straight
          minutes -- see FAIL_GRACE_MS. Order
          failures are NOT here: they belong on the ticket that caused
          them, next to the button you would press again. */}
      {errs.length > 0 && (
        <div className="d36-errtray" role="alert">
          {errs.map((m) => (
            <div className="d36-errline" key={m}>
              <span>{m}</span>
              <button type="button" className="d36-errx"
                onClick={() => dismissErr(m)}
                aria-label="dismiss">×</button>
            </div>
          ))}
          {errs.length > 1 && (
            <button type="button" className="d36-errclear"
              onClick={clearErrs}>clear all</button>
          )}
        </div>
      )}
      {toast && <div className="d36-toast">{toast}</div>}

      {/* Order and visibility both come from SECTIONS, so the tabs, the
          running order and what is rendered can never disagree. */}
      {SECTIONS.map(([id]) => {
        if (!shows(id)) return null;

        if (id === 'main') return (
          <React.Fragment key={id}>
            {/* SPY and QQQ: always here, never renamed, never removed. */}
            <div className="d36-secthd">
              <button type="button" className="d36-charttoggle"
                onClick={() => setMainOpen((v) => !v)}>
                {mainOpen ? '▾' : '▸'} main
              </button>
              <span className="d36-charthint">always on · not editable</span>
            </div>
            {mainOpen && <div className="d36-rows">{mainList.map(renderRow)}</div>}
          </React.Fragment>
        );

        if (id === 'watch') return (
          <React.Fragment key={id}>
            {/* Everything else, yours to rename, add and remove. */}
            <div className="d36-secthd">
              <button type="button" className="d36-charttoggle"
                onClick={() => setSnapOpen((v) => !v)}>
                {snapOpen ? '▾' : '▸'} watchlist · {watchList.length}
              </button>
              <span className="d36-charthint">✎ to add or remove</span>
            </div>
            {snapOpen && <div className="d36-rows">{watchList.map(renderRow)}</div>}
            {manage && snapOpen && (
              <div className="d36-addrow">
                <input className="d36-add" value={adding} placeholder="add a ticker…"
                  inputMode="text" autoCapitalize="characters" autoCorrect="off"
                  spellCheck={false} maxLength={10}
                  onChange={(e) => setAdding(e.target.value.toUpperCase())}
                  onKeyDown={(e) => { if (e.key === 'Enter') add(); }} />
                <button type="button" className="d36-addbtn" onClick={add}>add</button>
              </div>
            )}
          </React.Fragment>
        );

        if (id === 'positions') return (
          <React.Fragment key={id}>
            <div className="d36-secthd">
              <button type="button" className="d36-charttoggle"
                onClick={() => setPosOpen((v) => !v)}>
                {posOpen ? '▾' : '▸'} positions
              </button>
              <span className="d36-charthint">{live ? 'live venue' : 'sandbox venue'}</span>
            </div>
            {posOpen && user && (
              <PositionsPanel user={user} live={live} blocked={busy}
                onError={onPanelErr} onOk={onPanelOk} />
            )}
          </React.Fragment>
        );

        if (id === 'hot') return (
          <React.Fragment key={id}>
            {/* The desk's own scan, imported: same DMI gates, same
                5m/15m/30m/1h chips, same cached snapshot. Closed by default
                because a cold open is a 100-name sweep, and on a phone that
                should be asked for. */}
            <div className="d36-secthd">
              <button type="button" className="d36-charttoggle"
                onClick={() => setHotOpen((v) => !v)}>
                {hotOpen ? '▾' : '▸'} superhot + hot
                {sectionHasErr('hot') && <span title="error loading hot scan"> ⚠</span>}
              </button>
              <span className="d36-charthint">top 100 · DMI trend strength</span>
            </div>
            {hotOpen && user && (
              <div className="d36-hot">
                <Hot user={user} live={live} blocked={busy}
                  onPick={pickSym} onBuy={buySym} onError={onPanelErr} />
              </div>
            )}
          </React.Fragment>
        );

        if (id === 'commodities') return (
          <React.Fragment key={id}>
            <div className="d36-secthd">
              <button type="button" className="d36-charttoggle"
                onClick={() => setCommOpen((v) => !v)}>
                {commOpen ? '▾' : '▸'} CMDTS
                {sectionHasErr('commodities') && <span title="error loading commodities"> ⚠</span>}
              </button>
              <span className="d36-charthint">GLD · SLV · USO</span>
            </div>
            {commOpen && user && (
              <div className="d36-hot">
                <Commodities user={user} live={live} blocked={busy}
                  onPick={pickSym} onBuy={buySym} onError={onPanelErr} />
              </div>
            )}
          </React.Fragment>
        );

        if (id === 'charts') return (
          <React.Fragment key={id}>
            {/* The desk's own MiniChart, imported rather than
                reimplemented, so the pivot lines, the ADX/DI markers and the
                maximise control are the same ones and cannot drift. */}
            <div className="d36-charthd">
              <button type="button" className="d36-charttoggle"
                onClick={() => setCharts((v) => !v)}>
                {charts ? '▾' : '▸'} charts · {tickers.length}
                {sectionHasErr('bars') && <span title="error loading chart data"> ⚠</span>}
              </button>
              <span className="d36-charthint">tap a title to rechart · ⤢ to maximise</span>
            </div>
            {charts && user && (
              <div className="d36-charts">
                {tickers.map((sym) => (
                  <div className="d36-chartcell" key={`c-${sym}`}>
                    <ChartCell user={user} live={live} sym={sym} blocked={busy}
                      onRename={renameTicker} onError={onPanelErr} onBuy={buySym} />
                  </div>
                ))}
              </div>
            )}
          </React.Fragment>
        );

        if (id === 'flow') return (
          <React.Fragment key={id}>
            <div className="d36-secthd">
              <button type="button" className="d36-charttoggle"
                onClick={() => setFlowOpen((v) => !v)}>
                {flowOpen ? '▾' : '▸'} top option contracts
                {sectionHasErr('options flow') && <span title="error loading options flow"> ⚠</span>}
              </button>
              <span className="d36-charthint">unusual activity · top 25</span>
            </div>
            {flowOpen && user && (
              <div className="d36-hot">
                <Flow user={user} live={live} blocked={busy}
                  onPick={pickSym} onBuy={buySym} onError={onPanelErr} />
              </div>
            )}
          </React.Fragment>
        );

        if (id === 'top5') return (
          <React.Fragment key={id}>
            <div className="d36-secthd">
              <button type="button" className="d36-charttoggle"
                onClick={() => setTop5Open((v) => !v)}>
                {top5Open ? '▾' : '▸'} top 5
              </button>
              <span className="d36-charthint">gainers &amp; losers · megacaps</span>
            </div>
            {top5Open && user && (
              <TopFive user={user} onPick={pickSym} onBuy={buySym} />
            )}
          </React.Fragment>
        );

        return null;
      })}

      {popup && (
        <QuotePopup ticker={popup} accent="#86efac"
          onClose={() => setPopup(null)} onBuy={buySym} />
      )}

      <footer className="d36-footer">
        © {new Date().getFullYear()} Vidura World - 36 Trade Desk — by Sampath
      </footer>

      {buy && user && (
        <BuySheet user={user} symbol={buy.symbol} side={buy.side} live={live}
          onClose={closeBuy} onDone={setToast} />
      )}

      {/* Venue switch, confirmed. The mark blinks between the two venues'
          colours while the question is open — red for the live account it
          would move to, green for the sandbox — so the thing being changed
          is on screen, moving, before anyone taps yes. */}
      {venueAsk && (
        <div className="d36-scrim" onClick={(e) => {
          if (e.target === e.currentTarget) setVenueAsk(false);
        }}>
          <div className="d36-sheet" role="dialog" aria-modal="true"
            aria-label="switch venue">
            <div className="d36-sheet-hd">
              <span className="d36-sheet-sym">switch venue</span>
              <button type="button" className="d36-sheet-x"
                onClick={() => setVenueAsk(false)} aria-label="close">×</button>
            </div>

            <div className="d36-venueblink">
              <img src="/vidura-logo.svg" alt="" width="52" height="52"
                className={`d36-blink ${live ? 'to-paper' : 'to-live'}`} />
            </div>

            <p className="d36-pick" style={{ textAlign: 'center' }}>
              {live ? (
                <>Leaving <b>LIVE</b> for <b>paper</b>. New orders go to the
                  Tradier sandbox
                  {venues?.sandbox?.account_id && <> (<b>{venues.sandbox.account_id}</b>)</>}.
                  {' '}Positions already on the live account keep running and
                  are still managed.</>
              ) : (
                <>Going <b>LIVE</b>. Orders placed from this board will be real,
                  {venues?.live?.account_id
                    ? <> on account <b>{venues.live.account_id}</b>,</>
                    : <> on your production account,</>}
                  {' '}with real money.</>
              )}
            </p>

            <button type="button" className={`d36-go ${live ? 'call' : 'put'}`}
              onClick={() => { setLive((v) => !v); setVenueAsk(false); }}>
              {live ? 'switch to paper' : 'switch to live'}
            </button>
          </div>
        </div>
      )}

      {logout && (
        <div className="d36-scrim" onClick={(e) => {
          if (e.target === e.currentTarget) setLogout(false);
        }}>
          <div className="d36-sheet" role="dialog" aria-modal="true"
            aria-label="sign out">
            <div className="d36-sheet-hd">
              <span className="d36-sheet-sym">{user?.username}</span>
              <button type="button" className="d36-sheet-x"
                onClick={() => setLogout(false)} aria-label="close">×</button>
            </div>
            <p className="d36-pick">
              Signing out ends this session in <b>every world</b> — Tradier
              Platform, 36 Trades and Bot Station — and on every tab open on
              this browser. Positions already on the venue keep their resting
              take-profit, the stop-loss monitor belongs to the server and
              keeps running regardless, and any bot you started stays running.
            </p>
            <button type="button" className="d36-go put"
              onClick={async () => { await auth.logout(); window.location.reload(); }}>
              sign out
            </button>
          </div>
        </div>
      )}

      {autoOpen && user && (
        <div className="d36-scrim" onClick={(e) => {
          if (e.target === e.currentTarget) setAutoOpen(false);
        }}>
          <div className="d36-sheet d36-autosheet" role="dialog" aria-modal="true"
            aria-label="auto trade">
            <div className="d36-sheet-hd">
              <span className="d36-sheet-sym">auto trade</span>
              <span className={`d36-sheet-side ${live ? 'put' : 'call'}`}>
                {live ? 'live' : 'paper'}
              </span>
              <button type="button" className="d36-sheet-x"
                onClick={() => setAutoOpen(false)} aria-label="close">×</button>
            </div>
            {/* The desk's own form, so the knobs and their defaults are the
                same ones the auto-trader actually reads. It renders FROM
                those defaults, so it cannot mount before they arrive. */}
            {!autoST?.defaults ? (
              <div className="d36-pick">loading the auto-trader's settings…</div>
            ) : (
            <AutoTradeForm
              defaults={autoST.defaults}
              // `seed` is required, not optional: the form reads seed.buy_pct
              // directly while defaults is optional-chained, so omitting it
              // throws on mount. It carries the sizing the DESK is currently
              // set to, which here is the desk's own configured defaults.
              seed={{
                buy_pct: autoST.defaults.buy_pct ?? 50,
                tolerance_pct: autoST.defaults.tolerance_pct ?? 25,
                tp_pct: autoST.defaults.tp_pct ?? 15,
                sl_pct: autoST.defaults.sl_pct ?? 30,
                delta: autoST.defaults.delta
                  || `${autoST.defaults.delta_min ?? 0.25}-${autoST.defaults.delta_max ?? 0.5}`,
              }}
              paper={!live} busy={autoBusy}
              onClose={() => setAutoOpen(false)}
              onArm={async (body) => {
                setAutoBusy(true);
                try {
                  await vidura.autoTradeStart({
                    ...body, user_id: user.user_id, live,
                  });
                  setToast(`auto-trader armed on ${live ? 'live' : 'paper'}`);
                  setAutoOpen(false);
                  setAutoST(await vidura.autoTradeStatus(user.user_id));
                } catch (e) { failNow(e); }
                finally { setAutoBusy(false); }
              }} />
            )}
            {autoOn && (
              <button type="button" className="d36-go put"
                disabled={autoBusy}
                onClick={async () => {
                  setAutoBusy(true);
                  try {
                    await vidura.autoTradeStop(user.user_id);
                    setToast('auto-trader disarmed');
                    setAutoST(await vidura.autoTradeStatus(user.user_id));
                    setAutoOpen(false);
                  } catch (e) { failNow(e); }
                  finally { setAutoBusy(false); }
                }}>
                disarm
              </button>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
