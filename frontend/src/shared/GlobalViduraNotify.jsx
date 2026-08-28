// App-wide push notifications for the Vidura worlds.
//
// Polls the Vidura API for fresh super-signals and bot-run state changes;
// fires the existing Web-Audio sounds (signalSounds.js — kept verbatim)
// plus OS notifications when the user has granted permission. The toggle
// state is shared with the wellness world ('vidura.notify.enabled').

import { useEffect, useRef } from 'react';
import { vidura } from './viduraApi.js';
import { initAudio, playHotSignal, playSignalSound, soundEnabled } from '../signalSounds.js';

const ENABLED_KEY = 'vidura.notify.enabled';

export function notifyEnabled() {
  try { return localStorage.getItem(ENABLED_KEY) === '1'; } catch { return false; }
}

export async function setNotifyEnabled(on) {
  try { localStorage.setItem(ENABLED_KEY, on ? '1' : '0'); } catch { /* ignore */ }
  if (on && typeof Notification !== 'undefined' && Notification.permission === 'default') {
    try { await Notification.requestPermission(); } catch { /* ignore */ }
  }
  window.dispatchEvent(new CustomEvent('vidura-notify-toggle', { detail: { on } }));
}

function osNotify(title, body) {
  if (typeof Notification === 'undefined' || Notification.permission !== 'granted') return;
  try {
    new Notification(title, { body, icon: '/img/thumb-intraday.webp', tag: 'vidura-' + title });
  } catch { /* ignore */ }
}

export default function GlobalViduraNotify() {
  const seen = useRef(null); // Set of signal ids; null until first baseline poll

  useEffect(() => {
    initAudio();
    let stopped = false;

    async function poll() {
      if (stopped || !notifyEnabled()) return;
      try {
        const page = await vidura.superSignals({ days: 1, limit: 100 });
        const ids = new Set(page.items.map((s) => s.id));
        if (seen.current === null) {
          seen.current = ids; // baseline — never alert on first load
          return;
        }
        const fresh = page.items.filter((s) => !seen.current.has(s.id));
        seen.current = ids;
        if (!fresh.length) return;
        const hot = fresh.filter((s) => Number(s.grade) >= 3);
        if (soundEnabled()) {
          if (hot.length) playHotSignal();
          else playSignalSound(fresh[0].direction === 'SHORT' ? 'SHORT' : 'LONG');
        }
        const first = fresh[0];
        osNotify(
          hot.length ? '🔥 Super signal' : 'New signal',
          `${first.ticker} ${first.direction || ''} ${first.combo || ''}`.trim() +
            (fresh.length > 1 ? ` (+${fresh.length - 1} more)` : '')
        );
      } catch { /* backend away — stay silent */ }
    }

    poll();
    const t = setInterval(poll, 30000);
    return () => { stopped = true; clearInterval(t); };
  }, []);

  return null;
}
