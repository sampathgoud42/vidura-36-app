import React from 'react';
import { Link } from 'react-router-dom';
import { GUIDES_ENABLED, READING_GUIDE_URL } from '../config.js';

// Required on every page: the world, the reading guide, and "Designed by
// Sampath · Copyright 2026" (the credit the old "© Tradier Bot — by Sampath"
// grew into). The year is the copyright's, fixed, not today's.
// `overlay` pins it to the bottom of full-screen 3D sites instead of flowing.
// (External apps live in the header's "apps" burger, not here.)
export default function SiteFooter({ overlay = false, style = {}, showGuide = true, guideTo = '/guide' }) {
  return (
    <footer
      className={`site-footer ${overlay ? 'fixed bottom-0 left-0 right-0 pointer-events-auto' : ''}`}
      style={style}
    >
      <span><b>Tradier Bot</b></span>
      <span className="dot">◆</span>
      <a href={READING_GUIDE_URL} target="_blank" rel="noopener noreferrer"
        className="underline decoration-dotted underline-offset-4 hover:opacity-80"
        title="How to read the Super Signals, Best pairs and SUPERHOT panels (PDF)">
        Reading guide ↗
      </a>
      <span className="dot">◆</span>
      <span>Designed by <b>Sampath</b> · Copyright 2026</span>
      {GUIDES_ENABLED && showGuide && (
        <>
          <span className="dot">◆</span>
          <Link to={guideTo} className="underline decoration-dotted underline-offset-4 hover:opacity-80">
            How it was built
          </Link>
        </>
      )}
    </footer>
  );
}
