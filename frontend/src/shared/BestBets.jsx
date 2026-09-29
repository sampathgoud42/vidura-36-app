import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { ApiError, vidura } from './viduraApi.js';
import './superSignals.css';
import './bestBets.css';

// Best Bets — a 21 EMA on 4-hour bars across the desk's watchlist, as a link
// that opens a sheet. One component for both worlds, like Super Signals:
// `touch` is the 36 Trade Desk's 44pt layout.
//
//   A  deep retracement: a low fell more than 20% under the EMA and the price
//      is turning back up toward it; "days to catch" projects the last five
//      bars' pace, with the EMA closing from its side too.
//   B  fresh cross: the close crossed above the EMA on one of the last three
//      candles, and is less than 20% above it.
//
// Tradier serves no 4-hour bar; the API folds its 15-minute bars into
// 09:30-anchored ones (ema_screen.py). The sheet wears the report viewer's
// chrome (.ss-scrim / .ss-viewer), portaled to the body so no scrolling
// ancestor can trap it (iPhone Safari). Nothing here trades: a ticker opens
// the quote popup.

const POLL_MS = 3000;              // while a sweep runs behind the snapshot
const POLL_LIMIT_MS = 4 * 60_000;  // a 60-name sweep on the sandbox is ~70s
const VIEWS = [['setups', 'A + B'], ['A', 'A · retrace'], ['B', 'B · cross'], ['all', 'all scanned']];

// key, heading, kind, first click, filter hint
const COLS = [
  ['symbol', 'Ticker', 'text', 'asc', 'e.g. NV'],
  ['setup', 'Setup', 'text', 'asc', 'A / B'],
  ['price', 'Price', 'num', 'desc', '>20'],
  ['ema', '21 EMA', 'num', 'desc', '>20'],
  ['gap', '± EMA', 'num', 'asc', '<0'],
  ['distance_pct', 'Dist %', 'num', 'asc', '-10..0'],
  ['days_to_catch', 'Days to catch', 'num', 'asc', '<5'],
  ['deepest_pct', 'Deepest %', 'num', 'asc', '<-25'],
  ['cross_age', 'Crossed', 'num', 'asc', '<=2'],
  ['market_cap', 'Mkt cap', 'num', 'desc', '>10B'],
  ['industry', 'Industry', 'text', 'asc', 'semi'],
];
const NO_FILTERS = Object.fromEntries(COLS.map(([k]) => [k, '']));

function errText(e) {
  if (e instanceof ApiError) {
    if (e.status === 424) return 'No Tradier credential for this venue — the screen reads Tradier bars.';
    return e.detail || `HTTP ${e.status}`;
  }
  return 'the Vidura API did not answer';
}

const money = (v) => (v == null ? '—' : Math.abs(v) < 1 ? v.toFixed(4) : v.toFixed(2));
const signed = (v, d = 2, suffix = '') => (v == null ? '—'
  : `${v > 0 ? '+' : v < 0 ? '−' : ''}${Math.abs(v).toFixed(d)}${suffix}`);
function cap(v) {
  if (!v) return '—';
  const [unit, size] = [['T', 1e12], ['B', 1e9], ['M', 1e6]].find(([, s]) => v >= s) || ['', 1];
  return `$${(v / size).toFixed(size === 1 ? 0 : 2)}${unit}`;
}
function ago(at) {
  if (!at) return '';
  const s = Math.max(0, Date.now() / 1000 - at);
  if (s < 90) return 'just now';
  if (s < 5400) return `${Math.round(s / 60)} min ago`;
  return `${(s / 3600).toFixed(1)} h ago`;
}

// ---- per-column filters -------------------------------------------------
// Text columns match anywhere, case-insensitive. Number columns take >x, <x,
// >=x, <=x, =x, a range a..b, or a bare number meaning "at least"; K/M/B/T
// scale it, so ">10B" works on market cap.
function amount(text) {
  const m = /^(-?\d*\.?\d+)([kmbt])?$/i.exec(text);
  if (!m) return null;
  const scale = { k: 1e3, m: 1e6, b: 1e9, t: 1e12 }[(m[2] || '').toLowerCase()] || 1;
  return parseFloat(m[1]) * scale;
}

