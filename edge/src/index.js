// vidura36.app's front door: the desk's web app, served from Cloudflare's
// edge, in front of the named tunnel to the API on the desk's own machine.
//
// Only the web app's own paths are routed to this Worker (wrangler.jsonc), and
// those are static assets: Cloudflare serves them without running this script,
// free and unmetered, and they load even while the desk's machine is asleep.
//
// The API is NOT routed here, and that is the point of the design. A free
// Worker stops answering once it has used its 100,000 requests for the day --
// with run_worker_first, Cloudflare's docs say those requests get a 429 rather
// than falling back -- and the desk polls its API several times a second
// across a session. So /api/* goes to the tunnel exactly as it did before this
// Worker existed, uncapped. Any path left off the route list falls through the
// same way, to a machine that serves the same build itself: a forgotten route
// costs the edge copy of a page, never the page.
//
// The one request that does run this script is signing in, so it can be
// rate-limited here, before a password guess ever reaches the desk.

const LOGIN = '/api/v1/auth/login';

// What Cloudflare answers in the desk's place when its machine is not there:
// 530 when the tunnel has no connector, 502/52x when nothing answers behind it.
const ORIGIN_DOWN = new Set([502, 503, 504, 520, 521, 522, 523, 524, 530]);

const OFFLINE = 'The desk is not answering: its computer may be asleep or offline, '
  + 'or the desk may be restarting. Try again in a moment.';

function json(status, body) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'content-type': 'application/json', 'cache-control': 'no-store' },
  });
}

async function signIn(request, env) {
  // Ten tries a minute per address. The desk has its own lock -- ten wrong
  // passwords lock an operator for five minutes -- and this stands in front
  // of it, so a guesser is turned away before the desk is asked at all.
  // Without the binding (an account where it is unavailable) sign-in still
  // works, guarded by the desk's lock alone.
  if (request.method === 'POST' && env.LOGIN_LIMIT) {
    const ip = request.headers.get('CF-Connecting-IP') || 'unknown';
    const { success } = await env.LOGIN_LIMIT.limit({ key: ip });
    if (!success) {
      return json(429, {
        detail: 'Too many sign-in attempts from this network. Wait a minute and try again.',
      });
    }
  }

  // On to the desk, through the tunnel: fetch() of the incoming request is a
  // subrequest to the zone's origin, and does not come back to this Worker.
  let res;
  try {
    res = await fetch(request);
  } catch {
    return json(503, { detail: OFFLINE, offline: true });
  }
  // The desk answers in JSON. Cloudflare's own error pages are HTML, and the
  // sign-in card should say what they mean rather than "non-JSON response".
  const ct = res.headers.get('content-type') || '';
  if (ORIGIN_DOWN.has(res.status) && !ct.includes('json')) {
    return json(503, { detail: OFFLINE, offline: true });
  }
  return res;
}

export default {
  async fetch(request, env) {
    const { pathname } = new URL(request.url);
    if (pathname === LOGIN) return signIn(request, env);
    // Nothing else is sent to this script. If something is, it is the app.
    return env.ASSETS.fetch(request);
  },
};
