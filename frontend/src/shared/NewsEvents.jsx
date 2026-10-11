import React, { useCallback, useEffect, useState } from 'react';
import { createPortal } from 'react-dom';
import { vidura } from './viduraApi.js';
import './newsEvents.css';

/* News & Events: the US economic calendar that moves markets -- CPI, jobs,
   GDP, PCE, FOMC, jobless claims, Treasury auctions -- from yesterday to two
   weeks out, read from the agencies' own schedules through Apify. Fetched by
   the server daily at 08:15 CT; ↻ fetches it now (a paid run of a few cents).

   Collapsed it is one line: the next high-importance release. Open, the
   events by day in CT; tapping one opens its card with every field the
   calendar has. Both desks mount this same component. */

const DAY_FMT = new Intl.DateTimeFormat('en-US', {
  weekday: 'short', month: 'short', day: 'numeric', timeZone: 'UTC',
});
const OPEN_KEY = 'vidura.news.open';

function dayLabel(ymd, today) {
  if (ymd === today) return 'Today';
  const label = DAY_FMT.format(new Date(`${ymd}T12:00:00Z`));
  return label;
}

function ctToday() {
  return new Intl.DateTimeFormat('en-CA', { timeZone: 'America/Chicago' }).format(new Date());
}

function value(v, unit) {
  if (v === null || v === undefined || v === '') return '—';
  const n = Number(v);
  const txt = Number.isFinite(n) && Math.abs(n) >= 1000 ? n.toLocaleString() : String(v);
  return unit ? `${txt} ${unit}` : txt;
}

function errText(e) {
  return (e && (e.detail || e.message)) || 'the calendar could not be read';
}

