// Client for the Tradier Bot API (FastAPI, port 8791).
// The desk talks to nothing else: no vite middleware, no baked JSON,
// no local configs.
//
// Base URL resolution, in priority order:
//   1. ?api=https://host:8791  (persisted; ?api=off clears — same contract
//      as the legacy sports client, same localStorage key)
//   2. VITE_TRADIER_API build-time env var
//   3. dev/preview default: http://<current hostname>:8791
//   4. same-origin '' (reverse-proxy deployments routing /api to the API)

const API_BASE_KEY = 'api38.base';
const API_KEY_KEY = 'vidura.api.key'; // session token / shared X-API-Key

// Vite dev + preview ports for this project. On any of them the page and the
// API are different origins, so the base has to be spelled out; anywhere
// else the page was served by the API and same-origin is correct.
const DEV_PORTS = new Set(['5199', '4199', '5173', '4173']);
// 8791. The API moved off 8790 when it became api_v2 and this fallback did
// not follow, so anything served from a dev port asked a dead address and
// reported the backend as unreachable while it was running perfectly.
const API_PORT = '8791';
// The port it used to be. A base saved by an old `?api=...:8790` outlives the
// change -- localStorage has no idea the API moved -- so the desk stays
// broken until somebody thinks to pass ?api=off. Dropped on sight instead.
const RETIRED_PORTS = [':8790'];

// Chrome resolves "localhost" to ::1 first, and uvicorn binds 0.0.0.0 — IPv4
// only, because Python binds v6-only on Windows so `--host ::` would trade LAN
// access for loopback. Every poll (status, logs) then hits an address nothing
// is listening on: ERR_CONNECTION_REFUSED after a ~1.2s stall each, which is
// what made the app feel hung on refresh. Applied to EVERY branch below, not
// just the default: a base saved earlier by `?api=http://localhost:8790` lives
// in localStorage and would otherwise keep reproducing this forever.
function preferIpv4Loopback(base) {
  return String(base).replace('//localhost:', '//127.0.0.1:');
}

export function apiBase() {
  try {
    const q = new URLSearchParams(window.location.search).get('api');
    if (q !== null) {
      if (q === '' || q === 'off') localStorage.removeItem(API_BASE_KEY);
      else localStorage.setItem(API_BASE_KEY, q.replace(/\/+$/, ''));
    }
    const stored = localStorage.getItem(API_BASE_KEY);
    if (stored) {
      if (RETIRED_PORTS.some((p) => stored.includes(p))) {
        // Points at where the API used to be. Forget it and fall through to
        // the resolution below, which is right by construction.
        localStorage.removeItem(API_BASE_KEY);
      } else {
        return preferIpv4Loopback(stored);
      }
    }
  } catch { /* ignore */ }
  const built = import.meta.env?.VITE_TRADIER_API;
  if (built) return preferIpv4Loopback(built.replace(/\/+$/, ''));
  const { protocol, hostname, port } = window.location;
  if (DEV_PORTS.has(port)) {
    return preferIpv4Loopback(`${protocol}//${hostname}:${API_PORT}`);
  }
  // Served by the API itself (the shipped layout): same origin.
  return '';
}

export class ApiError extends Error {
  constructor(status, detail) {
    super(detail || `HTTP ${status}`);
    this.status = status;
    this.detail = detail;
  }
}

