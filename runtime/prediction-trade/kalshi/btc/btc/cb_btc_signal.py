import asyncio
import base64
import json
import os
import re
import secrets
import time

import aiohttp
import pandas as pd

try:                                            # standalone runs load their own .env
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

# --- CONFIGURATION ---
PRODUCT_ID = "BTC-USD"
API_HOST   = "api.coinbase.com"

# Coinbase Advanced Trade (CDP) credentials.  When BOTH are set, requests use
# the authenticated /api/v3/brokerage/products endpoint with an ES256 JWT;
# otherwise they fall back to the PUBLIC /api/v3/brokerage/market/products
# endpoint (no auth).  COINBASE_API_PRIVATE_KEY is the EC private-key PEM
# (literal "\n" in the env value is converted to real newlines).
#   COINBASE_API_KEY_NAME     = organizations/<org>/apiKeys/<key-id>
#   COINBASE_API_PRIVATE_KEY  = -----BEGIN EC PRIVATE KEY----- ... -----END EC PRIVATE KEY-----


def _b64url(data: bytes) -> str:
    """Base64url without padding (JWT segment encoding)."""
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _build_cb_jwt(method: str, path: str) -> str | None:
    """
    Build a Coinbase Advanced Trade ES256 JWT for ``method`` + ``path`` (path
    WITHOUT query string), signed with cryptography (no PyJWT dependency).
    Returns None when credentials are absent or signing fails.
    """
    key_name   = os.getenv("COINBASE_API_KEY_NAME", "").strip()
    key_secret = os.getenv("COINBASE_API_PRIVATE_KEY", "").replace("\\n", "\n").strip()
    if not (key_name and key_secret):
        return None
    try:
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import ec
        from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature

        private_key = serialization.load_pem_private_key(key_secret.encode(), password=None)
        now = int(time.time())
        uri = f"{method} {API_HOST}{path}"
        header  = {"alg": "ES256", "typ": "JWT", "kid": key_name,
                   "nonce": secrets.token_hex(16)}
        payload = {"sub": key_name, "iss": "cdp", "nbf": now, "exp": now + 120,
                   "uri": uri}
        signing_input = (
            f"{_b64url(json.dumps(header, separators=(',', ':')).encode())}."
            f"{_b64url(json.dumps(payload, separators=(',', ':')).encode())}"
        )
        der_sig = private_key.sign(signing_input.encode(), ec.ECDSA(hashes.SHA256()))
        r, s = decode_dss_signature(der_sig)
        raw_sig = r.to_bytes(32, "big") + s.to_bytes(32, "big")   # JOSE wants raw r||s
        return f"{signing_input}.{_b64url(raw_sig)}"
    except Exception as e:
        print(f"[cb_btc_signal] JWT build failed: {e}")
        return None


async def fetch_candles_async(session, product_id, granularity, lookback_seconds):
    """Asynchronously fetches candle data from Coinbase Advanced Trade API.

    Uses the authenticated endpoint + ES256 JWT when COINBASE_API_KEY_NAME /
    COINBASE_API_PRIVATE_KEY are set; otherwise the public market-data endpoint.
    """
    end_time = int(time.time())
    start_time = end_time - lookback_seconds

    # Prefer the authenticated endpoint when a JWT can be built; the path used
    # in the JWT's `uri` claim must match the request path exactly (no query).
    auth_path = f"/api/v3/brokerage/products/{product_id}/candles"
    token = _build_cb_jwt("GET", auth_path)
    if token:
        url = f"https://{API_HOST}{auth_path}"
        headers = {"Authorization": f"Bearer {token}"}
    else:
        # PUBLIC market-data endpoint (no auth) — note the `/market/` segment.
        url = f"https://{API_HOST}/api/v3/brokerage/market/products/{product_id}/candles"
        headers = {}

    params = {
        "start": str(start_time),
        "end": str(end_time),
        "granularity": granularity
    }

    try:
        async with session.get(url, params=params, headers=headers) as response:
            if response.status != 200:
                body = await response.text()
                print(f"[cb_btc_signal] {granularity} candles HTTP "
                      f"{response.status}: {body[:160]}")
                return pd.DataFrame()
            data = await response.json()
            candles = data.get('candles', [])
            if not candles:
                print(f"[cb_btc_signal] {granularity} candles empty response")
                return pd.DataFrame()

            df = pd.DataFrame(candles)
            for col in ['open', 'high', 'low', 'close', 'volume']:
                df[col] = df[col].astype(float)
            df = df.iloc[::-1].reset_index(drop=True)
            return df
    except Exception as e:
        print(f"[cb_btc_signal] {granularity} candles fetch error: {e}")
        return pd.DataFrame()

