// Client for the Tradier Bot API (FastAPI, port 8790).
// The desk talks to nothing else: no vite middleware, no baked JSON,
// no local configs.
//
// Base URL resolution, in priority order:
//   1. ?api=https://host:8790  (persisted; ?api=off clears — same contract
//      as the legacy sports client, same localStorage key)
//   2. VITE_TRADIER_API build-time env var
//   3. dev/preview default: http://<current hostname>:8790
//   4. same-origin '' (reverse-proxy deployments routing /api to the API)

const API_BASE_KEY = 'api38.base';
const API_KEY_KEY = 'vidura.api.key'; // session token / shared X-API-Key

// Vite dev + preview ports for this project. On any of them the page and the
// API are different origins, so the base has to be spelled out; anywhere
// else the page was served by the API and same-origin is correct.
const DEV_PORTS = new Set(['5199', '4199', '5173', '4173']);
const API_PORT = '8790';

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
    if (stored) return preferIpv4Loopback(stored);
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

async function req(method, path, { body, params, timeout = 30000 } = {}) {
  let url = apiBase() + '/api/v1' + path;
  if (params) {
    const qs = new URLSearchParams(
      Object.fromEntries(Object.entries(params).filter(([, v]) => v !== undefined && v !== null && v !== ''))
    ).toString();
    if (qs) url += (url.includes('?') ? '&' : '?') + qs;
  }
  const headers = { 'Content-Type': 'application/json' };
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
  put: (path, body, opts) => req('PUT', path, { ...opts, body }),
};

// ---- users ---------------------------------------------------------------

const USER_KEY = 'vidura.user.id';

// Default operator, overridable per browser (?operator=<name>, persisted) so
// a deployment on any machine can pick its own without a rebuild.
const OPERATOR_KEY = 'vidura.operator';

export function operatorName() {
  try {
    const q = new URLSearchParams(window.location.search).get('operator');
    if (q !== null) {
      if (q === '' || q === 'off') localStorage.removeItem(OPERATOR_KEY);
      else localStorage.setItem(OPERATOR_KEY, q);
    }
    const stored = localStorage.getItem(OPERATOR_KEY);
    if (stored) return stored;
  } catch { /* ignore */ }
  return import.meta.env?.VITE_TRADIER_OPERATOR || 'sampath';
}

