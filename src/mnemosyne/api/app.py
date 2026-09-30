"""Unified aggregation API over every connected archive provider."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import FastAPI, HTTPException, Query

from mnemosyne.config import get_config
from mnemosyne.engine import Engine
from mnemosyne.logger import get_logger
from mnemosyne.models import Asset

log = get_logger("api")


@asynccontextmanager
async def lifespan(app: FastAPI):
    engine = Engine(get_config())
    engine.catalog.sync()
    app.state.engine = engine
    try:
        yield
    finally:
        await engine.aclose()


def create_app() -> FastAPI:
    app = FastAPI(
        title="mnemosyne",
        version="0.1.0",
        description="Unified search over aggregated historical image archive providers.",
        lifespan=lifespan,
    )

    @app.get("/health")
    async def health() -> dict:
        engine: Engine = app.state.engine
        return {"status": "ok", "assets_total": engine.db.count_assets()}

    @app.get("/sources")
    async def sources() -> list[dict]:
        engine: Engine = app.state.engine
        return [
            {
                "id": d.id,
                "name": d.name,
                "institution": d.institution,
                "country": d.country,
                "protocol": d.protocol,
                "auth": d.auth,
                "license": d.license,
                "enabled": d.enabled,
                "tags": d.tags,
            }
            for d in engine.catalog.list()
        ]

    @app.get("/sources/status")
    async def sources_status() -> dict:
        return app.state.engine.status()

    @app.get("/search")
    async def search(
        q: Annotated[str, Query(min_length=1, description="Free-text query")],
        source: Annotated[list[str] | None, Query(description="Restrict to source ids")] = None,
        limit: Annotated[int, Query(ge=1, le=100)] = 20,
        year_from: Annotated[int | None, Query()] = None,
        year_to: Annotated[int | None, Query()] = None,
        license_contains: Annotated[str | None, Query()] = None,
    ) -> dict:
        engine: Engine = app.state.engine
        assets = await engine.search(q, source_ids=source, limit=limit)
        assets = _apply_filters(assets, year_from, year_to, license_contains)
        return {"query": q, "count": len(assets), "results": [_serialize(a) for a in assets]}

    @app.get("/asset/{asset_id}")
    async def asset(asset_id: str) -> dict:
        engine: Engine = app.state.engine
        found = engine.db.get_asset(asset_id)
        if found is None:
            raise HTTPException(status_code=404, detail="asset not found")
        return _serialize(found)

    return app


def _apply_filters(
    assets: list[Asset],
    year_from: int | None,
    year_to: int | None,
    license_contains: str | None,
) -> list[Asset]:
    out = assets
    if year_from is not None:
        out = [a for a in out if a.year is not None and a.year >= year_from]
    if year_to is not None:
        out = [a for a in out if a.year is not None and a.year <= year_to]
    if license_contains:
        needle = license_contains.lower()
        out = [a for a in out if needle in (a.license or "").lower()]
    return out


def _serialize(asset: Asset) -> dict:
    return {"provenance": asset.provenance(), **asset.model_dump()}


app = create_app()
