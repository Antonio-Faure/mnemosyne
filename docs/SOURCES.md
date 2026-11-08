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
**consentement écrit obtenu par e-mail** (référence stockée dans le descripteur
sous `extra.scraping_consent`). Vérifié par
`tests/test_sources_inventory.py::test_html_sources_carry_scraping_consent`.

- Sources déclarées : **66**
- Sources actives : **54**
- Sources désactivées : **12**

## Sources actives (54)

| id | Source | Pays | Protocole | Licence |
|----|--------|------|-----------|---------|
| albertina | ALBERTINA Sammlungen Online | AT | iiif | varies (vérifier par notice) |
| anmt | Archives nationales du monde du travail (Roubaix) | FR | iiif | Réutilisation libre (décision 21 août 2017) |
| arthistoricum | arthistoricum.net IIIF (Deutsche Fotothek / SLUB Dresden) | DE | iiif | varies (vérifier par notice) |
| atlanta | Atlanta History Center — Album | US | rest | PDM-1.0 / CC0-1.0 / CC-BY-4.0 |
| artic | Art Institute of Chicago | US | iiif | CC0-1.0 (domaine public) |
| bsb | Bavarian State Library | DE | iiif | PDM 1.0 |
| bsb_collection | Bavarian State Library — digital collections (IIIF) | DE | iiif | varies (vérifier par notice) |
| byu | BYU Digital Collections | US | rest | PDM-1.0 / CC0-1.0 / CC-BY-4.0 |
| carli | CARLI Digital Collections — Illinois | US | rest | PDM-1.0 / CC0-1.0 / CC-BY-4.0 |
| cleveland | Cleveland Museum of Art — Open Access | US | rest | CC0-1.0 |
| colenda | Colenda Digital Repository (Penn Libraries) | US | iiif | varies (rightsstatements.org) |
| cooper_hewitt | Cooper Hewitt, Smithsonian Design Museum | US | rest | CC0-1.0 |
| dpla | Digital Public Library of America | US | rest | varies (vérifier droits + fournisseur) |
| digital_commonwealth | Digital Commonwealth — Massachusetts | US | rest | PDM-1.0 |
| eol | Encyclopedia of Life | INTL | rest | CC0-1.0 / CC-BY-4.0 |
| europeana | Europeana | EU | rest | varies (vérifier par notice) |
| gallica | Gallica (BnF) | FR | sru | varies (vérifier par notice) |
| gbif | GBIF — Global Biodiversity Information Facility | INTL | rest | varies (CC0-1.0 / CC-BY-4.0) |
| hammer | Hammer Museum — Online Collections (IIIF) | US | iiif | varies (vérifier par notice) |
| harvard_art_museums | Harvard Art Museums (IIIF) | US | iiif | varies (vérifier par notice) |
| hennepin | Hennepin County Library — Digital Collections | US | rest | PDM-1.0 / CC0-1.0 / CC-BY-4.0 |
| hillsborough | Hillsborough County Public Library — Digital Collections | US | rest | PDM-1.0 / CC0-1.0 / CC-BY-4.0 |
| inaturalist | iNaturalist — Observations | INTL | rest | CC0-1.0 / CC-BY-4.0 |
| internet_archive | Internet Archive | US | rest | varies (vérifier par notice) |
| japan_search | Japan Search — ジャパンサーチ | JP | rest | PDM-1.0 / CC0-1.0 / CC-BY-4.0 |
| kmska | KMSKA — Royal Museum of Fine Arts Antwerp | BE | iiif | PDM 1.0 |
| leiden | Leiden University Libraries Digital Collections | NL | iiif | varies (vérifier par notice) |
| lehigh | Lehigh University Libraries — Preserve (IIIF) | US | iiif | varies (vérifier par notice) |
| llgc | National Library of Wales — Digital Collections (IIIF) | GB | iiif | PDM 1.0 |
| met | Metropolitan Museum of Art — Open Access | US | rest | CC0-1.0 |
| nationalmuseum_se | Nationalmuseum Sweden — IIIF | SE | iiif | varies (vérifier par notice) |
| nasa | NASA Image and Video Library | US | rest | Public Domain (NASA) |
| nb_no | National Library of Norway — Nasjonalbiblioteket | NO | rest | PDM-1.0 |
| ndl | National Diet Library Digital Collections (IIIF) | JP | iiif | PDM 1.0 |
| nga | National Gallery of Art (Washington, DC) | US | iiif | varies (vérifier par notice) |
| north_dakota | North Dakota Digital Horizons | US | rest | PDM-1.0 / CC0-1.0 / CC-BY-4.0 |
| openverse | Openverse | INTL | rest | varies (CC0 / CC BY / CC BY-SA) |
| paris_musees | Paris Musées — Collections (API) | FR | iiif | varies (vérifier par notice) |
| penn_state | Penn State Digital Collections | US | rest | PDM-1.0 / CC0-1.0 / CC-BY-4.0 |
| princeton_art_museum | Princeton University Art Museum (IIIF) | US | iiif | varies (vérifier par notice) |
| rit | RIT Digital Collections (RIT Libraries) | US | iiif | varies (vérifier par notice) |
| rijksmuseum | Rijksmuseum (IIIF via Europeana) | NL | iiif | PDM 1.0 |
| scdl | South Carolina Digital Library | US | rest | PDM-1.0 / CC0-1.0 / CC-BY-4.0 |
| smithsonian | Smithsonian Open Access | US | rest | CC0 (vérifier par notice) |
| smk | SMK — Statens Museum for Kunst (National Gallery of Denmark) | DK | iiif | PDM 1.0 |
| texas_history | The Portal to Texas History (UNT Libraries) | US | iiif | varies (vérifier par notice ; items `rights.access=restricted` ignorés) |
| teva | Tennessee Virtual Archive (TeVA) | US | rest | PDM-1.0 / CC0-1.0 / CC-BY-4.0 |
| vanderbilt | Vanderbilt University Museum of Art (IIIF) | US | iiif | varies (vérifier par notice) |
| wellesley | Wellesley College Digital Repository (IIIF) | US | iiif | varies (vérifier par notice) |
| wikidata | Wikidata | INTL | sparql | CC0 (données) |
| wikimedia | Wikimedia Commons | INTL | rest | varies (licence par fichier) |
| wikimedia_commons_photos | Wikimedia Commons — Photographies | INTL | rest | varies (licence par fichier) |
| yale | Yale University Library Digital Collections | US | iiif | varies (vérifier par notice) |
| yale_lux | Yale Collections Discovery (LUX) — IIIF | INTL | iiif | varies (vérifier par notice) |