export async function ensureUser(username = operatorName()) {
  // Find (or lazily create) the named user; remember the id locally. The
  // server owns the customer-folder layout — no machine paths from here.
  const users = await api.get('/users');
  let user = users.find((u) => u.username.toLowerCase() === username.toLowerCase());
  if (!user) {
    user = await api.post('/users', { username });
  }
  try { localStorage.setItem(USER_KEY, user.user_id); } catch { /* ignore */ }
  return user;
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
  users: () => api.get('/users'),

  // ---- bot station -------------------------------------------------------
  // The Kalshi bot families the station launches as subprocesses. Every one
  // of them is a script vendored under runtime/prediction-trade/, so these
  // endpoints never reach outside this project.
  bots: () => api.get('/bots'),

  // btc bots (btc15, btc60) — one umbrella, `bot` picks the family member
  btcStatus: (userId) => api.get('/bots/btc/status', { params: { user_id: userId } }),
  btcStart: (bot, body) => api.post(`/bots/btc/start?bot=${bot}`, body),
  btcStop: (bot, body) => api.post(`/bots/btc/stop?bot=${bot}`, body),
  btcLogs: (params) => api.get('/bots/btc/logs', { params }),
  btcTrades: (params) => api.get('/bots/btc/trades', { params }),
  btcSync: (userId) => api.post(`/bots/btc/sync-trades?user_id=${userId}`),
  btcProcesses: (bot) => api.get('/bots/btc/processes', { params: { bot } }),
  btcKill: (bot) => api.post(`/bots/btc/kill?bot=${bot}`),

  // multi-sport bot
  sportsProcesses: () => api.get('/bots/sports/processes'),
  sportsKill: () => api.post('/bots/sports/kill'),
  sportsConfig: () => api.get('/bots/sports/config'),
  sportsStatus: (userId) => api.get('/bots/sports/status', { params: { user_id: userId } }),
  sportsStart: (body) => api.post('/bots/sports/start', body),
  sportsStop: (body) => api.post('/bots/sports/stop', body),
  sportsLogs: (params) => api.get('/bots/sports/logs', { params }),
  sportsActiveBets: (userId) => api.get('/bots/sports/active-bets', { params: { user_id: userId } }),
  sportsPerformance: (params) => api.get('/bots/sports/performance', { params }),
  sportsTrades: (params) => api.get('/bots/sports/trades', { params }),
  sportsSync: (userId) => api.post(`/bots/sports/sync-trades?user_id=${userId}`),

  // parlay bot — its own process, bankroll and ledger, so its own spec path
  parleyProcesses: () => api.get('/bots/parley/processes'),
  parleyKill: () => api.post('/bots/parley/kill'),
  parleyStatus: (userId) => api.get('/bots/parley/status', { params: { user_id: userId } }),
  parleyStart: (body) => api.post('/bots/parley/start', body),
  parleyStop: (body) => api.post('/bots/parley/stop', body),
  parleyLogs: (params) => api.get('/bots/parley/logs', { params }),
  parleyActiveBets: (userId) => api.get('/bots/parley/active-bets', { params: { user_id: userId } }),
  parleyTrades: (params) => api.get('/bots/parley/trades', { params }),
  parleySync: (userId) => api.post(`/bots/parley/sync-trades?user_id=${userId}`),

  // commodity bots (gold15, silver15, oil15) — same umbrella pattern as BTC
  commodityStatus: (userId) => api.get('/bots/commodities/status', { params: { user_id: userId } }),
  commodityStart: (bot, body) => api.post(`/bots/commodities/start?bot=${bot}`, body),
  commodityStop: (bot, body) => api.post(`/bots/commodities/stop?bot=${bot}`, body),
  commodityLogs: (params) => api.get('/bots/commodities/logs', { params }),
  commodityTrades: (params) => api.get('/bots/commodities/trades', { params }),
  commoditySync: (userId) => api.post(`/bots/commodities/sync-trades?user_id=${userId}`),
  commodityProcesses: (bot) => api.get('/bots/commodities/processes', { params: { bot } }),
  commodityKill: (bot) => api.post(`/bots/commodities/kill?bot=${bot}`),
  // live gold/silver/oil DMI call-put readout (the v2 engine's signal) —
  // read-only market data, no user_id needed
  commodityDmiSignals: (force) => api.get('/bots/commodities/signals', { params: { force: force || undefined } }),

  kalshiClient: (userId) => api.post(`/users/${userId}/kalshi-client`),
  // live portfolio value (cash + open positions), server-cached ~30s
  portfolio: (userId) => api.get(`/users/${userId}/portfolio`),
  // daily PV snapshots (one per CST day, written by fresh /portfolio fetches)
  portfolioHistory: (userId) => api.get(`/users/${userId}/portfolio/history`),
  // settle stale-open ledger rows from Kalshi fills+settlements (all bot
  // families). hours = staleness floor, NOT a lookback window; apply=false
  // previews. Kalshi lookups per row -> generous timeout.
  botsReconcile: (userId, hours = 1, apply = true) =>
    api.post(`/bots/reconcile?user_id=${userId}&hours=${hours}&apply=${apply}`,
      undefined, { timeout: 180000 }),
  recordTrade: (userId, body) => api.post(`/users/${userId}/trades`, body),
  trades: (userId, params) => api.get(`/users/${userId}/trades`, { params }),

  // HOT: top-100 DMI/ADX trend scan. A 100-name bar sweep runs in the
  // background, so this reads a snapshot and never waits on the venue.
  tradierHot: (userId, live, interval, refresh) => api.get('/tradier/hot', {
    params: { user_id: userId, live, interval, refresh: refresh || undefined },
  }),
  tradierCommodities: (userId, live, refresh) => api.get('/tradier/commodities', {
    params: { user_id: userId, live, refresh: refresh || undefined },
  }),
  // tradier options executor
  // `live` is never persisted anywhere: every call states its venue, so a
  // reload always comes back on the sandbox.
  tradierVenue: (userId) => api.get('/tradier/venue', { params: { user_id: userId } }),
  // market-data-only session id for Tradier's WebSocket (production-only;
  // the account token stays on the server)
  tradierStreamSession: (userId) =>
    api.post(`/tradier/stream/session?user_id=${userId}`),
  // unusual options activity — served from a background sweep, so this
  // returns instantly with whatever snapshot exists
  // today's intraday bars — seeds a chart the socket then extends
  tradierTimesales: (userId, symbol, interval = '1min', live = false, days = 1) =>
    api.get('/tradier/timesales', {
      params: { user_id: userId, symbol, interval, live, days },
    }),
  tradierFlow: (userId, live = false, refresh = false) =>
    api.get('/tradier/flow', { params: { user_id: userId, live, refresh } }),
  tradierBalance: (userId, live = false) =>
    api.get('/tradier/balance', { params: { user_id: userId, live } }),
  tradierChain: (userId, params) => api.get('/tradier/chain', { params: { user_id: userId, ...params } }),
  tradierOpen: (body) => api.post('/tradier/positions', body, { timeout: 60000 }),
  // buy one named contract (the flow board already chose it)
  tradierBuyContract: (body) =>
    api.post('/tradier/positions/contract', body, { timeout: 60000 }),
  tradierPositions: (userId, status, venue = 'all', marks = false) =>
    api.get('/tradier/positions', { params: { user_id: userId, status, venue, marks } }),
  tradierSweep: (userId) => api.post(`/tradier/positions/sweep?user_id=${userId}`),
  tradierClose: (userId, id, force = false) =>
    api.post(`/tradier/positions/${id}/close?user_id=${userId}&force=${force}`),
  // move a live position's take-profit; re-rests the sell on the venue
  tradierSetTarget: (userId, id, targetPrice) =>
    api.post(`/tradier/positions/${id}/target`,
      { user_id: userId, target_price: targetPrice }, { timeout: 30000 }),
  tradierCarryOver: (userId, id, carryOver = true) =>
    api.post(`/tradier/positions/${id}/carryover`,
      { user_id: userId, carry_over: carryOver }),
  // desk ticker rail: Tradier batch quotes, yfinance fill for gaps/no-keys
  tradierQuotes: (userId, symbols) =>
    api.get('/tradier/quotes', { params: { user_id: userId, symbols } }),

  // SPY/QQQ/SPX level-cross watcher (levels_watcher.py in the day-trade repo)
  levelsStatus: () => api.get('/levels/status'),
  levelsStart: () => api.post('/levels/start'),
  levelsStop: () => api.post('/levels/stop'),

  // opening-range auto-trader (level cross -> confirmed -> managed 0DTE)
  autoTradeStart: (body) => api.post('/tradier/autotrade/start', body),
  autoTradeStop: (userId) => api.post(`/tradier/autotrade/stop?user_id=${userId}`),
  autoTradeStatus: (userId) => api.get('/tradier/autotrade/status', { params: { user_id: userId } }),

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
