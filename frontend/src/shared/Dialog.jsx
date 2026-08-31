// In-app replacements for window.confirm / window.prompt.
//
// Native dialogs were a poor fit here: iOS Safari can suppress them, they
// break the world's visual language, and — the reason this exists — two of
// them stacking made a cancelled start look like a dead button.
//
// Promise-based so call sites read the same as before:
//     if (!(await confirmDialog({ ... }))) return;
//     const sym = await promptDialog({ ... });        // null = cancelled
//
// <DialogHost /> is mounted once, app-wide, in App.jsx.

import React, { useCallback, useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import './dialog.css';

let _open = null; // set by DialogHost; null until it mounts

function ask(spec) {
  if (!_open) {
    // Host not mounted (shouldn't happen) — fall back rather than hang the
    // caller on a promise that never settles.
    if (spec.kind === 'prompt') return Promise.resolve(window.prompt(spec.title, spec.defaultValue || ''));
    return Promise.resolve(window.confirm(spec.title));
  }
  return new Promise((resolve) => _open({ ...spec, resolve }));
}

export function confirmDialog(spec) {
  return ask({ ...spec, kind: 'confirm' });
}

export function promptDialog(spec) {
  return ask({ ...spec, kind: 'prompt' });
}

export default function DialogHost() {
  const [spec, setSpec] = useState(null);
  const [value, setValue] = useState('');
  const confirmRef = useRef(null);
  const inputRef = useRef(null);

  useEffect(() => {
    _open = (s) => {
      setValue(s.defaultValue || '');
      setSpec(s);
    };
    return () => { _open = null; };
  }, []);

  const close = useCallback((result) => {
    setSpec((s) => {
      if (s) s.resolve(result);
      return null;
    });
  }, []);

  // focus the safe path first, and lock background scroll while open
  useEffect(() => {
    if (!spec) return undefined;
    const t = setTimeout(() => {
      (spec.kind === 'prompt' ? inputRef.current : confirmRef.current)?.focus();
    }, 30);
    const prev = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => {
      clearTimeout(t);
      document.body.style.overflow = prev;
    };
  }, [spec]);

  useEffect(() => {
    if (!spec) return undefined;
    const onKey = (e) => {
      if (e.key === 'Escape') { e.preventDefault(); close(spec.kind === 'prompt' ? null : false); }
      if (e.key === 'Enter' && spec.kind === 'prompt') { e.preventDefault(); close(value); }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [spec, value, close]);

  if (!spec) return null;

  const isPrompt = spec.kind === 'prompt';
  const cancelValue = isPrompt ? null : false;
  const danger = spec.tone === 'danger';

  return createPortal(
    <div
      className="vwd-backdrop"
      onMouseDown={(e) => { if (e.target === e.currentTarget) close(cancelValue); }}
    >
      <div
        className={`vwd-box ${danger ? 'danger' : ''}`}
        role="dialog"
        aria-modal="true"
        aria-labelledby="vwd-title"
      >
        <h2 className="vwd-title" id="vwd-title">{spec.title}</h2>

        {/* body keeps its newlines — these messages are written as blocks */}
        {spec.body && <div className="vwd-body">{spec.body}</div>}

        {spec.notes?.length > 0 && (
          <ul className="vwd-notes">
            {spec.notes.map((n) => <li key={n}>{n}</li>)}
          </ul>
        )}

        {isPrompt && (
          <input
            ref={inputRef}
            className="vwd-input"
            value={value}
            placeholder={spec.placeholder || ''}
            onChange={(e) => setValue(e.target.value)}
            autoComplete="off"
            autoCapitalize="characters"
            spellCheck="false"
          />
        )}

        <div className="vwd-actions">
          <button type="button" className="vwd-btn" onClick={() => close(cancelValue)}>
            {spec.cancelText || 'Cancel'}
          </button>
          <button
            ref={confirmRef}
            type="button"
            className={`vwd-btn primary ${danger ? 'danger' : ''}`}
            onClick={() => close(isPrompt ? value : true)}
            disabled={isPrompt && !value.trim()}
          >
            {spec.confirmText || 'Continue'}
          </button>
        </div>
      </div>
    </div>,
    document.body
  );
}
