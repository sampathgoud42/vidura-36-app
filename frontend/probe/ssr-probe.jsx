// Render every bot's launch console to a string, in Node, with no browser and
// no login.
//
// It exists because of a bug this project just shipped: a `const` whose
// initialiser read another `const` declared BELOW it. That is a temporal dead
// zone error -- it BUILDS CLEANLY, `vite build` reports success, and it throws
// only when React renders. Every bot console on the desk went blank while the
// build said the change was fine.
//
// A build proves the code parses. This proves it runs.
import { renderToString } from 'react-dom/server';
import React from 'react';
import { BotConsole } from './_console_copy.jsx';

const BOTS = ['btc15', 'btc60', 'sports', 'parley', 'gold15', 'silver15',
  'oil15', 'monitor15'];

const schema = {
  markets: {
    type: 'json',
    default: ['btc-15'],
    choices: [
      { value: 'btc-15', label: 'BTC', group: 'crypto', series: 'KXBTC15M' },
      { value: 'eth-15', label: 'ETH', group: 'crypto', series: 'KXETH15M' },
      { value: 'gold-15', label: 'Gold', group: 'commodities', series: 'KXGOLD15M' },
    ],
  },
  poll_s: { type: 'integer', default: 15 },
};

const versions = [{
  version: 'v1', default: true, exists: true,
  strategy: 'probe strategy', highlights: ['one', 'two'],
}];

const runningStatus = {
  running: true,
  runs: [{
    status: 'running', mode: 'live', pid: 1, bot_version: 'v1',
    started_at: '2026-09-10 16:00:00',
    extra: { config: { bankroll: 50, target_pct: 30, bank_sl_pct: 20 } },
  }],
  session: { pnl_usd: 1, trades_closed: 0, bankroll_pct: 2 },
  since_launch: {
    available: true, pct: 1.5, pnl_usd: 1, bankroll: 50,
    series: ['KXBTC15M'], markets: 1, markets_open: 0,
    staked_usd: 2, mixed_tickers: 0, detail: '',
  },
};

const CASES = [
  ['idle, never run', { cfg: undefined, status: null }],
  ['idle, empty cfg', { cfg: {}, status: { running: false, runs: [] } }],
  ['running live', { cfg: {}, status: runningStatus }],
];

let failed = 0;
for (const key of BOTS) {
  for (const [label, props] of CASES) {
    try {
      renderToString(React.createElement(BotConsole, {
        botKey: key,
        meta: { key, label: key.toUpperCase(), sub: 'probe', accent: '#fff' },
        schema,
        versions,
        onCfg: () => {},
        user: { user_id: 'u' },
        onClose: () => {},
        onChanged: () => {},
        onLogs: () => {},
        ...props,
      }));
      console.log(`  OK   ${key.padEnd(10)} ${label}`);
    } catch (e) {
      failed += 1;
      console.log(`  FAIL ${key.padEnd(10)} ${label}: ${e.message}`);
    }
  }
}
console.log(failed ? `\n${failed} render(s) FAILED` : '\nevery console rendered');
process.exit(failed ? 1 : 0);
