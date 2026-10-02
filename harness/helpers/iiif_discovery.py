"""IIIF discovery + verification helpers for mnemosyne.

Read-only helpers to (1) verify that a candidate IIIF Presentation manifest
really answers 200 with valid IIIF JSON (v2 "sequences" or v3 "items" +
@context) and (2) extract a rough item count plus a license/rights string, so
the coder can build `config/sources/*.yaml` descriptors with `protocol: iiif`.

Nothing here writes to the remote; it only GETs and parses. Used by the
navigator agent to produce /app/data/collections/iiif-candidatures.json.

2026-10-02: added a *browser-fetch* verification path. Several institutions
(e.g. Qatar Digital Library) answer a valid IIIF 200 only to a real browser
and refuse generic bot User-Agents. `verify_manifest_browser()` runs the GET
inside the attached Chrome via `fetch()` (read-only observation) so those
manifests can still be verified without weakening the requests path.
"""

from __future__ import annotations

import json
import re
import time

import requests

UA = (
    "mnemosyne-research-bot/1.0 "
    "(https://github.com/Antonio-Faure/mnemosyne; opensource research aggregator)"
)
HEADERS = {
    "User-Agent": UA,
    "Accept": "application/json, application/ld+json, */*;q=0.8",
}

_LIC_PATTERNS = [
    re.compile(r'"license"\s*:\s*"([^"]+)"'),
    re.compile(r'"rights"\s*:\s*"([^"]+)"'),
    re.compile(r'"attribution"\s*:\s*"([^"]+)"'),
]


def fetch_manifest(url: str, timeout: int = 30) -> requests.Response | None:
    """GET a manifest URL, returning the Response or None on hard failure."""
    for attempt in range(3):
        try:
            r = requests.get(url, headers=HEADERS, timeout=timeout,
                             allow_redirects=True)
            if r.status_code == 200:
                return r
        except Exception:  # noqa: BLE001
            pass
        time.sleep(1.0 * (attempt + 1))
    return None


def _analyze(text: str) -> dict:
    """Parse IIIF manifest JSON text into the standard result dict."""
    out = {"ok": False, "version": None, "items": 0, "license": None,
           "label": None, "error": None}
    try:
        data = json.loads(text)
    except Exception as exc:  # noqa: BLE001
        out["error"] = f"not_json:{exc}"[:80]
        return out

    has_ctx = "@context" in data
    if "sequences" in data:
        out["version"] = "2"
        out["items"] = sum(len(s.get("canvases", [])) for s in data["sequences"])
    elif "items" in data:
        out["version"] = "3"
        out["items"] = len(data["items"])

    is_iiif_manifest = "sc:Manifest" in text or "Manifest" in str(data.get("type", ""))
    if has_ctx and (out["version"] is not None or is_iiif_manifest):
        out["ok"] = True
    elif not has_ctx:
        out["error"] = "no_iiif_context"

    for pat in _LIC_PATTERNS:
        m = pat.search(text)
        if m:
            out["license"] = m.group(1)
            break
    if not out["license"]:
        for m in data.get("metadata", []) or []:
            lab = str(m.get("label", "")).lower()
            if any(k in lab for k in ("licen", "right", "attribut", "credit")):
                val = m.get("value")
                if isinstance(val, list):
                    val = " ".join(str(v) for v in val)
                out["license"] = str(val)[:200]
                break
    out["label"] = data.get("label")
    return out


def verify_manifest(url: str) -> dict:
    """Verify a IIIF Presentation manifest via requests (bot UA).

    Returns dict keys: ok, status, version ('2'|'3'|None), items (int),
    license (str|None), label (str|None), error (str|None).
    """
    out = {"ok": False, "status": None, "version": None, "items": 0,
           "license": None, "label": None, "error": None}
    r = fetch_manifest(url)
    if r is None:
        out["error"] = "no_200_response"
        return out
    out["status"] = r.status_code
    out.update(_analyze(r.text))
    return out


def fetch_manifest_browser(url: str, timeout: int = 40) -> str | None:
    """GET a URL from inside the attached Chrome (real browser UA/cookies).

    Read-only observation: it only performs a GET and returns the body text.
    Useful when a server refuses generic bot User-Agents. Returns the response
    body (str) or None if the fetch fails / the page is not a usable context.
    """
    from browser_harness.helpers import js

    snippet = (
        "(async () => {"
        " try {"
        "  const ctl = new AbortController();"
        f"  const t = setTimeout(() => ctl.abort(), {int(timeout * 1000)});"
        f"  const r = await fetch({url!r}, {{headers:{{'Accept':'application/json,application/ld+json,*/*'}}, signal: ctl.signal}});"
        "  clearTimeout(t);"
        "  const t2 = await r.text();"
        "  return JSON.stringify({status:r.status, body:t2});"
        " } catch(e){ return JSON.stringify({status:0, error:String(e)}); }"
        "})()"
    )
    raw = js(snippet)
    if not raw:
        return None
    try:
        obj = json.loads(raw) if isinstance(raw, str) else raw
    except Exception:  # noqa: BLE001
        return None
    if isinstance(obj, dict) and obj.get("status") == 200:
        return obj.get("body")
    return None


def verify_manifest_browser(url: str) -> dict:
    """Verify a manifest by fetching it inside the attached browser."""
    out = {"ok": False, "status": None, "version": None, "items": 0,
           "license": None, "label": None, "error": None, "via": "browser"}
    body = fetch_manifest_browser(url)
    if body is None:
        out["error"] = "browser_no_200"
        return out
    out["status"] = 200
    out.update(_analyze(body))
    return out


def verify_manifest_auto(url: str) -> dict:
    """Try requests first; fall back to an in-browser fetch on failure."""
    v = verify_manifest(url)
    if v["ok"]:
        return v
    b = verify_manifest_browser(url)
    if b["ok"]:
        return b
    return v  # report the requests-path error, which is the common case


def check_many(candidates: list[dict], use_browser_fallback: bool = False) -> list[dict]:
    """Verify a list of {institution, collection, manifest_url, ...}.

    Returns enriched copies with verification fields filled in. With
    `use_browser_fallback=True`, fall back to an in-browser fetch for manifests
    that refuse the bot User-Agent (requires an attached Chrome tab).
    """
    results = []
    for c in candidates:
        v = (verify_manifest_auto(c["manifest_url"]) if use_browser_fallback
             else verify_manifest(c["manifest_url"]))
        row = dict(c)
        row["status"] = v["status"]
        row["iiif_version"] = v["version"]
        row["items_hint"] = v["items"] or c.get("items_hint")
        row["license"] = c.get("license") or v["license"] or "unknown"
        row["verified"] = v["ok"]
        if v.get("via"):
            row["verified_via"] = v["via"]
        if v["error"]:
            row["error"] = v["error"]
        results.append(row)
        time.sleep(0.5)
    return results
