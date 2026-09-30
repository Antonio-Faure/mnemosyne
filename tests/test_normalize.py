from mnemosyne.models import Asset
from mnemosyne.normalize import DedupIndex, normalize


def _asset(sid: str, sa: str, **kw) -> Asset:
    return Asset.build("gallica", sa, **kw)


def test_normalize_drops_imageless_and_dedups():
    a = _asset("1", "1", image_url="http://x/1.jpg")
    b = _asset("2", "1", image_url="http://x/1.jpg")  # same source_asset_id -> same id
    c = _asset("3", "3")  # no image
    out = normalize([a, b, c])
    assert [x.id for x in out] == [a.id]


def test_dedup_index_title():
    idx = DedupIndex()
    a = Asset.build("gallica", "1", title="Puits de Lacq", image_url="http://x/1.jpg")
    b = Asset.build("gallica", "2", title="  puits   DE lacq ", image_url="http://x/2.jpg")
    assert not idx.is_duplicate(a)
    idx.add(a)
    assert idx.is_duplicate(b)
