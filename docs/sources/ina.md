# INA — Institut national de l'audiovisuel

Source for French audiovisual **archival notices** on the "pétrole français
oublié" (Lacq, Parentis-en-Born, Pechelbronn): filmed news (*Actualités
Françaises*), documentaries and radio programmes held by the INA legal deposit.

- **id**: `ina`
- **institution**: Institut national de l'audiovisuel (INA)
- **homepage (Surface A)**: <https://catalogue.ina.fr>
- **protocol**: `html` (regex parsing of OPSIS pages — see the consent trace below)
- **auth**: none (no API key)
- **type**: `audiovisual-archive-notice` — a **metadata notice + deep link**, not an image
- **license / rights**: *Tous droits réservés © INA*
- **reuse_allowed**: `false` · **media_download**: `false` · **attribution_required**: `true`
- **reuse / ordering**: <https://mediaclip.ina.fr/>
- **attribution**: `Source : INA — Institut national de l'audiovisuel`

## Two surfaces, only one is lawful to automate

### Surface A — `catalogue.ina.fr` (Inathèque / OPSIS 3.0.6 legal-deposit catalog) — **enabled**

Public HTML catalog of the French legal deposit. `robots.txt` is permissive (only
`GPTBot`/`ChatGPT-User` are blocked) with `Crawl-delay: 5`. There is **no open
API**, so this is a small, structure-less HTML surface parsed with regex.

- Search page (GET):
  `https://catalogue.ina.fr/docListe/{SECTION}/?base_label=TVNAT,RADIO,TVSAT,PUBTV,TVREG,CLIPTV,DLDON&itoustext=<q>&sujets_filter=Sujet&bool_operator=AND&tri=score1&nbLignes=50&page=1`
  - `SECTION` ∈ {`TV-RADIO` (used), `ECRIT`, `WEB-MEDIA`}. `TV-RADIO` = audiovisual.
  - `tri` = `score1` (relevance) or `datdif` (date, ascending only — the connector
    sorts client-side; undated notices default to `01/01/1900`, so they cluster first).
  - `nbLignes` ∈ {20, 50, 100, 500}; `page` 1-based.
  - Total is read from the `Enregistrements <a> à <b> sur <TOTAL>` counter.
  - Results are the `table.tableau-header-gris` rows `tr.result_line_a|_b`; cells are
    `[0]indice [1]chaîne [2]date DD/MM/YYYY [3]heure [4]durée HH:MM:SS(:FF) [5]titre(<a>)
    [6]collection [7]programme [8]genre`. Empty cells are common → parsed as `null`.
  - Notice link: `https://catalogue.ina.fr/doc/{SECTION}/{DOC_ID}/{slug}` (the
    `?rang=NN` query is dropped). `DOC_ID` is kept opaque (`DA`/`DO`=TV, `RD`=radio,
    `RE`=reportage, `PH`=parlé/photo …).
- Notice detail (GET the notice URL): OPSIS field table
  `<td class="…label_champs_form">LABEL</td><td id="CODE" class="…val_champs_form">VALUE</td>`.
  Fields are read **by `id` code** (falling back to the label): `NO, TI, TICOL,
  TIPROG, CH, DATDIF, DUREE, GENRE, DE, DES, RES, CHAP, SEQ, GEO, …`. The abstract
  is `RES` (*Résumé documentaire*) for TV notices but `CHAP` (*Chapeau*) for radio —
  the connector reads **`RES` then `CHAP`**. Keywords are `DE` (*Descripteurs*) +
  optional `DES` (*Descripteurs secondaires*), both ` ; `-separated.

The connector returns **notices only**: `title`, `description`, `date` (ISO),
`channel`, `genre`, `duration` (seconds), `keywords`, `collection`, `programme`,
`geo`, plus `page_url` (deep link). `image_url` / `media_url` are always `null`,
and `fetch()` **never downloads** anything.

#### Verified live examples (2026-10)

- Totals on `TV-RADIO`: `Lacq pétrole` = 166, `Parentis-en-Born pétrole` = 75,
  `Pechelbronn pétrole` = 105.
- `DA_AFE85003518` — *Le pétrole d'Aquitaine*, 04/05/1950, *Journal Les Actualités
  Françaises* (Presse filmée, 00:00:40). RES: "Premiers bilans des travaux de forage
  pétrolier entrepris six mois plus tôt à Lacq, en Aquitaine." ★ the killer 1950
  actualités record.
