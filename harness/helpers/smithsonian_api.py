"""Smithsonian Open Access API (EDAN) reference — mnemosyne browser research.

Endpoint: https://api.si.edu/openaccess/api/v1.0
Auth:     api_key query param; no key -> body "API_KEY_MISSING";
          bad key -> "API_KEY_INVALID" (plain text, not JSON).

Endpoints
---------
GET /search          q, start (default 0), rows (0..1000, default 10),
                     sort (id|newest|updated|random), type
                     (edanmdm|ead_collection|ead_component|all),
                     fqs, row_group (objects|archives), api_key
GET /category/:cat/search   cat in art_design|history_culture|science_technology
GET /content/:id     single record; id may be a row id or
                     `edanmdm%3Anmaahc_2011.123` (colon URL-encoded)
GET /stats           CC0 stats
GET /terms           field terms

Success shape
-------------
{
  "status": 200, "responseCode": 1,
  "response": {
    "rows": [ Row, ... ],
    "facets": [...],
    "rowCount": <int>,
    "message": "content found"
  }
}

Row
---
{
  "id": "<search row id>",
  "title": "<str>",
  "unitCode": "NMAAHC" | "SIL" | "FSG" | ...,
  "type": "edanmdm" | "ead_collection" | "ead_component",
  "url": "edanmdm:nmaahc_2011.123",
  "content": {
     "freetext": { date, name, notes, place, topic, setName, creditLine,
                   dataSource, identifier, objectType, objectRights,
                   physicalDescription },   # each: [{label, content}, ...]
     "indexedStructured": { date, name, place, topic, culture, object_type,
                            online_media_type, online_media_rights, ... },
     "descriptiveNonRepeating": {
        "guid": "http://n2t.net/ark:/...",
        "title": {"label": "Object Name", "content": "<title>"},
        "record_ID": "nmaahc_2011.123",
        "unit_code": "NMAAHC",
        "title_sort": "...",
        "data_source": "National Museum of African American History and Culture",
        "record_link": "https://nmaahc.si.edu/object/nmaahc_2011.123",
        "metadata_usage": {"access": "CC0"},
        "online_media": {"media": [ Media, ... ]}   # present only if media exists
     }
  },
  "hash": "...", "docSignature": "...", "timestamp": "...",
  "lastTimeUpdated": "...", "version": "..."
}

Media
-----
{
  "id": "media:NMAAHC-2011_123_001",
  "guid": "http://n2t.net/ark:/...",
  "type": "Images" | "Audio" | "Video" | ...,
  "idsId": "NMAAHC-2011_123_001",
  "usage": {"access": "CC0"},
  "content": "https://ids.si.edu/ids/deliveryService?id=NMAAHC-2011_123_001",
  "thumbnail": "https://ids.si.edu/ids/deliveryService?id=NMAAHC-2011_123_001",
  "altTextAccessibility": "",
  "extDescrAccessibility": "<long description>",
  "resources": [
    {"label": "High-resolution TIFF",
     "url": "https://ids.si.edu/ids/download?id=...tif",
     "width": 7682, "height": 865, "dimensions": "7682x865"},
    {"label": "High-resolution JPEG", "url": "...jpg", ...},
    {"label": "Screen Image", "url": "..._screen"},
    {"label": "Thumbnail Image", "url": "..._thumb"}
  ]
}

Rights
------
Open Access; most records CC0 (descriptiveNonRepeating.metadata_usage.access
and media[].usage.access). Some media carry indexedStructured
.online_media_rights == ["No Known Copyright Restrictions"].

Normalization notes for the connector
-------------------------------------
- asset id:        row["id"]
- source record:   descriptiveNonRepeating.record_link (fallback row["url"])
- title:           row["title"] or dnr.title.content
- thumbnail:       media[0]["thumbnail"] or media[0]["content"]
- full image:      media[0]["content"]
- license:         media[0].usage.access or dnr.metadata_usage.access  -> "CC0"
- date:            freetext.date[0].content
- creators/names:  [n["content"] for n in freetext.name]
- topics:          [t["content"] for t in freetext.topic]
- place:           [p["content"] for p in freetext.place]
- graceful no key: return [] WITHOUT any HTTP call.
"""

import json
import urllib.parse
import urllib.request

BASE_URL = "https://api.si.edu/openaccess/api/v1.0"


def search(q, api_key, rows=100, start=0, **extra):
    """Thin reference call. Returns parsed JSON dict, or raises on error."""
    params = {"q": q, "rows": rows, "start": start, "api_key": api_key}
    params.update(extra)
    url = BASE_URL + "/search?" + urllib.parse.urlencode(params)
    with urllib.request.urlopen(url, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def row_to_asset(row):
    """Reference normalization of one search Row to an Asset-like dict."""
    dnr = row.get("content", {}).get("descriptiveNonRepeating", {}) or {}
    freetext = row.get("content", {}).get("freetext", {}) or {}
    media = (dnr.get("online_media") or {}).get("media") or []
    first = media[0] if media else {}
    return {
        "id": row.get("id"),
        "title": row.get("title") or (dnr.get("title") or {}).get("content"),
        "source_url": dnr.get("record_link") or row.get("url"),
        "thumbnail_url": first.get("thumbnail") or first.get("content"),
        "image_url": first.get("content"),
        "license": (first.get("usage") or {}).get("access")
        or (dnr.get("metadata_usage") or {}).get("access"),
        "date": (freetext.get("date") or [{}])[0].get("content"),
        "creators": [n.get("content") for n in freetext.get("name", [])],
        "topics": [t.get("content") for t in freetext.get("topic", [])],
        "place": [p.get("content") for p in freetext.get("place", [])],
        "media_type": first.get("type"),
        "unit_code": row.get("unitCode"),
    }
