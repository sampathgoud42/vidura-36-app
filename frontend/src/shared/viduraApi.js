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

import { botRunning, forgetExperience, liteRunning } from './experience.js';

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

// What Cloudflare answers in the desk's place when its machine is not there:
// 530 when the tunnel has no connector, 502/52x when nothing answers behind
// it. Always an HTML page, never the desk's JSON -- so "non-JSON response" was
// true and told nobody anything. The edge Worker's sign-in says the same.
const ORIGIN_DOWN = new Set([502, 503, 504, 520, 521, 522, 523, 524, 530]);
export const DESK_OFFLINE = 'The desk is not answering: its computer may be asleep or '
  + 'offline, or the desk may be restarting. Try again in a moment.';

function offlineError(status) {
  const e = new ApiError(status, DESK_OFFLINE);
  e.offline = true;
  return e;
}

// A key per operator GESTURE, so a double-tap or a retry after a timeout is
// absorbed by the server instead of placing a second order.
function newIdempotencyKey() {
  try { return crypto.randomUUID(); } catch { /* older webview */ }
  return `${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

// ---- Lightweight mode -----------------------------------------------------
// Everything a Lightweight board may ask for: its five panels, the orders they
// place, and signing in. Enforced here, at the one door every request passes,
// so "lightweight" is a property of the traffic and not only of the layout: a
// panel added to a board later cannot quietly start loading in this mode --
// it gets a refusal, and has to be written for it. Prefixes of the path under
// /api/v1; experience.js says when this applies.
const LITE_PATHS = [
  '/auth/',                     // identity and world access
  '/tradier/venue',             // which accounts this operator can trade
  '/tradier/balance',           // buying power, which every order is sized from
  '/tradier/positions',         // managed positions: list, buy, sweep, close, target
  '/tradier/chain',             // the 36 Trades ticket's contract preview
  '/tradier/autotrade/',        // arm, disarm, status
  '/tradier/timesales',         // the chart's bars
  '/tradier/stream/session',    // the chart's live price (market data only)
  '/levels/stop',               // the Tradier desk's 15:00 safety stop
  '/super/quote/',              // the chart's pivots; a tapped ticker's quote
  '/super-signals/session',     // super signals
  '/super-signals/best-pairs',  // the best pair, and the arm form's pairs
  '/super-signals/rank',        // the arm form's signal types
  '/super-signals/desk/',       // the signal desk's start/stop switch (admins)
  // The Bot Station's compact board, which LITE opens it in: the cores and
  // their consoles, the crypto DMI strip and its trades, the luck parley
  // (all under /bots), the Kalshi account's value, and the rain board.
  '/bots',
  '/portfolio',
  '/climate/',
];

function liteRefuses(path) {
  return liteRunning() && !LITE_PATHS.some((p) => path.startsWith(p));
}

// Everything Bot only mode may ask for: the Bot Station's own endpoints and
// nothing of any other world's. A request outside this never leaves.
const BOT_PATHS = [
  '/auth/',                     // identity and world access
  '/bots',                      // bots, their logs and runs, the DMI signals,
                                // signal trades, the luck parley, reconcile
  '/portfolio',                 // the Kalshi account's value and its history
  '/trade-history',             // the account's settled record
  '/climate/',                  // the Rain Today board and its trades
];

function botRefuses(path) {
  return botRunning() && !BOT_PATHS.some((p) => path.startsWith(p));
}

async function req(method, path, { body, params, timeout = 30000,
                                   idempotencyKey } = {}) {
  // Refused before anything is sent. The status is a word rather than a
  // number because no HTTP status is true of a request that never left: the
  // desks print it as the error's badge.
  if (liteRefuses(path)) {
    throw new ApiError('lite',
      `${path.split('?')[0]} is not loaded in Lightweight mode - switch to Regular for it`);
  }
  if (botRefuses(path)) {
    throw new ApiError('bot',
      `${path.split('?')[0]} is not loaded in Bot only mode - switch to Regular for it`);
  }
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
  } catch (e) {
    // Two different failures used to read the same -- "Backend unreachable"
    // -- and they call for opposite responses. A TIMEOUT means the server
    // was reached and is still working: an order may be going through, so
    // retrying blindly is the wrong move. A network failure means nothing
    // got there at all.
    const err = e?.name === 'AbortError'
      ? new ApiError(null, `No answer within ${Math.round(timeout / 1000)}s — the desk `
        + 'may still be working on it. Check before trying again.')
      : new ApiError(null, 'Cannot reach the desk — check your connection, '
        + 'or the desk may be restarting.');
    err.offline = true;
    err.timeout = e?.name === 'AbortError';
    throw err;
  } finally {
    clearTimeout(timer);
  }
  const ct = resp.headers.get('content-type') || '';
  if (!ct.includes('json')) {
    if (ORIGIN_DOWN.has(resp.status)) throw offlineError(resp.status);
    throw new ApiError(resp.status, 'Backend not reachable (non-JSON response)');
  }
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
//
// Lightweight or Regular lives exactly as long as the token does, so both
// places the token changes hands forget it: login() and clearToken(), which
// every way out of a session goes through (sign-out, idle, 401, stale token).
export const auth = {
  token: () => { try { return localStorage.getItem(API_KEY_KEY) || ''; } catch { return ''; } },
  clearToken: () => {
    try { localStorage.removeItem(API_KEY_KEY); } catch { /* ignore */ }
    forgetExperience();
  },

  // Open endpoint: is a password needed at all on this server?
  status: () => api.get('/auth/status'),
  // Paper or live, for the sign-in screen to declare before you type.
  health: () => fetch(apiBase() + '/health').then((r) => r.json()),

  async login(username, password) {
    const out = await api.post('/auth/login', { username, password });
    try { localStorage.setItem(API_KEY_KEY, out.token); } catch { /* ignore */ }
    forgetExperience();              // a new session asks again
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
  // The sports with something open, for the ticket's sport picker. Two
  // listing calls on a cold server cache, so it gets more than the default.
  luckSports: () => api.get('/bots/luck/sports', { timeout: 60000 }),
  // The scheduled Luck parley: on/off, the ticket it places at 9:00 and
  // 18:00 Chicago time, and its latest runs.
  luckSchedule: () => api.get('/bots/luck/schedule'),
  setLuckSchedule: (body) => api.put('/bots/luck/schedule', body),
  // A DMI strip's CALL/PUT, bought by hand on the asset's Kalshi 15-minute
  // market. Placing carries the CONFIRMATION's key -- minted once when the
  // form opens -- so a retry after a lost response is the same order.
  signalTradePreview: (body) => api.post('/bots/signal-trade/preview', body),
  signalTradePlace: (body, key) => api.post('/bots/signal-trade/place', body,
    { idempotencyKey: key }),
  signalTrades: () => api.get('/bots/signal-trades'),
  // One combo across the fifteen-minute markets, from the DMI boards: the
  // list with its default ticks, then the purchase, under the confirmation's
  // key so a retry is the same combo.
  // The daily rain board (climate.rain_forecast): read it, rebuild it
  // (truncate and load, 20-60s), quote one city's market live, and buy YES or
  // NO on it under the confirmation's key so a retry is the same order.
  rainForecast: () => api.get('/climate/rain-forecast'),
  rainForecastRefresh: () => api.post('/climate/rain-forecast/refresh', {}, { timeout: 180000 }),
  rainQuote: (ticker) => api.get(`/climate/rain-forecast/quote?ticker=${encodeURIComponent(ticker)}`),
  rainTrade: (body, key) => api.post('/climate/rain-forecast/trade', body,
    { idempotencyKey: key }),
  combo15Preview: () => api.post('/bots/combo15/preview', {}),
  // Placing STARTS a job and returns; the sheet then reads the answer, up
  // to three minutes, so a slow RFQ can no longer be cut off by a timeout.
  combo15Place: async (body, key, onTick) => {
    let job = await api.post('/bots/combo15/place', body, { idempotencyKey: key });
    const until = Date.now() + 180000;
    while (job && job.status !== 'done' && Date.now() < until) {
      onTick?.(job.elapsed_s);
      await new Promise((r) => setTimeout(r, 1000));
      job = await api.get(`/bots/combo15/place/${encodeURIComponent(key)}`);
    }
    if (!job || job.status !== 'done') {
      throw new ApiError('timeout', 'the combo is still being placed after three minutes '
        + '— check the account before placing it again');
    }
    return job.result;
  },
  // Cash per Kalshi exchange shard, and moving it between them. The move
  // carries the confirmation's key: the exchange's transfer has none.
  kalshiShards: () => api.get('/bots/kalshi/shards'),
  kalshiShardTransfer: (body, key) => api.post('/bots/kalshi/shards/transfer', body,
    { idempotencyKey: key }),
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
  // what the ACCOUNT did: open positions and settled markets straight from
  // Kalshi, with the P&L of both. Not the ledger -- the ledger is what the
  // bots believed at entry, this is what the exchange has. Reaches back over
  // a thousand settlements, so it is slower than the panel it feeds.
  // Served from a two-minute cache; `fresh` (the panel's ↻) reads the exchange now.
  tradeHistory: (fresh) => api.get('/trade-history', { params: { fresh: fresh || undefined }, timeout: 60000 }),
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
  // Best Bets: a 21 EMA on 4-hour bars across a watchlist -- A, deep
  // retracements turning back up; B, fresh crosses. A snapshot like HOT: it
  // answers at once and says `refreshing` while a sweep runs behind it.
  tradierBestBets: (live, refresh) => api.get('/tradier/best-bets', {
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
  // The desks' filter chips, translated for the positions API, which filters on
  // one exact status: "all" is no filter at all and "sl_sold" is the old name
  // for a stop-out. "active" is TWO statuses (pending, open -- what the risk
  // monitor watches), so it is picked out of the whole list here. Sent as-is,
  // "all" and "active" matched no row, and every managed position -- auto-trade
  // entries included -- vanished from both desks.
  tradierPositions: async (userId, status, venue = 'all', marks = false) => {
    const wire = status === 'all' || status === 'active' ? undefined
      : status === 'sl_sold' ? 'sl_filled' : status;
    const page = await api.get('/tradier/positions', { params: { status: wire, venue, marks } });
    if (status !== 'active') return page;
    const items = (page.items || []).filter((p) => p.status === 'pending' || p.status === 'open');
    return { ...page, items, total: items.length };
  },
  // A monitor pass. Safe to poll -- it reads the venue and updates state.
  tradierSweep: (userId) => api.send(`/tradier/positions/sweep`),
  // Closes EVERY open and pending position. Never poll this, never put it on
  // a refresh path: it used to live at /positions/sweep and the desk's own
  // 30s refresh was flattening every order seconds after it was placed.
  tradierFlatten: (userId) => api.send(`/tradier/positions/flatten`),
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
  // News & Events: the US economic calendar (Apify, daily 08:15 CT); the
  // refresh is a paid run, so it waits up to three minutes for the actor.
  econCalendar: () => api.get('/tradier/econ-calendar'),
  econCalendarRefresh: () => api.post('/tradier/econ-calendar/refresh', {}, { timeout: 200000 }),
  levelsStatus: () => api.get('/levels/status'),
  levelsStart: () => api.post('/levels/start'),
  levelsStop: () => api.post('/levels/stop'),

  // opening-range auto-trader (level cross -> confirmed -> managed 0DTE)
  autoTradeStart: (body) => api.post('/tradier/autotrade/start', body),
  // Strategies run side by side: name one to disarm it, none to disarm all.
  autoTradeStop: (userId, strategy) => api.post(`/tradier/autotrade/stop`
    + (strategy ? `?strategy=${encodeURIComponent(strategy)}` : '')),
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
  // SPY dealer gamma from flashAlpha (all expiries -- the free plan has no
  // 0DTE split): read at 08:45 and 11:19 CT, refreshed on demand. The read
  // is a cheap DB snapshot; the refresh spends one of five daily calls.
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

  // ---- super signals: the signal-agent desk (its own project, proxied) ------
  superSignalsSession: (date) =>
    api.get('/super-signals/session', { params: date ? { date } : undefined }),
  // signal types ranked by the report's edge score (today, else yesterday),
  // history-disagreeing types already left out -- the auto-trade form's list
  superSignalsRank: (date) =>
    api.get('/super-signals/rank', { params: date ? { date } : undefined }),
  // the report's best ticker + signal pairs over 30 sessions, best first;
  // { min_win_pct, min_edge, min_net_r } are optional and inclusive
  superSignalsBestPairs: (mins) => api.get('/super-signals/best-pairs', { params: mins }),
  // The signal desk's switch, admins only: start it as its 08:15 task does
  // (a missed morning, or after a stop), or end its day early -- the agents
  // finish their cycle and the day's report is written.
  // New signals to the operator's Telegram channels -- 'vidura' (only the
  // three-star best pairs) or 'super' (every signal), one feed each. The
  // token goes in, once, and never comes back: the feed says only whether
  // one is saved.
  superSignalsTelegram: (channel = 'vidura') =>
    api.get('/super-signals/telegram', { params: { channel } }),
  setSuperSignalsTelegram: (body) => api.put('/super-signals/telegram', body),
  superSignalsTelegramChats: (body) => api.post('/super-signals/telegram/chats', body || {}),
  testSuperSignalsTelegram: (channel = 'vidura') =>
    api.post('/super-signals/telegram/test', {}, { params: { channel } }),
  superSignalsDeskStart: () => api.post('/super-signals/desk/start', {}),
  superSignalsDeskStop: () => api.post('/super-signals/desk/stop', {}),
  superSignalsReports: () => api.get('/super-signals/reports'),
  // a report page is ~1 MB of HTML; give it longer than a board poll
  superSignalsReport: (date) =>
    api.get(`/super-signals/reports/${encodeURIComponent(date)}`, { timeout: 60000 }),

  // ---- BreakoutRadar: eight-rule breakout scans, US + India (Yahoo) -------
  // `params` carries market, timeframe and any thresholds. A read re-judges
  // the cached scan; refresh=true starts a new download in the background.
  breakoutScan: (params) => api.get('/breakout/scan', { params }),
  // a chart outside the last scan is fetched on its own: give it a moment
  breakoutChart: (ticker, params) =>
    api.get(`/breakout/chart/${encodeURIComponent(ticker)}`, { params, timeout: 60000 }),
  // relayed, never stored: the token rides in this one request
  breakoutAlert: (body) => api.post('/breakout/alerts/send', body),

};
