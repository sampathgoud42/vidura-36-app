// SPY 0DTE gamma pusher — readable source for the bookmarklet.
//
// Runs ON the getgamma.io dashboard tab. That page is already logged in, so
// it can read the option chain the vendor blocks from a server; this scrapes
// that response and posts the handful of fields the desk needs to the Tradier
// Bot API. The server never calls getgamma itself — that is the whole point
// of the design, and why the payload is pushed rather than fetched.
//
// Click once to start (pushes immediately, then every 5 minutes).
// Click again on the same tab to stop.
//
// To rebuild the one-liner after editing this file:
//     python tools/make_bookmarklet.py
//
// ---------------------------------------------------------------------------
// CONFIG — the two values that change per machine.
// ---------------------------------------------------------------------------

// Where the desk is. 8791 on this machine (vidura-world still owns 8790).
// A public tunnel URL works here too, which is how you push from a laptop
// that is not the one running the desk.
const API = 'http://127.0.0.1:8791';

// Scoped push token from .env (TBOT_GEX_PUSH_TOKEN). It authorises the two
// gex0dte paths and nothing else — it cannot read positions or place orders.
const TOKEN = 'PASTE_TBOT_GEX_PUSH_TOKEN_HERE';

const EVERY_MS = 5 * 60 * 1000;

(() => {
  // /api/options only means "the option chain" on getgamma's own origin.
  // Anywhere else it is some unrelated endpoint, and the failure is
  // confusing enough to be worth naming.
  if (!/(^|\.)getgamma\.io$/.test(location.hostname)) {
    alert('Vidura 0DTE: run this ON the getgamma dashboard tab.\n\n'
      + 'This tab is ' + location.hostname
      + ', where /api/options is not the option chain.');
    return;
  }

  // Second click = stop. The interval id lives on window so it survives
  // between bookmarklet invocations on the same tab.
  if (window.__vidPush) {
    clearInterval(window.__vidPush);
    window.__vidPush = null;
    alert('Vidura 0DTE auto-push STOPPED');
    return;
  }

  // One id per run, so the server can tell a restarted pusher from a
  // continuing one when it reads the heartbeat trail.
  const session = Math.random().toString(36).slice(2, 10);
  let seq = 0;

  const beat = (ok, reason) => {
    // Liveness is a separate path from data on purpose: routing it through
    // /refresh would stamp a stalled feed as fresh.
    fetch(API + '/api/v1/super/gex0dte/heartbeat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-API-Key': TOKEN },
      body: JSON.stringify({
        session: session, seq: seq, ok: ok, reason: reason || '',
        wall: Date.now(), mono: Math.round(performance.now()),
      }),
    }).catch(() => { /* never let the heartbeat break the push */ });
  };

  const go = async (loud) => {
    seq += 1;
    try {
      const r = await fetch('/api/options?ticker=SPY&mode=0dte&strikes=50',
        { credentials: 'include' });
      const ct = r.headers.get('content-type') || '';
      if (!ct.includes('json')) {
        // A logged-out or expired dashboard returns the HTML login page
        // with a 200, so status alone does not catch this.
        if (loud) {
          alert('Vidura 0DTE: getgamma answered HTTP ' + r.status
            + ' with a page, not the chain.\n\n'
            + 'Reload the dashboard tab and click again.');
        }
        beat(false, 'html-not-json-' + r.status);
        return;
      }
      const d = await r.json();

      // Only what compute() needs. Sending the whole chain would be a much
      // larger POST carrying data the desk has no use for.
      const payload = {
        ticker: d.ticker,
        spotPrice: d.spotPrice,
        mode: d.mode,
        timestamp: d.timestamp,
        marketStatus: d.marketStatus,
        marketOpen: d.marketOpen,
        contracts: d.contracts.map((c) => ({
          contract_type: c.contract_type,
          strike_price: c.strike_price,
          open_interest: c.open_interest,
          greeks: { gamma: c.greeks && c.greeks.gamma },
        })),
      };

      const q = await fetch(API + '/api/v1/super/gex0dte/refresh', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-API-Key': TOKEN },
        body: JSON.stringify({ payload: payload }),
      });
      const v = await q.json().catch(() => ({}));

      if (!q.ok) {
        const why = v.detail || ('HTTP ' + q.status);
        if (loud) {
          alert('Vidura 0DTE push failed: ' + why
            + (q.status === 401
              ? '\n\nThe desk rejected the token. Check TBOT_GEX_PUSH_TOKEN '
                + 'in .env matches this bookmarklet, and that the desk is running.'
              : ''));
        }
        beat(false, String(why).slice(0, 120));
        return;
      }

      beat(true, '');
      if (loud) {
        alert('Vidura 0DTE auto-push STARTED (every 5 min)\n\n'
          + 'spot ' + payload.spotPrice
          + '  ·  ' + payload.contracts.length + ' contracts\n'
          + (v.note || ''));
      }
    } catch (e) {
      // A refused connection here almost always means the desk is not
      // running, or is on a different port than API above.
      if (loud) {
        alert('Vidura 0DTE failed: ' + e + '\n\nIs the desk running at '
          + API + ' ?');
      }
      beat(false, String(e).slice(0, 120));
    }
  };

  go(true);
  window.__vidPush = setInterval(() => go(false), EVERY_MS);
})();