## Sources désactivées (12)

| id | Source | Pays | Protocole | Licence | Raison de la désactivation |
|----|--------|------|-----------|---------|----------------------------|
| belvedere | Belvedere — Sammlung Online | AT | iiif | varies | Œuvres sous droit d'auteur (© Bildrecht, Wien) — à confirmer par la politique du projet |
| cudl | Cambridge Digital Library (CUDL) | GB | iiif | CC BY-NC 4.0 | CC BY-NC — usage non commercial |
| ecodices | e-codices — Virtual Manuscript Library of Switzerland | CH | iiif | CC BY-NC 4.0 | CC BY-NC — usage non commercial |
| irht | IRHT — Arca (bibliothèque numérique des manuscrits) | FR | iiif | varies | Licence variable — CC BY-NC 3.0 sur certains manuscrits ; à confirmer par la politique du projet |
| loc_wwi_photos | Library of Congress — World War I photographs | US | rest | varies | API JSON `?fo=json` officielle mais 403 Akamai depuis l'IP d'exécution (2026-11-08) ; connecteur prêt, activation dès que l'accès est rétabli |
| mai_saint_etienne | Musée d'Art et d'Industrie de Saint-Étienne | FR | rest | © Musée d'Art et d'Industrie de Saint-Étienne | Mention globale réservant l'usage commercial des images (autorisation requise) — non commercial |
| musee_orsay | Musée d'Orsay — Collections (IIIF) | FR | iiif | Droits réservés — © EPMO | Mentions légales EPMO : reproduction/représentation interdite sans autorisation expresse — à confirmer par la politique du projet |
| musei_vaticani | Musei Vaticani — Catalogo Online | VA | iiif | varies | Droits à confirmer par la politique du projet avant activation |
| pop | POP — Plateforme ouverte du patrimoine | FR | iiif | Licence Ouverte 2.0 (métadonnées) | Images par notice majoritairement restrictives (DIFF/DIFFU) — ne pas republier ; métadonnées réutilisables |
| vam | Victoria and Albert Museum | GB | iiif | varies | V&A Terms and Conditions (restrictif) |
| vatican | Vatican Library — DigiVatLib | VA | iiif | varies | Usage gratuit non commercial d'après le site — à confirmer |
| wellcome | Wellcome Collection | GB | iiif | CC BY-NC 4.0 | CC BY-NC — usage non commercial |

Cette table est maintenue en accord avec les descripteurs : voir
`tests/test_sources_inventory.py`.

## Sources dégradées / indisponibles (constat 2026-11-08)

Constat issu de la tâche resolver #148, revérifié via `fetch_url` le 2026-11-08
(tâche #149). Aucune source n'est activée ni désactivée ici. Les fournisseurs
ci-dessous restent **actifs** mais leur état est documenté (`notes:` des
descripteurs) :

- **gallica**, **nga** : HTTP 403 (WAF/Cloudflare) depuis l'IP d'exécution ;
  blocage IP/ASN, pas un bug de chemin — code OK, laissé actif mais signalé
  « indisponible depuis cette IP ».
- **dpla** : l'API v2 est servie sous `/v2/items` (segment `items` requis) —
  corrigé.
- **met** : 404 sur un objet = ignoré proprement (l'objet absent ne dégrade plus
  la source).
- **eol** : 5xx/429 transitoires du CDN tolérés (result set abandonné, pas
  d'erreur de source).