def analyze_timeframe(df):
    """Calculates trend/volume score for a given dataframe."""
    if df.empty or len(df) < 5: return 0
    recent_close, prior_close = df['close'].iloc[-1], df['close'].iloc[-5]
    trend = 1 if recent_close > prior_close else -1
    
    # Volume Confirmation (2x multiplier if volume is expanding)
    recent_vol, avg_vol = df['volume'].iloc[-3:].mean(), df['volume'].mean()
    return trend * 2 if recent_vol > avg_vol else trend

def get_signal(score):
    return "BUY 🟢" if score > 0 else "SELL 🔴" if score < 0 else "NEUTRAL 🟡"

async def run_analysis(verbose: bool = True):
    """
    Fetch + analyze BTC across timeframes and RETURN all 5 outputs:

        {
            "5min":           "BUY 🟢" | "SELL 🔴" | "NEUTRAL 🟡",
            "10min":          ...,
            "15min":          ...,
            "overall_score":  int   (signed sum across all timeframes),
            "live_btc_value": float (latest 5-min close, USD),
        }

    Set ``verbose=False`` to suppress the printout when called as a library.
    """
    # Mapping lookbacks (pulling 100 bars for context)
    timeframes = {
        "5 Min":   {"gran": "ONE_MINUTE", "sec": 5 * 60 * 10},
        "10 Min":  {"gran": "ONE_MINUTE", "sec": 10 * 60 * 10},
        "15 Min":  {"gran": "ONE_MINUTE", "sec": 15 * 60 * 10},
        "30 Min":  {"gran": "FIVE_MINUTE", "sec": 30 * 60 * 10},
        "1 Hour":  {"gran": "FIVE_MINUTE", "sec": 60 * 60 * 10},
        "3 Hour":  {"gran": "FIFTEEN_MINUTE", "sec": 180 * 60 * 10},
        "6 Hour":  {"gran": "THIRTY_MINUTE", "sec": 360 * 60 * 10}
    }

    async with aiohttp.ClientSession() as session:
        tasks = [fetch_candles_async(session, PRODUCT_ID, v["gran"], v["sec"]) for v in timeframes.values()]
        dataframes = await asyncio.gather(*tasks)
        results = dict(zip(timeframes.keys(), dataframes))

        live_btc_value = results["5 Min"]['close'].iloc[-1] if not results["5 Min"].empty else 0.0

        signals = {label: get_signal(analyze_timeframe(df)) for label, df in results.items()}
        overall_score = sum(analyze_timeframe(df) for df in results.values())

        out = {
            "5min":           signals["5 Min"],
            "10min":          signals["10 Min"],
            "15min":          signals["15 Min"],
            "overall_score":  overall_score,
            "live_btc_value": float(live_btc_value),
        }

        if verbose:
            print(f"1) 5-Min Signal:   {out['5min']}")
            print(f"2) 10-Min Signal:  {out['10min']}")
            print(f"3) 15-Min Signal:  {out['15min']}")
            print(f"4) Overall Score:  {out['overall_score']:+}")
            print(f"5) Live BTC Value: ${out['live_btc_value']:,.2f}")

        return out

# Granularity aliases → Coinbase enum, and enum → seconds-per-candle.
_GRAN_ALIAS = {
    "1m": "ONE_MINUTE", "5m": "FIVE_MINUTE", "15m": "FIFTEEN_MINUTE",
    "30m": "THIRTY_MINUTE", "1h": "ONE_HOUR", "2h": "TWO_HOUR",
    "6h": "SIX_HOUR", "1d": "ONE_DAY",
}
_GRAN_SECONDS = {
    "ONE_MINUTE": 60, "FIVE_MINUTE": 300, "FIFTEEN_MINUTE": 900,
    "THIRTY_MINUTE": 1800, "ONE_HOUR": 3600, "TWO_HOUR": 7200,
    "SIX_HOUR": 21600, "ONE_DAY": 86400,
}


