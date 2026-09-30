// Every clock the desks show is Central time -- America/Chicago, CST or CDT
// as the season has it -- whatever zone the browser happens to be in.
//
// The desk's rules are written in Central time (the 0DTE cutoff, the
// auto-trader's window, the signal desk's 15:00 report), so a time shown in
// any other zone is one the operator has to convert before it can be compared
// with anything. Two kinds of time reach the pages, and both come through here:
//
//   * INSTANTS from the API: epoch seconds or milliseconds, or ISO strings. A
//     string with no zone is UTC -- the API stores and sends naive UTC.
//   * EXCHANGE WALL CLOCKS: bar times as the venue writes them, with no zone
//     ("2026-09-30T09:30" -- Tradier's are New York time, Yahoo's the
//     listing's own). wallToDesk() is told whose clock it was. A bare date
//     (a daily bar) is a trading day, not an instant, and is left alone.

export const DESK_TZ = 'America/Chicago';
export const EXCHANGE_TZ = { US: 'America/New_York', INDIA: 'Asia/Kolkata' };

const FORMATS = new Map();
function format(zone, opts) {
  const key = `${zone}|${JSON.stringify(opts)}`;
  let f = FORMATS.get(key);
  if (!f) {
    f = new Intl.DateTimeFormat('en-US', { timeZone: zone, ...opts });
    FORMATS.set(key, f);
  }
  return f;
}

function partsIn(zone, date, opts) {
  const out = {};
  format(zone, opts).formatToParts(date).forEach((p) => { out[p.type] = p.value; });
  return out;
}

const HM = { hour: '2-digit', minute: '2-digit', hourCycle: 'h23' };
const HMS = { ...HM, second: '2-digit' };
const YMDHMS = { year: 'numeric', month: '2-digit', day: '2-digit', ...HMS };

// Anything that names an instant, as a Date; null for nothing usable.
export function toDate(v) {
  if (v == null || v === '') return null;
  if (v instanceof Date) return Number.isNaN(v.getTime()) ? null : v;
  if (typeof v === 'number') return Number.isFinite(v) && v > 0 ? new Date(v < 1e12 ? v * 1000 : v) : null;
  const s = String(v).trim();
  if (/^\d+(\.\d+)?$/.test(s)) return toDate(Number(s));
  const iso = /(Z|[+-]\d\d:?\d\d)$/i.test(s) ? s : `${s.replace(' ', 'T')}Z`;
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? null : d;
}

// "14:05" -- 24-hour, as the desk's own schedule is written.
export function deskTime(v, { seconds = false } = {}) {
  const d = toDate(v);
  if (!d) return '';
  const p = partsIn(DESK_TZ, d, seconds ? HMS : HM);
  return seconds ? `${p.hour}:${p.minute}:${p.second}` : `${p.hour}:${p.minute}`;
}

// "Sep 30, 14:05"
export function deskDateTime(v, { seconds = false } = {}) {
  const d = toDate(v);
  if (!d) return '';
  const p = partsIn(DESK_TZ, d, { month: 'short', day: 'numeric', ...(seconds ? HMS : HM) });
  return `${p.month} ${p.day}, ${p.hour}:${p.minute}${seconds ? `:${p.second}` : ''}`;
}

// "2026-09-30" -- the desk's day an instant falls on.
export function deskDay(v) {
  const d = toDate(v);
  if (!d) return '';
  const p = partsIn(DESK_TZ, d, YMDHMS);
  return `${p.year}-${p.month}-${p.day}`;
}

// A scan's stamp: "14:05 CST" today, "Sep 29, 15:40 CST" on an earlier day.
export function deskStamp(v) {
  const d = toDate(v);
  if (!d) return '';
  return deskDay(d) === deskDay(new Date()) ? `${deskTime(d)} CST` : `${deskDateTime(d)} CST`;
}

// ---- exchange wall clocks ---------------------------------------------------

const WALL = /^(\d{4})-(\d{2})-(\d{2})(?:[T ](\d{2}):(\d{2})(?::(\d{2}))?)?/;
const pad = (n) => String(n).padStart(2, '0');

function utcWall(ms) {
  const d = new Date(ms);
  return `${d.getUTCFullYear()}-${pad(d.getUTCMonth() + 1)}-${pad(d.getUTCDate())}`
    + `T${pad(d.getUTCHours())}:${pad(d.getUTCMinutes())}`;
}

// How far `zone`'s wall clock is ahead of UTC at an instant, in ms.
function offsetMs(zone, ms) {
  const p = partsIn(zone, new Date(ms), YMDHMS);
  return Date.UTC(+p.year, +p.month - 1, +p.day, +p.hour % 24, +p.minute, +p.second) - ms;
}

// An exchange wall-clock time as the desk's wall clock: "2026-09-30T08:30".
// New York to Chicago is always one hour -- the two change clocks together --
// which spares the common case (every Tradier bar) the zone arithmetic.
export function wallToDesk(wall, zone = EXCHANGE_TZ.US) {
  const m = WALL.exec(String(wall || ''));
  if (!m) return String(wall || '');
  if (m[4] == null) return `${m[1]}-${m[2]}-${m[3]}`;
  const asUtc = Date.UTC(+m[1], +m[2] - 1, +m[3], +m[4], +m[5], +(m[6] || 0));
  if (zone === EXCHANGE_TZ.US) return utcWall(asUtc - 3_600_000);
  if (zone === DESK_TZ) return utcWall(asUtc);
  // the instant this wall clock names in `zone`, checked once more across a
  // clock change, then read on the desk's clock
  let at = asUtc - offsetMs(zone, asUtc);
  const again = asUtc - offsetMs(zone, at);
  if (again !== at) at = again;
  return utcWall(at + offsetMs(DESK_TZ, at));
}

// Just the desk clock of an exchange wall-clock time: "08:30".
export function wallClock(wall, zone = EXCHANGE_TZ.US) {
  const t = wallToDesk(wall, zone);
  return t.length > 10 ? t.slice(11, 16) : '';
}
