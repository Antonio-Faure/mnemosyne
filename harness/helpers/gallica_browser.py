"""Gallica / BnF — download IIIF images through a REAL browser (Cloudflare bypass).

WHY THIS EXISTS
---------------
gallica.bnf.fr is behind Cloudflare Bot Management. Plain HTTP clients
(requests / urllib) get *intermittent* HTTP 403 from a flagged egress — even
with a full Chrome header set, and even after warming a `__cf_bm` cookie in a
Session (observed: warm session still 403'd). A real Chrome, which solves
Cloudflare's JS challenge and presents a genuine browser TLS/JA3 fingerprint,
consistently gets HTTP 200. The IIIF *metadata* (manifest.json, small JSON) is
often fetchable, but the *image bytes* are what the adversarial resolver needs,
e.g. André Citroën, Agence Mondial 1932, ark:/12148/btv1b9045938h.

This is the "gallica_browser" sibling of the pure-HTTP `gallica` connector:
same fonds, different scope = fetch the IMAGE through a real browser.

PROVEN FACTS (harness Chrome, on gallica.bnf.fr origin, 2026):
  * Plain requests/urllib: 403 (flaky) even with browser headers / __cf_bm.
  * In-page fetch() from a gallica origin: 200 image/jpeg for all targets:
      btv1b9045938h  André Citroën portrait, 1932   5240x7000   1 canvas
      btv1b8447015s  obus Jusqu'à Javel 1915        77 canvases (album)
      btv1b90113191  affiche usine 1920             8348x11359  1 canvas
      btv1b531358363 Rol, Deauville 1924            8498x6131   1 canvas
      btv1b9032948p  Meurisse, stand Citroën 1919   5100x7000   1 canvas
  * Burst of 15 album-page fetches: all 200 in ~1s (no aggressive rate limit).
  * Rare transient HTTP 500 on the IIIF image server -> retry once.

IMAGE URL TEMPLATE (IIIF Image API v1.1 level2):
  service   = https://gallica.bnf.fr/iiif/ark:/12148/<ark>/f<n>
  thumbnail = {service}/full/400,/0/default.jpg      (~4-50 KB)
  preview   = {service}/full/1024,/0/default.jpg      (~140-245 KB)  <-- good default
  native    = {service}/full/full/0/native.jpg        (~4-5.7 MB)
  boxed     = {service}/full/!1024,1024/0/default.jpg (fit-in box, keeps aspect)
The manifest's sequences[0].canvases[i].images[0].resource["@id"] is exactly
the native URL; swap the /full/.../0/native.jpg tail for another size.

USAGE
-----
The harness `browser()` runtime does NOT import helper modules; paste these
functions inside a `browser(code)` block (or import them if your runner allows).
Always call `ensure_same_origin()` first: in-page fetch() is same-origin, so a
cross-origin body is opaque/unreadable.
"""

from __future__ import annotations

import base64
import json
import struct

import browser_harness.helpers as H

GALLICA_MANIFEST = "https://gallica.bnf.fr/iiif/ark:/12148/{ark}/manifest.json"
GALLICA_SERVICE = "https://gallica.bnf.fr/iiif/ark:/12148/{ark}/f{n}"
ANY_GALLICA_PAGE = "https://gallica.bnf.fr/iiif/ark:/12148/btv1b9045938h/manifest.json"

_TO_B64_TEMPLATE = r"""
(function(){
  window.__dl = window.__dl || {};
  window.__dl[__KEY__] = {pending:true};
  fetch(__URL__).then(async r=>{
    const buf = await r.arrayBuffer();
    const bytes = new Uint8Array(buf);
    let bin=''; const CH=0x8000;
    for(let i=0;i<bytes.length;i+=CH){
      bin += String.fromCharCode.apply(null, bytes.subarray(i,i+CH));
    }
    window.__dl[__KEY__] = {status:r.status, ct:r.headers.get('content-type'),
                            n:bytes.length, b64:btoa(bin)};
  }).catch(e=>{ window.__dl[__KEY__] = {error:String(e)}; });
  return 'fired';
})();
"""

_MANIFEST_TEMPLATE = r"""
(function(){
  window.__mf = {pending:true};
  fetch(__URL__).then(r=>r.text()).then(t=>{window.__mf={ok:true,text:t};})
    .catch(e=>{window.__mf={error:String(e)};});
  return 'fired';
})();
"""


def ensure_same_origin() -> str:
    """Make sure the attached tab is on gallica.bnf.fr so fetch() is same-origin."""
    origin = str(H.js("location.origin") or "")
    if "gallica.bnf.fr" not in origin:
        H.goto_url(ANY_GALLICA_PAGE)
        H.wait_for_load()
    return str(H.js("location.origin") or "")


def image_url(ark: str, n: int = 1, size: str = "1024,") -> str:
    """Build an IIIF image URL. size examples: '400,', '1024,', '!1024,1024', 'full'."""
    svc = GALLICA_SERVICE.format(ark=ark, n=n)
    tail = "0/native.jpg" if size == "full" else "0/default.jpg"
    return f"{svc}/full/{size}/{tail}"


def _to_base64_js(key: str, url: str) -> str:
    """JS: fetch url -> arrayBuffer -> base64, stored at window.__dl[key]."""
    return (_TO_B64_TEMPLATE.replace("__KEY__", json.dumps(key))
            .replace("__URL__", json.dumps(url)))


