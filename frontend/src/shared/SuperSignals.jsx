import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { ApiError, vidura } from './viduraApi.js';
import './superSignals.css';

// Super Signals — the signal-agent desk, inside both trading worlds.
//
// Today's signals from the desk's eight strategy agents with their live
// outcomes, the watchlist tracker's hits, the desk's own health, and every
// daily report. All of it arrives through /super-signals, which proxies the
// desk's read-only service; the desk is a separate project with its own
// schedule, so "offline" here means its service is down, not this API.
//
// One component for both worlds, so they show one feature rather than two
// versions of it: `compact` is the Tradier right rail, `touch` the 36 Trade
// Desk section (Apple's 44pt targets, no nested scrolling). Colours are the
// --tr-* tokens, which each world defines — .tr-root on the desk, .d36-hot
// on 36 Trades.
//
// Nothing here trades. "call ▸" / "put ▸" opens the desk's own buy ticket
// with the symbol and side filled in; the order is still yours to confirm.

const POLL_OPEN_MS = 60_000;       // a 5m bar and its outcomes land once a bar; a minute catches each
const POLL_IDLE_MS = 10 * 60_000;  // outside the desk's day only a new report changes anything
const PAGE = 40;                   // rows before "more" — a busy day is several hundred
const FRESH_MS = 5 * 60_000;       // a new signal stays marked this long
const SCOPE_KEY = 'superSignals.scope';
const SCOPES = [['all', 'all'], ['open', 'open'], ['watch', '★ watchlist']];
const OFFLINE = 'The signal desk’s service is not running on this machine '
  + '(task Vidura_SignalAgents_API). Signals and reports come back as soon as it is.';

function cstMinutes() {
  const c = new Date(new Date().toLocaleString('en-US', { timeZone: 'America/Chicago' }));
  return { day: c.getDay(), m: c.getHours() * 60 + c.getMinutes() };
}

// The desk's day plus its wrap-up: 08:15 start to the ~15:15 report.
function deskHours() {
  const { day, m } = cstMinutes();
  return day > 0 && day < 6 && m >= 495 && m < 920;
}

function errText(e) {
  if (e instanceof ApiError) return e.status === 503 ? 'offline' : (e.detail || `HTTP ${e.status}`);
  return 'the Vidura API did not answer';
}

const px = (v) => (v == null ? '—' : Number(v).toFixed(2));
const rStr = (r) => (r == null ? '' : `${r > 0 ? '+' : r < 0 ? '−' : ''}${Math.abs(r).toFixed(2)}R`);
const label = (s) => String(s || '').replace(/_/g, ' ').replace(/\+/g, ' + ');
const md = (iso) => (iso ? iso.slice(5) : '');

function loadScope() {
  try {
    const v = localStorage.getItem(SCOPE_KEY);
    if (SCOPES.some(([id]) => id === v)) return v;
  } catch { /* private mode */ }
  return 'all';
}

// One trade idea can fire several of an agent's setups on the same bar —
// flow's combos above all (the desk's own report warns it double-counts). It
// is listed once with its setups folded under it; the tallies stay the desk's
// per-signal numbers, so they match the daily report.
function groupSignals(rows) {
  const out = [];
  const at = new Map();
  rows.forEach((r) => {
    const k = `${r.agent}|${r.ticker}|${r.direction}|${r.time}`;
    const g = at.get(k);
    if (g) {
      g.rows.push(r);
      if (r.watch && !g.watch) g.watch = r.watch;
      return;
    }
    const ng = { ...r, key: k, rows: [r] };
    at.set(k, ng);
    out.push(ng);
  });
  return out;
}

function tallyOf(rows) {
  const t = { signals: rows.length, target: 0, stop: 0, timeout: 0, open: 0, net_r: 0 };
  rows.forEach((r) => {
    if (r.outcome === 'target' || r.outcome === 'stop' || r.outcome === 'timeout') {
      t[r.outcome] += 1;
      t.net_r += r.r || 0;
    } else t.open += 1;
  });
  return t;
}

