from mnemosyne.catalog import Catalog
from mnemosyne.db import Database
from mnemosyne.models import SourceState


def test_catalog_sync_and_state(config):
    db = Database(config.db_file())
    catalog = Catalog(config.sources_path, db)

    descriptors = catalog.sync()
    assert [d.id for d in descriptors] == ["gallica"]
    assert catalog.state("gallica") == SourceState.DISCOVERED

    catalog.set_state("gallica", SourceState.CONNECTED)
    assert catalog.state("gallica") == SourceState.CONNECTED

    # a sync must preserve state
    catalog.sync()
    assert catalog.state("gallica") == SourceState.CONNECTED
    db.close()
