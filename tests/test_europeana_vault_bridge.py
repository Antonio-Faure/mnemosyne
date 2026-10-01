"""End-to-end bridge: a vault-stored Europeana key reaches the connector.

Proves the whole chain that the operator workflow relies on, without network:

    vault["europeana_api_key"]
        -> Engine startup: export_vault_secrets() -> os.environ["EUROPEANA_API_KEY"]
        -> EuropeanaConnector sends the key as the ``wskey`` query param
        -> normalized ``Asset`` list.

The remaining gap (an actual key in the vault) is filled by the browser agent;
this test locks in that once the child ("europeana_api_key") exists, the parent
env var and the connector both light up.
"""

from __future__ import annotations

import os
from typing import Any

from mnemosyne.models import Protocol, SourceDescriptor
from mnemosyne.secrets import export_vault_secrets
from mnemosyne.sources.europeana import EuropeanaConnector
from mnemosyne.vault import Vault, init_vault

PAYLOAD: dict[str, Any] = {
    "success": True,
    "itemsCount": 1,
    "items": [
        {
            "id": "/9200338/OilWell",
            "title": ["Puits de pétrole"],
            "dcCreator": ["Anonyme"],
            "edmIsShownBy": ["https://example.org/img/oil.jpg"],
            "edmPreview": ["https://example.org/img/oil_thumbs.jpg"],
            "type": "IMAGE",
        }
    ],
}


class FakeHttp:
    """Records calls and returns a canned Europeana payload."""

    def __init__(self, payload: dict[str, Any]):
        self.payload = payload
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def get_json(self, url: str, **kwargs: Any) -> Any:
        self.calls.append((url, kwargs))
        return self.payload


def _descriptor() -> SourceDescriptor:
    return SourceDescriptor(
        id="europeana",
        name="Europeana",
        protocol=Protocol.REST,
        base_url="https://api.europeana.eu/record/v2/search.json",
        auth="api_key",
        key_env="EUROPEANA_API_KEY",
    )


async def test_vault_key_reaches_connector(tmp_path, monkeypatch):
    monkeypatch.delenv("MNEMOSYNE_VAULT_KEY", raising=False)
    monkeypatch.delenv("EUROPEANA_API_KEY", raising=False)
    path = init_vault(tmp_path / "vault.enc")
    Vault(path).set("europeana_api_key", "vault-key-123")

    # Engine startup: vault -> env
    exported = export_vault_secrets(path, [_descriptor()])
    assert exported == ["EUROPEANA_API_KEY"]
    assert os.environ["EUROPEANA_API_KEY"] == "vault-key-123"

    http = FakeHttp(PAYLOAD)
    connector = EuropeanaConnector(_descriptor(), http)
    try:
        assets = await connector.search("puits de pétrole", limit=5)
    finally:
        os.environ.pop("EUROPEANA_API_KEY", None)

    # connector -> assets, with the vault key actually sent as `wskey`
    assert len(assets) == 1
    assert assets[0].source_id == "europeana"
    assert assets[0].image_url == "https://example.org/img/oil.jpg"
    assert http.calls, "connector must call the search endpoint when keyed"
    _, kwargs = http.calls[0]
    assert kwargs["params"]["wskey"] == "vault-key-123"
