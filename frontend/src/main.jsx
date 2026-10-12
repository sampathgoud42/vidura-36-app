import React from 'react';
import { createRoot } from 'react-dom/client';
import { BrowserRouter } from 'react-router-dom';
import App from './App.jsx';
import './index.css';
import { startLiveRefresh } from './shared/liveRefresh.js';

// no StrictMode: its dev-only double-mount replays the desk's polling
// effects and doubles every startup request to the API.
createRoot(document.getElementById('root')).render(
  <BrowserRouter>
    <App />
  </BrowserRouter>
);

// a new deploy reaches open pages by itself (shared/liveRefresh.js)
startLiveRefresh();