def _parse_duration_seconds(v) -> int:
    """'24h'→86400, '5m'→300, '2d'→172800, '90s'→90.  A bare number = hours."""
    if isinstance(v, (int, float)):
        return int(v * 3600)
    m = re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*([smhd]?)\s*", str(v).lower())
    if not m:
        raise ValueError(f"bad duration {v!r} (use e.g. '24h', '30m', '2d')")
    n, unit = float(m.group(1)), (m.group(2) or "h")
    return int(n * {"s": 1, "m": 60, "h": 3600, "d": 86400}[unit])


def _parse_granularity(g) -> str:
    """'5m'→'FIVE_MINUTE'; also accepts the Coinbase enum directly."""
    s = str(g).strip().lower()
    if s in _GRAN_ALIAS:
        return _GRAN_ALIAS[s]
    enum = str(g).strip().upper()
    if enum in _GRAN_SECONDS:
        return enum
    raise ValueError(f"unknown granularity {g!r} (use e.g. '5m','15m','1h')")


async def get_support_resistance(lookback="24h", granularity: str = "5m",
                                 product_id: str = PRODUCT_ID,
                                 verbose: bool = True) -> dict:
    """
    Support/resistance levels for roughly the NEXT 1 hour, derived from the
    past ``lookback`` of ``granularity`` candles using the classic floor-trader
    pivot formula.

    Args:
        lookback     — window string ('24h', '6h', '30m', '2d', …) or a number
                       interpreted as HOURS.
        granularity  — candle size ('1m','5m','15m','30m','1h','2h','6h','1d')
                       or a Coinbase enum.  e.g. get_support_resistance('24h','5m').

    Over the window:  H = highest high, L = lowest low, C = last close.
        Pivot  P  = (H + L + C) / 3
        R1 = 2P − L     S1 = 2P − H
        R2 = P + (H−L)  S2 = P − (H−L)
        R3 = H + 2(P−L) S3 = L − 2(H−P)
    LIVE_PRICE = latest close.

    Returns a dict (floats, rounded to 2dp):
        {"R3","R2","R1","LIVE_PRICE","S1","S2","S3"}
    All zeros on bad args / fetch failure.  ``verbose=False`` silences output.
    """
    _zero = {k: 0.0 for k in ("R3", "R2", "R1", "LIVE_PRICE", "S1", "S2", "S3")}

    try:
        lookback_seconds = _parse_duration_seconds(lookback)
        gran_enum = _parse_granularity(granularity)
    except Exception as e:
        print(f"[cb_btc_signal] support/resistance: {e}")
        return _zero

    # Coinbase returns at most 350 candles per request — clamp the window.
    gran_s = _GRAN_SECONDS[gran_enum]
    max_seconds = 350 * gran_s
    if lookback_seconds > max_seconds:
        print(f"[cb_btc_signal] support/resistance: {lookback}@{granularity} = "
              f"{lookback_seconds // gran_s} candles > 350 cap — clamping to "
              f"{max_seconds // gran_s} candles.")
        lookback_seconds = max_seconds

    async with aiohttp.ClientSession() as session:
        df = await fetch_candles_async(session, product_id, gran_enum, lookback_seconds)

    if df.empty or len(df) < 2:
        if verbose:
            print("[cb_btc_signal] support/resistance: no candle data.")
        return _zero

    H = float(df["high"].max())
    L = float(df["low"].min())
    C = float(df["close"].iloc[-1])
    P = (H + L + C) / 3.0

    out = {
        "R3":         round(H + 2.0 * (P - L), 2),
        "R2":         round(P + (H - L), 2),
        "R1":         round(2.0 * P - L, 2),
        "LIVE_PRICE": round(C, 2),
        "S1":         round(2.0 * P - H, 2),
        "S2":         round(P - (H - L), 2),
        "S3":         round(L - 2.0 * (H - P), 2),
    }

    if verbose:
        print(f"Support/Resistance (next ~1h, from {lookback} of {granularity} candles):")
        print(f"  R3         : ${out['R3']:,.2f}")
        print(f"  R2         : ${out['R2']:,.2f}")
        print(f"  R1         : ${out['R1']:,.2f}")
        print(f"  LIVE_PRICE : ${out['LIVE_PRICE']:,.2f}")
        print(f"  S1         : ${out['S1']:,.2f}")
        print(f"  S2         : ${out['S2']:,.2f}")
        print(f"  S3         : ${out['S3']:,.2f}")

    return out


if __name__ == "__main__":
    asyncio.run(run_analysis())
    asyncio.run(get_support_resistance())