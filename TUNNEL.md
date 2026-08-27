# Reaching the desk from anywhere

The app keeps running on your machine; a Cloudflare tunnel gives it a public
HTTPS address. Nothing is hosted elsewhere, no credentials leave the folder,
and the moment your PC sleeps the link goes dead.

Double-click **`launch.bat`** (or run it). It brings the desk up, publishes
it, prints the address in a banner, copies it to your clipboard, and holds
the window open so it stays on screen:

```bash
launch.bat
```

```
  =================================================================
     https://barely-describing-corn-festival.trycloudflare.com
  =================================================================
```

Closing that window does not stop anything - the desk and the tunnel are
started detached. From a terminal you are already sitting in, the same thing
without the window-hold:

```bash
start.bat --tunnel
```

```
API      pid 11004  http://127.0.0.1:8791   [LIVE TRADING]
Desk     http://127.0.0.1:8791/   (served by the API)
Tunnel   pid 12336  https://automobiles-hoped-emperor-rouge.trycloudflare.com
Docs     http://127.0.0.1:8791/docs
```

`stop.bat` takes the tunnel down first, then the desk, so the link is never
live pointing at a server that is shutting down.

Because a quick-tunnel hostname is random and changes on every restart, the
current one has its own command — output is the bare URL, nothing else, so
it pipes and copies cleanly:

```bash
url.bat
```

`status.bat` shows it too, alongside everything else.

---

## Read this before you share the link

The tunnel puts a desk that can place **real options orders** on the public
internet. Between the internet and your brokerage account there is now
exactly one thing: the password in `customers/sampath/.sam`.

What is protecting it:

- every `/api` call needs a login session — an unauthenticated visitor sees
  the sign-in screen and nothing else
- ten wrong passwords locks that operator for five minutes
- each failed attempt costs a fixed second, so guessing is slow
- Cloudflare terminates TLS, so the link is HTTPS end to end

What is not:

- a ten-character password is the whole of it. If it is a word, change it.
- there is no second factor unless you add Cloudflare Access (below)
- a quick-tunnel URL is unguessable but not secret — anything you paste it
  into can reach your desk

Treat the URL as a credential.

---

## The URL changes on every restart

Quick tunnels get a random hostname that dies with the process. Fine for a
look from your phone; useless as a bookmark, and it makes auto-start
pointless because you would have to come back to this machine to read the
new address.

For a permanent hostname you need a free Cloudflare account with a domain on
it. Then, once:

```bash
cloudflared tunnel login
```

```bash
cloudflared tunnel create tradier-bot
```

```bash
cloudflared tunnel route dns tradier-bot desk.yourdomain.com
```

Write `%USERPROFILE%\.cloudflared\config.yml`:

```yaml
tunnel: tradier-bot
credentials-file: C:\Users\you\.cloudflared\<tunnel-id>.json

ingress:
  - hostname: desk.yourdomain.com
    service: http://127.0.0.1:8791
  - service: http_status:404
```

`start.bat --tunnel` picks that up automatically — it looks for a named
tunnel before falling back to a quick one — and `desk.yourdomain.com` stays
yours. Override the name with `TBOT_TUNNEL_NAME` if you keep several.

---

## Adding a second gate (recommended for live)

With a named tunnel you can put **Cloudflare Access** in front, free for up
to 50 users. Cloudflare then checks you before the request ever reaches your
PC:

    visitor → Cloudflare Access (email one-time code) → your sign-in → desk

In the Cloudflare dashboard: **Zero Trust → Access → Applications → Add an
application → Self-hosted**, point it at `desk.yourdomain.com`, and add one
policy allowing your email address.

That is two independent gates in front of a live brokerage account, and
unauthenticated traffic never touches your machine at all. For a desk that
trades real money over a public URL, this is the configuration to want.

---

## Starting automatically

Only worth doing once you have a stable hostname — otherwise the desk comes
back after a reboot at an address you cannot predict.

```bash
python tools\autostart.py install
```

Registers a Scheduled Task (`TradierBotDesk`) that runs `start.bat --tunnel`
at logon, unelevated. `start` is idempotent, so it is harmless if the desk is
already up.

```bash
python tools\autostart.py status
```

```bash
python tools\autostart.py remove
```

Use `--no-tunnel` to start the desk at logon but keep it off the internet
until you ask.

On Linux/macOS the same command prints a systemd user unit to install; add
`loginctl enable-linger $USER` if it should run without you logged in.

---

## Notes

**Quick tunnels are best-effort.** Cloudflare offers no uptime guarantee on
`trycloudflare.com` and rate-limits abuse. A named tunnel on your own domain
is the supported path.

**Your machine is the whole deployment.** Sleep, hibernate, or a dropped
network takes the desk down — and with it the 10-second stop-loss monitor.
Open positions keep their take-profit (that order rests on Tradier) but
nothing is watching the stop. If you rely on the desk while away, set the
machine never to sleep.

**Sessions end at restart.** They are in-memory, so a reboot signs you out
everywhere — including whatever phone you left logged in.

**Diagnosing.** `var/tunnel.out` is cloudflared's own log. `status.bat` says
whether the process is alive and what URL it published.