export default function NewsEvents({ touch = false }) {
  const [open, setOpen] = useState(() => {
    try { return localStorage.getItem(OPEN_KEY) === '1'; } catch { return false; }
  });
  const [data, setData] = useState(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState('');
  const [pick, setPick] = useState(null);

  const load = useCallback(async () => {
    try { setData(await vidura.econCalendar()); setErr(''); }
    catch (e) { setErr(errText(e)); }
  }, []);
  // The calendar changes once a day; a ten-minute look picks up the 08:15
  // run and a refresh someone else pressed, without hammering anything.
  useEffect(() => {
    load();
    const t = setInterval(() => { if (!document.hidden) load(); }, 10 * 60 * 1000);
    return () => clearInterval(t);
  }, [load]);

  const toggle = () => setOpen((v) => {
    try { localStorage.setItem(OPEN_KEY, v ? '0' : '1'); } catch { /* per-browser only */ }
    return !v;
  });

  const refresh = async (e) => {
    e.stopPropagation();
    if (busy) return;
    setBusy(true); setErr('');
    try { setData(await vidura.econCalendarRefresh()); }
    catch (ex) { setErr(errText(ex)); }
    finally { setBusy(false); }
  };

  const events = (data && data.events) || [];
  const today = ctToday();
  const nowCt = new Intl.DateTimeFormat('sv-SE', {
    timeZone: 'America/Chicago', year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit',
  }).format(new Date()).replace(',', '');
  const next = events.find((e) => e.importance === 'high' && (e.release_ct || '') >= nowCt)
    || events.find((e) => (e.release_ct || '') >= nowCt);
  const byDay = events.reduce((acc, e) => {
    const d = (e.release_ct || '').slice(0, 10) || 'undated';
    (acc[d] = acc[d] || []).push(e);
    return acc;
  }, {});

  return (
    <div className={`nev ${touch ? 'nev--touch' : ''} ${open ? 'open' : ''}`}>
      <div className="nev-hd" role="button" tabIndex={0} aria-expanded={open}
        onClick={toggle} onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') toggle(); }}>
        <span className="nev-tag">📅 NEWS &amp; EVENTS</span>
        {!open && next && (
          <span className="nev-next" title={`next: ${next.event} ${next.release_ct} CT`}>
            <i className={`imp ${next.importance}`} />{next.event} · {next.release_ct?.slice(5)}
          </span>
        )}
        <span className="nev-sp" />
        <button type="button" className="nev-refresh" onClick={refresh} disabled={busy}
          aria-label="fetch the calendar now"
          title="fetch the calendar now — a paid Apify run, a few cents; it also runs by itself at 08:15 CT">
          <span className={busy || data?.refreshing ? 'spin' : ''} aria-hidden="true">↻</span>
        </button>
        <span className="nev-caret" aria-hidden="true">{open ? '−' : '+'}</span>
      </div>

      {open && (
        <div className="nev-bd">
          {err && <p className="nev-err">⚠ {err}</p>}
          {busy && <p className="nev-note">fetching the calendar from Apify… (up to a minute)</p>}
          {data && !data.fetched_at && !busy && (
            <p className="nev-note">not fetched yet — it runs at {data.daily_at_ct || '08:15'} CT, or press ↻</p>
          )}
          {Object.entries(byDay).map(([day, rows]) => (
            <div key={day} className="nev-day">
              <div className={`nev-dayhd ${day === today ? 'today' : ''}`}>{dayLabel(day, today)}</div>
              {rows.map((e) => {
                const past = (e.release_ct || '') < nowCt;
                return (
                  <button key={e.id} type="button"
                    className={`nev-row ${past ? 'past' : ''} ${e.status === 'released' ? 'released' : ''}`}
                    onClick={() => setPick(e)} title="open the event">
                    <span className="t">{(e.release_ct || '').slice(11) || '—'}</span>
                    <i className={`imp ${e.importance}`} title={`${e.importance} importance`} />
                    <span className="ev">{e.event}</span>
                    <span className="ag">{e.agency}</span>
                    {e.status === 'released' && e.actual != null
                      ? <span className="act">{value(e.actual)}</span>
                      : e.previous != null && <span className="prev">prev {value(e.previous)}</span>}
                  </button>
                );
              })}
            </div>
          ))}
          {data?.fetched_ct && (
            <p className="nev-note">
              fetched {data.fetched_ct.slice(5)} CT ({data.trigger}) · times CT · ● high ○ medium
              {(data.notices || []).length > 0 && (
                <span title={(data.notices || []).join('\n')}> · {data.notices.length} note{data.notices.length > 1 ? 's' : ''}</span>
              )}
            </p>
          )}
        </div>
      )}

      {pick && <EventCard ev={pick} onClose={() => setPick(null)} />}
    </div>
  );
}

function EventCard({ ev, onClose }) {
  useEffect(() => {
    const onKey = (e) => { if (e.key === 'Escape') onClose(); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);
  const rows = [
    ['When (CT)', ev.release_ct],
    ['When (ET)', ev.release_datetime_et && `${ev.release_date_et} ${ev.release_time_et || ''}`.trim()],
    ['Agency', ev.agency],
    ['Release', ev.release_name],
    ['Period', ev.period],
    ['Category', ev.category && ev.category.replace(/_/g, ' ')],
    ['Importance', ev.importance],
    ['Status', ev.status + (ev.date_confirmed === false ? ' · date tentative' : '')],
    ['Actual', ev.actual != null ? value(ev.actual, ev.unit) : null],
    ['Previous', ev.previous != null ? value(ev.previous, ev.unit) : null],
    ['Series', ev.actual_series],
    ['Vintage', ev.actual_vintage],
    ['Data note', ev.actual_note],
    ['Notes', ev.notes],
  ].filter(([, v]) => v !== null && v !== undefined && v !== '');
  return createPortal(
    <div className="nev-scrim" onClick={onClose}>
      <div className="nev-card" role="dialog" aria-modal="true" aria-label={ev.event}
        onClick={(e) => e.stopPropagation()}>
        <div className="nev-cardhd">
          <i className={`imp ${ev.importance}`} />
          <h3>{ev.event}</h3>
          <button type="button" className="nev-x" onClick={onClose} aria-label="close">×</button>
        </div>
        <dl className="nev-fields">
          {rows.map(([k, v]) => (<React.Fragment key={k}><dt>{k}</dt><dd>{v}</dd></React.Fragment>))}
        </dl>
        {ev.source_url && (
          <a className="nev-src" href={ev.source_url} target="_blank" rel="noopener noreferrer">
            official source ↗
          </a>
        )}
      </div>
    </div>,
    document.body,
  );
}
