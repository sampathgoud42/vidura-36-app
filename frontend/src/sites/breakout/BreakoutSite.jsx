import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import BestBetsLink from '../../shared/BestBets.jsx';
import { createPortal } from 'react-dom';
import WorldHeader from '../../shared/WorldHeader.jsx';
import SiteFooter from '../../shared/SiteFooter.jsx';
import { ApiError, vidura } from '../../shared/viduraApi.js';
import { EXCHANGE_TZ, deskStamp, wallToDesk } from '../../shared/cst.js';
import BreakoutChart from './BreakoutChart.jsx';
import '../../shared/worldHeader.css';
import './breakout.css';

// BreakoutRadar — its own world: breakout scans of the US (S&P 500 +
// Nasdaq-100) and Indian (Nifty 500) markets against eight rules, all of
// which must hold.
//
// Data moves only when asked. "Run Scan" (or the auto-refresh, when it is on)
// downloads the market's candles in the background; everything else -- the
// market tab, the timeframe, every slider in the parameter drawer -- re-judges
// the scan already on the server, instantly, and downloads nothing.
//
// Scans are STORED: the day's first sign-in runs every market and timeframe,
// and a page opened on one with no scan in memory shows the stored rows with
// when they were scanned (CST). Only a scan in memory re-judges a threshold, so
// stored rows judged with other thresholds say so, and Rescan applies these.
//
// Alerts ride on scans: when one this page started lands, any breakout not
// alerted before goes to Telegram and/or Discord through the API's relay. The
// bot token, chat id and webhook stay in this browser; the server sends and
// forgets them.

const MARKETS = [['US', '🇺🇸', 'USA Market'], ['INDIA', '🇮🇳', 'India Market']];
const TIMEFRAMES = [['5m', '5 min'], ['15m', '15 min'], ['1h', '1 hour'], ['4h', '4 hour'], ['1d', 'daily']];
const AUTO = [['off', 'off'], ['15', '15 min'], ['60', '1 hour']];
const POLL_MS = 2000;

// The specification's thresholds. null = "the spec's own for this market or
// timeframe": body 5% on 4h/1d and 2.5% below; cap $50M or Rs 3 crore.
const SPEC = {
  consolidation_bars: 20, max_range_pct: 12, breakout_pct: 2, min_body_pct: null,
  min_rvol: 1.5, min_adv: 500000, near_high_pct: 10, min_market_cap: null, breakout_within: 3,
};
const RULE_TEXT = {
  consolidation: 'Consolidation', penetration: 'Close above range', body: 'Candle body',
  market_cap: 'Market cap', rvol: 'Relative volume', liquidity: '20-day avg volume',
  near_high: 'Near a high', trend: 'Above 20 & 50 EMA',
};

const store = {
  get(key, fallback) {
    try {
      const raw = localStorage.getItem(key);
      return raw == null ? fallback : JSON.parse(raw);
    } catch { return fallback; }
  },
  set(key, value) {
    try { localStorage.setItem(key, JSON.stringify(value)); } catch { /* private mode */ }
  },
};

function errText(e) {
  if (e instanceof ApiError) {
    const d = e.detail;
    if (Array.isArray(d)) return d.map((x) => x.msg || String(x)).join('; ');
    return d || `HTTP ${e.status}`;
  }
  return 'the Vidura API did not answer';
}

// ---- formatting --------------------------------------------------------------
const sym = (market) => (market === 'INDIA' ? '₹' : '$');
function money(v, market) {
  if (v == null) return '—';
  const locale = market === 'INDIA' ? 'en-IN' : 'en-US';
  return `${sym(market)}${v.toLocaleString(locale, { minimumFractionDigits: 2, maximumFractionDigits: v < 1 ? 4 : 2 })}`;
}
const pct = (v, d = 2) => (v == null ? '—' : `${v > 0 ? '+' : v < 0 ? '−' : ''}${Math.abs(v).toFixed(d)}%`);
function cap(v, market) {
  if (!v) return '—';
  if (market === 'INDIA') {
    return `₹${(v / 1e7).toLocaleString('en-IN', { maximumFractionDigits: v < 1e9 ? 1 : 0 })} Cr`;
  }
  const [unit, size] = [['T', 1e12], ['B', 1e9], ['M', 1e6]].find(([, s]) => v >= s) || ['', 1];
  return `$${(v / size).toFixed(size === 1 ? 0 : 2)}${unit}`;
}
function shares(v) {
  if (v == null) return '—';
  if (v >= 1e6) return `${(v / 1e6).toFixed(2)}M`;
  if (v >= 1e3) return `${(v / 1e3).toFixed(0)}K`;
  return String(Math.round(v));
}
function ago(at) {
  if (!at) return '';
  const s = Math.max(0, Date.now() / 1000 - at);
  if (s < 90) return 'just now';
  if (s < 5400) return `${Math.round(s / 60)} min ago`;
  if (s < 172800) return `${(s / 3600).toFixed(1)} h ago`;
  return `${Math.round(s / 86400)} days ago`;
}
const TRIGGER = { daily: 'daily scan', rescan: 'rescanned', first: 'first scan' };
const rvolTier = (v) => (v == null ? '' : v >= 3 ? 'hot' : v >= 2 ? 'high' : 'ok');
const sizeTier = (v) => (v == null ? '' : v >= 8 ? 'hot' : v >= 4 ? 'high' : 'ok');