// Rows that were not there on the previous poll, marked until FRESH_MS old.
// The first answer is the baseline: opening the panel lights up nothing.
function useFresh(ids) {
  const seen = useRef(null);
  const [fresh, setFresh] = useState({});
  useEffect(() => {
    if (!ids) return;
    if (seen.current === null) { seen.current = new Set(ids); return; }
    const arrivals = ids.filter((id) => !seen.current.has(id));
    arrivals.forEach((id) => seen.current.add(id));
    if (!arrivals.length) return;
    const now = Date.now();
    setFresh((p) => {
      const n = { ...p };
      arrivals.forEach((id) => { n[id] = now; });
      return n;
    });
  }, [ids]);
  useEffect(() => {
    const t = setInterval(() => setFresh((p) => {
      const now = Date.now();
      const kept = Object.fromEntries(Object.entries(p).filter(([, at]) => now - at < FRESH_MS));
      return Object.keys(kept).length === Object.keys(p).length ? p : kept;
    }), 15_000);
    return () => clearInterval(t);
  }, []);
  return fresh;
}

function deskStatus(d) {
  if (!d) return null;
  const beats = (d.desk?.agents || [])
    .map((a) => `${a.id} ${a.stale ? 'stale' : 'ok'}${a.updated ? ` ${a.updated.slice(11, 16)}` : ''}`)
    .join(' · ');
  const tracker = d.tracker?.alive ? 'tracker live' : 'tracker idle';
  if (d.phase === 'open' && d.is_today) {
    if (!d.desk?.alive) {
      return { cls: 'warn', text: 'desk offline',
        title: `The desk is not running — signals are as of its last run. ${tracker}` };
    }
    const stale = (d.desk.agents || []).filter((a) => a.stale).length;
    return { cls: stale ? 'warn' : 'live',
      text: `live · ${d.desk.feed_last_bar ? d.desk.feed_last_bar.slice(11, 16) : '—'}`,
      title: `last 5m bar ${d.desk.feed_last_bar || '—'} CST · ${beats} · ${tracker}` };
  }
  return { cls: 'idle', text: d.phase === 'pre-open' ? 'pre-open' : 'closed', title: tracker };
}

