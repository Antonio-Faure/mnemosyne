# Roadmap — recherche sémantique sur les images d'archives

## Vision

Passer de « agréger des centaines de fournisseurs » à « trouver l'image
d'archive la plus pertinente pour une requête », y compris par similarité
visuelle (une usine de 1900, un derrick, une affiche). Cible : recherche
multimodale (texte ↔ image) sur l'ensemble du corpus agrégé.

## Principe : incrémental, pas un « common crawl » séparé

Un méga-crawl one-shot (tout télécharger d'un coup) est **fragile, coûteux et
juridiquement lourd**. On enrichit plutôt **ce qu'on harvest déjà** :

```
asset (déjà stocké : image_url + métadonnées + provenance)
  → vignette (PAS le full-res)
  → déduplication perceptuelle (pHash/embedding)         [normalize/]
  → embedding multimodal (image + contexte texte)
  → vecteur stocké + index
  → recherche hybride (BM25 métadonnées + vecteur)
```

Réutilise l'architecture existante (connecteurs, `normalize/`, provenance) au
lieu de la dupliquer.

## Modèles d'embedding

| Option | Avantages | Inconvénients |
|---|---|---|
| Google multimodal (Vertex) | forte qualité image+texte | payant/appel, dépendance API |
| SigLIP 2 / Jina CLIP v2 (ouverts) | local, pas cher, offline | à opérer (GPU/CPU), qualité un poil en dessous |
| Embeddings texte seuls (métadonnées) | quasi gratuit, immédiat | pas de similarité visuelle |

Le « dernier modèle Google » n'est pas forcément le meilleur **rapport
qualité/prix** pour un crawl massif : commencer par étage 1 (texte), mesurer,
puis monter.

## Coûts & stockage

- Stocker **vignettes + métadonnées + lien**, jamais des téraoctets de full-res.
- Traiter **par source**, en flux, avec cache (pas de retraitement).
- Dédup avant embedding (pHash) pour ne pas payer deux fois la même image.
- Étages progressifs (voir plus bas).

## Droits & éthique

- Indexer ≠ mirroir : conserver l'attribution, la licence et le lien canonique.
- Ne pas recopier le full-res d'œuvres sous droits réservés ; vignette + métadonnées.
- La provenance (`Asset.provenance()`) est déjà là — l'étendre au stockage des vecteurs.

## Intégration dans le projet

- `normalize/` : dédup déjà en place ; y brancher l'embedding.
- `assets` (SQLite) : ajouter `embedding` (BLOB) + table/index vecteur
  (pgvector/Qdrant/LanceDB si volume).
- Nouveau job heartbeat `vectorize` : enrichit les assets non vectorisés.
- API : `/search?mode=semantic` en plus du plein-texte.

## Étapes

1. **Étage 1 — texte** : vectoriser les métadonnées (titre/date/lieu/description).
   Quasi gratuit, utile tout de suite.
2. **Étage 2 — image (échantillon)** : embeddings multimodaux sur un sous-ensemble,
   mesurer qualité et coût.
3. **Étage 3 — flux complet** : job incrémental par source, dédup pHash avant embedding.
4. **Étage 4 — recherche hybride + dédup inter-fournisseurs** : fusion
   BM25 + vecteur, regroupement des doublons (même image chez Gallica/Europeana/Commons).

## Questions ouvertes

- Modèle : local (SigLIP2) vs API (Google) selon budget.
- Stockage vecteur : rester en SQLite+extension ou passer à un vector DB dédié ?
- Politique de vignette : taille, format, cache.
