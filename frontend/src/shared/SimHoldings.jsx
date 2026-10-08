import React, { useCallback, useEffect, useState } from 'react';
import { vidura } from './viduraApi.js';
import { confirmDialog } from './Dialog.jsx';
import './simHoldings.css';

// The LONG-TERM (SIM) venue's holdings: the simulated account's shares (and
// any option it holds), each with its cost, mark, value and P&L, and a sell.
// Shown only while SIM is the board's venue, and always labelled as
// simulated -- it is never presented as a real account.
const REFRESH_MS = 30000;

const usd = (v) => (v == null ? '—' : `${v < 0 ? '-' : ''}$${Math.abs(v).toLocaleString('en-US', {
  minimumFractionDigits: 2, maximumFractionDigits: 2 })}`);
const qtyText = (q) => (Number.isInteger(q) ? String(q) : q.toFixed(4).replace(/0+$/, ''));

export default function SimHoldings({ reloadKey = 0, touch = false, onError }) {
  const [res, setRes] = useState(null);
  const [busy, setBusy] = useState('');

  const load = useCallback(async () => {
    try { setRes(await vidura.simAccount()); } catch (e) { onError?.(e); }
  }, [onError]);

  useEffect(() => {
    load();
    const id = setInterval(load, REFRESH_MS);
    return () => clearInterval(id);
  }, [load, reloadKey]);

  const sell = async (h) => {
    const ok = await confirmDialog({
      title: `Sell ${qtyText(h.quantity)} ${h.symbol}?`,
      body: `A market sell of the whole simulated holding, about ${usd(h.value)} at the current price. `
        + 'Filled in the regular session; outside it, it waits for the open.',
      notes: ['LONG-TERM (SIM) — simulated, no real money moves.'],
      confirmText: 'Sell', cancelText: 'Keep',
    });
    if (!ok) return;
    setBusy(h.symbol);
    try { await vidura.simSell(h.symbol, h.quantity); await load(); } catch (e) { onError?.(e); }
    finally { setBusy(''); }
  };

  if (!res?.configured) return null;
  const b = res.balances || {};
  const rows = (res.holdings || []).filter((h) => h.asset === 'equity');
  return (
    <section className={`sim-hold${touch ? ' sim-hold--touch' : ''}`} aria-label="LONG-TERM (SIM) holdings">
      <div className="sim-hd">
        <span className="sim-tag">{res.label || 'LONG-TERM (SIM)'}</span>
        <span className="sim-sum">
          equity <b>{usd(b.total_equity)}</b> · cash <b>{usd(b.total_cash)}</b> · holdings <b>{usd(b.market_value)}</b>
          {' · '}open P&amp;L <b className={b.open_pl > 0 ? 'up' : b.open_pl < 0 ? 'down' : ''}>{usd(b.open_pl)}</b>
        </span>
      </div>
      {rows.length === 0 ? (
        <p className="sim-empty">No shares held.</p>
      ) : (
        <div className="sim-wrap">
          <table className="sim-table">
            <thead>
              <tr>
                <th className="tk">symbol</th><th>qty</th><th>avg cost</th><th>mark</th>
                <th>value</th><th>P&amp;L</th><th>%</th><th className="act"><span className="sr">sell</span></th>
              </tr>
            </thead>
            <tbody>
              {rows.map((h) => (
                <tr key={h.symbol}>
                  <td className="tk"><b>{h.symbol}</b></td>
                  <td>{qtyText(h.quantity)}</td>
                  <td>{h.avg_price.toFixed(2)}</td>
                  <td>{h.mark.toFixed(2)}</td>
                  <td>{usd(h.value)}</td>
                  <td className={h.pl > 0 ? 'up' : h.pl < 0 ? 'down' : ''}>{usd(h.pl)}</td>
                  <td className={h.pl > 0 ? 'up' : h.pl < 0 ? 'down' : ''}>
                    {h.pl_pct == null ? '—' : `${h.pl_pct > 0 ? '+' : ''}${h.pl_pct.toFixed(2)}%`}
                  </td>
                  <td className="act">
                    <button type="button" className="sim-sell" disabled={!!busy}
                      onClick={() => sell(h)} title={`sell the simulated ${h.symbol} holding at market`}>
                      {busy === h.symbol ? '…' : 'sell'}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <p className="sim-note">Simulated account — fills against real Tradier quotes; no real money moves.</p>
    </section>
  );
}
