# Reaching the desk from anywhere

The app keeps running on your machine; a Cloudflare tunnel gives it a public
HTTPS address. Nothing is hosted elsewhere, no credentials leave the folder,
and the moment your PC sleeps the link goes dead.

The desk has a permanent address:

```
https://vidura36.app
```

`www.vidura36.app` reaches the same place. Both are CNAMEs onto the named
tunnel, so the address does not change between restarts -- unlike the random
`trycloudflare.com` hostname the quick tunnel used to hand out.

## Starting it

```bash
start.bat --tunnel
```

The tunnel config lives in the project, not in your home directory:

```
runtime/tunnel/config.yml     the hostname -> service mapping (committed)
runtime/tunnel/*.json         the tunnel credential      (NEVER committed)
runtime/tunnel/cert.pem       the account cert           (NEVER committed)
```

It was moved there from `%USERPROFILE%\.cloudflared` deliberately. A config
in a home directory is a reference outside this folder: it is invisible to
anyone reading the repo, it survives deleting the project, and copying the
project to another machine silently leaves it behind.

The credential JSON is a bearer secret, not a settings file -- anything
holding it can answer as vidura36.app -- so it is gitignored alongside the
cert. `config.yml` contains no secrets and is committed, which is what makes
the setup reproducible.

To run it by hand:

```bash
cloudflared tunnel --config runtime/tunnel/config.yml run tradier-bot
```

`stop.bat` takes the tunnel down first, then the desk, so the link is never
live pointing at a server that is shutting down.

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

**This is a named tunnel, which is the supported path.** The desk used to
publish on a random `trycloudflare.com` hostname -- best-effort, no uptime
guarantee, rate-limited, and a different address after every restart.
vidura36.app is a stable hostname on a zone you control.

**Your machine is the whole deployment.** Sleep, hibernate, or a dropped
network takes the desk down — and with it the stop-loss monitor. This is less
dangerous than it was: exits are now armed as a PAIR, so an armed position
has both a take-profit and a stop resting at the venue and both survive this
machine going away. What does not survive is the monitored fallback, which
covers positions the venue would not accept a stop for. If you rely on the
desk while away, set the machine never to sleep.

**Sessions end at restart.** They are in-memory, so a reboot signs you out
everywhere — including whatever phone you left logged in.

**Diagnosing.** `var/tunnel.out` is cloudflared's own log. `status.bat` says
whether the process is alive and what URL it published.
