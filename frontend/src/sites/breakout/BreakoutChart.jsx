import React, { useEffect, useMemo, useRef, useState } from 'react';
import { EXCHANGE_TZ, wallToDesk } from '../../shared/cst.js';

// BreakoutRadar's chart: the desk's candle mechanism -- a canvas sized to its
// real laid-out box, hollow up bodies and filled down ones, the price axis on
// the right, a dotted crosshair snapped to the candle under the pointer (see
// MiniChart in TradierSite.jsx) -- drawing the scan's own candles rather than
// fetching Tradier's, with the breakout read on top:
//
//   the consolidation channel   a shaded box over the N candles it spans
//   the breakout candle         an arrow under it, and an outline
//   the 20 and 50 EMA           two lines, in the legend's colours
//
// Pointer events rather than mouse ones, so a finger drags the crosshair on
// an iPhone the way a mouse does on the desk.

const UP = '#10b981';
const UP_LINE = '#34d399';
const DOWN = '#f87171';
const EMA20 = '#6ee7b7';
const EMA50 = '#fbbf24';
const FAINT = '#6b7a90';
const GRID = 'rgba(16, 185, 129, 0.10)';
const FONT = 'ui-monospace, Consolas, monospace';

// Candle times arrive on the exchange's clock and are drawn on the desk's
// (CST); a daily candle is a trading day and keeps its date.
function label(t, timeframe, prev) {
  const day = t.slice(5, 10);
  if (timeframe === '1d') return day;
  const hm = t.slice(11, 16);
  return !prev || prev.slice(0, 10) !== t.slice(0, 10) ? day : hm;
}

