import React, { Suspense, lazy, useEffect } from 'react';
import { Routes, Route, useLocation } from 'react-router-dom';
import { titleForPath } from './shared/worlds.js';
import GlobalViduraNotify from './shared/GlobalViduraNotify.jsx';
import DialogHost from './shared/Dialog.jsx';
import LoginGate from './auth/LoginGate.jsx';
import ExperienceGate, { RegularOnly } from './auth/ExperienceGate.jsx';
import { WorldGate, DefaultWorld } from './auth/WorldGate.jsx';

// The desk is the whole app here, but it stays lazy: its bundle is large and
// the branded loader is what the user sees while it arrives.
const WORLD_CODE = {
  '/tradier-platform': () => import('./sites/tradier/TradierSite.jsx'),
  '/36-trade-desk': () => import('./sites/desk36/Desk36Site.jsx'),
  '/bot-station': () => import('./sites/botstation/BotStationSite.jsx'),
  '/breakout-radar': () => import('./sites/breakout/BreakoutSite.jsx'),
};
// A tab opened before a deploy still names the OLD build's files, and a
// deploy replaces them: switching worlds then asks for a file that is gone,
// the import rejects, and with nothing to catch it React empties the page --
// the blank screen only a hard refresh cured. A world's code that will not
// load reloads the page once instead, which fetches the new build. Once per
// RELOAD_GUARD_MS: a file that is truly missing shows the error card below
// rather than reloading forever.
const RELOAD_KEY = 'vidura.reloadedForBuild';
const RELOAD_GUARD_MS = 30000;

function reloadForNewBuild() {
  try {
    const last = Number(sessionStorage.getItem(RELOAD_KEY) || 0);
    if (Date.now() - last < RELOAD_GUARD_MS) return false;
    sessionStorage.setItem(RELOAD_KEY, String(Date.now()));
  } catch { /* storage blocked: reload anyway, once per page load */ }
  window.location.reload();
  return true;
}

const isChunkError = (e) => /dynamically imported module|Importing a module script failed|Failed to fetch|error loading dynamically|ChunkLoadError|Unable to preload/i
  .test(String(e?.message || e));

function lazyWorld(load) {
  return lazy(() => load().catch((e) => {
    // reloading: never resolve, so nothing renders the failure in between
    if (isChunkError(e) && reloadForNewBuild()) return new Promise(() => {});
    throw e;
  }));
}

// Vite's own signal that a preloaded file of a lazy chunk failed.
window.addEventListener('vite:preloadError', (event) => {
  if (reloadForNewBuild()) event.preventDefault();
});

const Tradier = lazyWorld(WORLD_CODE['/tradier-platform']);
const Desk36 = lazyWorld(WORLD_CODE['/36-trade-desk']);
const BotStation = lazyWorld(WORLD_CODE['/bot-station']);
const Breakout = lazyWorld(WORLD_CODE['/breakout-radar']);

// The world this address opens starts downloading now, alongside the sign-in
// check, rather than after it: the lazy import only fired once the gates
// above it had answered, a full round trip later. React.lazy then finds the
// module already loaded (or on its way). A failure here is left to lazy,
// which asks again and reports it where the page can show it.
{
  const here = Object.keys(WORLD_CODE).find((p) => window.location.pathname.startsWith(p));
  if (here) WORLD_CODE[here]().catch(() => {});
}

function Loader() {
  return (
    <div className="fixed inset-0 grid place-items-center bg-[#050510]">
      <div className="flex flex-col items-center gap-4">
        <div className="loader-ring" />
        <span
          className="text-indigo-200/70 tracking-[0.4em] text-xs font-light"
          style={{ fontFamily: 'Outfit, sans-serif' }}
        >
          TRADIER&nbsp;BOT
        </span>
      </div>
    </div>
  );
}

// Anything a world throws while rendering lands here, not on a blank page:
// what went wrong, and a reload. A stale build's missing file reloads by
// itself (above); this is for everything else. Keyed by the path, so moving
// to another world clears it.
class WorldErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { error: null };
  }

  static getDerivedStateFromError(error) {
    return { error };
  }

  componentDidCatch(error) {
    if (isChunkError(error)) reloadForNewBuild();
    console.error('world crashed:', error);   // eslint-disable-line no-console
  }

  render() {
    const { error } = this.state;
    if (!error) return this.props.children;
    return (
      <div className="fixed inset-0 grid place-items-center bg-[#050510] p-4">
        <div className="max-w-md w-full rounded-xl border border-indigo-400/30 bg-[#0b0f24] p-5 text-center"
          style={{ fontFamily: 'Outfit, sans-serif' }}>
          <p className="text-indigo-100 text-base font-semibold mb-2">This page did not load</p>
          <p className="text-indigo-200/70 text-sm mb-4 break-words">
            {isChunkError(error)
              ? 'A newer version of the app is out. Reloading fetches it.'
              : String(error?.message || error).slice(0, 240)}
          </p>
          <button type="button" onClick={() => window.location.reload()}
            className="rounded-lg border border-indigo-400/50 px-5 text-indigo-100 hover:bg-indigo-500/20"
            style={{ minHeight: 44 }}>
            ↻ Reload
          </button>
        </div>
      </div>
    );
  }
}

function RoutedBoundary({ children }) {
  const { pathname } = useLocation();
  const world = pathname.split('/')[1] || '';
  return <WorldErrorBoundary key={world}>{children}</WorldErrorBoundary>;
}

// The tab follows the route. LoginGate overrides it while the desk is
// locked, and restores this on the way back in.
function PageTitle() {
  const { pathname } = useLocation();
  useEffect(() => { document.title = titleForPath(pathname); }, [pathname]);
  return null;
}

export default function App() {
  return (
    // LoginGate renders nothing but itself until the API confirms a session,
    // so the desk's polling never starts for a signed-out browser.
    <LoginGate>
      {/* Then Lightweight or Regular, once per session: nothing below mounts
          until it is answered, and a switch remounts all of it. */}
      <ExperienceGate>
        <PageTitle />
        <GlobalViduraNotify />
        <DialogHost />
        <RoutedBoundary>
        <Suspense fallback={<Loader />}>
          <Routes>
            {/* '/' goes to whichever world this operator actually lands on;
                every world route is behind its own enabled flag, so an old
                bookmark to a disabled world explains itself. Both trading
                worlds carry a Lightweight board of their own; Bot Station
                and BreakoutRadar have none, so they are walled off in that
                mode. */}
            <Route path="/" element={<DefaultWorld />} />
            <Route path="/tradier-platform/*" element={
              <WorldGate id="tradier-platform"><Tradier /></WorldGate>} />
            <Route path="/36-trade-desk/*" element={
              <WorldGate id="36-trade-desk"><Desk36 /></WorldGate>} />
            <Route path="/bot-station/*" element={
              <WorldGate id="bot-station">
                {/* No RegularOnly: Lightweight opens it as the compact board (PV,
                    crypto DMI, luck parley, rain, cores) and asks for nothing else. */}
                <BotStation />
              </WorldGate>} />
            <Route path="/breakout-radar/*" element={
              <WorldGate id="breakout-radar">
                <RegularOnly world="BreakoutRadar"><Breakout /></RegularOnly>
              </WorldGate>} />
            <Route path="*" element={<DefaultWorld />} />
          </Routes>
        </Suspense>
        </RoutedBoundary>
      </ExperienceGate>
    </LoginGate>
  );
}