export function numberFilter(raw) {
  const s = String(raw || '').replace(/[\s,$%]/g, '').replace('≥', '>=').replace('≤', '<=')
    .replace(/−/g, '-');
  if (!s) return null;
  const range = /^(-?[\d.]+[kmbt]?)\.\.(-?[\d.]+[kmbt]?)$/i.exec(s);
  if (range) {
    const a = amount(range[1]);
    const b = amount(range[2]);
    if (a == null || b == null) return 'bad';
    const lo = Math.min(a, b);
    const hi = Math.max(a, b);
    return (v) => v != null && v >= lo && v <= hi;
  }
  const m = /^(>=|<=|>|<|=)?(-?[\d.]+[kmbt]?)$/i.exec(s);
  const x = m ? amount(m[2]) : null;
  if (x == null) return 'bad';
  const op = m[1] || '>=';
  return (v) => v != null && (op === '>' ? v > x : op === '<' ? v < x : op === '>='
    ? v >= x : op === '<=' ? v <= x : Math.abs(v - x) < 1e-9);
}

function textFilter(raw) {
  const s = String(raw || '').trim().toLowerCase();
  return s ? (v) => String(v ?? '').toLowerCase().includes(s) : null;
}

// Blanks sort last whichever way; ties keep the API's order (A soonest catch,
// then B freshest cross, then the rest).
function sortRows(rows, key, dir) {
  const sign = dir === 'asc' ? 1 : -1;
  return [...rows].sort((a, b) => {
    const x = a[key];
    const y = b[key];
    if (x == null || y == null) {
      if (x == null && y == null) return a._i - b._i;
      return x == null ? 1 : -1;
    }
    const c = typeof x === 'number' ? x - y : String(x).localeCompare(String(y));
    return c ? sign * c : a._i - b._i;
  });
}

export default function BestBetsLink({ touch = false, accent = '#5b6af0', live = false, onPick }) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button type="button" className={`bb-link${touch ? ' bb-link--touch' : ''}`}
        onClick={() => setOpen(true)}
        title="4-hour 21 EMA screen: deep retracements turning back up, and fresh crosses above the EMA — every column sorts and filters">
        ★ Best bets<span className="d">· long term · 4H 21 EMA ›</span>
      </button>
      {open && <BestBetsSheet accent={accent} live={live} onPick={onPick}
        onClose={() => setOpen(false)} />}
    </>
  );
}