export default function BreakoutChart({ data, height = 360 }) {
  const canvasRef = useRef(null);
  const geomRef = useRef(null);
  const [box, setBox] = useState({ w: 0, h: 0 });
  const [cursor, setCursor] = useState(null);
  const [hover, setHover] = useState(null);

  useEffect(() => {
    const cv = canvasRef.current;
    if (!cv) return undefined;
    const read = () => setBox((prev) => (prev.w === cv.clientWidth && prev.h === cv.clientHeight
      ? prev : { w: cv.clientWidth, h: cv.clientHeight }));
    read();
    if (typeof ResizeObserver === 'undefined') return undefined;
    const ro = new ResizeObserver(read);
    ro.observe(cv);
    return () => ro.disconnect();
  }, []);

  const candles = data?.candles || [];
  const tf = data?.timeframe;
  const zone = EXCHANGE_TZ[data?.market] || EXCHANGE_TZ.US;
  const times = useMemo(() => candles.map((c) => (tf === '1d' ? c.t : wallToDesk(c.t, zone))),
    [candles, tf, zone]);

  useEffect(() => {
    const cv = canvasRef.current;
    if (!cv) return;
    const dpr = window.devicePixelRatio || 1;
    const w = box.w || cv.clientWidth || 320;
    const h = box.h || cv.clientHeight || height;
    cv.width = Math.round(w * dpr);
    cv.height = Math.round(h * dpr);
    const ctx = cv.getContext('2d');
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, w, h);
    geomRef.current = null;
    if (!candles.length) return;

    const padL = 4;
    const padR = 58;
    const padT = 24;
    const padB = 22;
    const plotW = w - padL - padR;
    const plotH = h - padT - padB;
    const e20 = data.ema20 || [];
    const e50 = data.ema50 || [];

    let hi = -Infinity;
    let lo = Infinity;
    candles.forEach((c, i) => {
      hi = Math.max(hi, c.h, e20[i] ?? -Infinity, e50[i] ?? -Infinity);
      lo = Math.min(lo, c.l, e20[i] ?? Infinity, e50[i] ?? Infinity);
    });
    if (data.consolidation_high != null) hi = Math.max(hi, data.consolidation_high);
    if (data.consolidation_low != null) lo = Math.min(lo, data.consolidation_low);
    const padSpan = (hi - lo) * 0.07 || 0.5;
    hi += padSpan;
    lo -= padSpan * 1.6;                     // room under the lows for the arrow
    const span = hi - lo || 1;
    const y = (v) => padT + (1 - (v - lo) / span) * plotH;
    const slot = plotW / candles.length;
    const body = Math.max(1.5, Math.min(11, slot * 0.62));
    const cx = (i) => padL + slot * (i + 0.5);
    const decimals = candles[candles.length - 1].c < 1 ? 4 : 2;

    ctx.font = `9px ${FONT}`;
    ctx.textBaseline = 'middle';

    // grid + price axis
    ctx.strokeStyle = GRID;
    ctx.lineWidth = 1;
    ctx.fillStyle = FAINT;
    ctx.textAlign = 'left';
    for (let i = 0; i <= 4; i += 1) {
      const v = lo + (span * i) / 4;
      const yy = Math.round(y(v)) + 0.5;
      ctx.beginPath();
      ctx.moveTo(padL, yy);
      ctx.lineTo(padL + plotW, yy);
      ctx.stroke();
      ctx.fillText(v.toFixed(decimals), padL + plotW + 5, y(v));
    }

    // time axis
    const every = Math.max(1, Math.ceil(candles.length / Math.max(2, Math.floor(plotW / 70))));
    ctx.textAlign = 'center';
    candles.forEach((c, i) => {
      if (i % every !== 0) return;
      ctx.fillText(label(times[i], tf, i >= every ? times[i - every] : null), cx(i), h - padB / 2);
    });

    // the consolidation channel, under everything else
    const at = new Map(candles.map((c, i) => [c.t, i]));
    const s0 = at.get(data.consolidation_start);
    const s1 = at.get(data.consolidation_end);
    if (s0 != null && s1 != null && data.consolidation_high != null) {
      const x0 = padL + slot * s0;
      const x1 = padL + slot * (s1 + 1);
      const y0 = y(data.consolidation_high);
      const y1 = y(data.consolidation_low);
      ctx.fillStyle = 'rgba(16, 185, 129, 0.13)';
      ctx.fillRect(x0, y0, x1 - x0, y1 - y0);
      ctx.setLineDash([4, 3]);
      ctx.strokeStyle = 'rgba(52, 211, 153, 0.85)';
      ctx.strokeRect(Math.round(x0) + 0.5, Math.round(y0) + 0.5, Math.round(x1 - x0), Math.round(y1 - y0));
      ctx.setLineDash([]);
      ctx.fillStyle = UP_LINE;
      ctx.textAlign = 'left';
      ctx.textBaseline = 'bottom';
      ctx.font = `bold 9px ${FONT}`;
      // the verdict's own figure, so the box and the checklist agree
      const pct = data.verdict?.range_pct
        ?? ((data.consolidation_high - data.consolidation_low) / data.consolidation_low) * 100;
      ctx.fillText(`range ${pct.toFixed(1)}%`, x0 + 3, y0 - 2);
      ctx.textBaseline = 'middle';
      ctx.font = `9px ${FONT}`;
    }

    // candles
    candles.forEach((c, i) => {
      const up = c.c >= c.o;
      const color = up ? UP : DOWN;
      const x = cx(i);
      ctx.strokeStyle = color;
      ctx.fillStyle = color;
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.moveTo(Math.round(x) + 0.5, y(c.h));
      ctx.lineTo(Math.round(x) + 0.5, y(c.l));
      ctx.stroke();
      const top = Math.min(y(c.o), y(c.c));
      const hgt = Math.max(1, Math.abs(y(c.c) - y(c.o)));
      if (up) {
        ctx.globalAlpha = 0.3;
        ctx.fillRect(x - body / 2, top, body, hgt);
        ctx.globalAlpha = 1;
        ctx.strokeRect(Math.round(x - body / 2) + 0.5, Math.round(top) + 0.5, Math.round(body), Math.round(hgt));
      } else {
        ctx.fillRect(x - body / 2, top, body, hgt);
      }
    });

    // the two EMAs
    [[e20, EMA20], [e50, EMA50]].forEach(([series, colour]) => {
      ctx.strokeStyle = colour;
      ctx.lineWidth = 1.5;
      ctx.beginPath();
      let started = false;
      series.forEach((v, i) => {
        if (v == null) return;
        if (!started) { ctx.moveTo(cx(i), y(v)); started = true; } else ctx.lineTo(cx(i), y(v));
      });
      ctx.stroke();
    });

    // the breakout candle: an outline and an arrow under it
    const b = at.get(data.breakout_candle_timestamp);
    if (b != null && data.verdict?.rules?.penetration) {
      const c = candles[b];
      const x = cx(b);
      ctx.strokeStyle = UP_LINE;
      ctx.lineWidth = 1.5;
      ctx.shadowColor = UP_LINE;
      ctx.shadowBlur = 8;
      ctx.strokeRect(x - body / 2 - 2.5, y(c.h) - 3, body + 5, y(c.l) - y(c.h) + 6);
      ctx.shadowBlur = 0;
      // under the candle, and under the channel too, so the arrow and its
      // word never sit on the consolidation box
      const floor = data.consolidation_low != null ? Math.max(y(c.l), y(data.consolidation_low)) : y(c.l);
      const tip = floor + 8;
      ctx.fillStyle = UP_LINE;
      ctx.beginPath();
      ctx.moveTo(x, tip);
      ctx.lineTo(x - 6, tip + 10);
      ctx.lineTo(x + 6, tip + 10);
      ctx.closePath();
      ctx.fill();
      ctx.font = `bold 9px ${FONT}`;
      ctx.textAlign = x > padL + plotW - 40 ? 'right' : 'center';
      ctx.textBaseline = 'top';
      ctx.fillText('breakout', x > padL + plotW - 40 ? x + 6 : x, tip + 12);
      ctx.textBaseline = 'middle';
      ctx.font = `9px ${FONT}`;
    }

    // legend
    ctx.textAlign = 'left';
    ctx.font = `10px ${FONT}`;
    let lx = padL + 4;
    [['EMA 20', EMA20], ['EMA 50', EMA50]].forEach(([text, colour]) => {
      ctx.fillStyle = colour;
      ctx.fillRect(lx, padT - 13, 14, 2);
      ctx.fillText(text, lx + 18, padT - 12);
      lx += ctx.measureText(text).width + 34;
    });

    // last close on the axis
    const last = candles[candles.length - 1];
    ctx.fillStyle = last.c >= last.o ? UP : DOWN;
    ctx.fillRect(padL + plotW + 2, y(last.c) - 7, padR - 4, 14);
    ctx.fillStyle = '#04120c';
    ctx.font = `9px ${FONT}`;
    ctx.textAlign = 'left';
    ctx.fillText(last.c.toFixed(decimals), padL + plotW + 5, y(last.c));

    // crosshair
    if (cursor) {
      const i = Math.max(0, Math.min(candles.length - 1, Math.floor((cursor.x - padL) / slot)));
      const cy = Math.max(padT, Math.min(padT + plotH, cursor.y));
      ctx.save();
      ctx.setLineDash([2, 3]);
      ctx.strokeStyle = 'rgba(167, 243, 208, 0.7)';
      ctx.beginPath();
      ctx.moveTo(Math.round(cx(i)) + 0.5, padT);
      ctx.lineTo(Math.round(cx(i)) + 0.5, padT + plotH);
      ctx.moveTo(padL, Math.round(cy) + 0.5);
      ctx.lineTo(padL + plotW, Math.round(cy) + 0.5);
      ctx.stroke();
      ctx.restore();
      ctx.fillStyle = 'rgba(167, 243, 208, 0.92)';
      ctx.fillRect(padL + plotW + 2, cy - 7, padR - 4, 14);
      ctx.fillStyle = '#04120c';
      ctx.fillText((lo + (1 - (cy - padT) / plotH) * span).toFixed(decimals), padL + plotW + 5, cy);
    }
    geomRef.current = { padL, slot };
  }, [candles, data, box, height, cursor, tf, times]);

  const onMove = (e) => {
    const g = geomRef.current;
    const cv = canvasRef.current;
    if (!g || !cv) return;
    const r = cv.getBoundingClientRect();
    const x = e.clientX - r.left;
    setCursor({ x, y: e.clientY - r.top });
    const i = Math.floor((x - g.padL) / g.slot);
    setHover(i >= 0 && i < candles.length ? i : null);
  };

  const i = hover ?? (candles.length ? candles.length - 1 : null);
  const shown = i != null ? candles[i] : null;
  return (
    <div className="brc">
      <div className="brc-read" aria-live="off">
        {shown ? (
          <>
            <span>{times[i].replace('T', ' ')}{tf === '1d' ? '' : ' CST'}</span>
            <span>O {shown.o}</span><span>H {shown.h}</span><span>L {shown.l}</span>
            <span className={shown.c >= shown.o ? 'up' : 'down'}>C {shown.c}</span>
            <span className="e20">20 {data.ema20?.[i] ?? '—'}</span>
            <span className="e50">50 {data.ema50?.[i] ?? '—'}</span>
          </>
        ) : <span>&nbsp;</span>}
      </div>
      <canvas ref={canvasRef} className="brc-canvas" style={{ height }}
        onPointerMove={onMove} onPointerDown={onMove}
        onPointerLeave={() => { setCursor(null); setHover(null); }} />
    </div>
  );
}