// ---- the table ---------------------------------------------------------------
const COLUMNS = [
  // key, heading, first click
  ['ticker', 'Ticker', 'asc'],
  ['price', 'Price', 'desc'],
  ['change_pct', '% Change', 'desc'],
  ['breakout_size_pct', 'Breakout Size %', 'desc'],
  ['rvol', 'RVOL', 'desc'],
  ['range_pct', 'Consolidation Range %', 'asc'],
  ['market_cap', 'Market Cap', 'desc'],
];

// The table is the last 30 days, not just this scan: every breakout the
// server remembers (scan.history, the latest to pop up first), with this
// scan's live row standing in for any ticker still passing. A ticker whose
// breakout candle changed broke out again: it is back on top, starred.
function withHistory(rows, history, at) {
  const live = new Map((rows || []).map((r) => [r.ticker, r]));
  const out = [];
  const listed = new Set();
  (history || []).forEach((h) => {
    const cur = live.get(h.ticker);
    out.push(cur
      ? { ...cur, popped_at: h.popped_at, last_seen: h.last_seen, hits: h.hits, again: h.again, current: true }
      : { ...h, current: false });
    listed.add(h.ticker);
  });
  // passing only under this page's own thresholds: new to the history
  (rows || []).forEach((r) => {
    if (!listed.has(r.ticker)) out.push({ ...r, popped_at: at, hits: 1, again: false, current: true });
  });
  return out.sort((a, b) => (b.popped_at || 0) - (a.popped_at || 0)
    || (b.current ? 1 : 0) - (a.current ? 1 : 0)
    || (a.breakout_age ?? 0) - (b.breakout_age ?? 0));
}

function sortRows(rows, key, dir) {
  if (!key) return rows;
  const sign = dir === 'asc' ? 1 : -1;
  return [...rows].sort((a, b) => {
    const x = a[key];
    const y = b[key];
    if (x == null || y == null) return x == null && y == null ? 0 : x == null ? 1 : -1;
    const c = typeof x === 'number' ? x - y : String(x).localeCompare(String(y));
    return sign * c;
  });
}