- `DA_CPF86613985` / `DO_CPF86613985` — *Pétrole de Lacq* (1957).
- `PH_PHD86026047` — *Pétrole de Lacq*, 26/04/1950, Journal parlé, 00:04:00.
- `DA_CPB7605002212` — *Lacq*, 09/01/1976, Antenne 2, Magazine.
- `RD_913264.001.003` — *Pour mémoire : l'histoire du gaz et du pétrole en France*,
  Radio Bleue, 10/06/1998, *Libre échange*, 00:15:00 (CHAP = "Chronique de Bernard
  DEUTSCH…"). ★ radio documentary.
- Parentis: *INCENDIE A PARENTIS EN BORN* (31/01/1958, 00:00:55); *Barge de forage
  sur le lac de Parentis* (25/03/1981, F3 Aquitaine); *L'exploitation du pétrole à
  Parentis en Born* (18/09/1999).
- Pechelbronn: *Exposition : le pétrole à Pechelbronn* (13/08/1982, F3 Alsace);
  *Le pétrole de Pechelbronn* (ici Alsace, 00:02:30).

### Surface B — `www.ina.fr` public clips ("L'INA éclaire l'actu") — **disabled**

`www.ina.fr` carries public clips **with** thumbnails and a JSON search endpoint
(`https://www.ina.fr/ajax/recherche?q=<q>&media=2&espace=1&offset=N`, where
`media` 1=Articles 2=Vidéos 3=Audios 4=Publicités), and detail pages embed
`schema.org VideoObject` JSON-LD. Thumbnails live on
`cdn-hub.ina.fr/notice/{360x270|450x450|690x517}/{hash}/{ID}.jpeg` — the `{hash}`
directory is **required and not derivable**. But `robots.txt` blocks `/*q=` (and a
large set of AI-bot user agents) with `Crawl-delay: 5`, and the CGU allow
**streaming only, no reuse**.

Therefore Surface B is **shipped off**: `public_search_allowed()` returns `False`
and `InaConnector.search_public()` raises `PermissionError`. Enabling it is a
one-flag change (`PUBLIC_SEARCH_ALLOWED`) once **written permission** from
mediaclip / INA mediapro is on file.

## Known limitation: image-less notices

`Asset`s from INA carry no `image_url`/`thumbnail_url` (metadata only). The
engine's `normalize()` step currently drops any asset lacking both an image and a
thumbnail, so INA notices do **not** surface through the meta API yet. This is a
deliberate metadata-only design (no media is ever downloaded or reused); exposing
INA records in results requires either (a) relaxing `normalize()` for notice-only
sources, or (b) adding the public thumbnail once Surface B is authorised. Tracked
as a follow-up.

## Consent trace

`protocol: html` + `extra.scraping_consent` cite the browser-agent SPEC #160
authorisation (2026-11-08): catalogue.ina.fr access limited to metadata notices
(permissive robots, Crawl-delay 5 s), **no media downloaded, no reuse**; Surface B
stays disabled.

## Constants & API

Module `src/mnemosyne/sources/ina.py`:

- `CATALOGUE`, `SECTION_DEFAULT`, `SORT_DEFAULT`, `SORTS`, `BASES`, `NB_LIGNES`,
  `CRAWL_DELAY = 5.0`, `LICENSE`, `NOTICE_TYPE`, `FIELD_MAP`, `PUBLIC_SEARCH_ALLOWED`.
- `build_search_url(query, *, section, bases, sort, n_rows, page)`
- `total_from(html)`, `parse_search_page(html) -> (total, rows)`
- `parse_notice(html, url=None) -> dict`
- `parse_date_fr`, `parse_duration`
- `public_search_allowed() -> False`
- `InaConnector.search / search_all (paginated, honours Crawl-delay 5 s) /
  get_notice / notice_to_asset / fetch (always None) / search_public (gated)`

## Tests

`tests/test_ina.py` (offline, fixtures in `tests/fixtures/ina/`):

- `build_search_url` shape + validation.
- `parse_search_page` (fixture `search_lacq.html`: total 166, `DA_AFE85003518`
  row fields, empty cells → `null`).
- `parse_notice` on a TV notice (`RES`, `DE`+`DES`, duration→seconds) and a radio
  notice (`CHAP` fallback).
- `parse_duration` cases.
- descriptor: `enabled` true, `reuse_allowed`/`media_download` false, attribution
  set, registered in `CONNECTORS`.
- `fetch()` does no media download.
- Surface B gate: `public_search_allowed()` is `False`, `search_public` raises.
- pagination honours `Crawl-delay 5 s` (`_pace` recorded).
