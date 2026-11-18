"""Federated search API over every connected archive provider (live queries)."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from mnemosyne.api.observatory import router as observatory_router
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
        description=(
            "Federated live search over historical image archive providers — "
            "no image copies."
        ),
        lifespan=lifespan,
    )
    app.include_router(observatory_router)

    @app.get("/health")
    async def health() -> dict:
        return {"status": "ok"}

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

    @app.get("/history")
    async def history(top: Annotated[int, Query(ge=1, le=100)] = 15) -> dict:
        from mnemosyne.browser.history import read_history

        engine: Engine = app.state.engine
        path = engine.config.data_path / "chrome-profile" / "Default" / "History"
        return read_history(path, top=top)

    @app.get("/explorer", include_in_schema=False)
    async def explorer() -> FileResponse:
        """The public search page: one field, live results, links to the sources."""
        path = _search_page_path()
        if path is None:
            raise HTTPException(status_code=404, detail="page de recherche introuvable")
        return FileResponse(path, media_type="text/html")

    _mount_frontend(app)
    return app


def _search_page_path():
    """Locate `web/search.html` in the repo, the container mount, or a custom path."""
    import os
    from pathlib import Path

    candidates: list[Path] = []
    if os.environ.get("MNEMOSYNE_SEARCH_PAGE"):
        candidates.append(Path(os.environ["MNEMOSYNE_SEARCH_PAGE"]))
    try:
        candidates.append(Path(get_config().root) / "web" / "search.html")
    except Exception:  # noqa: BLE001 - config is optional for the API module
        pass
    candidates.append(Path("/repo/web/search.html"))
    candidates.append(Path(__file__).resolve().parents[3] / "web" / "search.html")
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


def _mount_frontend(app: FastAPI) -> None:
    """Serve the built observatory SPA at `/` when it exists.

    Candidates, first match wins: `MNEMOSYNE_WEB_DIST`, the repo's `web/dist`,
    the container mount (`/repo/web/dist`), then the package-relative path.
    """
    import os
    from pathlib import Path

    candidates: list[Path] = []
    if os.environ.get("MNEMOSYNE_WEB_DIST"):
        candidates.append(Path(os.environ["MNEMOSYNE_WEB_DIST"]))
    try:
        candidates.append(Path(get_config().root) / "web" / "dist")
    except Exception:  # noqa: BLE001 - config is optional for the API module
        pass
    candidates.append(Path("/repo/web/dist"))
    candidates.append(Path(__file__).resolve().parents[3] / "web" / "dist")
    for candidate in candidates:
        if candidate.is_dir():
            app.mount("/", StaticFiles(directory=str(candidate), html=True), name="web")
            log.info("observatory frontend: %s", candidate)
            return


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
