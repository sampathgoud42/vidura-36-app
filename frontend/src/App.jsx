import React, { Suspense, lazy, useEffect } from 'react';
import { Routes, Route, useLocation } from 'react-router-dom';
import { titleForPath } from './shared/worlds.js';
import GlobalViduraNotify from './shared/GlobalViduraNotify.jsx';
import DialogHost from './shared/Dialog.jsx';
import LoginGate from './auth/LoginGate.jsx';
import { WorldGate, DefaultWorld } from './auth/WorldGate.jsx';

// The desk is the whole app here, but it stays lazy: its bundle is large and
// the branded loader is what the user sees while it arrives.
const Tradier = lazy(() => import('./sites/tradier/TradierSite.jsx'));
const Desk36 = lazy(() => import('./sites/desk36/Desk36Site.jsx'));
const BotStation = lazy(() => import('./sites/botstation/BotStationSite.jsx'));

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
      <PageTitle />
      <GlobalViduraNotify />
      <DialogHost />
      <Suspense fallback={<Loader />}>
        <Routes>
          {/* '/' goes to whichever world this operator actually lands on;
              every world route is behind its own enabled flag, so an old
              bookmark to a disabled world explains itself. */}
          <Route path="/" element={<DefaultWorld />} />
          <Route path="/tradier-platform/*" element={
            <WorldGate id="tradier-platform"><Tradier /></WorldGate>} />
          <Route path="/36-trade-desk/*" element={
            <WorldGate id="36-trade-desk"><Desk36 /></WorldGate>} />
          <Route path="/bot-station/*" element={
            <WorldGate id="bot-station"><BotStation /></WorldGate>} />
          <Route path="*" element={<DefaultWorld />} />
        </Routes>
      </Suspense>
    </LoginGate>
  );
}
