"""Tests for the Musee francais du petrole connector (task #187).

Offline tests exercise the pure parsers/normalisers on fixtures (no network);
the last test is a live smoke check that skips itself when the network/the
museum host is unreachable.

Runs under pytest OR `python test_musee_petrole.py` (plain asserts).
"""

from __future__ import annotations

import musee_petrole as mp


def test_inventory_number_parsing():
    assert mp.inventory_number("Maquette presse filtre PECH_1997.0.214_1") == "PECH.1997.0.214"
    assert mp.inventory_number("PECH_2019-1-1_3") == "PECH.2019.1.1"
    assert mp.inventory_number("PECH_2014-1-1_v2") == "PECH.2014.1.1"
    assert mp.inventory_number("06pechelbronn-cherot_Antar") is None
    assert mp.inventory_number("") is None


# --------------------------------------------------------------- helpers

def test_good_title_and_prettify():
    assert mp._good_title("5") is False
    assert mp._good_title("1 2 3") is False
    assert mp._good_title("cherot") is True
    assert mp._prettify("Aquarelle_Sauer_1_PECH_2013") == "Aquarelle Sauer 1 PECH 2013"


# --------------------------------------------------------------- content

def test_extract_images_context_and_https():
    html = (
        '<h2>La marque Antar</h2>'
        '<p>Texte de contexte autour de l image.</p>'
        '<a href="x"><img class="wp-image-464 alignright" '
        'src="http://www.musee-du-petrole.com/wp-content/uploads/a.jpg" '
        'alt="06pechelbronn-cherot_Antar" width="458" height="306"></a>'
    )
    imgs = mp.extract_images(html)
    assert len(imgs) == 1
    im = imgs[0]
    assert im["media_id"] == 464
    assert im["heading"] == "La marque Antar"
    assert im["alt"] == "06pechelbronn-cherot_Antar"
    assert im["src"].startswith("https://")          # http -> https canonicalised
    assert "contexte" in im["context"]


def test_extract_images_skips_decorative():
    html = ('<img src="https://x/logo.png">'
            '<img src="https://x/1x1-pixel.png">'
            '<img class="wp-image-1" src="https://x/photo.jpg">')
    imgs = mp.extract_images(html)
    assert len(imgs) == 1 and imgs[0]["media_id"] == 1


# --------------------------------------------------------------- media

def _fake_media():
    u = "http://www.musee-du-petrole.com/wp-content/uploads/2015/03/"
    return {
        "id": 720,
        "date": "2015-03-04T12:00:00",
        "title": {"rendered": "raffinerie vue"},
        "source_url": u + "raffinerievue.jpg",
        "filename": "raffinerievue.jpg",
        "media_type": "image",
        "mime_type": "image/jpeg",
        "media_details": {"width": 1200, "height": 500, "sizes": {
            "medium": {"source_url": u + "raffinerievue-300x125.jpg"},
            "full": {"source_url": u + "raffinerievue.jpg"},
        }},
    }


def test_media_to_item_shape():
    it = mp.media_to_item(_fake_media())
    assert it["id"] == "mfdp:media:720"
    assert it["title"] == "raffinerie vue"
    assert it["thumbnail"].endswith("raffinerievue-300x125.jpg")   # 'medium' preferred
    assert it["image"].startswith("https://")
    assert it["license"].startswith("In Copyright")
    assert it["license_rights"].startswith("https://rightsstatements.org/")
    assert it["enabled"] is True
    for k in ("url", "image", "thumbnail", "title", "subtitle", "source", "license"):
        assert k in it


def test_content_image_prefers_heading_over_numeric_alt():
    page = {"id": 218, "link": "https://www.musee-du-petrole.com/historique/",
            "title": {"rendered": "Historique"}}
    img = {"media_id": 460, "src": "https://www.musee-du-petrole.com/wp-content/uploads/conrad.jpg",
           "alt": "5", "heading": "Les freres Schlumberger", "context": "texte"}
    it = mp.content_image_to_item(page, img, {"medium": "https://x/conrad-300.jpg"})
    assert it["title"] == "Les freres Schlumberger"        # not the bare "5"
    assert it["thumbnail"].endswith("conrad-300.jpg")
    assert it["page_url"].endswith("/historique/")


def test_license_info_present():
    li = mp.license_info()
    assert li["rights"].startswith("https://rightsstatements.org/")
    assert "Musee du Petrole" in li["holder"]
    assert li["nc"] is True


# --------------------------------------------------------------- live smoke

def test_live_search_smoke():
    """Network test: skip cleanly if the museum host is unreachable."""
    try:
        r = mp.search("Schlumberger", limit=3, content_pages=2)
    except Exception as e:  # noqa: BLE001
        try:
            import pytest
            pytest.skip(f"network unavailable: {e}")
        except ImportError:
            print("SKIP live smoke (network):", e)
            return
    assert isinstance(r, list) and r, "expected at least one item"
    joined = " ".join((it.get("title") or "") + " " + (it.get("subtitle") or "") for it in r)
    assert "Schlumberger" in joined or "schlumberger" in joined.lower()


# --------------------------------------------------------------- plain runner

if __name__ == "__main__":
    offline = [v for k, v in sorted(globals().items())
               if k.startswith("test_") and k != "test_live_search_smoke"]
    for fn in offline:
        fn()
        print("ok:", fn.__name__)
    print("running live smoke ...")
    test_live_search_smoke()
    print("all done")
