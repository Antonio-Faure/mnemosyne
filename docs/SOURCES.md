# Sources actives et licences

Inventaire des fournisseurs déclarés dans `config/sources/*.yaml`.

Une source est dite **active** quand son descripteur ne porte pas
`enabled: false`. Les fournisseurs dont la licence est restrictive
(non commerciale ou conditions d'utilisation particulières) sont **désactivés**
en attendant que la politique du projet les autorise — vérifié par
`tests/test_iiif_catalog.py::test_restricted_licenses_are_not_enabled`.

## Politique d'accès aux images (pas de scraping)

Quand un service expose un **accès programmatique** (API REST, IIIF, SRU,
SPARQL, OAI-PMH, JSON…), c'est lui qui doit être utilisé : le scraping HTML est
interdit. Un scraper HTML (`protocol: html`) n'est autorisé que pour une
**petite structure sans aucun accès programmatique**, et seulement après
**consentement écrit obtenu par e-mail** (l'agent navigateur demande
l'autorisation ; la référence est stockée dans le descripteur sous
`extra.scraping_consent`). Vérifié par
`tests/test_sources_inventory.py::test_html_sources_carry_scraping_consent`.

- Sources déclarées : **28**
- Sources actives : **19**
- Sources désactivées : **9**

## Sources actives (19)

| id | Source | Institution | Pays | Protocole | Auth | Licence | Droits / notes |
|---|---|---|---|---|---|---|---|
| albertina | ALBERTINA Sammlungen Online | ALBERTINA (Graphische Sammlung), Wien | AT | iiif | none | varies | ALBERTINA, Wien — beaucoup de domaine public (Gemeinfrei), vérifier par notice |
| anmt | Archives nationales du monde du travail (Roubaix) | Archives nationales du monde du travail | FR | iiif | none | Réutilisation libre (décision 21 août 2017) | ANMT — réutilisation libre commerciale et non commerciale ; attribution requise (origine + cote + titre du fonds) ; vues « non affichables » (`ligeoRestrictedAccess`) ignorées |
| arthistoricum | arthistoricum.net IIIF (Deutsche Fotothek / SLUB Dresden) | arthistoricum.net — Fachinformationsdienst Kunst, Fotografie, Design (SLUB Dresden) | DE | iiif | none | varies | SLUB Dresden / arthistoricum.net — vérifier par notice (conditions Deutsche Fotothek) |
| artic | Art Institute of Chicago | Art Institute of Chicago (AIC) | US | iiif | none | Public Domain (CC0-1.0) | Domaine public — *The Bedroom*, Vincent van Gogh (1888) |
| bsb | Bavarian State Library | Bayerische Staatsbibliothek, München | DE | iiif | none | [PDM 1.0](https://creativecommons.org/publicdomain/mark/1.0/) | Public Domain Mark — Bayerische Staatsbibliothek |
| cleveland | Cleveland Museum of Art — Open Access | Cleveland Museum of Art | US | rest | none | CC0-1.0 | CC0 1.0 Universal (images) ; œuvres sous-jacentes dans le domaine public |
| dpla | Digital Public Library of America | Digital Public Library of America | US | rest | api_key | varies | Par notice ; agrégateur US (équivalent d'Europeana), vérifier `rights` et le fournisseur |
| europeana | Europeana | Europeana Foundation | EU | rest | api_key | varies | Par notice ; *rights statements* Europeana (domaine public / CC / droits réservés) |
| gallica | Gallica (BnF) | Bibliothèque nationale de France | FR | sru | none | varies | BnF — vérifier par notice (domaine public / sous licence) |
| internet_archive | Internet Archive | Internet Archive | US | rest | none | varies | Par item ; beaucoup de domaine public |
| leiden | Leiden University Libraries Digital Collections | Leiden University Libraries (Universiteitsbibliotheek Leiden) | NL | iiif | none | varies | Leiden University Libraries — vérifier par notice (domaine public / sous licence) |
| openverse | Openverse | WordPress Foundation | INTL | rest | none | varies | Licences Creative Commons uniquement |
| paris_musees | Paris Musées — Collections (API) | Paris Musées (Ville de Paris) | FR | iiif | none | varies | Paris Musées — vérifier la mention de droits par notice (majorité domaine public) ; manifeste unique par notice (pas de Collection IIIF) |
| rijksmuseum | Rijksmuseum (IIIF via Europeana) | Rijksmuseum, Amsterdam | NL | iiif | none | [PDM 1.0](https://creativecommons.org/publicdomain/mark/1.0/) | Public Domain Mark — Rijksmuseum SK-A-3262 |
| smithsonian | Smithsonian Open Access | Smithsonian Institution | US | rest | api_key | CC0 | Open Access ; majoritairement CC0, vérifier par notice (`metadata_usage.access`, `media[].usage.access`) |
| vanderbilt | Vanderbilt University Museum of Art (IIIF) | Vanderbilt University Museum of Art | US | iiif | none | varies | Vanderbilt University Museum of Art — vérifier par notice (droits réservés possibles) ; manifeste unique par notice (pas de Collection IIIF) |
| wikidata | Wikidata | Wikimedia Foundation | INTL | sparql | none | CC0 | CC0 (données) ; les images suivent la licence de leur fichier Commons |
| wikimedia | Wikimedia Commons | Wikimedia Foundation | INTL | rest | none | varies | Licence par fichier Commons (CC BY-SA, CC0, DP…) |
| yale | Yale University Library Digital Collections | Yale University Library, New Haven | US | iiif | none | varies | Yale University Library — beaucoup de domaine public, vérifier par notice |

## Sources désactivées (9)

| id | Source | Institution | Pays | Protocole | Licence | Raison de la désactivation |
|---|---|---|---|---|---|---|
| cudl | Cambridge Digital Library (CUDL) | Cambridge University Library | GB | iiif | [CC BY-NC 4.0](https://creativecommons.org/licenses/by-nc/4.0/) | CC BY-NC — usage non commercial |
| ecodices | e-codices — Virtual Manuscript Library of Switzerland | e-codices (University of Fribourg) | CH | iiif | [CC BY-NC 4.0](https://creativecommons.org/licenses/by-nc/4.0/) | CC BY-NC — usage non commercial |
| irht | IRHT — Arca (bibliothèque numérique des manuscrits) | Institut de recherche et d'histoire des textes (IRHT-CNRS) | FR | iiif | varies | Licence variable — CC BY-NC 3.0 sur certains manuscrits ; à confirmer par la politique du projet |
| mai_saint_etienne | Musée d'Art et d'Industrie de Saint-Étienne | Musée d'Art et d'Industrie de Saint-Étienne (Pôle muséal) | FR | rest | © Musée d'Art et d'Industrie de Saint-Étienne | Mention globale réservant l'usage commercial des images (autorisation requise) — non commercial |
| musei_vaticani | Musei Vaticani — Catalogo Online | Musei Vaticani (Musei e Gallerie Pontificie) | VA | iiif | varies | Droits à confirmer par la politique du projet avant activation |
| pop | POP — Plateforme ouverte du patrimoine | Ministère de la Culture (France) | FR | iiif | Licence Ouverte 2.0 (métadonnées) | Images par notice majoritairement restrictives (DIFF/DIFFU) — ne pas republier ; métadonnées réutilisables |
| vam | Victoria and Albert Museum | Victoria and Albert Museum, London | GB | iiif | varies | V&A Terms and Conditions (restrictif) |
| vatican | Vatican Library — DigiVatLib | Biblioteca Apostolica Vaticana | VA | iiif | varies | Usage gratuit non commercial d'après le site — à confirmer |
| wellcome | Wellcome Collection | Wellcome Collection, London | GB | iiif | [CC BY-NC 4.0](https://creativecommons.org/licenses/by-nc/4.0/) | CC BY-NC — usage non commercial |

## Raccourcis licence

- **Domaine public / CC0** : `artic`, `bsb`, `cleveland`, `rijksmuseum`,
  `smithsonian` (plus `wikidata` pour les données).
- **Réutilisation libre (y compris commerciale), attribution requise** : `anmt`
  — décision du 21 août 2017 (art. L.213-1 du code du patrimoine) ; certaines
  vues restent « non affichables » par notice et sont ignorées.
- **Varies / par notice** : `albertina`, `arthistoricum`, `dpla`, `europeana`,
  `gallica`, `internet_archive`, `leiden`, `openverse`, `paris_musees`,
  `vanderbilt`, `wikimedia`, `yale` — la licence est décidée au niveau de
  l'`Asset` à la frontière du connecteur, pas de la source.
- **Non commercial / restrictif** : `cudl`, `ecodices`, `irht`,
  `mai_saint_etienne`, `musei_vaticani`, `vam`, `vatican`, `wellcome`.
- **Métadonnées libres, images restrictives** : `pop` — métadonnées sous Licence
  Ouverte 2.0 (etalab) ; images soumises à autorisation par notice (DIFF/DIFFU),
  donc la source est désactivée pour ne pas republier d'images restreintes.

Cette table est maintenue en accord avec les descripteurs : voir
`tests/test_sources_inventory.py`.
