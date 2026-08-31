---
name: vidura36
description: >
  Build, test, and deploy the tradier-bot project to vidura36.app. Use this skill
  whenever making changes that need to go live — frontend edits, bug fixes, new
  features, CSS tweaks, or any code change that requires a build and restart.
  Also use when the user says "deploy", "restart", "push", "ship it", "go live",
  "build and restart", or asks to commit and push changes. This skill enforces
  world sync, iPhone Safari compatibility, clean restarts, and git hygiene on
  every deploy.
---

# Deploy — vidura36.app

This skill governs how changes ship to production. Every deploy follows the same
sequence: sync both worlds, check mobile compatibility, build, clean-restart,
and push to git. Skipping a step risks broken UI on one world, a stale tunnel,
or uncommitted work.

## 1. Sync both worlds

The platform has two worlds that share components but render independently:

| World | File | Role |
|---|---|---|
| Tradier Platform | `frontend/src/sites/tradier/TradierSite.jsx` | Upstream — shared components live here |
| 36 Trades | `frontend/src/sites/desk36/Desk36Site.jsx` | Imports shared components, has its own layout |

Shared components (`HotScan`, `CommoditiesPanel`, `OptionsFlow`, `MiniChart`,
`BuyTicket`) are defined in `TradierSite.jsx` and imported by `Desk36Site.jsx`.

**The rule**: every user-visible change must appear in both worlds. A feature
added to one and missing from the other is a bug. When editing:

- If the change is in a shared component → it flows to both automatically, but
  verify both worlds render it correctly (layout, section order, error states).
- If the change is world-specific (section headers, layout, CSS) → make the
  equivalent change in the other world's file and stylesheet.
- CSS lives in `tradier.css` and `desk36.css` respectively — keep both in sync.

## 2. iPhone Safari compatibility (36 Trades)

The 36 Trades world is the mobile-first desk. It must work flawlessly on iPhone
Safari. These constraints exist because Safari's rendering engine has specific
behaviours that break common CSS patterns.

### Target devices

- iPhone 15 Pro (393×852)
- iPhone 15 Pro Max (430×932)
- iPhone 16 Pro (402×874)
- iPhone 16 Pro Max (440×956)
- iPad (768×1024 and up)

### CSS rules

- `-webkit-` prefixes on `backdrop-filter`, transforms, `overflow-scrolling`
- `-webkit-overflow-scrolling: touch` on scrollable containers
- Touch targets: minimum 44×44px (Apple HIG)
- `env(safe-area-inset-top)`, `env(safe-area-inset-bottom)` for notch and
  home indicator — apply to sticky headers, footers, and fixed elements
- Inputs must be `font-size: 16px` or larger — anything smaller triggers
  Safari's auto-zoom, which breaks the layout
- Never use `position: fixed` inside a scrollable container — Safari moves
  fixed elements with the scroll instead of pinning them
- Avoid CSS `gap` in flex containers without margin fallbacks — older Safari
  versions ignore `gap` in flexbox
- No hover-only interactions — everything reachable by tap or double-tap

### Testing

Before deploying, test the 36 Trades world at mobile viewport sizes using the
Browser pane:

1. Resize to mobile preset (375×812)
2. Check layout, touch targets, scrolling
3. Resize to 430×932 (Pro Max)
4. Verify nothing overflows or clips

## 3. Build and clean restart

The deploy sequence never varies. `appctl.py` manages only its own processes
(tracked by PID files under `var/`) and does not interfere with other apps on
the machine.

### Full sequence (PowerShell)

```powershell
# Step 1: Build frontend
Set-Location D:\_projects\vidura-36-app\frontend
npx vite build

# Step 2: Clean restart with named tunnel
Set-Location D:\_projects\vidura-36-app
python tools\appctl.py restart --tunnel
```

### Verifying the restart

The tunnel output must say:

```
Tunnel   pid XXXXX  named tunnel 'tradier-bot' (stable hostname)
```

If it says `trycloudflare.com` or "quick-tunnel", something is wrong — check
`~/.cloudflared/config.yml` exists and has `tunnel: tradier-bot`.

Never use `kill`, `taskkill`, `Stop-Process`, or any other process-killing
command. `appctl.py restart` handles shutdown cleanly: tunnel first, then desk,
then API, in order.

### Report the URL

After a successful restart, always report:

[https://vidura36.app](https://vidura36.app)

This is the permanent address. Never report a `trycloudflare.com` URL.

## 4. Git — commit and push

After deploy is confirmed working:

```powershell
Set-Location D:\_projects\vidura-36-app
git status
```

Review the output. Then stage and commit:

- Stage specific files by name — never `git add -A` or `git add .`
- Never commit files containing secrets: `.env`, `credentials.json`, API keys,
  `customers/*/.sam` password files
- Write a descriptive commit message (what changed and why)
- Push to origin

```powershell
git add <specific files>
git commit -m "descriptive message

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
git push
```

## 5. The complete deploy checklist

1. Make changes in both worlds (sync)
2. Check 36 Trades mobile CSS rules (Safari compat)
3. `npx vite build` in `frontend/`
4. `python tools\appctl.py restart --tunnel` from project root
5. Verify "named tunnel" in output
6. Report [https://vidura36.app](https://vidura36.app)
7. `git status` → stage → commit → push