export default function SuperSignals({
  compact = false, touch = false, accent = '#5b6af0', paused = false, onPick, onTrade,
}) {
  const [data, setData] = useState(null);
  const [err, setErr] = useState(null);           // text, or 'offline'
  const [reports, setReports] = useState(null);
  const [scope, setScopeState] = useState(loadScope);
  const [agent, setAgent] = useState('');
  const [openKey, setOpenKey] = useState(null);
  const [shown, setShown] = useState(PAGE);
  const [viewer, setViewer] = useState(null);     // report date on screen

  const setScope = (v) => {
    setScopeState(v);
    setShown(PAGE);
    try { localStorage.setItem(SCOPE_KEY, v); } catch { /* ignore */ }
  };

  const load = useCallback(async () => {
    try {
      setData(await vidura.superSignalsSession());
      setErr(null);
    } catch (e) { setErr(errText(e)); }
  }, []);

  const loadReports = useCallback(async () => {
    try { setReports((await vidura.superSignalsReports()).reports || []); } catch { /* strip waits */ }
  }, []);

  // Once a minute through the desk's day, every ten minutes otherwise, and
  // never while the tab is hidden — coming back refreshes at once. The first
  // load always runs, so a desk opened in a background tab is ready when it
  // is switched to. `paused` (a sheet is open on 36 Trades) skips the tick
  // rather than rebuilding the timer, so the next one stays on schedule.
  const pausedRef = useRef(paused);
  useEffect(() => { pausedRef.current = paused; }, [paused]);
  useEffect(() => {
    let alive = true;
    let timer = null;
    let first = true;
    const tick = async () => {
      if (first || (!document.hidden && !pausedRef.current)) await load();
      first = false;
      if (alive) timer = setTimeout(tick, deskHours() ? POLL_OPEN_MS : POLL_IDLE_MS);
    };
    tick();
    const onVis = () => { if (!document.hidden) load(); };
    document.addEventListener('visibilitychange', onVis);
    return () => {
      alive = false;
      clearTimeout(timer);
      document.removeEventListener('visibilitychange', onVis);
    };
  }, [load]);

  // The list changes when a day's report is written, so follow the session.
  const reportKey = data ? `${data.date}|${data.report?.available}` : '';
  useEffect(() => { loadReports(); }, [loadReports, reportKey]);

  const ids = useMemo(() => (data
    ? [...data.signals.map((s) => s.id), ...data.watchlist.map((w) => w.id)] : null), [data]);
  const fresh = useFresh(ids);

  const watchNote = useMemo(
    () => Object.fromEntries((data?.watches || []).map((w) => [w.name, w.note])), [data]);

  const rows = useMemo(() => {
    if (!data) return [];
    if (scope === 'watch') return data.watchlist.map((w) => ({ ...w, key: w.id, rows: [w] }));
    let list = data.signals;
    if (agent) list = list.filter((s) => s.agent === agent);
    if (scope === 'open') list = list.filter((s) => s.outcome === 'open');
    return groupSignals(list);
  }, [data, scope, agent]);

  const tally = useMemo(() => {
    if (!data) return null;
    if (scope === 'watch') return tallyOf(data.watchlist);
    if (agent) return (data.agents || []).find((a) => a.id === agent) || tallyOf([]);
    return data.totals;
  }, [data, scope, agent]);

  const status = deskStatus(data);
  const titles = useMemo(
    () => Object.fromEntries((data?.agents || []).map((a) => [a.id, a.title])), [data]);
  const recent = (reports || []).filter((r) => r.date !== data?.today);
  const todayReady = !!(data?.is_today && data.report?.available);
  const openCount = data ? data.totals.open : 0;
  const counts = { all: data?.totals.signals, open: openCount, watch: data?.watchlist.length };

  return (
    <section className={`ss tr-panel${compact ? ' ss--compact' : ''}${touch ? ' ss--touch' : ''}`}
      aria-label="super signals">
      <div className="ss-head">
        <span className="tr-eyebrow ss-eyebrow">super signals</span>
        {status && (
          <span className={`ss-status ${status.cls}`} title={status.title}>
            <span className="ss-dot" />{status.text}
          </span>
        )}
        {data && (
          <span className="ss-day" title={`session ${data.date}`}>
            {data.is_today ? 'today' : `${data.weekday} ${md(data.date)}`}
          </span>
        )}
      </div>

      {err === 'offline' && <p className="ss-offline">{OFFLINE}</p>}
      {err && err !== 'offline' && <p className="tr-err ss-err">⚠ {err}</p>}
      {!data && !err && <p className="ss-empty">loading today&rsquo;s signals…</p>}

      {data && (
        <>
          {tally && (
            <div className="ss-score" title={'targets – stops – timeouts, open, and net R of the '
              + 'settled signals · each signal counts once, as in the daily report'}>
              <span><b className="w">{tally.target}</b>–<b className="l">{tally.stop}</b>–
                <b className="t">{tally.timeout}</b></span>
              <span><b className="o">{tally.open}</b> open</span>
              <span className={`ss-net ${tally.net_r > 0 ? 'pos' : tally.net_r < 0 ? 'neg' : ''}`}>
                {rStr(tally.net_r)}
              </span>
              <span className="ss-count">{tally.signals} signal{tally.signals === 1 ? '' : 's'}</span>
            </div>
          )}
          {data.econ && <p className="ss-econ" title="macro events today">⚑ {data.econ}</p>}

          <div className="ss-seg" role="group" aria-label="which signals">
            {SCOPES.map(([id, text]) => (
              <button key={id} type="button" className={scope === id ? 'on' : ''}
                aria-pressed={scope === id} onClick={() => setScope(id)}>
                {text}{counts[id] != null && <span className="n">{counts[id]}</span>}
              </button>
            ))}
          </div>

          {scope !== 'watch' && (
            <div className="ss-agents" role="group" aria-label="filter by agent">
              {(data.agents || []).map((a) => (
                <button key={a.id} type="button"
                  className={`ss-chip${agent === a.id ? ' on' : ''}${a.signals ? '' : ' zero'}`}
                  aria-pressed={agent === a.id} title={a.title}
                  onClick={() => { setAgent((v) => (v === a.id ? '' : a.id)); setShown(PAGE); }}>
                  {a.id}<b>{a.signals}</b>
                </button>
              ))}
            </div>
          )}

          {rows.length === 0 && (
            <div className="ss-empty">
              {scope === 'watch' ? (
                <>No watchlist hits {data.is_today ? 'yet today' : 'this session'}.
                  {data.watches?.length > 0 && (
                    <span className="ss-watching"> Watching {data.watches.length}:{' '}
                      {data.watches.map((w) => w.name).join(' · ')}</span>
                  )}</>
              ) : data.signals.length === 0 ? (
                <>No signals yet{data.phase === 'pre-open' ? ' — the desk opens at 08:30 CST' : ''}.
                  {data.previous && (
                    <span> Last session {md(data.previous.date)}: {data.previous.signals} signals
                      {data.previous.report && (
                        <> · <button type="button" className="ss-link"
                          onClick={() => setViewer(data.previous.date)}>read its report</button></>
                      )}</span>
                  )}</>
              ) : 'Nothing under this filter.'}
            </div>
          )}

          {rows.length > 0 && (
            <ul className="ss-list">
              {(compact ? rows : rows.slice(0, shown)).map((g) => {
                const long = g.direction !== 'SHORT';
                const isOpen = openKey === g.key;
                const isFresh = g.rows.some((r) => fresh[r.id]);
                return (
                  <li key={g.key} className={`ss-sig${isFresh ? ' fresh' : ''}${isOpen ? ' x' : ''}`}>
                    <div className="ss-l1">
                      <span className="ss-time">{g.time}</span>
                      <span className={`ss-dir ${long ? 'long' : 'short'}`}
                        aria-label={long ? 'long' : 'short'}>{long ? '▲' : '▼'}</span>
                      <button type="button" className="ss-tkr" onClick={() => onPick?.(g.ticker)}
                        title={`${g.ticker} — quote, levels, chart`}>{g.ticker}</button>
                      <button type="button" className="ss-what" aria-expanded={isOpen}
                        onClick={() => setOpenKey(isOpen ? null : g.key)}
                        title={scope === 'watch' ? g.watch : `${titles[g.agent] || g.agent} · ${label(g.setup)}`}>
                        {scope === 'watch' ? (
                          <><span className="ss-star">★</span> {label(g.watch)}</>
                        ) : (
                          <>
                            <span className="ss-agent">{g.agent}</span> {label(g.setup)}
                            {g.grade && <span className="ss-grade"> [{g.grade}]</span>}
                            {g.rows.length > 1 && <span className="ss-x"> ×{g.rows.length}</span>}
                            {g.watch && <span className="ss-star" title={`watchlist: ${g.watch}`}> ★</span>}
                          </>
                        )}
                      </button>
                    </div>
                    {/* the outcome sits with the prices it resolves, which
                        leaves line one to the setup -- the part that says why */}
                    <div className="ss-l2">
                      <span className="ss-px">
                        {px(g.price)} → <span className="w">{px(g.target)}</span> / <span className="l">{px(g.stop)}</span>
                        {g.horizon_min ? ` · ${g.horizon_min}m` : ''}
                      </span>
                      <span className={`ss-oc ${g.outcome}`}
                        title={g.outcome === 'open' ? 'still racing to target or stop'
                          : `${g.outcome}${g.exit_time ? ` at ${g.exit_time}` : ''}`}>
                        {g.outcome === 'open' ? 'open' : rStr(g.r) || g.outcome}
                      </span>
                    </div>
                    {isOpen && (
                      <div className="ss-detail">
                        {g.outcome === 'open' ? (
                          <p>Open · racing ±{g.tp_pct}% · flat by {g.deadline || '15:00'} CST</p>
                        ) : (
                          <p><b className={`ss-oc ${g.outcome}`}>{g.outcome}</b>
                            {g.exit_time && ` at ${g.exit_time}`}{g.exit_price != null && ` · ${px(g.exit_price)}`}
                            {g.pnl_pct != null && ` · ${g.pnl_pct > 0 ? '+' : ''}${g.pnl_pct.toFixed(2)}%`}
                            {g.r != null && ` · ${rStr(g.r)}`}</p>
                        )}
                        {g.context && <p className="ss-ctx">{g.context}</p>}
                        {g.rows.length > 1 && (
                          <p className="ss-setups">{g.rows.length} setups on this bar:{' '}
                            {g.rows.map((r) => label(r.setup)).join(' · ')}</p>
                        )}
                        {(g.watch || scope === 'watch') && watchNote[g.watch] && (
                          <p className="ss-note">★ {watchNote[g.watch]}</p>
                        )}
                        <p className="ss-meta">
                          {titles[g.agent] || g.agent}
                          {g.block && ` · ${g.block}`}{g.source && ` · ${g.source}`}
                          {g.confluence > 1 && ` · confluence ${g.confluence}`}
                          {g.repeats > 0 && ` · repeated ${g.repeats}×`}
                        </p>
                        <div className="ss-actions">
                          {onTrade && g.outcome === 'open' && (
                            <button type="button" className={`ss-btn ${long ? 'call' : 'put'}`}
                              onClick={() => onTrade(g.ticker, long ? 'call' : 'put')}
                              title={`open a buy ticket for a ${g.ticker} ${long ? 'call' : 'put'} — nothing is placed until you confirm it`}>
                              {long ? 'call' : 'put'} ▸
                            </button>
                          )}
                          {onPick && (
                            <button type="button" className="ss-btn" onClick={() => onPick(g.ticker)}>
                              {g.ticker} quote
                            </button>
                          )}
                        </div>
                      </div>
                    )}
                  </li>
                );
              })}
            </ul>
          )}
          {!compact && rows.length > shown && (
            <button type="button" className="ss-more" onClick={() => setShown((n) => n + PAGE)}>
              show {Math.min(PAGE, rows.length - shown)} more of {rows.length - shown}
            </button>
          )}
        </>
      )}

      {(reports?.length > 0 || data?.is_today) && (
        <div className="ss-reports">
          <div className="ss-rhead">daily reports</div>
          <div className="ss-pills">
            {data?.is_today && (
              <button type="button" className="ss-pill today" disabled={!todayReady}
                onClick={() => setViewer(data.today)}
                title={todayReady ? `today's report · ${data.today}`
                  : 'the desk writes today’s report after the 15:00 CST close'}>
                today{!todayReady && <span className="d">15:00</span>}
              </button>
            )}
            {recent.slice(0, compact ? 3 : 5).map((r) => (
              <button key={r.date} type="button" className="ss-pill" onClick={() => setViewer(r.date)}
                title={`${r.weekday} ${r.date} · built ${r.built}`}>
                {r.weekday}<span className="d">{md(r.date)}</span>
              </button>
            ))}
            {recent.length > 0 && (
              <button type="button" className="ss-pill more" onClick={() => setViewer(recent[0].date)}
                title="every report on file">all ▾</button>
            )}
          </div>
        </div>
      )}

      {viewer && (
        <ReportViewer date={viewer} reports={reports || []} accent={accent}
          onClose={() => setViewer(null)} />
      )}
    </section>
  );
}

