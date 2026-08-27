import React, { useCallback, useEffect, useState } from 'react';
import { vidura } from './viduraApi.js';
import './quotePopup.css';

// Shared live-quote + pivot-levels popup — the same desk popup the Super
// Signals world opens when a ticker is clicked, extracted so other worlds
// (Tradier desk rails) can offer identical ticker links. Self-contained:
// own CSS (qtp-*), data from GET /super/quote/{ticker} (yfinance, keyless,
// server-cached 60s). Theme with the `accent` prop per world.
export default function QuotePopup({ ticker, onClose, onBuy, accent = '#e879f9' }) {
  const [q, setQ] = useState(null);
  const [err, setErr] = useState(null);

  const load = useCallback(async () => {
    setErr(null);
    setQ(null);
    try {
      setQ(await vidura.superQuote(ticker));
    } catch (e) {
      setErr(e?.detail || e?.message || 'quote unavailable');
    }
  }, [ticker]);

  useEffect(() => { load(); }, [load]);

  useEffect(() => {
    const onKey = (e) => { if (e.key === 'Escape') onClose(); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  const up = q && Number(q.change) >= 0;
  const levels = q
    ? [['R3', q.pivots.R3], ['R2', q.pivots.R2], ['R1', q.pivots.R1], ['P', q.pivots.P],
       ['S1', q.pivots.S1], ['S2', q.pivots.S2], ['S3', q.pivots.S3]]
    : [];
  const TEN = {
    above_10min: ['ABOVE_10MIN', '#34d399', 'price is above the last completed 10-minute range'],
    within_10min: ['WITHIN_10MIN', '#fbbf24', 'price is inside the last completed 10-minute range'],
    below_10min: ['BELOW_10MIN', '#f87171', 'price is below the last completed 10-minute range'],
  };
  const ten = q?.ten_min ? TEN[q.ten_min.state] : null;

  return (
    <div className="qtp-backdrop" style={{ '--qtp-accent': accent }} onClick={onClose}
      role="dialog" aria-modal="true" aria-label={`${ticker} quote`}>
      <div className="qtp-card" onClick={(e) => e.stopPropagation()}>
        <button type="button" className="qtp-close" onClick={onClose} aria-label="close">✕</button>
        <p className="qtp-title">{ticker} · INTRADAY DESK</p>

        {!q && !err && <p className="qtp-loading qtp-mono">⏳ fetching live quote…</p>}
        {err && (
          <div className="qtp-err qtp-mono">
            ⚠ {err}
            <button type="button" className="qtp-chip" onClick={load}>retry</button>
          </div>
        )}

        {q && (
          <>
            <div className="qtp-price">
              <b style={{ color: up ? '#34d399' : '#f87171' }}>
                {q.price != null ? q.price.toLocaleString() : '—'}
              </b>
              <span className="qtp-mono qtp-chg" style={{ color: up ? '#34d399' : '#f87171' }}>
                {q.change != null ? `${up ? '+' : ''}${q.change} (${q.change_pct}%)` : ''}
              </span>
              <span className="qtp-mono qtp-cur">{q.currency}</span>
            </div>

            <div className="qtp-badges">
              {ten && (
                <span className="qtp-badge" style={{ '--qt-c': ten[1] }}
                  title={`${ten[2]} — 10min bar H ${q.ten_min.high} / L ${q.ten_min.low}`}>
                  {ten[0]}
                </span>
              )}
              {q.vwap != null && (
                <span className="qtp-badge" style={{ '--qt-c': q.price >= q.vwap ? '#34d399' : '#f87171' }}
                  title="session VWAP from 5-minute bars">
                  VWAP {q.vwap.toLocaleString()} · {q.vwap_dist_pct > 0 ? '+' : ''}{q.vwap_dist_pct}%
                </span>
              )}
            </div>

            <p className="qtp-eyebrow qtp-mono">
              intraday pivots · from {q.prior_session.date} session
              (O {q.prior_session.open} · H {q.prior_session.high} · L {q.prior_session.low} · C {q.prior_session.close})
            </p>
            <div className="qtp-pivots qtp-mono">
              {levels.map(([name, v]) => {
                const isP = name === 'P';
                const nearest = q.price != null && v != null
                  && levels.every(([, o]) => o == null || Math.abs(q.price - v) <= Math.abs(q.price - o));
                return (
                  <div key={name}
                    className={`qtp-lvl ${isP ? 'pivot' : name[0] === 'R' ? 'res' : 'sup'} ${nearest ? 'near' : ''}`}
                    title={nearest ? 'price is nearest this level' : undefined}>
                    <span>{name}</span>
                    <b>{v != null ? v.toLocaleString() : '—'}</b>
                    {q.price != null && v != null && (
                      <small>{q.price >= v ? 'below px' : 'above px'}</small>
                    )}
                  </div>
                );
              })}
            </div>

            <div className="qtp-actions">
              <a className="qtp-chip qtp-tv" href={q.tv_url} target="_blank" rel="noopener noreferrer">
                📊 open in TradingView ↗
              </a>
              <button type="button" className="qtp-chip" onClick={load}>↻ refresh</button>
              {onBuy && (
                <>
                  <button type="button" className="qtp-chip qtp-buy-call"
                    onClick={() => { onBuy(ticker, 'call'); onClose(); }}>buy call</button>
                  <button type="button" className="qtp-chip qtp-buy-put"
                    onClick={() => { onBuy(ticker, 'put'); onClose(); }}>buy put</button>
                </>
              )}
            </div>
            <p className="qtp-meta">yfinance · cached 60s · fetched {String(q.fetched_at).slice(11, 19)} UTC</p>
          </>
        )}
      </div>
    </div>
  );
}
