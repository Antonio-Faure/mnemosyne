"""Paris Musees - IIIF reference for mnemosyne (task #51).

Reconnaissance by the mnemosyne navigator agent. Read-only: every function
only GETs and parses; nothing here writes to the remote.

Source
------
Paris Musees - etablissement public of the 14 museums of the City of Paris
(280k+ notices: oeuvres, bibliographic resources, archives). The API host
https://apicollections.parismusees.paris.fr is a Drupal 10 site that serves
JSON-LD (GraphQL + IIIF); the public portal is
https://www.parismuseescollections.paris.fr.

IIIF entry point - a SINGLE manifest (there is NO collection)
------------------------------------------------------------
The host serves IIIF Presentation API v2 manifests, one per digitised object:

    https://apicollections.parismusees.paris.fr/iiif/<visuel_id>/manifest
    e.g. .../iiif/320025034/manifest   (sample given in task #51)

Verified: HTTP 200, ``Content-Type: application/json``, public, NO auth, works
with a bot User-Agent. Shape: @context presentation/2, @type "sc:Manifest",
sequences[].canvases[].images[].resource.@id = a STATIC Drupal image

    .../sites/default/files/styles/<size>/collections/atoms/images/<MUS>/<file>.jpg?itok=...

There is no IIIF Image API and no IIIF Collection:
  * /iiif , /iiif/ , /iiif/collection , /iiif/collection/<n|slug>  -> 404
  * /iiif/<visuel_id>/info.json and .../full/full/0/default.jpg     -> 404
  * the manifest carries NO ``service``, ``within``, ``license``, ``rights``,
    ``related``; only ``thumbnail`` (a static Drupal image style URL) is present.

``<visuel_id>`` (e.g. 320025034) is an internal "visuel" id - it is NOT the
notice nid and NOT the oeuvre nid; /iiif/<nid>/manifest -> 404 (checked nid
151109 for the same object). Manifests therefore cannot be enumerated from the
IIIF side: the ONLY entry point is one manifest = one object.

Search / metadata (NOT usable with auth:none)
---------------------------------------------
The host also exposes a GraphQL API, POST https://.../graphql, documented at
https://www.parismuseescollections.paris.fr/fr/documentation-de-l-api-du-portail-des-collections
(see /fr/se-connecter-a-l-api). It REQUIRES a per-account token sent in the
``auth-token`` header (generated under "Mon compte > Auth Tokens"); without it
the endpoint answers 403 and the schema explorer /explorer is login-gated. So
the GraphQL "search endpoint" cannot back an ``auth: none`` descriptor.

The public portal notice page
    https://www.parismuseescollections.paris.fr/fr/<museum>/oeuvres/<slug>
embeds the manifest URL in a block labelled "IIIF Manifest"
(class ``field iiif-manifest-field``, link class ``lien-iiif``), so a manifest
id can be discovered per object from the portal (HTML) if ever needed.

Rights
------
The portal notice carries a CC0 statement:
    <a href="https://creativecommons.org/publicdomain/zero/1.0/">CC0</a>
    credit "CC0 Paris Musees / <museum>".
Per the 2020 "open content" policy only public-domain 2D works are offered in
HD under CC0; in-copyright works are shown low-def only. The IIIF manifest
itself carries NO licence field, so any rights value must come from the
descriptor.

Recommended descriptor (GENERIC IIIF connector - no bespoke code needed)
------------------------------------------------------------------------
Create the ``paris_musees`` source descriptor with:

    # config/sources/paris_musees.yaml
    slug: paris_musees
    name: Paris Musees
    protocol: iiif
    base_url: https://apicollections.parismusees.paris.fr
    auth: none
    extra:
      manifest: https://apicollections.parismusees.paris.fr/iiif/320025034/manifest

Caveat: a single manifest yields a single object. The generic IIIF connector
cannot enumerate this host (no collection); a broader harvest would need the
token-gated GraphQL API or per-object discovery.
"""

from __future__ import annotations

import json
import urllib.request

BASE = "https://apicollections.parismusees.paris.fr"
MANIFEST_TMPL = BASE + "/iiif/{visuel_id}/manifest"
SAMPLE_VISUEL_ID = "320025034"
SAMPLE_MANIFEST = BASE + "/iiif/" + SAMPLE_VISUEL_ID + "/manifest"
UA = (
    "mnemosyne-research-bot/1.0 "
    "(https://github.com/Antonio-Faure/mnemosyne; opensource research aggregator)"
)


def manifest_url(visuel_id):
    """Build the IIIF manifest URL for a Paris Musees internal visuel id."""
    return MANIFEST_TMPL.format(visuel_id=visuel_id)


def fetch(visuel_id=SAMPLE_VISUEL_ID, timeout=30):
    """GET a manifest and return the parsed JSON (raises on HTTP error)."""
    url = manifest_url(visuel_id)
    req = urllib.request.Request(
        url, headers={"User-Agent": UA, "Accept": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def verify(visuel_id=SAMPLE_VISUEL_ID):
    """Return {ok, status, iiif_version, canvases, has_service, has_license}."""
    out = {
        "ok": False,
        "status": None,
        "iiif_version": None,
        "canvases": 0,
        "has_service": False,
        "has_license": False,
    }
    try:
        data = fetch(visuel_id)
    except Exception as exc:  # noqa: BLE001
        out["error"] = str(exc)[:200]
        return out
    out["status"] = 200
    text = json.dumps(data)
    if "presentation/2" in text:
        out["iiif_version"] = "2"
    elif "presentation/3" in text:
        out["iiif_version"] = "3"
    if "sequences" in data:
        out["canvases"] = sum(len(s.get("canvases", [])) for s in data["sequences"])
    elif "items" in data:
        out["canvases"] = len(data["items"])
    out["has_service"] = '"service"' in text
    out["has_license"] = ('"license"' in text) or ('"rights"' in text)
    out["ok"] = out["iiif_version"] is not None
    return out
