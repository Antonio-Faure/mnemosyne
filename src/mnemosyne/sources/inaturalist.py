"""iNaturalist observations — REST API v1 (``/observations``).

Public, keyless biodiversity platform (California Academy of Sciences /
National Geographic Society). Observations carry photos whose licence is
granted per photo; we keep only ``cc0`` or ``cc-by`` photos and always re-check
``photo.license_code`` on our side (the ``photo_license`` API filter is not
trusted on its own).

A single observation may expose several qualifying photos, so **one photo = one
Asset**. Provider shapes are normalized into the canonical :class:`Asset` at
this boundary; the raw provider form never leaks past it. Images are never
downloaded here — only URLs are recorded (``square.jpg`` thumbnail and the
``large.jpg`` main image).
"""

from __future__ import annotations

import math
from typing import Any

from mnemosyne.connectors.base import Connector
from mnemosyne.models import Asset
from mnemosyne.util import parse_year

#: allowed photo-level licences (lower-case ``license_code``)
_ALLOWED_LICENSES = ("cc0", "cc-by")

#: canonical licence name per iNaturalist ``license_code``
_LICENSE_NAMES = {"cc0": "CC0-1.0", "cc-by": "CC-BY-4.0"}


def _large_url(url: str) -> str:
    """Main image: swap the ``square.jpg`` rendition for ``large.jpg``.

    Falls back to the URL unchanged when it is not a ``square.jpg`` rendition.
    """
    if "square.jpg" in url:
        return url.replace("square.jpg", "large.jpg")
    return url


class INaturalistConnector(Connector):
    async def search(self, query: str, limit: int = 20, **filters: Any) -> list[Asset]:
        per_page = min(max(limit, 10), 200)
        quality_grade = filters.get("quality_grade", "research")
        max_pages = int(filters.get("max_pages", 3))

        assets: list[Asset] = []
        page = 1
        while page <= max_pages:
            params = {
                "q": query,
                "photos": "true",
                "photo_license": "cc0,cc-by",
                "per_page": per_page,
                "page": page,
                "quality_grade": quality_grade,
            }
            data = await self.http.get_json(
                f"{self.descriptor.base_url}/observations", params=params
            )
            results = data.get("results") or []
            if not results:
                break

            for observation in results:
                assets.extend(self._observation_to_assets(observation))
                if len(assets) >= limit:
                    break
            if len(assets) >= limit:
                break

            total = data.get("total_results")
            if isinstance(total, int) and per_page > 0:
                last_page = math.ceil(total / per_page)
                if page >= last_page:
                    break
            page += 1

        return assets[:limit]

    def _observation_to_assets(self, observation: dict[str, Any]) -> list[Asset]:
        """Normalize one observation into assets, one per qualifying photo."""
        assets: list[Asset] = []
        for index, photo in enumerate(observation.get("photos") or []):
            if not isinstance(photo, dict):
                continue
            license_code = photo.get("license_code")
            url = photo.get("url")
            if license_code not in _ALLOWED_LICENSES or not url:
                continue
            assets.append(self._photo_to_asset(observation, photo, index))
        return assets

    def _photo_to_asset(
        self, observation: dict[str, Any], photo: dict[str, Any], index: int
    ) -> Asset:
        obs_id = observation.get("id")
        photo_id = photo.get("id")
        source_asset_id = str(photo_id) if photo_id is not None else f"{obs_id}-{index}"
        license_code = photo["license_code"]
        url = photo["url"]

        taxon = observation.get("taxon") or {}
        title = (
            taxon.get("preferred_common_name")
            or observation.get("species_guess")
            or taxon.get("name")
            or f"iNaturalist observation {obs_id}"
        )
        user = observation.get("user") or {}
        creator = user.get("login") or photo.get("attribution")
        observed_on = observation.get("observed_on")

        dimensions = photo.get("original_dimensions") or {}

        return Asset.build(
            self.id,
            source_asset_id,
            title=title,
            description=observation.get("place_guess") or "",
            creator=creator,
            date_text=observed_on,
            year=parse_year(observed_on),
            license=_LICENSE_NAMES[license_code],
            rights=photo.get("attribution"),
            page_url=f"https://www.inaturalist.org/observations/{obs_id}",
            image_url=_large_url(url),
            thumbnail_url=url,
            width=dimensions.get("width"),
            height=dimensions.get("height"),
            extra={
                "observation_id": obs_id,
                "photo_id": photo_id,
                "taxon": taxon.get("name"),
                "license_code": license_code,
                "attribution": photo.get("attribution"),
                "place_guess": observation.get("place_guess"),
                "quality_grade": observation.get("quality_grade"),
                "observed_on": observed_on,
            },
        )