function ResultsTable({ rows, market, onChart, near = false }) {
  const [sort, setSort] = useState({ key: null, dir: 'desc' });
  const sorted = useMemo(() => sortRows(rows, sort.key, sort.dir), [rows, sort]);
  const onSort = (key, first) => setSort((s) => (s.key === key
    ? { key, dir: s.dir === 'asc' ? 'desc' : 'asc' } : { key, dir: first }));
  return (
    <div className="br-tablewrap">
      <table className="br-table">
        <thead>
          <tr>
            {COLUMNS.map(([key, head, first]) => {
              const on = sort.key === key;
              return (
                <th key={key} scope="col" className={key === 'ticker' ? 'tk' : 'num'}
                  aria-sort={on ? (sort.dir === 'asc' ? 'ascending' : 'descending') : 'none'}>
                  <button type="button" onClick={() => onSort(key, first)}
                    title={`sort by ${head} · again to reverse`}>
                    {head}<span className="ar" aria-hidden="true">{on ? (sort.dir === 'asc' ? '▲' : '▼') : '↕'}</span>
                  </button>
                </th>
              );
            })}
            {near && <th scope="col" className="plain">Missed</th>}
            <th scope="col" className="act plain"><span className="sr">chart</span></th>
          </tr>
        </thead>
        <tbody>
          {sorted.map((r) => (
            <tr key={r.ticker} className={r.current === false ? 'old' : undefined}>
              <td className="tk">
                <b>{r.ticker}</b>
                {r.again && (
                  <span className="br-again" title={`broke out again -- ${r.hits} breakouts in the last 30 days`}>*</span>
                )}
                {r.current === false && (
                  <span className="age past" title={`no longer passing; it last did ${ago(r.last_seen)}, and its numbers are from then`}>
                    {ago(r.last_seen)}
                  </span>
                )}
                {r.current !== false && r.breakout_age > 0 && (
                  <span className="age" title={`the breakout candle was ${r.breakout_age} candle${r.breakout_age === 1 ? '' : 's'} ago, and it is holding`}>
                    {r.breakout_age} ago
                  </span>
                )}
                {r.name && <span className="nm">{r.name}</span>}
              </td>
              <td className="num">{money(r.price, market)}</td>
              <td className={`num ${r.change_pct > 0 ? 'up' : r.change_pct < 0 ? 'down' : ''}`}>{pct(r.change_pct)}</td>
              <td className="num">
                <span className={`br-badge ${sizeTier(r.breakout_size_pct)}`}
                  title={`closed ${pct(r.breakout_size_pct)} above the consolidation top`}>{pct(r.breakout_size_pct, 1)}</span>
              </td>
              <td className="num">
                <span className={`br-badge ${rvolTier(r.rvol)}`}
                  title="breakout candle volume ÷ the 20 candles before it">
                  {r.rvol == null ? '—' : `${r.rvol.toFixed(1)}×`}
                </span>
              </td>
              <td className="num">{pct(r.range_pct, 1).replace('+', '')}</td>
              <td className="num" title={r.rules?.market_cap == null ? 'not verified: Yahoo did not answer for it' : ''}>
                {cap(r.market_cap, market)}
              </td>
              {near && <td className="miss">{(r.failed || []).map((k) => RULE_TEXT[k] || k).join(', ')}</td>}
              <td className="act">
                <button type="button" className="br-chartbtn" onClick={() => onChart(r.ticker)}>
                  View Chart
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ---- the parameter drawer ------------------------------------------------------
function Slider({ label, hint, value, auto, min, max, step, unit, onChange, onAuto }) {
  const shown = value ?? auto;
  return (
    <div className="br-field">
      <div className="br-fieldhd">
        <span>{label}</span>
        <span className="v">{shown == null ? '—' : Number(shown).toLocaleString('en-US')}{unit}</span>
      </div>
      <div className="br-fieldrow">
        <input type="range" min={min} max={max} step={step} value={shown ?? min}
          aria-label={label} onChange={(e) => onChange(Number(e.target.value))} />
        <input type="number" inputMode="decimal" min={min} max={max} step={step}
          value={shown ?? ''} aria-label={`${label}, exact value`}
          onChange={(e) => onChange(e.target.value === '' ? null : Number(e.target.value))} />
      </div>
      <p className="br-hint">
        {hint}
        {onAuto && value != null && (
          <> · <button type="button" className="br-linkbtn" onClick={onAuto}>use the spec&rsquo;s</button></>
        )}
      </p>
    </div>
  );
}

function ParamsDrawer({ params, applied, market, timeframe, onChange, onReset, onClose }) {
  useEffect(() => {
    const onKey = (e) => { if (e.key === 'Escape') onClose(); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);
  const set = (key) => (v) => onChange({ ...params, [key]: v });
  const capUnit = market === 'INDIA' ? 1e7 : 1e6;
  const capAuto = applied?.min_market_cap != null ? applied.min_market_cap / capUnit : null;
  return createPortal(
    <div className="br-scrim" onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <aside className="br-drawer" role="dialog" aria-modal="true" aria-label="scan parameters">
        <div className="br-sheethd">
          <span className="br-sheettitle">parameters</span>
          <button type="button" className="br-btn ghost" onClick={onReset}>reset to spec</button>
          <button type="button" className="br-x" onClick={onClose} aria-label="close parameters">×</button>
        </div>
        <div className="br-sheetbody">
          <p className="br-hint">Changes re-judge the last scan at once; nothing is downloaded.</p>
          <Slider label="1 · Consolidation candles" hint="the N candles before the breakout (spec: 20)"
            value={params.consolidation_bars} min={5} max={60} step={1} unit=""
            onChange={set('consolidation_bars')} />
          <Slider label="1 · Max consolidation range" hint="body range over those candles (spec: 12%)"
            value={params.max_range_pct} min={1} max={30} step={0.5} unit="%"
            onChange={set('max_range_pct')} />
          <Slider label="2 · Close above the range" hint="breakout close over the channel top (spec: 2%)"
            value={params.breakout_pct} min={0} max={15} step={0.5} unit="%"
            onChange={set('breakout_pct')} />
          <Slider label="3 · Min candle body" unit="%"
            hint={`green body ÷ open (spec: ${['4h', '1d'].includes(timeframe) ? '5%' : '2.5%'} on ${timeframe})`}
            value={params.min_body_pct} auto={applied?.min_body_pct} min={0} max={15} step={0.25}
            onChange={set('min_body_pct')} onAuto={() => set('min_body_pct')(null)} />
          <Slider label={`4 · Min market cap (${market === 'INDIA' ? '₹ crore' : '$ million'})`} unit=""
            hint={market === 'INDIA' ? 'spec: ₹3 crore' : 'spec: $50M'}
            value={params.min_market_cap == null || params.cap_market !== market
              ? null : params.min_market_cap / capUnit}
            auto={capAuto} min={0} max={market === 'INDIA' ? 50000 : 20000} step={1}
            onChange={(v) => set('min_market_cap')(v == null ? null : v * capUnit)}
            onAuto={() => set('min_market_cap')(null)} />
          <Slider label="5 · Min relative volume" hint="× the 20-candle average, no upper cap (spec: 1.5×)"
            value={params.min_rvol} min={1} max={6} step={0.1} unit="×" onChange={set('min_rvol')} />
          <Slider label="6 · Min 20-day avg volume" hint="shares a day (spec: 500,000)"
            value={params.min_adv} min={0} max={5000000} step={50000} unit=""
            onChange={set('min_adv')} />
          <Slider label="7 · Within % of a high" hint="of the 20-day, 50-day or all-time high (spec: 10%)"
            value={params.near_high_pct} min={1} max={30} step={0.5} unit="%"
            onChange={set('near_high_pct')} />
          <Slider label="Breakout within the last" hint="candles; 1 = only the newest (default 3)"
            value={params.breakout_within} min={1} max={5} step={1} unit=" candles"
            onChange={set('breakout_within')} />
        </div>
      </aside>
    </div>,
    document.body,
  );
}

// ---- alerts ------------------------------------------------------------------
function compose(scan, fresh) {
  const flag = scan.market === 'INDIA' ? '🇮🇳 India' : '🇺🇸 US';
  const lines = fresh.slice(0, 15).map((r) => `• ${r.ticker} ${money(r.price, scan.market)} `
    + `${pct(r.change_pct)} · breakout ${pct(r.breakout_size_pct, 1)} · RVOL ${r.rvol?.toFixed(1)}×`);
  const more = fresh.length > 15 ? `\n…and ${fresh.length - 15} more` : '';
  return `📡 BreakoutRadar · ${flag} · ${scan.timeframe}\n${fresh.length} new breakout${fresh.length === 1 ? '' : 's'}:\n${lines.join('\n')}${more}`;
}

async function sendAlerts(cfg, text) {
  const out = [];
  if (cfg.telegram_token && cfg.telegram_chat) {
    out.push(vidura.breakoutAlert({ channel: 'telegram', token: cfg.telegram_token,
      chat_id: cfg.telegram_chat, text }).then(() => 'telegram ✓').catch((e) => `telegram: ${errText(e)}`));
  }
  if (cfg.discord_webhook) {
    out.push(vidura.breakoutAlert({ channel: 'discord', webhook_url: cfg.discord_webhook, text })
      .then(() => 'discord ✓').catch((e) => `discord: ${errText(e)}`));
  }
  return out.length ? Promise.all(out) : ['no channel is set up'];
}

function AlertsSheet({ cfg, onChange, onClose }) {
  const [result, setResult] = useState(null);
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    const onKey = (e) => { if (e.key === 'Escape') onClose(); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);
  const set = (key) => (e) => onChange({ ...cfg, [key]: e.target.type === 'checkbox' ? e.target.checked : e.target.value.trim() });
  const test = async () => {
    setBusy(true);
    setResult((await sendAlerts(cfg, '📡 BreakoutRadar test: alerts reach this chat.')).join(' · '));
    setBusy(false);
  };
  return createPortal(
    <div className="br-scrim" onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <aside className="br-drawer" role="dialog" aria-modal="true" aria-label="alerts">
        <div className="br-sheethd">
          <span className="br-sheettitle">alerts</span>
          <button type="button" className="br-x" onClick={onClose} aria-label="close alerts">×</button>
        </div>
        <div className="br-sheetbody">
          <label className="br-toggle">
            <input type="checkbox" checked={!!cfg.enabled} onChange={set('enabled')} />
            <span>Alert me to new breakouts when a scan lands</span>
          </label>
          <fieldset className="br-fs">
            <legend>Telegram</legend>
            <label className="br-in"><span>Bot token</span>
              <input type="password" autoComplete="off" spellCheck={false} value={cfg.telegram_token || ''}
                placeholder="123456789:AA…" onChange={set('telegram_token')} /></label>
            <label className="br-in"><span>Chat ID</span>
              <input type="text" inputMode="text" autoComplete="off" spellCheck={false}
                value={cfg.telegram_chat || ''} placeholder="-1001234567890 or @channel"
                onChange={set('telegram_chat')} /></label>
          </fieldset>
          <fieldset className="br-fs">
            <legend>Discord</legend>
            <label className="br-in"><span>Webhook URL</span>
              <input type="password" autoComplete="off" spellCheck={false} value={cfg.discord_webhook || ''}
                placeholder="https://discord.com/api/webhooks/…" onChange={set('discord_webhook')} /></label>
          </fieldset>
          <div className="br-row">
            <button type="button" className="br-btn" disabled={busy} onClick={test}>
              {busy ? 'sending…' : 'send a test'}
            </button>
            {result && <span className="br-hint" aria-live="polite">{result}</span>}
          </div>
          <p className="br-hint">
            Stored in this browser only. Each alert carries them to the desk&rsquo;s API, which relays
            the message and keeps nothing. Alerts fire when a scan this page started lands — your
            Run Scan, or the auto-refresh — so they need this page open. Each breakout is alerted once.
          </p>
        </div>
      </aside>
    </div>,
    document.body,
  );
}

// ---- the chart modal -------------------------------------------------------------
function ChartModal({ ticker, market, timeframe, query, onClose }) {
  const [data, setData] = useState(null);
  const [err, setErr] = useState(null);
  const closeRef = useRef(null);
  useEffect(() => {
    let alive = true;
    setData(null);
    setErr(null);
    vidura.breakoutChart(ticker, query)
      .then((d) => { if (alive) setData(d); })
      .catch((e) => { if (alive) setErr(errText(e)); });
    return () => { alive = false; };
  }, [ticker, query]);
  useEffect(() => {
    const onKey = (e) => { if (e.key === 'Escape') onClose(); };
    window.addEventListener('keydown', onKey);
    const prev = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    closeRef.current?.focus();
    return () => {
      window.removeEventListener('keydown', onKey);
      document.body.style.overflow = prev;
    };
  }, [onClose]);
  const v = data?.verdict;
  return createPortal(
    <div className="br-scrim center" onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div className="br-modal" role="dialog" aria-modal="true" aria-label={`${ticker} chart`}>
        <div className="br-sheethd">
          <span className="br-sheettitle big">{ticker}</span>
          {data?.name && <span className="br-sub">{data.name}</span>}
          <span className="br-sub">{market === 'INDIA' ? 'NSE' : 'US'} · {timeframe}</span>
          <button type="button" className="br-x" ref={closeRef} onClick={onClose} aria-label="close chart">×</button>
        </div>
        <div className="br-modalbody">
          {err && <p className="br-msg err">⚠ {err}</p>}
          {!err && !data && <p className="br-msg">loading {ticker}…</p>}
          {data && (
            <>
              <BreakoutChart data={data} height={window.innerWidth < 720 ? 300 : 400} />
              {v?.available && (
                <div className="br-verdict">
                  <p className={`br-verdicthd ${v.passed ? 'pass' : 'fail'}`}>
                    {v.passed ? '● all eight rules hold' : `○ ${v.failed.length} rule${v.failed.length === 1 ? '' : 's'} short`}
                    {v.breakout_candle_timestamp && ` · breakout candle ${
                      wallToDesk(v.breakout_candle_timestamp, EXCHANGE_TZ[market]).replace('T', ' ')}${
                      timeframe === '1d' ? '' : ' CST'}`}
                  </p>
                  <ul className="br-rules">
                    {[
                      ['consolidation', `range ${pct(v.range_pct, 1).replace('+', '')} over ${query.consolidation_bars ?? 20} candles`],
                      ['penetration', `closed ${pct(v.breakout_size_pct, 1)} above ${money(v.consolidation_high, market)}`],
                      ['body', `body ${pct(v.body_pct, 1)}`],
                      ['market_cap', v.market_cap == null ? 'not verified' : cap(v.market_cap, market)],
                      ['rvol', v.rvol == null ? '—' : `${v.rvol.toFixed(2)}× the 20-candle average`],
                      ['liquidity', `${shares(v.adv)} shares a day`],
                      ['near_high', `${pct(v.pct_from_high20, 1)} from the 20-day high`],
                      ['trend', `20 EMA ${money(v.ema20, market)} · 50 EMA ${money(v.ema50, market)}`],
                    ].map(([rule, why]) => {
                      const ok = v.rules[rule];
                      return (
                        <li key={rule} className={ok === true ? 'ok' : ok === false ? 'no' : 'na'}>
                          <span className="mk" aria-hidden="true">{ok === true ? '✓' : ok === false ? '✗' : '?'}</span>
                          <b>{RULE_TEXT[rule]}</b> <span>{why}</span>
                        </li>
                      );
                    })}
                  </ul>
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </div>,
    document.body,
  );
}

// ---- the world -------------------------------------------------------------------
export default function BreakoutSite() {
  const [market, setMarket] = useState(() => store.get('breakout.market', 'US'));
  const [timeframe, setTimeframe] = useState(() => store.get('breakout.timeframe', '1d'));
  const [params, setParams] = useState(() => ({ ...SPEC, ...store.get('breakout.params', {}) }));
  const [auto, setAuto] = useState(() => store.get('breakout.auto', 'off'));
  const [alertCfg, setAlertCfg] = useState(() => store.get('breakout.alerts', { enabled: false }));
  const [scan, setScan] = useState(null);
  const [err, setErr] = useState(null);
  const [drawer, setDrawer] = useState(null);         // 'params' | 'alerts' | null
  const [chartOf, setChartOf] = useState(null);
  const [showNear, setShowNear] = useState(false);
  const [alertNote, setAlertNote] = useState(null);

  useEffect(() => { store.set('breakout.market', market); }, [market]);
  useEffect(() => { store.set('breakout.timeframe', timeframe); }, [timeframe]);
  useEffect(() => { store.set('breakout.params', params); }, [params]);
  useEffect(() => { store.set('breakout.auto', auto); }, [auto]);
  useEffect(() => { store.set('breakout.alerts', alertCfg); }, [alertCfg]);

  // The market cap floor is per market, so a typed one does not travel.
  const query = useMemo(() => {
    const q = { market, timeframe };
    Object.entries(params).forEach(([k, v]) => {
      if (v != null && v !== '' && !Number.isNaN(v) && !(k === 'min_market_cap' && params.cap_market !== market)) q[k] = v;
    });
    delete q.cap_market;
    return q;
  }, [market, timeframe, params]);

  const seq = useRef(0);
  const poll = useRef(null);
  const started = useRef(null);            // when THIS page last started a scan
  const alertRef = useRef(alertCfg);
  useEffect(() => { alertRef.current = alertCfg; }, [alertCfg]);

  const landed = useCallback(async (s) => {
    // New breakouts since the last alert for this market and timeframe.
    const key = `breakout.seen.${s.market}.${s.timeframe}`;
    const seen = new Set(store.get(key, []));
    const fresh = s.rows.filter((r) => !seen.has(`${r.ticker}|${r.breakout_candle_timestamp}`));
    s.rows.forEach((r) => seen.add(`${r.ticker}|${r.breakout_candle_timestamp}`));
    store.set(key, [...seen].slice(-800));
    const cfg = alertRef.current;
    if (!cfg.enabled || !fresh.length) return;
    const sent = await sendAlerts(cfg, compose(s, fresh));
    setAlertNote(`alerted ${fresh.length} new: ${sent.join(' · ')}`);
  }, []);

  const load = useCallback(async (refresh = false, q = query) => {
    const mine = ++seq.current;
    clearTimeout(poll.current);
    if (refresh) started.current = Date.now() / 1000;
    try {
      const s = await vidura.breakoutScan({ ...q, refresh: refresh || undefined });
      if (mine !== seq.current) return;
      setScan(s);
      setErr(null);
      if (s.refreshing) {
        poll.current = setTimeout(() => load(false, q), POLL_MS);
      } else if (started.current && s.at && s.at >= started.current - 1) {
        started.current = null;
        landed(s);
      }
    } catch (e) {
      if (mine === seq.current) setErr(errText(e));
    }
  }, [query, landed]);

  // Market, timeframe and thresholds re-judge what is there, a beat after the
  // last change so a dragged slider asks once.
  useEffect(() => {
    const t = setTimeout(() => load(false), 300);
    return () => clearTimeout(t);
  }, [load]);
  useEffect(() => () => clearTimeout(poll.current), []);

  // Auto-refresh: a scan on a timer while this page is open.
  useEffect(() => {
    if (auto === 'off') return undefined;
    const t = setInterval(() => { if (!scan?.refreshing) load(true); }, Number(auto) * 60_000);
    return () => clearInterval(t);
  }, [auto, load, scan?.refreshing]);

  const running = !!scan?.refreshing;
  const progress = scan?.progress;
  const pctDone = progress?.total ? Math.round((100 * progress.done) / progress.total) : null;
  const listed = useMemo(() => (scan?.at ? withHistory(scan.rows, scan.history, scan.at) : []),
    [scan]);
  const failures = Object.entries(scan?.failures || {}).filter(([, n]) => n > 0).sort((a, b) => b[1] - a[1]);
  const universe = scan?.universe;
  const listNote = universe ? Object.entries(universe.lists || {})
    .map(([, l]) => `${l.source === 'live' ? 'live' : l.source === 'saved' ? `saved ${l.as_of}` : `snapshot ${l.as_of}`}`)
    .filter((v, i, a) => a.indexOf(v) === i).join(', ') : '';

  return (
    <div className="br-root">
      <WorldHeader accent="#10b981" title="BreakoutRadar" showSound={false} />
      <main className="br-main">
        <nav className="br-nav" aria-label="scan">
          <h1 className="br-brand"><span aria-hidden="true">📡</span> Breakout<b>Radar</b></h1>
          <div className="br-pills" role="tablist" aria-label="market">
            {MARKETS.map(([id, flag, text]) => (
              <button key={id} type="button" role="tab" aria-selected={market === id}
                className={market === id ? 'on' : ''} onClick={() => setMarket(id)}>
                <span aria-hidden="true">{flag}</span> {text}
              </button>
            ))}
          </div>
          <label className="br-select">
            <span>timeframe</span>
            <select value={timeframe} onChange={(e) => setTimeframe(e.target.value)}>
              {TIMEFRAMES.map(([id, text]) => <option key={id} value={id}>{text}</option>)}
            </select>
          </label>
          <button type="button" className="br-run" disabled={running} onClick={() => load(true)}>
            {running ? `scanning${pctDone != null ? ` ${pctDone}%` : '…'}` : scan?.at ? '↻ Rescan' : '▶ Run Scan'}
          </button>
          <button type="button" className="br-btn ghost" onClick={() => setDrawer('params')}
            title="the eight rules' thresholds">⚙ Parameters</button>
          <label className="br-select">
            <span>auto</span>
            <select value={auto} onChange={(e) => setAuto(e.target.value)}>
              {AUTO.map(([id, text]) => <option key={id} value={id}>{text}</option>)}
            </select>
          </label>
          <button type="button" className={`br-btn ghost${alertCfg.enabled ? ' on' : ''}`}
            onClick={() => setDrawer('alerts')} title="Telegram / Discord alerts for new breakouts">
            {alertCfg.enabled ? '🔔 Alerts on' : '🔕 Alerts'}
          </button>
        </nav>

        {/* The trading worlds' long-term screen, one tap from here too. Its
            tickers are US names: picking one opens its chart on the US market. */}
        <div className="br-links">
          <BestBetsLink accent="#10b981"
            onPick={(sym) => { setMarket('US'); setChartOf(sym); }} />
        </div>

        {running && (
          <div className="br-progress" role="progressbar" aria-valuemin={0} aria-valuemax={100}
            aria-valuenow={pctDone ?? 0}>
            <i style={{ width: `${pctDone ?? 3}%` }} />
            <span>{progress?.phase || 'starting'} {progress?.total ? `${progress.done}/${progress.total}` : ''}</span>
          </div>
        )}

        <section className="br-summary" aria-live="polite">
          {err && <p className="br-msg err">⚠ {err}</p>}
          {!err && scan?.last_error && (
            <p className="br-msg err">
              ⚠ The {deskStamp(scan.last_error.at)} scan did not land: {scan.last_error.reason}
              {scan.at ? ` — showing the ${deskStamp(scan.at)} scan.` : '.'}
            </p>
          )}
          {!err && scan && !scan.at && (
            <p className="br-msg">
              {running ? `Scanning the ${market === 'INDIA' ? 'Nifty 500' : 'S&P 500 + Nasdaq-100'} on ${timeframe} — a minute or two.`
                : <>No {market === 'INDIA' ? 'India' : 'US'} scan on {timeframe} yet. Press <b>Run Scan</b>.</>}
            </p>
          )}
          {!err && scan?.at && (
            <>
              <p className="br-count">
                <b className="n">{scan.rows.length}</b> breakout{scan.rows.length === 1 ? '' : 's'}
                {listed.length > scan.rows.length && (
                  <span title="every ticker that passed on this market and timeframe in the last 30 days stays listed, the latest to pop up first; * broke out again">
                    {' '}now · <b>{listed.length}</b> in the last 30 days
                  </span>
                )}
                <span> · {scan.scanned} scanned{scan.unavailable ? ` (${scan.unavailable} without data)` : ''}</span>
                <span> · {universe?.name}{listNote && ` (${listNote})`}</span>
                <span title={scan.stored ? `stored ${scan.scanned_at || ''}` : 'held in memory: thresholds re-judge at once'}>
                  {' · '}scanned <b>{deskStamp(scan.at)}</b> ({ago(scan.at)}{TRIGGER[scan.trigger] ? `, ${TRIGGER[scan.trigger]}` : ''})
                </span>
                {running && <span className="run"> · refreshing</span>}
              </p>
              {scan.params_match === false && (
                <p className="br-hint">
                  These rows were judged with other thresholds than yours. Press <b>↻ Rescan</b> to judge
                  this market with your parameters — after that every slider answers at once.
                </p>
              )}
              {failures.length > 0 && (
                <p className="br-fails" title="how many names each rule turned away (a name can fail several)">
                  turned away by:{' '}
                  {failures.slice(0, 5).map(([rule, n]) => (
                    <span key={rule} className="br-chip">{RULE_TEXT[rule]} {n}</span>
                  ))}
                </p>
              )}
            </>
          )}
          {alertNote && <p className="br-hint">{alertNote}</p>}
        </section>

        {scan?.at && listed.length > 0 && (
          <ResultsTable rows={listed} market={market} onChart={setChartOf} />
        )}
        {scan?.at && scan.rows.length === 0 && (
          <p className="br-empty">
            Nothing passes all eight rules on {timeframe} right now
            {failures[0] && <> — {RULE_TEXT[failures[0][0]].toLowerCase()} turned away the most ({failures[0][1]})</>}.
            {' '}Loosen a threshold under <b>Parameters</b>, or look at the near misses.
          </p>
        )}

        {scan?.near_misses?.length > 0 && (
          <section className="br-near">
            <button type="button" className="br-neartoggle" aria-expanded={showNear}
              onClick={() => setShowNear((v) => !v)}>
              {showNear ? '▾' : '▸'} near misses · one rule short ({scan.near_misses.length})
            </button>
            {showNear && <ResultsTable rows={scan.near_misses} market={market} onChart={setChartOf} near />}
          </section>
        )}

        <p className="br-foot">
          Eight rules, all at once: a tight consolidation (≤{scan?.params?.max_range_pct ?? 12}% on candle bodies over
          {' '}{scan?.params?.consolidation_bars ?? 20} candles), a close ≥{scan?.params?.breakout_pct ?? 2}% above it that
          still holds, a green body ≥{scan?.params?.min_body_pct ?? '5'}%, market cap over
          {' '}{market === 'INDIA' ? '₹3 crore' : '$50M'}, RVOL ≥{scan?.params?.min_rvol ?? 1.5}×, 20-day average volume
          {' '}over {shares(scan?.params?.min_adv ?? 500000)} shares, within {scan?.params?.near_high_pct ?? 10}% of a
          {' '}20-day/50-day/all-time high, and above the 20 and 50 EMA. Candles from Yahoo; 4-hour candles are hourly
          ones folded on the open. Not advice — a screen, not a signal to trade.
        </p>
      </main>
      <SiteFooter />

      {drawer === 'params' && (
        <ParamsDrawer params={params} applied={scan?.params} market={market} timeframe={timeframe}
          onChange={(p) => setParams({ ...p, cap_market: p.min_market_cap == null ? null : market })}
          onReset={() => setParams({ ...SPEC })} onClose={() => setDrawer(null)} />
      )}
      {drawer === 'alerts' && (
        <AlertsSheet cfg={alertCfg} onChange={setAlertCfg} onClose={() => setDrawer(null)} />
      )}
      {chartOf && (
        <ChartModal ticker={chartOf} market={market} timeframe={timeframe} query={query}
          onClose={() => setChartOf(null)} />
      )}
    </div>
  );
}
