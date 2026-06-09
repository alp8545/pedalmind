#!/usr/bin/env python3
"""Daily Garmin token refresh from a residential IP.

Why this exists: connectapi.garmin.com consistently 429s OAuth2 refreshes
coming from Render's datacenter IPs (11 straight failures observed June 2026),
while the same refresh from a home connection succeeds on the first try.
So the server NEVER refreshes on its own as the primary path — this script,
run daily by a systemd user timer on Alessio's machine, does it instead:

  1. login to PedalMind → JWT
  2. GET  /api/garmin/auth/export-tokens  → authoritative bundle from server DB
  3. garth.resume + refresh_oauth2()      → from residential IP
  4. POST /api/garmin/auth/inject-tokens  → push refreshed bundle, clear backoff

Run with the PedalMind backend venv (needs garth):
  ~/pedalmind/backend/.venv/bin/python ~/pedalmind/scripts/garmin_local_refresh.py

Credentials are read from ~/.config/pedalmind/env (KEY=VALUE lines):
  PEDALMIND_URL=https://pedalmind.onrender.com
  PEDALMIND_EMAIL=...
  PEDALMIND_PASSWORD=...
"""

import base64
import json
import logging
import os
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

CONFIG_FILE = Path.home() / ".config" / "pedalmind" / "env"
STATE_DIR = Path.home() / ".local" / "state" / "pedalmind"
LOG_FILE = STATE_DIR / "garmin_refresh.log"
# Local fallback copy of the last good bundle (in case server DB is empty)
LOCAL_BUNDLE_DIR = Path.home() / ".local" / "share" / "pedalmind" / "garth"

STATE_DIR.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[logging.FileHandler(LOG_FILE), logging.StreamHandler()],
)
log = logging.getLogger("garmin_refresh")


def load_config() -> dict:
    cfg = {}
    for line in CONFIG_FILE.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            cfg[k.strip()] = v.strip()
    return cfg


def http_json(url: str, method: str = "GET", payload: dict | None = None,
              jwt: str | None = None, timeout: int = 120) -> dict:
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    if jwt:
        req.add_header("Authorization", f"Bearer {jwt}")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def retry(fn, attempts=3, base_wait=20, what=""):
    """Retry helper for Render cold starts (~30-50s)."""
    for i in range(attempts):
        try:
            return fn()
        except Exception as e:
            if i == attempts - 1:
                raise
            wait = base_wait * (i + 1)
            log.warning("%s failed (%s) — retry in %ds", what, e, wait)
            time.sleep(wait)


def main() -> int:
    cfg = load_config()
    base = cfg.get("PEDALMIND_URL", "https://pedalmind.onrender.com").rstrip("/")
    email, password = cfg["PEDALMIND_EMAIL"], cfg["PEDALMIND_PASSWORD"]

    # 1. Login (retry: first hit may wake the Render container)
    jwt = retry(
        lambda: http_json(f"{base}/api/auth/login", "POST",
                          {"email": email, "password": password})["access_token"],
        what="login",
    )
    log.info("Logged in to PedalMind")

    # 2. Pull authoritative bundle from server DB (fall back to local copy)
    bundle = None
    try:
        resp = http_json(f"{base}/api/garmin/auth/export-tokens", jwt=jwt)
        bundle = json.loads(base64.b64decode(resp["tokens"]))
        log.info("Pulled bundle from server DB (%d files)", len(bundle))
    except Exception as e:
        log.warning("export-tokens failed (%s) — using local bundle", e)
        if LOCAL_BUNDLE_DIR.exists():
            bundle = {p.name: json.loads(p.read_text())
                      for p in LOCAL_BUNDLE_DIR.glob("*.json")}
    if not bundle:
        log.error("No token bundle available (server or local) — aborting")
        return 1

    # 3. Refresh from residential IP
    import garth
    with tempfile.TemporaryDirectory(prefix="garth_refresh_") as tmp:
        for fname, content in bundle.items():
            (Path(tmp) / fname).write_text(json.dumps(content))
        garth.resume(tmp)
        before = garth.client.oauth2_token.expires_at
        if before - time.time() > 20 * 3600:
            log.info("Access token still fresh (%.1fh left) — refreshing anyway to rotate", (before - time.time()) / 3600)
        garth.client.refresh_oauth2()
        garth.save(tmp)

        new_bundle = {p.name: json.loads(p.read_text())
                      for p in Path(tmp).glob("*.json")}
        t = new_bundle["oauth2_token.json"]
        log.info("Refreshed OK — access %.1fh, refresh %.1fd",
                 (t["expires_at"] - time.time()) / 3600,
                 (t["refresh_token_expires_at"] - time.time()) / 86400)

        # Keep a local fallback copy
        LOCAL_BUNDLE_DIR.mkdir(parents=True, exist_ok=True)
        for fname, content in new_bundle.items():
            (LOCAL_BUNDLE_DIR / fname).write_text(json.dumps(content))

    # 4. Push back to server (clears any backoff state too)
    b64 = base64.b64encode(json.dumps(new_bundle).encode()).decode()
    result = retry(
        lambda: http_json(f"{base}/api/garmin/auth/inject-tokens", "POST",
                          {"tokens": b64}, jwt=jwt),
        what="inject-tokens",
    )
    log.info("Injected: %s (persisted_to_db=%s)",
             result.get("message"), result.get("persisted_to_db"))
    if not result.get("persisted_to_db"):
        log.error("Server did not persist the bundle to DB!")
        return 1

    log.info("Done — PedalMind Garmin auth is healthy for the next ~23h")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        log.exception("Garmin local refresh FAILED")
        sys.exit(1)
