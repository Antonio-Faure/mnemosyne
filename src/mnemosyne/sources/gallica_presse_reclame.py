"""Gallica (BnF) — presse photographique & réclame publicitaire (1919-1935).

Sibling ciblé du connecteur Gallica générique : même API officielle SRU
(Dublin Core) + images exposées via IIIF, mais la requête CQL restreint la
recherche aux **photographies de presse** et aux **affiches / réclame**
(Agence Rol, Agence Meurisse, département des Estampes) sur une fenêtre
temporelle — là où le connecteur générique ramène surtout des livres et
périodiques. Aucun scraping : tout passe par l'API programmatique (SRU + IIIF).

La requête produite ressemble à :

    (gallica all "<mots>")
      and (dc.type all "photographie" or dc.type all "affiche" ...)
      and (dc.date within "1919 1935")

Les facettes sont réglables via le descripteur (`extra.doc_types`,
`extra.year_min`, `extra.year_max`) sans toucher au code.
"""

from __future__ import annotations

from mnemosyne.sources.gallica import GallicaConnector


class GallicaPresseReclameConnector(GallicaConnector):
    """Gallica SRU, restreint aux types « presse / réclame » sur une période."""

    SOURCE_TAG = "gallica-presse-reclame-sru"

    #: facette « Type de document » de Gallica visée par défaut
    DEFAULT_DOC_TYPES: tuple[str, ...] = ("photographie", "affiche", "estampe")
    DEFAULT_YEAR_MIN = 1919
    DEFAULT_YEAR_MAX = 1935

    def _doc_types(self) -> tuple[str, ...]:
        raw = (self.descriptor.extra or {}).get("doc_types")
        if raw:
            cleaned = tuple(str(t).strip() for t in raw if str(t).strip())
            if cleaned:
                return cleaned
        return self.DEFAULT_DOC_TYPES

    def _year_bounds(self) -> tuple[int | None, int | None]:
        extra = self.descriptor.extra or {}
        try:
            low = extra.get("year_min", self.DEFAULT_YEAR_MIN)
            high = extra.get("year_max", self.DEFAULT_YEAR_MAX)
            year_min = int(low) if low is not None else None
            year_max = int(high) if high is not None else None
        except (TypeError, ValueError):
            return self.DEFAULT_YEAR_MIN, self.DEFAULT_YEAR_MAX
        return year_min, year_max

    def _cql(self, query: str, **filters) -> str:
        clauses = [f'gallica all "{query}"']

        types = self._doc_types()
        if types:
            type_clause = " or ".join(f'dc.type all "{t}"' for t in types)
            clauses.append(f"({type_clause})")

        year_min, year_max = self._year_bounds()
        if year_min and year_max:
            clauses.append(f'dc.date within "{year_min} {year_max}"')

        return " and ".join(clauses)
