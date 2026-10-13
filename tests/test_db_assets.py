"""Database.save_assets: the count must reflect real insertions (dedup)."""

from mnemosyne.db import Database
from mnemosyne.models import Asset


def test_save_assets_counts_only_new_rows(config):
    db = Database(config.db_file())
    asset = Asset.build("gallica", "1", title="Puits de Lacq 1950", image_url="http://x/1.jpg")

    assert db.save_assets([asset]) == 1
    assert db.save_assets([asset]) == 0
    assert db.count_assets("gallica") == 1
    db.close()
