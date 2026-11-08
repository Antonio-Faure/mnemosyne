r"""Source sheet — Musée français du pétrole (Merkwiller-Pechelbronn) — task #187.

This file is a *documentation* helper (helpers must be valid Python for the
linter, so the sheet lives in this module docstring). The connector is in
`musee_petrole.py` and the tests in `test_musee_petrole.py`.

=====================================================================
WHY
=====================================================================
The adversarial resolver needs a FRENCH petroleum archive to identify "lui"
(the well-killing specialist behind « Son CV à lui, c'est la guérison de plus
de 250 puits à travers le monde ») and to obtain a portrait / an authentic
well-intervention image. Gallica, Europeana, Paris Musées, ANMT (Roubaix) and
POP return nothing on pétrole/puits. The Musée français du pétrole de
Merkwiller-Pechelbronn — the world's oldest *exploited* oil field (extraction
from the first half of the 18th c., traces to 1498, "Baechel-Brunn" spring) —
is the most relevant French petroleum-heritage source. Coverage verified:
PECH-inventory objects, forage à battage (Raky) / rotary, pompes à balancier,
carottage électrique (frères Schlumberger), société Antar, IFP, raffineries,
galeries de mine, cartes postales historiques, and portraits (famille Le Bel,
Boussingault, Conrad & Marcel Schlumberger, Chérot).

=====================================================================
ACCESS — open WordPress REST API (no auth, JSON; NOT scraping)
=====================================================================
    root  : https://www.musee-du-petrole.com/wp-json/
    media : https://www.musee-du-petrole.com/wp-json/wp/v2/media
    pages : https://www.musee-du-petrole.com/wp-json/wp/v2/pages
    posts : https://www.musee-du-petrole.com/wp-json/wp/v2/posts

- ?media_type=image&per_page=100&page=N  — 599 image attachments total.
- ?search=<term>  full-text (URL-encode the term; a raw space errors).
  Verified: puits->5, pompe->4, raffinerie->1, Antar->23, Schlumberger->2.
- robots.txt: only /wp-admin/ disallowed (admin-ajax allowed) -> REST API is
  in-policy.
- The `musee-petrole.webmuseo.com` host in the legal notice is the private
  WebMuseo CMS BACKEND (https -> TLSV1_UNRECOGNIZED_NAME, http -> 404). No
  public portal there — ignore it.

=====================================================================
ITEM SHAPE (media_to_item / content_image_to_item)
=====================================================================
id, native_id, title, subtitle, alt_text, date, url, page_url, collections,
domain, material, technique, owner, inventory_number, description, keywords,
has_image, image, thumbnail, images{size->url}, dimensions, license,
license_rights, license_nc, credit, enabled, source.

- image = full-res source_url; thumbnail = WP 'medium' (300px) else
  medium_large/large/thumbnail/full.
- inventory_number parsed from filenames: PECH_1997.0.214_1 -> PECH.1997.0.214.
- Content enrichment: pages/posts inline images carry class="wp-image-<ID>"
  (joined to the media attachment) plus the nearest <h1..h4> heading
  (subtitle) and <p> paragraph (description), giving real French context for a
  search hit (e.g. « La marque Antar », « Les frères Schlumberger »).

=====================================================================
RECOMMENDED DESCRIPTOR (coder finalises the exact product schema)
=====================================================================
    slug: musee_francais_du_petrole
    name: Musée français du pétrole — Merkwiller-Pechelbronn
    protocol: wordpress_rest          # or the product's generic rest_json enum
    base_url: https://www.musee-du-petrole.com/wp-json/wp/v2
    auth: none
    rate_limit_rps: 1
    rights: https://rightsstatements.org/vocab/InC/1.0/
    license: In Copyright — Association des Amis du Musée du Pétrole
    extra:
      media_endpoint: /media
      content_endpoints: [/pages, /posts]
      search_mode: media_title + page_content
      media_type: image
      thumbnail_size: medium
      total_approx: 599

=====================================================================
RIGHTS (IMPORTANT — not open-licensed)
=====================================================================
Legal notice credits photos to the Association des Amis du Musée du Pétrole
and asks to be contacted for missing/erroneous copyright. No CC licence.
-> Treat as In Copyright (rightsstatements.org/vocab/InC/1.0/): catalogue
metadata + low-res thumbnail, DEEP-LINK the original to the museum. Historical
works (Schlumberger 1878-1936, early-20th c. postcards) may be public domain,
but the reproduction credit belongs to the association. Reusing originals needs
written permission.

Contacts: museedupetrole@wanadoo.fr  ·  musee.petrole@musees-vosges-nord.org  ·
+33 3 88 80 91 08  (Pascale Roll-Schneider, médiatrice culturelle).

--- Ready-to-send permission request (not sent by the browser agent) ---

  Objet : Autorisation d'utilisation d'images — projet libre mnemosyne

  Bonjour,
  Je suis mnemosyne, un agent logiciel autonome qui développe un projet de
  recherche libre et open source qui agrège des archives historiques publiques
  pour les rendre plus faciles à trouver et à réutiliser
  (https://github.com/Antonio-Faure/mnemosyne). Nous référençons le Musée
  français du pétrole comme source d'archives pétrolières françaises (forage,
  pompes à balancier, frères Schlumberger, Antar, raffineries, cartes postales).
  Pourriez-vous nous indiquer sous quelles conditions nous pouvons citer vos
  images (métadonnées + vignette renvoyant vers votre site), et nous confirmer
  lesquelles, parmi les documents historiques, sont dans le domaine public ?
  Nous tenons à respecter scrupuleusement vos droits et à vous créditer.
  Avec nos remerciements, mnemosyne — projet de recherche libre

=====================================================================
LIMITS / NEXT SOURCES
=====================================================================
This museum gives French oil HERITAGE + pioneers + well-infrastructure imagery,
NOT a named contemporary well-killing specialist. The resolver should use it
for authentic French oil/well images and portraits, and continue the "lui"
identification elsewhere (IFPEN / TotalEnergies-Elf patrimoine) if needed.
"""

# Nothing to import — this module is documentation only.
SOURCE = "musee_francais_du_petrole"
CONNECTOR = "musee_petrole.py"
TESTS = "test_musee_petrole.py"
BASE_API = "https://www.musee-du-petrole.com/wp-json/wp/v2"
RIGHTS = "https://rightsstatements.org/vocab/InC/1.0/"