// A key per operator GESTURE, so a double-tap or a retry after a timeout is
// absorbed by the server instead of placing a second order.
function newIdempotencyKey() {
  try { return crypto.randomUUID(); } catch { /* older webview */ }
  return `${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

async function req(method, path, { body, params, timeout = 30000,
                                   idempotencyKey } = {}) {
  let url = apiBase() + '/api/v1' + path;
  if (params) {
    const qs = new URLSearchParams(
      Object.fromEntries(Object.entries(params).filter(([, v]) => v !== undefined && v !== null && v !== ''))
    ).toString();
    if (qs) url += (url.includes('?') ? '&' : '?') + qs;
  }
  const headers = { 'Content-Type': 'application/json' };
  if (idempotencyKey) headers['Idempotency-Key'] = idempotencyKey;
  try {
    const key = localStorage.getItem(API_KEY_KEY);
    if (key) headers['X-API-Key'] = key;
  } catch { /* ignore */ }
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), timeout);
  let resp;
  try {
    resp = await fetch(url, {
      method,
      headers,
      body: body !== undefined ? JSON.stringify(body) : undefined,
      signal: ctrl.signal,
    });
  } finally {
    clearTimeout(timer);
  }
  const ct = resp.headers.get('content-type') || '';
  if (!ct.includes('json')) throw new ApiError(resp.status, 'Backend not reachable (non-JSON response)');
  const data = await resp.json();
  if (!resp.ok) {
    // A dead session is not this call site's problem to render. Sessions live
    // in the API's memory, so every restart signs everyone out mid-session and
    // EVERY polling panel starts throwing at once — which used to paint "Sign
    // in to use this desk" across the whole board while the login screen was
    // never shown. Announce it once, globally, and let the gate take over.
    //
    // Keyed on the server's own login_required marker, not on the status code:
    // a wrong password is also a 401, and /auth/* must be free to report its
    // own failures without tearing the desk down.
    if (resp.status === 401 && data?.login_required && !path.startsWith('/auth/')) {
      sessionExpired(data?.detail || 'Session ended');
    }
    throw new ApiError(resp.status, data?.detail || JSON.stringify(data));
  }
  return data;
}

// ---- session expiry, broadcast once ---------------------------------------
// The gate subscribes; everything else keeps throwing as it always did, so no
// existing call site has to change.
const _expiryListeners = new Set();
let _expiredAt = 0;

export function onSessionExpired(fn) {
  _expiryListeners.add(fn);
  return () => _expiryListeners.delete(fn);
}

function sessionExpired(detail) {
  auth.clearToken();
  // A board mid-poll fires a dozen requests at once and they all come back
  // 401 together. One notification is the truth; twelve is a stampede.
  const now = Date.now();
  if (now - _expiredAt < 3000) return;
  _expiredAt = now;
  _expiryListeners.forEach((fn) => {
    try { fn(detail); } catch { /* a bad listener must not block the rest */ }
  });
}

export const api = {
  get: (path, opts) => req('GET', path, opts),
  post: (path, body, opts) => req('POST', path, { ...opts, body }),
  // Every write that moves money goes through this one.
  send: (path, body, opts) => req('POST', path,
    { ...opts, body, idempotencyKey: newIdempotencyKey() }),
  put: (path, body, opts) => req('PUT', path, { ...opts, body }),
};

// ---- users ---------------------------------------------------------------

const USER_KEY = 'vidura.user.id';

// operatorName() used to read ?operator= from the URL, persist it, and fall
// back to a hardcoded 'sampath'. That parameter chose WHICH OPERATOR'S ACCOUNT
// the desk acted on, so anyone could trade anyone else's book by editing the
// address bar. It is gone, and there is no replacement: the server decides who
// you are from the session and the desk is simply told.
export async function ensureUser() {
  // /auth/me answers identity AND world access in one call. The desk used to
  // ask GET /users (which listed every operator), find itself by name, and
  // create the account if it was missing.
  const me = await api.get('/auth/me');
  try { localStorage.setItem(USER_KEY, me.tenant_id); } catch { /* ignore */ }
  return { ...me, user_id: me.tenant_id };
}

export function storedUserId() {
  try { return localStorage.getItem(USER_KEY) || null; } catch { return null; }
}

// ---- convenience wrappers used by more than one world --------------------

// ---- desk login ----------------------------------------------------------
// The session token rides in the SAME localStorage key and the SAME header
// the shared-key mode already used, so every call above authenticates
// without a single call site changing.
export const auth = {
  token: () => { try { return localStorage.getItem(API_KEY_KEY) || ''; } catch { return ''; } },
  clearToken: () => { try { localStorage.removeItem(API_KEY_KEY); } catch { /* ignore */ } },

  // Open endpoint: is a password needed at all on this server?
  status: () => api.get('/auth/status'),
  // Paper or live, for the sign-in screen to declare before you type.
  health: () => fetch(apiBase() + '/health').then((r) => r.json()),

  async login(username, password) {
    const out = await api.post('/auth/login', { username, password });
    try { localStorage.setItem(API_KEY_KEY, out.token); } catch { /* ignore */ }
    return out;
  },

  me: () => api.get('/auth/me'),

  async logout() {
    try { await api.post('/auth/logout'); } catch { /* the token dies either way */ }
    auth.clearToken();
  },
};

export const vidura = {
  health: () => fetch(apiBase() + '/health').then((r) => r.json()),

  // ---- bot station -------------------------------------------------------
  // The Kalshi bot families the station launches as subprocesses. Every one
  // of them is a script vendored under runtime/prediction-trade/, so these
  // endpoints never reach outside this project.
  bots: () => api.get('/bots'),

  // btc bots (btc15, btc60) — one umbrella, `bot` picks the family member
  // One bot, by key. Each per-family helper below asks about a single
  // hard-coded bot, so btc60, silver15 and oil15 had no status at all —
  // and they return an OBJECT where the caller iterated a list.
  botStatus: (key) => api.get(`/bots/${key}/status`),
  // All bots in one request. Seven per tick was most of the desk's
  // steady-state load, and seven database sessions with it.
  botStatuses: () => api.get('/bots/statuses'),
  btcStatus: (_userId) => api.get('/bots/btc15/status'),
  // The luck bot has no process to start: it is previewed, then confirmed.
  //
  // Both calls scan the entire live board -- ~48,000 markets across ~1,000
  // series -- which runs well past the 30s default and was aborting mid-scan.
  // Placing scans AGAIN to re-check the legs are still live, and may then sit
  // through a 60s stake escalation, so it gets the longer of the two.
  luckPreview: (body) => api.post('/bots/luck/preview', body, { timeout: 300000 }),
  luckPlace: (body) => api.post('/bots/luck/place', body, { timeout: 420000 }),
  // Both of the above now return a job id immediately; this is the poll.
  luckJob: (jobId) => api.get(`/bots/luck/job/${jobId}`),
  // The one ledger every bot writes to, with P&L already banded by window.
  tradeEventLog: (params) => api.get('/bots/event-log', { params }),
  // Launch/stop history from the run table, not from this browser's memory.
  botRuns: (params) => api.get('/bots/runs', { params }),
  btcStart: (bot, body) => api.post(`/bots/${bot}/start`, body),
  btcStop: (bot, body) => api.post(`/bots/${bot}/stop`, body),
  btcLogs: (params) => api.get('/bots/btc15/logs', { params }),
  btcProcesses: (bot) => api.get('/bots/btc15/processes', { params: { bot } }),
  btcKill: (bot) => api.post(`/bots/${bot}/kill`),

  // multi-sport bot
  sportsProcesses: () => api.get('/bots/sports/processes'),
  sportsKill: () => api.post('/bots/sports/kill'),
  sportsConfig: () => api.get('/bots/sports/config'),
  sportsStatus: (_userId) => api.get('/bots/sports/status'),
  sportsStart: (body) => api.post('/bots/sports/start', body),
  sportsStop: (body) => api.post('/bots/sports/stop', body),
  sportsLogs: (params) => api.get('/bots/sports/logs', { params }),
  sportsActiveBets: (userId) => api.get('/bots/sports/active-bets', { params: {} }),
  sportsPerformance: (params) => api.get('/bots/sports/performance', { params }),

  // parlay bot — its own process, bankroll and ledger, so its own spec path
  parleyProcesses: () => api.get('/bots/parley/processes'),
  parleyKill: () => api.post('/bots/parley/kill'),
  parleyStatus: (_userId) => api.get('/bots/parley/status'),
  parleyStart: (body) => api.post('/bots/parley/start', body),
  parleyStop: (body) => api.post('/bots/parley/stop', body),
  parleyLogs: (params) => api.get('/bots/parley/logs', { params }),
  parleyActiveBets: (userId) => api.get('/bots/parley/active-bets', { params: {} }),

  // commodity bots (gold15, silver15, oil15) — same umbrella pattern as BTC
  commodityStatus: (_userId) => api.get('/bots/gold15/status'),
  commodityStart: (bot, body) => api.post(`/bots/${bot}/start`, body),
  commodityStop: (bot, body) => api.post(`/bots/${bot}/stop`, body),
  commodityLogs: (params) => api.get('/bots/gold15/logs', { params }),
  commodityProcesses: (bot) => api.get('/bots/gold15/processes', { params: { bot } }),
  commodityKill: (bot) => api.post(`/bots/${bot}/kill`),
  // live gold/silver/oil DMI call-put readout (the v2 engine's signal) —
  // read-only market data, no user_id needed
  commodityDmiSignals: (force) => api.get('/bots/commodities/signals', { params: { force: force || undefined } }),
  cryptoDmiSignals: (force) => api.get('/bots/crypto/signals', { params: { force: force || undefined } }),

  kalshiClient: (userId) => api.post('/credentials/tradier_sandbox/verify'),
  // live portfolio value (cash + open positions), server-cached ~30s
  portfolio: (userId) => api.get('/portfolio'),
  // daily PV snapshots (one per CST day, written by fresh /portfolio fetches)
  portfolioHistory: (userId) => api.get('/portfolio/history'),
  // settle stale-open ledger rows from Kalshi fills+settlements (all bot
  // families). hours = staleness floor, NOT a lookback window; apply=false
  // previews. Kalshi lookups per row -> generous timeout.
  botsReconcile: (userId, hours = 1, apply = true) =>
    api.post(`/bots/reconcile?hours=${hours}&apply=${apply}`,
      undefined, { timeout: 180000 }),
  recordTrade: (userId, body) => api.post('/trades', body),
  trades: (userId, params) => api.get('/trades', { params }),

  // HOT: top-100 DMI/ADX trend scan. A 100-name bar sweep runs in the
  // background, so this reads a snapshot and never waits on the venue.
  tradierHot: (userId, live, interval, refresh) => api.get('/tradier/hot', {
    params: { live, interval, refresh: refresh || undefined },
  }),
  tradierCommodities: (userId, live, refresh) => api.get('/tradier/commodities', {
    params: { live, refresh: refresh || undefined },
  }),
  // tradier options executor
  // `live` is never persisted anywhere: every call states its venue, so a
  // reload always comes back on the sandbox.
  tradierVenue: (userId) => api.get('/tradier/venue', { params: {} }),
  // market-data-only session id for Tradier's WebSocket (production-only;
  // the account token stays on the server)
  tradierStreamSession: (userId) =>
    api.post(`/tradier/stream/session`),
  // unusual options activity — served from a background sweep, so this
  // returns instantly with whatever snapshot exists
  // today's intraday bars — seeds a chart the socket then extends
  tradierTimesales: (userId, symbol, interval = '1min', live = false, days = 1) =>
    api.get('/tradier/timesales', {
      params: { symbol, interval, live, days },
    }),
  tradierFlow: (userId, live = false, refresh = false) =>
    api.get('/tradier/flow', { params: { live, refresh } }),
  tradierBalance: (userId, live = false) =>
    api.get('/tradier/balance', { params: { live } }),
  tradierChain: (userId, params) => api.get('/tradier/chain', { params: { ...params } }),
  tradierOpen: (body) => api.send('/tradier/positions', body, { timeout: 60000 }),
  // buy one named contract (the flow board already chose it)
  tradierBuyContract: (body) =>
    api.send('/tradier/positions/contract', body, { timeout: 60000 }),
  tradierPositions: (userId, status, venue = 'all', marks = false) =>
    api.get('/tradier/positions', { params: { status, venue, marks } }),
  tradierSweep: (userId) => api.send(`/tradier/positions/sweep`),
  tradierClose: (userId, id, force = false) =>
    api.send(`/tradier/positions/${id}/close?force=${force}`),
  // move a live position's take-profit; re-rests the sell on the venue
  tradierSetTarget: (userId, id, targetPrice) =>
    api.send(`/tradier/positions/${id}/target`,
      { target_price: targetPrice }, { timeout: 30000 }),
  tradierCarryOver: (userId, id, carryOver = true) =>
    api.send(`/tradier/positions/${id}/carryover`,
      { carry_over: carryOver }),
  // desk ticker rail: Tradier batch quotes, yfinance fill for gaps/no-keys
  tradierQuotes: (userId, symbols) =>
    api.get('/tradier/quotes', { params: { symbols } }),

  // SPY/QQQ/SPX level-cross watcher (levels_watcher.py in the day-trade repo)
  levelsStatus: () => api.get('/levels/status'),
  levelsStart: () => api.post('/levels/start'),
  levelsStop: () => api.post('/levels/stop'),

  // opening-range auto-trader (level cross -> confirmed -> managed 0DTE)
  autoTradeStart: (body) => api.post('/tradier/autotrade/start', body),
  autoTradeStop: (userId) => api.post(`/tradier/autotrade/stop`),
  autoTradeStatus: (userId) => api.get('/tradier/autotrade/status', { params: {} }),

  // super research
  superState: (all) => api.get('/super/state', { params: all ? { all: 1 } : undefined }),
  superOn: () => api.post('/super/on'),
  superOff: (category) => api.post('/super/off', category ? { category } : {}),
  superConfig: () => api.get('/super/config'),
  superSetConfig: (enabled) => api.post('/super/config', { enabled }),
  superRegenerate: (categories, force) => {
    const qs = new URLSearchParams();
    if (categories) qs.set('categories', categories);
    if (force) qs.set('force', 'true');
    const q = qs.toString();
    return api.post('/super/regenerate' + (q ? `?${q}` : ''));
  },
  superSignals: (params) => api.get('/super/signals', { params }),
  superSyncNow: () => api.post('/super/sync'),
  superSyncStatus: () => api.get('/super/sync/status'),
  superGex: () => api.get('/super/gex'),
  superGexReload: () => api.post('/super/gex/reload'),
  superGexRefresh: (tickers, persist = true) => {
    const qs = new URLSearchParams();
    if (tickers) qs.set('tickers', tickers);
    if (!persist) qs.set('persist', 'false');
    const q = qs.toString();
    return api.post('/super/gex/refresh' + (q ? `?${q}` : ''), undefined, { timeout: 90000 });
  },
  superGexQuota: () => api.get('/super/gex/quota'),
  superEcon: () => api.get('/super/econ'),
  // SPY 0DTE dealer gamma (getgamma.io). The read is a cheap DB snapshot.
  // Refresh takes no credentials — the vendor endpoint needs none.
  superGex0dte: () => api.get('/super/gex0dte'),
  superGex0dteRefresh: () => api.post('/super/gex0dte/refresh', {}, { timeout: 60000 }),
  // hourly net-gamma history, 08:00–16:00 CST; omit `date` for today
  superGex0dteHistory: (date) =>
    api.get('/super/gex0dte/history' + (date ? `?date=${encodeURIComponent(date)}` : '')),
  superGex0dteHistoryDates: () => api.get('/super/gex0dte/history/dates'),
  // onboard a ticker into a category on the default engines; the B-book build
  // runs detached, so poll superTickerStatus for it
  superAddTicker: (category, ticker, label) =>
    api.post('/super/tickers', { category, ticker, label }, { timeout: 60000 }),
  superTickerStatus: (id) => api.get(`/super/tickers/${encodeURIComponent(id)}/status`),
  // per-category TP/SL race target the engines are scored at
  superEnginePct: () => api.get('/super/engine-pct'),
  superSetEnginePct: (category, tp_pct, sl_pct) =>
    api.post('/super/engine-pct', { category, tp_pct, sl_pct }),
  // desk-wide A/B admission gates (tp-before-sl %) — engine_common constants
  superEngineGates: () => api.get('/super/engine-gates'),
  superSetEngineGates: (a_tpsl, b_tpsl) =>
    api.post('/super/engine-gates', { a_tpsl, b_tpsl }),
  superRegenerateStatus: () => api.get('/super/regenerate/status'),
  // server-cached (12h TTL) — a cold sweep is ~100 yfinance calls, so allow
  // headroom on the rare miss rather than aborting at the 30s default
  superEarnings: (hours = 24, refresh = false) =>
    api.get('/super/earnings', { params: { hours, refresh: refresh || undefined }, timeout: 120000 }),
  superSnapshots: (params) => api.get('/super/snapshots', { params }),
  superQuote: (ticker) => api.get(`/super/quote/${encodeURIComponent(ticker)}`),

};
