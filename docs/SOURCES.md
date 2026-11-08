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

- Sources déclarées : **66**
- Sources actives : **53**
- Sources désactivées : **13**
## Sources actives (53)
| albertina | ALBERTINA Sammlungen Online | ALBERTINA (Graphische Sammlung), Wien | AT | iiif | none | varies | ALBERTINA, Wien — beaucoup de domaine public (Gemeinfrei), vérifier par notice |
| anmt | Archives nationales du monde du travail (Roubaix) | Archives nationales du monde du travail | FR | iiif | none | Réutilisation libre (décision 21 août 2017) | ANMT — réutilisation libre commerciale et non commerciale ; attribution requise (origine + cote + titre du fonds) ; vues « non affichables » (`ligeoRestrictedAccess`) ignorées |
| arthistoricum | arthistoricum.net IIIF (Deutsche Fotothek / SLUB Dresden) | arthistoricum.net — Fachinformationsdienst Kunst, Fotografie, Design (SLUB Dresden) | DE | iiif | none | varies | SLUB Dresden / arthistoricum.net — vérifier par notice (conditions Deutsche Fotothek) |
| atlanta | Atlanta History Center — Album | Atlanta History Center | US | rest | none | PDM-1.0 / CC0-1.0 / CC-BY-4.0 | Atlanta History Center — API CONTENTdm publique sans clé (album.atlantahistorycenter.com/digital/api) ; recherche `/search/searchterm/<q>` (maxRecords 10, pagination `start`) puis `/singleitem/collection/<alias>/id/<id>` ; filtre image `contentType` `image/*` et `imageUri` non vide ; filtre droits explicites (PD/NoC-US/CC0/CC BY ; rejette droits réservés, non évalués et CC BY-NC/ND) ; images via IIIF `iiif/2/<alias>:<id>` (!1200 image, !400 vignette) ; aucun téléchargement (URLs seulement) |
| artic | Art Institute of Chicago | Art Institute of Chicago (AIC) | US | iiif | none | Public Domain (CC0-1.0) | Domaine public — *The Bedroom*, Vincent van Gogh (1888) |
| bsb | Bavarian State Library | Bayerische Staatsbibliothek, München | DE | iiif | none | [PDM 1.0](https://creativecommons.org/publicdomain/mark/1.0/) | Public Domain Mark — Bayerische Staatsbibliothek |
| bsb_collection | Bavarian State Library — digital collections (IIIF) | Bayerische Staatsbibliothek, München | DE | iiif | none | varies | Bayerische Staatsbibliothek — vérifier par notice (domaine public pour une grande partie) ; Collection IIIF « top » (iiif/presentation/v2/collection/top) |
| byu | BYU Digital Collections | Brigham Young University | US | rest | none | PDM-1.0 / CC0-1.0 / CC-BY-4.0 | Brigham Young University — API CONTENTdm publique sans clé (contentdm.lib.byu.edu/digital/api) ; recherche `/search/searchterm/<q>` (maxRecords 10, pagination `start`) puis `/singleitem/collection/<alias>/id/<id>` ; filtre image `contentType` commençant par `image/*` et `imageUri` non vide ; filtre droits explicites par notice (PD/NoC-US/CC0/CC BY ; rejette « not evaluated », « undetermined », « all rights reserved », « In Copyright », CC BY-NC/ND) ; images via IIIF `iiif/2/<alias>:<id>` (!1200 image, !400 vignette) ; aucun téléchargement (URLs seulement), aucun scraping HTML |
| carli | CARLI Digital Collections — Illinois | Consortium of Academic and Research Libraries in Illinois | US | rest | none | PDM-1.0 / CC0-1.0 / CC-BY-4.0 | Consortium of Academic and Research Libraries in Illinois — API CONTENTdm publique sans clé (collections.carli.illinois.edu/digital/api) ; recherche `/digital/api/search/searchterm/<q>` (maxRecords 10, pagination `start`) puis `/digital/api/singleitem/collection/<alias>/id/<id>` ; filtre image `contentType` `image/*` et `imageUri` non vide ; filtre droits explicites par notice (PD/NoC-US/CC0/CC BY ; rejette InC, CNE, droits réservés et restrictions non commerciales / CC BY-NC/ND) ; images via IIIF `iiif/2/<alias>:<id>` (!1200 image, !400 vignette) ; aucun téléchargement (URLs seulement), aucun scraping HTML. Seeds orientés portrait/Chicago : la requête `portrait` renvoie des images ouvertes (collection chm_museum, « No known copyright restrictions ») |
| cleveland | Cleveland Museum of Art — Open Access | Cleveland Museum of Art | US | rest | none | CC0-1.0 | CC0 1.0 Universal (images) ; œuvres sous-jacentes dans le domaine public |
| colenda | Colenda Digital Repository (Penn Libraries) | University of Pennsylvania Libraries — rightsstatements.org par notice (majorité domaine public / No Copyright) ; manifeste unique par notice (pas de Collection IIIF) |
| cooper_hewitt | Cooper Hewitt, Smithsonian Design Museum — Collections | Cooper Hewitt, Smithsonian Design Museum | US | rest | none | CC0-1.0 | Cooper Hewitt / Smithsonian Open Access — API GraphQL publique sans clé ; médias marqués `multimedia[].cc0 = true` en CC0 1.0 Universal ; seuls les médias CC0 porteurs d'une URL sont moissonnés ; rate limit anonyme (~30/min, HTTP 429 + Retry-After) |
| dpla | Digital Public Library of America | Digital Public Library of America | US | rest | api_key | varies | Par notice ; agrégateur US (équivalent d'Européana), vérifier `rights` et le fournisseur ; recherche `/v2/items` (correctif 2026-11-08) |
| digital_commonwealth | Digital Commonwealth — Massachusetts Collections | Digital Commonwealth (Massachusetts) | US | rest | none | PDM-1.0 | Digital Commonwealth — API Blacklight JSON publique sans clé (digitalcommonwealth.org/search.json) ; ne conserver que les notices explicitement ouvertes (`reuse_allowed_ssi` == « no restrictions » / `rights_ss` « No known copyright restrictions » / CC0) ; images via IIIF (iiif.digitalcommonwealth.org, !1200/!400) ; aucune image téléchargée |
| eol | Encyclopedia of Life | Encyclopedia of Life | INTL | rest | none | CC0-1.0 / CC-BY-4.0 | Encyclopedia of Life — API REST publique sans clé (eol.org/api) ; recherche `/search/1.0.json` (page 1-based, itemsPerPage 50, borné par `totalResults`) puis détail `/pages/1.0/<id>.json` (`taxonConcept.dataObjects[]`) ; une image qualifiée = un Asset ; conserver seulement les dataObjects `image/*` dont `license` est CC0 1.0 ou CC BY 3.0/4.0 (revérifié côté connecteur, http(s) avec ou sans www) ; attribution par média (`rightsHolder`) ; page détail récupérée seulement tant que la limite n'est pas atteinte (`max_pages` défaut 3) ; 5xx/429 transitoires tolérés (correctif 2026-11-08) ; aucun téléchargement (URLs seulement), aucun scraping HTML |
| europeana | Europeana | Europeana Foundation | EU | rest | api_key | varies | Europeana — Search API v2 (api.europeana.eu/record/v2/search.json) ; clé API requise (`EUROPEANA_API_KEY`) ; images via `edmIsShownBy`, vignettes via `edmPreview` ; droits par notice (domaine public / CC / droits réservés) |
| gallica | Gallica (BnF) | Bibliothèque nationale de France | FR | sru | none | varies | Gallica (BnF) — SRU renvoie des notices Dublin Core ; images exposées via IIIF ; vérifier les droits par notice (domaine public / sous licence) ; **indisponible depuis cette IP (Cloudflare/WAF 403, 2026-11-08)** — voir « Sources dégradées » ci-dessous |
| gbif | GBIF — Global Biodiversity Information Facility | GBIF | INTL | rest | none | varies (CC0-1.0 / CC-BY-4.0) | GBIF — API REST publique sans clé (api.gbif.org/v1/occurrence/search, mediaType=StillImage) ; une occurrence peut produire plusieurs Assets (un par média) ; conserver seulement les médias dont `media[].license` est CC0 1.0 ou CC BY 4.0 (revérifié côté connecteur, http(s) avec ou sans www) ; attribution par média (`rightsHolder`/`creator`) ; pagination par offset (limit ≤ 300, `count`, `endOfRecords`) ; aucun téléchargement (URLs seulement) |
| hammer | Hammer Museum — Online Collections (IIIF) | Hammer Museum, University of California, Los Angeles (UCLA) | US | iiif | none | varies | Hammer Museum (UCLA) — droits par notice (CC0 / domaine public ou « In Copyright », rightsstatements.org) ; manifeste unique par objet (pas de Collection IIIF) |
| harvard_art_museums | Harvard Art Museums (IIIF) | Harvard Art Museums, Cambridge, MA | US | iiif | none | varies | Harvard Art Museums — vérifier la mention de droits par notice (nombreux domaines publics) ; manifeste unique par objet (pas de Collection IIIF) |
| hennepin | Hennepin County Library — Digital Collections | Hennepin County Library | US | rest | none | PDM-1.0 / CC0-1.0 / CC-BY-4.0 | Hennepin County Library — API CONTENTdm publique sans clé (digitalcollections.hclib.org/digital/api) ; recherche `/search/searchterm/<q>` (maxRecords 10, pagination `start`) puis `/singleitem/collection/<alias>/id/<id>` ; filtre image `contentType` `image/*` et `imageUri` non vide ; filtre droits explicites par notice (PD/NoC-US/CC0/CC BY ; rejette InC/CNE, droits réservés et CC BY-NC/ND) ; l'imageUri `/api/singleitem/image/...` (403 OCLC) est ignoré et reconstruit en IIIF `/digital/iiif/2/<alias>:<id>` (!1200 image, !400 vignette) ; aucun téléchargement (URLs seulement) |
| hillsborough | Hillsborough County Public Library — Digital Collections | Tampa-Hillsborough County Public Library | US | rest | none | PDM-1.0 / CC0-1.0 / CC-BY-4.0 | Hillsborough County Public Library — API CONTENTdm publique sans clé (digitalcollections.hcplc.org/digital/api) ; recherche `/search/searchterm/<q>` (maxRecords 10, pagination `start`) puis `/singleitem/collection/<alias>/id/<id>` ; filtre image `contentType` `image/*` et `imageUri` non vide ; filtre droits explicites par notice (PD/NoC-US/CC0/CC BY ; rejette InC/CNE, droits réservés et CC BY-NC/ND) ; images via IIIF `iiif/2/<alias>:<id>` (!1200 image, !400 vignette) ; aucun téléchargement (URLs seulement) |
| inaturalist | iNaturalist — Observations | iNaturalist (California Academy of Sciences / National Geographic Society) | INTL | rest | none | CC0-1.0 / CC-BY-4.0 | iNaturalist — API REST publique sans clé (api.inaturalist.org/v1/observations) ; une photo qualifiée = un Asset ; conserver seulement les photos dont le `license_code` au niveau photo est cc0 ou cc-by (revérifié côté connecteur) ; attribution par photo (`photo.attribution`) ; image principale = `square.jpg`→`large.jpg`, vignette = `square.jpg` ; pagination 1-based (`per_page` ≤ 200, `total_results`) ; aucun téléchargement (URLs seulement) |
| internet_archive | Internet Archive | Internet Archive | US | rest | none | varies | Par item ; beaucoup de domaine public |
| japan_search | Japan Search — ジャパンサーチ | Japan Search (National Diet Library) | JP | rest | none | PDM-1.0 / CC0-1.0 / CC-BY-4.0 | Japan Search — agrégateur national japonais, API REST publique sans clé (jpsearch.go.jp/api/item/search/jps-cross) ; filtres f-contents=image, f-caccess=internet, f-rights répété (+pdm/+cc0/+ccby) ; pagination from/size (size clamp 100) ; images via contentsUrl[0] sinon thumbnailUrl[0] ; licences pdm→PDM-1.0, cc0→CC0-1.0, ccby→CC-BY-4.0 ; vérifier par notice ; aucun téléchargement (URLs seulement), aucun scraping HTML |
| kmska | KMSKA — Koninklijk Museum voor Schone Kunsten Antwerpen (Royal Museum of Fine Arts Antwerp) | Koninklijk Museum voor Schone Kunsten Antwerpen | BE | iiif | none | [PDM 1.0](https://creativecommons.org/publicdomain/mark/1.0/) | Royal Museum of Fine Arts Antwerp — Flemish Community (domaine public, CC0) ; Collection IIIF « Top Level Collection for Imagehub » (iiif/2/collection/manifest.json) |
| leiden | Leiden University Libraries Digital Collections | Leiden University Libraries (Universiteitsbibliotheek Leiden) | NL | iiif | none | varies | Leiden University Libraries — vérifier par notice (domaine public / sous licence) |
| lehigh | Lehigh University Libraries — Preserve (IIIF) | Lehigh University Libraries | US | iiif | none | varies | Lehigh University Libraries — vérifier par notice (droits variables, rightsstatements.org possible) ; Islandora/Cantaloupe ; manifeste unique par notice (pas de Collection IIIF) |
| llgc | National Library of Wales — Digital Collections (IIIF) | Llyfrgell Genedlaethol Cymru – The National Library of Wales | GB | iiif | none | [PDM 1.0](https://creativecommons.org/publicdomain/mark/1.0/) | Public Domain Mark — National Library of Wales (vérifier par notice) ; manifeste unique par notice (pas de Collection IIIF) |
| met | Metropolitan Museum of Art — Open Access | The Metropolitan Museum of Art, New York | US | rest | none | CC0-1.0 | Met Open Access — images du domaine public sous CC0 1.0 Universal ; vérifier par notice (`isPublicDomain`, `primaryImage`) ; recherche v1.1 (l'ancien v1 retiré le 2026-10-01) ; ne conserver que `isPublicDomain == true` et `primaryImage` non vide ; objet absent (404) ignoré proprement (correctif 2026-11-08) |
| nationalmuseum_se | Nationalmuseum Sweden — IIIF (iiifhosting.com) | Nationalmuseum (Sweden) | SE | iiif | none | varies | Nationalmuseum (Sweden) — vérifier par notice (domaine public / CC) ; manifeste unique par objet (pas de Collection IIIF) |
| nasa | NASA Image and Video Library | NASA | US | rest | none | Public Domain (NASA) | NASA content generally not copyrighted; some items may be third-party — verify per item ; API REST publique sans clé (images-api.nasa.gov/search) ; pagination 1-based (`page_size` ≤ 100, `collection.metadata.total_hits`) ; ignorer items sans `links` ou `media_type != image` ; URLs d'images via `links[].href` (~large / ~medium / ~orig, vignette ~thumb) ; page_url images.nasa.gov/details/<nasa_id> ; aucun téléchargement (URLs seulement) |
| nb_no | National Library of Norway — Nasjonalbiblioteket | National Library of Norway | NO | rest | none | PDM-1.0 | Bibliothèque nationale de Norvège — API REST publique sans clé (api.nb.no/catalog/v1/items) ; ne garder que les notices `accessInfo.isPublicDomain == true` et `accessInfo.isDigital == true` (viewability ≠ « NONE ») ; images via manifeste IIIF (première page des livres multi-pages), vignette `thumbnail` si présente ; pagination 0-based (`page`, `size` ≤ 100, `totalPages`) ; aucun scraping HTML, aucune image téléchargée |
| ndl | National Diet Library Digital Collections (IIIF) | National Diet Library (国立国会図書館), Tokyo | JP | iiif | none | [PDM 1.0](https://creativecommons.org/publicdomain/mark/1.0/) | 国立国会図書館 National Diet Library, JAPAN — Public Domain Mark (PDM) ; manifeste unique par notice (pas de Collection IIIF) |
| nga | National Gallery of Art (Washington, DC) | National Gallery of Art | US | iiif | none | varies | National Gallery of Art — Open Access (images du domaine public libres, y compris usage commercial ; métadonnées CC0) ; vérifier les droits par notice ; manifeste unique par objet (pas de Collection IIIF) ; **indisponible depuis cette IP (WAF 403, 2026-11-08)** — voir « Sources dégradées » ci-dessous |
| north_dakota | North Dakota Digital Horizons | North Dakota State Library / NDSU Libraries | US | rest | none | PDM-1.0 / CC0-1.0 / CC-BY-4.0 | North Dakota State Library / NDSU Libraries — API CONTENTdm publique sans clé (digitalhorizonsonline.org/digital/api) ; recherche `/search/searchterm/<q>` (maxRecords 10, pagination `start`) puis `/singleitem/collection/<alias>/id/<id>` ; filtre image `contentType` `image/*` et `imageUri` non vide ; filtre droits explicites par notice (PD/NoC-US/CC0/CC BY ; rejette « In Copyright », « Copyright held by the University Archives. », InC/CNE, droits réservés et CC BY-NC/ND) ; images via IIIF `iiif/2/<alias>:<id>` (!1200 image, !400 vignette) ; page_url via itemLink ; aucun téléchargement (URLs seulement) |
| openverse | Openverse | WordPress Foundation | INTL | rest | none | varies | Licences Creative Commons uniquement (CC0, CC BY, CC BY-SA ; exclut NC/ND) ; API REST publique sans clé (api.openverse.org/v1/images) ; ne conserver que les licences ouvertes ; pagination `page`/`page_size` |
| paris_musees | Paris Musées — Collections (API) | Paris Musées (Ville de Paris) | FR | iiif | none | varies | Paris Musées — vérifier la mention de droits par notice (majorité domaine public) ; manifeste unique par notice (pas de Collection IIIF) |
| penn_state | Penn State Digital Collections | Pennsylvania State University Libraries | US | rest | none | PDM-1.0 / CC0-1.0 / CC-BY-4.0 | Pennsylvania State University Libraries — API CONTENTdm publique sans clé (digital.libraries.psu.edu/digital/api) ; recherche `/search/searchterm/<q>` (maxRecords 10, pagination `start`) puis `/singleitem/collection/<alias>/id/<id>` ; filtre image `contentType` `image/*` et `imageUri` non vide ; filtre droits explicites par notice (PD/NoC-US/CC0/CC BY ; rejette « In Copyright », InC/CNE, droits réservés et CC BY-NC/ND) ; images via IIIF `iiif/2/<alias>:<id>` (!1200 image, !400 vignette) ; page_url via itemLink ; aucun téléchargement (URLs seulement) |
| princeton_art_museum | Princeton University Art Museum (IIIF) | Princeton University Art Museum, Princeton, NJ | US | iiif | none | varies | Princeton University Art Museum — vérifier la mention de droits par notice (nombreux domaines publics) ; manifeste unique par objet (pas de Collection IIIF) |
| rit | RIT Digital Collections (RIT Libraries) | Rochester Institute of Technology Libraries, Rochester, NY | US | iiif | none | varies | RIT Libraries — vérifier la mention de droits par notice (Cary Graphic Arts Collection et autres fonds) ; manifeste unique par objet (pas de Collection IIIF) |
| rijksmuseum | Rijksmuseum (IIIF via Europeana) | Rijksmuseum, Amsterdam | NL | iiif | none | [PDM 1.0](https://creativecommons.org/publicdomain/mark/1.0/) | Public Domain Mark — Rijksmuseum SK-A-3262 |
| scdl | South Carolina Digital Library | University of South Carolina | US | rest | none | PDM-1.0 / CC0-1.0 / CC-BY-4.0 | University of South Carolina — API CONTENTdm publique sans clé (digital.tcl.sc.edu/digital/api) ; recherche `/search/searchterm/<q>` (maxRecords 10, pagination `start`) puis `/singleitem/collection/<alias>/id/<id>` ; filtre image `contentType` `image/*` et `imageUri` non vide ; filtre droits explicites (PD/NoC-US/CC0/CC BY ; rejette droits réservés, non évalués et CC BY-NC/ND) ; images via IIIF `iiif/2/<alias>:<id>` (!1200 image, !400 vignette) ; aucun téléchargement (URLs seulement) |
| smithsonian | Smithsonian Open Access | Smithsonian Institution | US | rest | api_key | CC0 | Open Access ; majoritairement CC0, vérifier par notice (`metadata_usage.access`, `media[].usage.access`) |
| smk | SMK — Statens Museum for Kunst (National Gallery of Denmark) | SMK — Statens Museum for Kunst | DK | iiif | none | [PDM 1.0](https://creativecommons.org/publicdomain/mark/1.0/) | Public Domain Mark — SMK — the national gallery of Denmark |
| teva | Tennessee Virtual Archive (TeVA) | Tennessee State Library and Archives | US | rest | none | PDM-1.0 / CC0-1.0 / CC-BY-4.0 | Tennessee State Library and Archives — API CONTENTdm publique sans clé (teva.contentdm.oclc.org/digital/api) ; recherche `/search/searchterm/<q>` (maxRecords 10, pagination `start`) puis `/singleitem/collection/<alias>/id/<id>` ; filtre image `contentType` `image/*` et `imageUri` non vide ; filtre droits explicites (NoC-US/PD/CC0/CC BY ; rejette non évalués et droits réservés) ; images via IIIF `iiif/2/<alias>:<id>` (!1200 image, !400 vignette) ; aucun téléchargement (URLs seulement) |
| vanderbilt | Vanderbilt University Museum of Art (IIIF) | Vanderbilt University Museum of Art | US | iiif | none | varies | Vanderbilt University Museum of Art — vérifier par notice (droits réservés possibles) ; manifeste unique par notice (pas de Collection IIIF) |
| wellesley | Wellesley College Digital Repository (IIIF) | Wellesley College Library | US | iiif | none | varies | Wellesley College — vérifier par notice (droits variables, rightsstatements.org possible) ; manifeste unique par notice (pas de Collection IIIF) ; hôte derrière un challenge Cloudflare Turnstile (accès programmatique à résoudre via navigateur/HITL) |
| wikidata | Wikidata | Wikimedia Foundation | INTL | sparql | none | CC0 | CC0 (données) ; les images suivent la licence de leur fichier Commons |
| wikimedia | Wikimedia Commons | Wikimedia Foundation | INTL | rest | none | varies | Licence par fichier Commons (CC BY-SA, CC0, DP…) |
| wikimedia_commons_photos | Wikimedia Commons — Photographies | Wikimedia Foundation | INTL | rest | none | varies | Licence par fichier Commons (CC BY-SA, CC0, DP…) ; recherche namespace 6 (fichier) via `imageinfo`, restreinte à `filetype:bitmap` + garde MIME raster — exclut les PDF/DjVu de livres numérisés ; photos de 1914 (troupes allemandes Bruxelles/Liège, réfugiés belges, Louvain) ; `maxlag=5` |
| yale | Yale University Library Digital Collections | Yale University Library, New Haven | US | iiif | none | varies | Yale University Library — beaucoup de domaine public, vérifier par notice |
| yale_lux | Yale Collections Discovery (LUX) — IIIF | Yale University (LUX) | INTL | iiif | none | varies | Yale University (LUX) — beaucoup de domaine public (CC0), vérifier par notice ; manifeste unique (pas de Collection IIIF) |

## Sources désactivées (13)

| id | Source | Institution | Pays | Protocole | Licence | Raison de la désactivation |
|---|---|---|---|---|---|---|
| belvedere | Belvedere — Sammlung Online | Österreichische Galerie Belvedere, Wien | AT | iiif | varies | Œuvres sous droit d'auteur (© Bildrecht, Wien) — à confirmer par la politique du projet |
| cudl | Cambridge Digital Library (CUDL) | Cambridge University Library | GB | iiif | [CC BY-NC 4.0](https://creativecommons.org/licenses/by-nc/4.0/) | CC BY-NC — usage non commercial |
| ecodices | e-codices — Virtual Manuscript Library of Switzerland | e-codices (University of Fribourg) | CH | iiif | [CC BY-NC 4.0](https://creativecommons.org/licenses/by-nc/4.0/) | CC BY-NC — usage non commercial |
| irht | IRHT — Arca (bibliothèque numérique des manuscrits) | Institut de recherche et d'histoire des textes (IRHT-CNRS) | FR | iiif | varies | Licence variable — CC BY-NC 3.0 sur certains manuscrits ; à confirmer par la politique du projet |
| loc_wwi_photos | Library of Congress — World War I photographs (Prints & Photographs) | Library of Congress | US | rest | varies | API JSON `?fo=json` officielle mais **403 Akamai** depuis l'IP d'exécution (2026-11-08) ; connecteur prêt, activation dès que l'accès est rétabli (même cas que Gallica/NGA) |
| mai_saint_etienne | Musée d'Art et d'Industrie de Saint-Étienne | Musée d'Art et d'Industrie de Saint-Étienne (Pôle muséal) | FR | rest | © Musée d'Art et d'Industrie de Saint-Étienne | Mention globale réservant l'usage commercial des images (autorisation requise) — non commercial |
| musee_orsay | Musée d'Orsay — Collections (IIIF) | Établissement public des musées d'Orsay et de l'Orangerie (EPMO) | FR | iiif | Droits réservés — © EPMO | Mentions légales EPMO : reproduction/représentation interdite sans autorisation expresse (droits réservés) — à confirmer par la politique du projet |
| musee_petrole_pechelbronn | Musée français du pétrole — Merkwiller-Pechelbronn (photothèque) | Musée français du pétrole (Merkwiller-Pechelbronn) | FR | rest | Inconnue — en attente d'autorisation écrite | Autorisation écrite en attente (formulaire web du musée + e-mail Parc Vosges du Nord, 2026-11-08 ; adresses officielles du musée hors service) ; aucun accès programmatique, aucun scraping sans consentement écrit — voir `extra.authorization_request` |
| musei_vaticani | Musei Vaticani — Catalogo Online | Musei Vaticani (Musei e Gallerie Pontificie) | VA | iiif | varies | Droits à confirmer par la politique du projet avant activation |
| pop | POP — Plateforme ouverte du patrimoine | Ministère de la Culture (France) | FR | iiif | Licence Ouverte 2.0 (métadonnées) | Images par notice majoritairement restrictives (DIFF/DIFFU) — ne pas republier ; métadonnées réutilisables |
| vam | Victoria and Albert Museum | Victoria and Albert Museum, London | GB | iiif | varies | V&A Terms and Conditions (restrictif) |
| vatican | Vatican Library — DigiVatLib | Biblioteca Apostolica Vaticana | VA | iiif | varies | Usage gratuit non commercial d'après le site — à confirmer |
| wellcome | Wellcome Collection | Wellcome Collection, London | GB | iiif | [CC BY-NC 4.0](https://creativecommons.org/licenses/by-nc/4.0/) | CC BY-NC — usage non commercial |

## Raccourcis licence

- **Domaine public / CC0** : `atlanta`, `artic`, `bsb`, `byu`, `carli`, `cleveland`, `cooper_hewitt`,
  `digital_commonwealth`, `hennepin`, `hillsborough`, `japan_search`, `kmska`, `llgc`, `met`, `nasa`, `nb_no`, `ndl`, `north_dakota`, `penn_state`, `rijksmuseum`, `scdl`, `smk`, `smithsonian`, `teva` (plus
  `wikidata` pour les données ; `nasa` = domaine public US, pas CC0 ; `atlanta`,
  `byu`, `carli`, `hennepin`, `hillsborough`, `north_dakota`, `penn_state`, `scdl`, `teva` = CONTENTdm — filtre PD/NoC-US/CC0/CC BY par
  notice ; `japan_search` — filtre pdm/cc0/ccby par notice).
- **Réutilisation libre (y compris commerciale), attribution requise** : `anmt`,
  `eol`, `gbif`, `inaturalist` — `anmt` : décision du 21 août 2017 (art. L.213-1
  du code du patrimoine) ; certaines vues restent « non affichables » par notice
  et sont ignorées. `eol` : uniquement les médias sous CC0 1.0 ou CC BY 3.0/4.0
  (licence vérifiée au niveau de chaque média `dataObjects[].license`),
  attribution par média. `gbif` : uniquement les médias sous CC0 1.0 ou CC BY 4.0
  (licence vérifiée au niveau de chaque média `media[].license`), attribution par
  média. `inaturalist` : uniquement les photos sous CC0 ou CC BY 4.0.
- **Varies / par notice** : `albertina`, `arthistoricum`, `bsb_collection`,
  `colenda`, `dpla`, `europeana`, `gallica`, `hammer`, `harvard_art_museums`,
  `internet_archive`, `leiden`, `lehigh`, `nationalmuseum_se`, `nga`, `openverse`,
  `paris_musees`, `princeton_art_museum`, `rit`, `vanderbilt`, `wellesley`, `wikimedia`,
  `wikimedia_commons_photos`, `yale`, `yale_lux` — la licence est décidée au
  niveau de l'`Asset` à la frontière du connecteur, pas de la source.
- **Non commercial / restrictif** : `belvedere`, `cudl`, `ecodices`, `irht`,
  `mai_saint_etienne`, `musee_orsay`, `musei_vaticani`, `vam`, `vatican`,
  `wellcome`.
- **Métadonnées libres, images restrictives** : `pop` — métadonnées sous Licence
  Ouverte 2.0 (etalab) ; images soumises à autorisation par notice (DIFF/DIFFU),
  donc la source est désactivée pour ne pas republier d'images restreintes.
- **Autorisation en attente (droits non établis)** : `musee_petrole_pechelbronn` —
  la photothèque du Musée français du pétrole (Merkwiller-Pechelbronn) ne propose
  aucun accès programmatique documenté et n'a concédé aucune licence de
  réutilisation ; autorisation écrite, licence et mention de crédit restent à
  établir (demande du 2026-11-08 via formulaire web du musée + Parc Vosges du
  Nord, adresses officielles du musée hors service ; voir
  `extra.authorization_request`). Source désactivée, aucun scraping.

Cette table est maintenue en accord avec les descripteurs : voir
`tests/test_sources_inventory.py`.

## Sources dégradées / indisponibles (constat 2026-11-08)

Constat issu de la tâche resolver #148 (`catalog_search` sur tout le catalogue),
ensuite reproduit/vérifié via `fetch_url` le **2026-11-08** (tâche #149). Aucune
source n'est activée ni désactivée ici : les compteurs de l'en-tête (déclarées /
actives / désactivées) restent **inchangés** par ce constat. Les fournisseurs ci-dessous restent
**actifs** mais leur état est documenté (`notes:` des descripteurs + ce tableau).

| source | URL testée | code/erreur avant | diagnostic | correctif / test | statut final |
|--------|-----------|-------------------|-----------|------------------|--------------|
| dpla | `https://api.dp.la/v2` | HTTP 404 | segment `/items` manquant : l'API v2 est servie sous `/v2/items` | `dpla.py` : URL = `base_url + /items` (clé toujours lue depuis le vault, `DPLA_API_KEY`) ; tests `test_dpla.py` | **corrigé** (`/v2` → 404 confirmé, `/v2/items` → 403 auth = bon chemin) |
| met | `https://collectionapi.metmuseum.org/public/collection/v1/objects/294856` | HTTP 404 | id d'objet absent/retiré : le 404 remontait comme erreur de source et dégradait tout le Met | `met.py` : 404 sur un objet = ignoré proprement (`continue`) ; 401/403/5xx re-levés (non masqués) ; tests `test_met.py` | **corrigé** (404 objet toléré hors ligne) |
| eol | `https://eol.org/api/search/1.0.json` | HTTP 520 (Cloudflare, transitoire) | 5xx transitoire du CDN ; `520` n'est pas dans les statuts retentés par le client HTTP | `eol.py` : les 5xx/429 transitoires (dont 520–527) sont tolérés (result set abandonné, pas d'erreur de source) ; 4xx (droits/accès) non masqués ; test `test_eol_transient.py` | **vérifié transitoire** (revérifié à 200 le 2026-11-08) + tolérance ajoutée |
| gallica | `https://gallica.bnf.fr/SRU` et `https://gallica.bnf.fr/services/engine/search/sru` | HTTP 403 (page WAF Cloudflare « Sorry, you have been blocked », ~5665 o) | blocage **IP/ASN (infrastructurel)**, identique avec User-Agent navigateur ; pas un bug de chemin/requête — le connecteur SRU/IIIF est correct | aucun changement de code au hasard (par consigne) ; diagnostic tracé (`notes:` descripteur) | **indisponible depuis cette IP (Cloudflare)** — code OK |
| nga | `https://www.nga.gov/api/v1/iiif/presentation/manifest.json?cultObj:id=395` | HTTP 403 (WAF www.nga.gov) | blocage **IP/ASN** de même famille ; le connecteur frappe bien l'API IIIF officielle (aucun scraping HTML) | aucun changement de code au hasard ; diagnostic tracé (`notes:` descripteur) | **indisponible depuis cette IP (WAF/Cloudflare)** — code OK |

Notes de diagnostic :

- Les hôtes `api.dp.la`, `collectionapi.metmuseum.org`, `gallica.bnf.fr`,
  `www.nga.gov` renvoient 403 à cette IP d'exécution, alors que `example.com` et
  `eol.org` répondent normalement : le blocage est donc bien au niveau WAF/IP et
  **non** dans nos requêtes (excepté le segment `/items` de DPLA, réellement buggé).
- **Gallica / NGA** sont laissés **actifs** mais signalés « indisponible depuis
  cette IP (Cloudflare/WAF) » ; une réactivation fonctionnelle suppose une IP/ASN
  non bloquée (ou un accès via navigateur/HITL), hors périmètre du code.
