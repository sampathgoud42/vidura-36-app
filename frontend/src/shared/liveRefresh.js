// Live refresh: an open page picks up a new deploy by itself.
//
// A build's entry script is content-hashed (/assets/index-<hash>.js) and
// served immutable, so a tab left open keeps running the build it loaded
// until someone hard-refreshes -- the helios moon sat grey over a WIN on
// 2026-10-12 for exactly that reason. Every CHECK_MS this asks the server
// for index.html (no cache) and compares its entry script with the one this
// page is running. When they differ it reloads -- but only when nobody is
// mid-action: no field focused, no dialog open. Otherwise it waits for the
// next check, or for the tab to be hidden, when a reload costs nothing.
//
// Off in the dev server, which has no hashed entry and reloads on its own.

const CHECK_MS = 60 * 1000;
const ENTRY = /\/assets\/index-[\w-]+\.js/;

function runningEntry() {
  for (const s of document.querySelectorAll('script[type="module"][src]')) {
    const m = s.getAttribute('src').match(ENTRY);
    if (m) return m[0];
  }
  return null;
}

async function servedEntry() {
  try {
    const res = await fetch(`/?build-check=${Date.now()}`, { cache: 'no-store' });
    if (!res.ok) return null;
    const m = (await res.text()).match(ENTRY);
    return m ? m[0] : null;
  } catch {
    return null;                      // offline or restarting: ask again later
  }
}

function busy() {
  const el = document.activeElement;
  if (el && (el.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(el.tagName))) return true;
  return !!document.querySelector('[role="dialog"], [aria-modal="true"]');
}

export function startLiveRefresh() {
  const mine = runningEntry();
  if (!mine) return;                  // dev server
  let stale = false;
  const reloadIfSafe = () => {
    if (stale && (document.hidden || !busy())) window.location.reload();
  };
  const check = async () => {
    if (!stale) {
      const served = await servedEntry();
      stale = !!served && served !== mine;
    }
    reloadIfSafe();
  };
  setInterval(check, CHECK_MS);
  document.addEventListener('visibilitychange', () => {
    if (document.hidden) reloadIfSafe();
    else check();
  });
}
