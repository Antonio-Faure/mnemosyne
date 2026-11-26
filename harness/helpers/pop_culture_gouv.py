"""Client for the POP v2 API (Plateforme Ouverte du Patrimoine, Ministère de la Culture).

Discovered while investigating the "Cité de l'automobile – Musée national de
l'automobile (Mulhouse)" source (task #543). The museum itself offers no
programmatic collection access, BUT the national POP/Joconde platform exposes a
real, open API (JSON + IIIF manifests) covering the collections of French
"Musées de France" — a legitimate programmatic heritage source for Mnemosyne.

Base host: https://api.pop.culture.gouv.fr  (returns {"message":"POPv2 API"})
Bases: joconde, museo, memoire, merimee, palissy, enluminures, mnr, autor, ...

Endpoints (verified live):
  GET /search/simple?text=<q>&from=0&size=<n>&facets[base][0]=<base>
        -> {took, total, hits:[{"_source": {REF, TITR, LOCA, CONTIENT_IMAGE,
            REFIM, WWW, DENO, ...}}]}
  GET /notices/<base>/<ref>                      -> full notice object
  GET /notices/<base>/<ref>/associated-notices   -> [{title, notices:[...]}]
        (for a museo record, REFMEM lists linked object notices)
  GET /notices/<base>/<ref>/iiif/manifest        -> IIIF Presentation manifest
  GET /producers/public                          -> list of producers

Usage (stdlib only, works outside browser-harness too):
    from pop_culture_gouv import pop_search, pop_notice, pop_manifest
    pop_search("traction avant", base="joconde", size=10)
"""
import json
import urllib.parse
import urllib.request

BASE_HOST = "https://api.pop.culture.gouv.fr"
_UA = "Mnemosyne-Archivist/1.0 (+https://github.com/Antonio-Faure/mnemosyne)"


def _get(path, params=None, timeout=20):
    url = BASE_HOST + path
    if params:
        url += "?" + urllib.parse.urlencode(params, doseq=True)
    req = urllib.request.Request(url, headers={"User-Agent": _UA, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8", "replace"))


def pop_search(text, base="joconde", size=20, start=0):
    """Full-text search within one POP base. Returns the raw {total, hits, ...} dict."""
    return _get("/search/simple", {
        "text": text,
        "from": start,
        "size": size,
        "facets[base][0]": base,
    })


def pop_search_records(text, base="joconde", size=20, start=0):
    """Convenience: return list of hit _source dicts."""
    return [h.get("_source", {}) for h in pop_search(text, base, size, start).get("hits", [])]


def pop_notice(base, ref):
    """Fetch one notice, e.g. pop_notice('museo','M0035')."""
    return _get(f"/notices/{base}/{ref}")


def pop_associated_notices(base, ref):
    """Linked notices for a record (e.g. the objects linked to a museo museum record)."""
    return _get(f"/notices/{base}/{ref}/associated-notices")


def pop_manifest(base, ref):
    """IIIF Presentation manifest for a notice (images, if any)."""
    return _get(f"/notices/{base}/{ref}/iiif/manifest")


def pop_producers():
    return _get("/producers/public")


if __name__ == "__main__":
    r = pop_search("traction avant", base="joconde", size=3)
    print("total:", r.get("total"))
    for s in [h.get("_source", {}) for h in r.get("hits", [])]:
        print(" -", s.get("REF"), "|", (s.get("TITR") or "")[:60], "| LOCA=", s.get("LOCA"))
