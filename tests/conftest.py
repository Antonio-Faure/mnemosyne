from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from mnemosyne.config import AppConfig, Config


@pytest.fixture
def sources_dir(tmp_path: Path) -> Path:
    d = tmp_path / "sources"
    d.mkdir()
    (d / "gallica.yaml").write_text(
        yaml.safe_dump(
            {
                "id": "gallica",
                "name": "Gallica (BnF)",
                "protocol": "sru",
                "base_url": "https://example.invalid/SRU",
                "auth": "none",
                "seeds": ["test seed"],
            }
        ),
        encoding="utf-8",
    )
    return d


@pytest.fixture
def config(tmp_path: Path, sources_dir: Path) -> Config:
    cfg = Config(
        app=AppConfig(data_dir=str(tmp_path / "data")),
        sources_dir=str(sources_dir),
    )
    cfg.root = tmp_path
    return cfg