function BestBetsSheet({ accent, live, onPick, onClose }) {
  const [res, setRes] = useState(null);
  const [err, setErr] = useState(null);
  const [view, setView] = useState('setups');
  const [filters, setFilters] = useState(NO_FILTERS);
  const [sort, setSort] = useState({ key: null, dir: 'asc' });
  const closeRef = useRef(null);
  const polling = useRef(null);

  const load = useCallback(async (refresh = false) => {
    clearTimeout(polling.current);
    const started = Date.now();
    const tick = async (first) => {
      try {
        const d = await vidura.tradierBestBets(live, first && refresh);
        setRes(d);
        setErr(null);
        if (d.refreshing && Date.now() - started < POLL_LIMIT_MS) {
          polling.current = setTimeout(() => tick(false), POLL_MS);
        }
      } catch (e) { setErr(errText(e)); }
    };
    tick(true);
  }, [live]);

  useEffect(() => {
    load(false);
    return () => clearTimeout(polling.current);
  }, [load]);

  useEffect(() => {
    const onKey = (e) => { if (e.key === 'Escape') onClose(); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  // the board underneath must not scroll behind the sheet
  useEffect(() => {
    const prev = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    closeRef.current?.focus();
    return () => { document.body.style.overflow = prev; };
  }, []);

  const tests = useMemo(() => Object.fromEntries(COLS.map(([key, , kind]) => [
    key, kind === 'num' ? numberFilter(filters[key]) : textFilter(filters[key]),
  ])), [filters]);
  const bad = COLS.filter(([k]) => tests[k] === 'bad').map(([k]) => k);

  const all = useMemo(() => (res?.rows || []).map((r, i) => ({ ...r, _i: i })), [res]);
  const counts = useMemo(() => ({
    setups: all.filter((r) => r.setup).length,
    A: all.filter((r) => r.setup === 'A').length,
    B: all.filter((r) => r.setup === 'B').length,
    all: all.length,
  }), [all]);

  const rows = useMemo(() => {
    let list = all;
    if (view === 'setups') list = list.filter((r) => r.setup);
    else if (view !== 'all') list = list.filter((r) => r.setup === view);
    COLS.forEach(([key]) => {
      const test = tests[key];
      if (typeof test === 'function') list = list.filter((r) => test(r[key]));
    });
    return sort.key ? sortRows(list, sort.key, sort.dir) : list;
  }, [all, view, tests, sort]);

  const filtered = Object.values(filters).some((v) => v.trim());
  const onSort = (key, first) => setSort((s) => (s.key === key
    ? { key, dir: s.dir === 'asc' ? 'desc' : 'asc' } : { key, dir: first }));
  const meta = res?.meta || {};
  const tf = meta.timeframe || {};
  const rules = meta.rules || {};

  return createPortal(
    <div className="ss-scrim" style={{ '--ss-accent': accent }}
      onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div className="ss-viewer bp bb" role="dialog" aria-modal="true"
        aria-label="best bets: 4-hour 21 EMA screen">
        <div className="ss-vhead">
          <span className="ss-vtitle">best bets · 4h · {rules.span || 21} ema</span>
          <button type="button" className="ss-vbtn wide" disabled={!!res?.refreshing}
            onClick={() => load(true)} title="run the screen again now">
            {res?.refreshing ? 'scanning…' : '↻ refresh'}
          </button>
          <button type="button" className="ss-vbtn" ref={closeRef} onClick={onClose}
            aria-label="close best bets" title="close (Esc)">×</button>
        </div>

        <form className="bb-bar" onSubmit={(e) => e.preventDefault()}
          aria-label="which setups to list">
          <div className="bb-seg" role="group" aria-label="setup">
            {VIEWS.map(([id, text]) => (
              <button key={id} type="button" className={view === id ? 'on' : ''}
                aria-pressed={view === id} onClick={() => setView(id)}>
                {text}<span className="n">{res ? counts[id] : ''}</span>
              </button>
            ))}
          </div>
          {filtered && (
            <button type="button" className="ss-vbtn wide bb-clear"
              onClick={() => setFilters(NO_FILTERS)}>clear filters</button>
          )}
          <p className="bb-sum" aria-live="polite">
            {res ? (
              <>
                <b>{rows.length}</b> shown · A {counts.A} · B {counts.B} of {meta.scanned ?? '…'} scanned
                {tf.bar && ` · ${tf.bar} bars from ${tf.source_interval}, ${tf.anchor}`}
                {res.at && ` · updated ${ago(res.at)}`}
                {meta.venue && ` · ${meta.venue}`}
                {res.refreshing && ' · scanning…'}
              </>
            ) : (err ? '' : 'loading…')}
          </p>
        </form>

        <div className="ss-vbody">
          {err && <p className="ss-vmsg err">⚠ {err}</p>}
          {!err && res && !res.at && (
            <p className="ss-vmsg">The first scan is running: {meta.scanned || 'the'} tickers,
              one Tradier call each. The table fills in when it lands.</p>
          )}
          {!err && res?.at && (
            <>
              <table className="ss-bp bb-table">
                {/* One header row: each cell stacks its sort button over its
                    filter. Two sticky rows would each need the other's
                    height as an offset, which Safari gets wrong. */}
                <thead>
                  <tr>
                    {COLS.map(([key, head, kind, first, hint]) => {
                      const on = sort.key === key;
                      return (
                        <th key={key} scope="col" className={`${kind}${key === 'symbol' ? ' tk' : ''}`}
                          aria-sort={on ? (sort.dir === 'asc' ? 'ascending' : 'descending') : 'none'}>
                          <button type="button" onClick={() => onSort(key, first)}
                            title={`sort by ${head} · again to reverse`}>
                            {head}
                            <span className="ar" aria-hidden="true">{on ? (sort.dir === 'asc' ? '▲' : '▼') : '↕'}</span>
                          </button>
                          <input value={filters[key]} placeholder={hint}
                            inputMode={kind === 'num' ? 'text' : 'search'}
                            autoCapitalize="off" autoCorrect="off" spellCheck={false}
                            aria-label={`filter ${head}`} aria-invalid={bad.includes(key)}
                            className={bad.includes(key) ? 'bad' : ''}
                            onChange={(e) => setFilters((f) => ({ ...f, [key]: e.target.value }))} />
                        </th>
                      );
                    })}
                  </tr>
                </thead>
                <tbody>
                  {rows.map((r) => (
                    <tr key={r.symbol} className={r.available === false ? 'dead' : ''}>
                      <td className="tk">
                        <button type="button" className="bb-tkr" onClick={() => onPick?.(r.symbol)}
                          title={r.name ? `${r.name} — quote and levels` : `${r.symbol} — quote and levels`}>
                          {r.symbol}
                        </button>
                      </td>
                      <td title={r.available === false ? r.reason
                        : r.setup === 'A' ? 'deep retracement, turning back up'
                          : r.setup === 'B' ? 'fresh cross above the EMA' : 'in neither setup'}>
                        {r.setup ? <span className={`bb-setup ${r.setup}`}>{r.setup}</span>
                          : <span className="bb-none">{r.available === false ? 'n/a' : '—'}</span>}
                      </td>
                      <td className="num">{money(r.price)}</td>
                      <td className="num">{money(r.ema)}</td>
                      <td className={`num ${r.gap > 0 ? 'pos' : r.gap < 0 ? 'neg' : ''}`}>{signed(r.gap)}</td>
                      <td className={`num ${r.distance_pct > 0 ? 'pos' : r.distance_pct < 0 ? 'neg' : ''}`}>
                        {signed(r.distance_pct, 2, '%')}
                      </td>
                      <td className="num" title={r.days_to_catch == null ? (r.setup === 'A'
                        ? 'not closing at the current pace' : '')
                        : `≈ ${r.hours_to_catch} trading hours · ${r.bars_to_catch} four-hour bars at ${signed(r.velocity, 4)}/bar`}>
                        {r.days_to_catch == null ? '—' : `${r.days_to_catch.toFixed(1)} d`}
                      </td>
                      <td className="num" title={r.deepest_at ? `deepest low vs its EMA: ${r.deepest_at.replace('T', ' ').slice(0, 16)} ET` : ''}>
                        {signed(r.deepest_pct, 1, '%')}
                      </td>
                      <td className="num" title={r.cross_age ? `last crossed above the EMA ${r.cross_age} candle${r.cross_age === 1 ? '' : 's'} ago (1 = the newest)` : 'no cross above in the window'}>
                        {r.cross_age == null ? '—' : `${r.cross_age} ago`}
                      </td>
                      <td className="num">{cap(r.market_cap)}</td>
                      <td className="ind" title={r.sector || ''}>{r.industry || '—'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {rows.length === 0 && (
                <p className="ss-vmsg">
                  {view === 'all' || filtered ? 'Nothing matches these filters.'
                    : 'Nothing is in a setup right now. "all scanned" shows every ticker and how close it came.'}
                </p>
              )}
              <p className="ss-bp-note bb-note">
                4-hour bars are built from Tradier&rsquo;s 15-minute bars, anchored on the 09:30 open
                (09:30–13:30, 13:30–16:00); Tradier keeps 40 days of them, so the EMA reads the last
                ~55 bars and the newest bar may still be forming. <b>A</b>: a low more than
                {' '}{rules.deep_pct ?? 20}% under the EMA in that window, and the price turning back up.
                {' '}<b>B</b>: crossed above the EMA within {rules.cross_within ?? 3} candles, now less
                than {rules.near_pct ?? 20}% above. Days to catch assume the last five bars&rsquo; pace
                holds and count the EMA moving toward the price — a projection, not a forecast.
                Filters: text matches anywhere; numbers take &gt;x, &lt;x, a..b, or a bare minimum
                (&ldquo;&gt;10B&rdquo; on market cap). Click a heading to sort, again to reverse.
              </p>
            </>
          )}
        </div>
      </div>
    </div>,
    document.body,
  );
}