// A daily report, in a frame the report cannot climb out of: sandboxed with
// scripts only, so its window selector works but it runs with no origin —
// never with this desk's, and never near the session token. Portaled to the
// body so no scrolling ancestor can trap a fixed overlay (iPhone Safari).
function ReportViewer({ date, reports, accent, onClose }) {
  const [cur, setCur] = useState(date);
  const [page, setPage] = useState(null);         // { date, html }
  const [err, setErr] = useState(null);
  // A report is ~1 MB of HTML and takes a moment to paint on a phone; until
  // the frame says it has loaded, the sheet says so instead of showing blank.
  const [painted, setPainted] = useState(null);   // date whose frame has loaded
  const closeRef = useRef(null);

  const dates = reports.length ? reports.map((r) => r.date) : [date];
  const i = dates.indexOf(cur);
  const newer = i > 0 ? dates[i - 1] : null;
  const older = i >= 0 && i < dates.length - 1 ? dates[i + 1] : null;

  useEffect(() => {
    let alive = true;
    setErr(null);
    vidura.superSignalsReport(cur)
      .then((d) => { if (alive) setPage({ date: cur, html: d.html }); })
      .catch((e) => { if (alive) setErr(errText(e)); });
    return () => { alive = false; };
  }, [cur]);

  useEffect(() => {
    const onKey = (e) => {
      if (e.key === 'Escape') onClose();
      else if (e.key === 'ArrowLeft' && older) setCur(older);
      else if (e.key === 'ArrowRight' && newer) setCur(newer);
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose, older, newer]);

  // the board underneath must not scroll behind the sheet
  useEffect(() => {
    const prev = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    closeRef.current?.focus();
    return () => { document.body.style.overflow = prev; };
  }, []);

  const ready = page && page.date === cur;
  const save = () => {
    if (!ready) return;
    const url = URL.createObjectURL(new Blob([page.html], { type: 'text/html' }));
    const a = document.createElement('a');
    a.href = url;
    a.download = `signal_report_${cur}.html`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 10_000);
  };

  return createPortal(
    <div className="ss-scrim" style={{ '--ss-accent': accent }}
      onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div className="ss-viewer" role="dialog" aria-modal="true" aria-label={`signal report ${cur}`}>
        <div className="ss-vhead">
          <span className="ss-vtitle">signal report</span>
          <button type="button" className="ss-vbtn" disabled={!older}
            onClick={() => setCur(older)} aria-label="older report" title="older report (←)">‹</button>
          <select className="ss-vsel" value={cur} onChange={(e) => setCur(e.target.value)}
            aria-label="report date">
            {(reports.length ? reports : [{ date, weekday: '' }]).map((r) => (
              <option key={r.date} value={r.date}>{r.weekday} {md(r.date)}</option>
            ))}
          </select>
          <button type="button" className="ss-vbtn" disabled={!newer}
            onClick={() => setCur(newer)} aria-label="newer report" title="newer report (→)">›</button>
          <button type="button" className="ss-vbtn wide" disabled={!ready} onClick={save}
            title="save this report as an .html file">save</button>
          <button type="button" className="ss-vbtn" ref={closeRef} onClick={onClose}
            aria-label="close report" title="close (Esc)">×</button>
        </div>
        <div className="ss-vbody">
          {err && <p className="ss-vmsg err">⚠ {err === 'offline' ? OFFLINE : err}</p>}
          {!err && painted !== cur && <p className="ss-vmsg">loading the {cur} report…</p>}
          {!err && ready && (
            <iframe key={cur} title={`signal report ${cur}`} sandbox="allow-scripts"
              srcDoc={page.html} className={painted === cur ? '' : 'hold'}
              onLoad={() => setPainted(cur)} />
          )}
        </div>
      </div>
    </div>,
    document.body,
  );
}