def _dl_expr(key: str) -> str:
    """JS expression: state of window.__dl[key] without the (huge) b64 payload."""
    kj = json.dumps(key)
    return ("JSON.stringify(Object.assign({}, window.__dl[" + kj + "], "
            "{b64: (window.__dl[" + kj + "] && window.__dl[" + kj + "].b64)?'Y':null}))")


def fetch_images(urls: dict[str, str], timeout_s: int = 120, chunk: int = 200000,
                 retries: int = 1) -> dict[str, dict]:
    """Fetch many images concurrently via in-page fetch. Returns {key: {status, ct, bytes|error}}.

    arrayBuffer -> base64 is retrieved in `chunk`-char slices to dodge the 5 s
    CDP IPC timeout on large (multi-MB) images.
    """
    ensure_same_origin()
    for k, u in urls.items():
        H.js(_to_base64_js(k, u))

    pending = set(urls)
    results: dict[str, dict] = {}
    waited = 0.0
    while pending and waited < timeout_s:
        H.wait(1)
        waited += 1
        for k in list(pending):
            meta = json.loads(H.js(_dl_expr(k)))
            if meta.get("pending"):
                continue
            pending.discard(k)
            if meta.get("error"):
                results[k] = {"error": meta["error"]}
                continue
            kj = json.dumps(k)
            length = H.js("window.__dl[" + kj + "].b64.length") if meta.get("b64") else 0
            b64 = ""
            i = 0
            while i < (length or 0):
                b64 += H.js("window.__dl[" + kj + "].b64.slice("
                            + str(i) + "," + str(i + chunk) + ")")
                i += chunk
            results[k] = {
                "status": meta.get("status"),
                "ct": meta.get("ct"),
                "bytes": base64.b64decode(b64) if b64 else b"",
            }
    # retry transient failures (e.g. 500) once
    for k, u in urls.items():
        r = results.get(k, {})
        bad = r.get("error") or (r.get("status") not in (200, None))
        empty = not (isinstance(r.get("bytes"), (bytes, bytearray)) and r["bytes"])
        if retries > 0 and (bad or empty):
            again = fetch_images({k: u}, timeout_s, chunk, retries=retries - 1)
            results[k] = again[k]
    return results


def save_image(url: str, dest_path: str, chunk: int = 200000) -> dict:
    """Fetch one image via the browser, write it to disk, verify JPEG/PNG magic."""
    res = fetch_images({"img": url}, chunk=chunk).get("img", {})
    raw = res.get("bytes") or b""
    info = {"status": res.get("status"), "ct": res.get("ct"), "nbytes": len(raw),
            "path": dest_path, "magic": raw[:4].hex() if raw else None, "ok": False}
    if raw[:3] == b"\xff\xd8\xff":
        info["kind"] = "jpeg"
        info["ok"] = True
    elif raw[:8] == b"\x89PNG\r\n\x1a\n":
        info["kind"] = "png"
        info["ok"] = True
    if info["ok"]:
        with open(dest_path, "wb") as f:
            f.write(raw)
        info["dims"] = _jpeg_dims(raw) if info["kind"] == "jpeg" else _png_dims(raw)
    return info


def manifest_canvases(ark: str, limit: int | None = None) -> dict:
    """Fetch a manifest via the browser and list its canvases' image info.

    Returns {label, description, license, n_canvas, images:[{canvas,label,res_id,w,h}]}.
    """
    ensure_same_origin()
    url = GALLICA_MANIFEST.format(ark=ark)
    H.js(_MANIFEST_TEMPLATE.replace("__URL__", json.dumps(url)))
    meta = {}
    for _ in range(30):
        H.wait(1)
        meta = json.loads(H.js(
            "JSON.stringify({p:!!window.__mf.pending, e:window.__mf.error||null, "
            "ok:!!window.__mf.ok})"))
        if not meta["p"]:
            break
    if meta.get("e"):
        return {"error": meta["e"]}
    j = json.loads(H.js("window.__mf.text"))
    canv = (j.get("sequences") or [{}])[0].get("canvases", [])
    imgs = []
    for ci, c in enumerate(canv if limit is None else canv[:limit]):
        for im in c.get("images", []):
            r = im.get("resource", {})
            imgs.append({"canvas": ci, "label": c.get("label"),
                         "res_id": r.get("@id"), "w": r.get("width"), "h": r.get("height")})
    return {"label": j.get("label"), "description": j.get("description"),
            "license": j.get("license"), "n_canvas": len(canv), "images": imgs}


def _jpeg_dims(b: bytes):
    i = 2
    while i < len(b):
        if b[i] != 0xFF:
            i += 1
            continue
        m = b[i + 1]
        if m in (0xC0, 0xC1, 0xC2, 0xC3):
            h = struct.unpack(">H", b[i + 5:i + 7])[0]
            w = struct.unpack(">H", b[i + 7:i + 9])[0]
            return (w, h)
        if m in (0xD8, 0xD9):
            i += 2
            continue
        seglen = struct.unpack(">H", b[i + 2:i + 4])[0]
        i += 2 + seglen
    return None


def _png_dims(b: bytes):
    if len(b) >= 24 and b[:8] == b"\x89PNG\r\n\x1a\n":
        return (struct.unpack(">I", b[16:20])[0], struct.unpack(">I", b[20:24])[0])
    return None
