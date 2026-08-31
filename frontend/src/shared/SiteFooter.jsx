import React from 'react';
import { Link } from 'react-router-dom';
import { GUIDES_ENABLED } from '../config.js';

// Required on every page: © Tradier Bot — by Sampath.
// `overlay` pins it to the bottom of full-screen 3D sites instead of flowing.
// (External apps live in the header's "apps" burger, not here.)
export default function SiteFooter({ overlay = false, style = {}, showGuide = true, guideTo = '/guide' }) {
  return (
    <footer
      className={`site-footer ${overlay ? 'fixed bottom-0 left-0 right-0 pointer-events-auto' : ''}`}
      style={style}
    >
      <span>
        © {new Date().getFullYear()} <b>Tradier Bot</b> — by Sampath
      </span>
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
