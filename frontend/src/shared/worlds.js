// The worlds this build ships, and what the browser tab says in each.
//
// Data, not a component, and deliberately its own module: App.jsx needs the
// titles on every route change, and importing them from WorldHeader.jsx
// dragged that whole component — SVG icons, menus and all — into the entry
// bundle, un-splitting a chunk that is otherwise loaded lazily per world.
//
// This list is the switcher's whole source of truth. Add a route in App.jsx
// and an entry here and the world appears in the menu and titles its own tab.

export const WORLDS = [
  { path: '/tradier-platform', label: 'Tradier Platform', icon: '🎯', blurb: 'options executor' },
  { path: '/36-trade-desk', label: '36 Trades', icon: '⚡', blurb: 'mobile trade desk' },
  { path: '/bot-station', label: 'Bot Station', icon: '🤖', blurb: 'kalshi bot control' },
];

// Signed out there is no world yet, so the tab carries the app itself.
export const SIGNED_OUT_TITLE = 'Vidura World - Sam';

export function titleForPath(pathname) {
  const world = WORLDS.find((w) => (pathname || '').startsWith(w.path));
  return world ? world.label : SIGNED_OUT_TITLE;
}
