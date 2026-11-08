# Résolveur adversarial phrase → image d'archive

## Vision

Le catalogue répond à « trouve-moi des images sur X ». Le résolveur répond à
« **cette phrase historique précise** est-elle illustrable par une image
d'archive, et laquelle ? ».

Il prend en entrée :

- des **transcripts de vidéos d'histoire** (YouTube), découpés en phrases ;
- un **corpus de textes historiques** (livres, presse, archives) destiné à
  fournir le vocabulaire, les entités et les preuves.

Il produit :

1. pour chaque phrase, un **match** (image + preuves + confiance) ou une
   **abstention** ;
2. pour chaque abstention, un **trou de couverture** : pays, période, type
   d'image, sources candidates à onboarder.

Le résolveur ne remplace pas les connecteurs d'images : il les utilise et les
met à l'épreuve.

## Non-objectifs

- Ce n'est pas un générateur d'images.
- Ce n'est pas un « common crawl » : on interroge les APIs/passages nécessaires.
- Ce n'est pas un juge automatique sans humain : le golden dataset et la revue
  opérateur restent la référence.

## Pipeline

```mermaid
graph TB
    classDef input fill:#e3f2fd,stroke:#1e88e5,color:#0d47a1
    classDef process fill:#f3e5f5,stroke:#8e24aa,color:#4a148c
    classDef output fill:#e8f5e9,stroke:#43a047,color:#1b5e20

    A1(["transcript YouTube"]) --> B1["segmentation phrases"]
    A2(["textes historiques"]) --> B2["chunks + citations"]
    B1 --> C1["extraction claim<br/>quand / où / qui / quoi"]
    B2 --> C1
    C1 --> D1["génération de requêtes<br/>multilingues + synonymes d'époque"]
    D1 --> E1["récupération candidats<br/>catalogue + textes"]
    E1 --> F1["panneau adversarial"]
    F1 --> G1{"match défendable ?"}
    G1 -->|oui| H1(["Asset + preuves + confiance"])
    G1 -->|non| H2(["abstention"])
    H2 --> I1["trou de couverture<br/>sources candidates"]
    I1 --> J1(["spec pour la boucle agency"])
```

## Modèle de données (SQLite, même DB que le catalogue)

```sql
texts (
  id TEXT PRIMARY KEY,
  source TEXT, title TEXT, author TEXT, date TEXT, language TEXT,
  license TEXT, url TEXT, content TEXT, retrieved_at TEXT
)

text_chunks (
  id INTEGER PRIMARY KEY,
  text_id TEXT, ordinal INTEGER, content TEXT,
  start_char INTEGER, end_char INTEGER
)

segments (
  id TEXT PRIMARY KEY,             -- yt_<video>_<index>
  video_id TEXT, video_title TEXT, channel TEXT, video_url TEXT,
  start_s REAL, end_s REAL, text TEXT
)

claims (
  segment_id TEXT PRIMARY KEY,
  when_text TEXT, where_text TEXT, who_json TEXT,
  what_text TEXT, event_type TEXT, visual_intent TEXT,
  must_include_json TEXT, must_exclude_json TEXT,
  queries_json TEXT, model TEXT, created_at TEXT
)

candidates (
  id INTEGER PRIMARY KEY,
  segment_id TEXT, asset_id TEXT, query TEXT,
  rank INTEGER, score REAL, evidence_json TEXT, created_at TEXT
)

verdicts (
  id INTEGER PRIMARY KEY,
  candidate_id INTEGER, lens TEXT,          -- support|refute|anachronism|provenance|visual
  verdict TEXT,                             -- support|reject|neutral
  confidence REAL, reasons_json TEXT, model TEXT, created_at TEXT
)

matches (
  segment_id TEXT PRIMARY KEY,
  asset_id TEXT, status TEXT,               -- match|partial|no_match|ambiguous
  confidence REAL, chosen_by TEXT, reasons_json TEXT, created_at TEXT
)

golden_labels (
  segment_id TEXT PRIMARY KEY,
  status TEXT, images_json TEXT, hard_negatives_json TEXT,
  notes TEXT, annotator TEXT, updated_at TEXT
)
```

Les `candidates` pointent vers `assets` ; aucune image n'est dupliquée.

## Golden dataset

Un JSONL, une ligne par phrase. Schéma JSON :
[`schemas/golden_sentence.schema.json`](../schemas/golden_sentence.schema.json).

```json
{
  "id": "yt_<video_id>_<sentence_index>",
  "video": {
    "id": "<youtube id>",
    "title": "...",
    "channel": "...",
    "url": "https://www.youtube.com/watch?v=...",
    "published_at": "2026-01-01"
  },
  "segment": {
    "start_s": 123.4,
    "end_s": 130.2,
    "text": "In 1914, the German army crossed into neutral Belgium."
  },
  "claim": {
    "when": "1914",
    "where": "Belgium",
    "who": ["German army"],
    "event": "invasion of Belgium"
  },
  "gold": {
    "status": "match",
    "images": [
      {
        "url": "https://...",
        "source_id": "gallica",
        "source_asset_id": "...",
        "why": "photo de l'entrée des troupes à Bruxelles, 1914"
      }
    ],
    "hard_negatives": [
      {
        "url": "https://...",
        "why_wrong": "même guerre, mais 1918 / autre ville"
      }
    ]
  },
  "notes": "Une photo de réfugiés belges est aussi acceptable.",
  "annotator": "operator"
}
```

Règles d'annotation :

- `match` : au moins une image défendable pour la phrase ;
- `partial` : l'image illustre une partie seulement (ex. le bon pays, la
  mauvaise année) ;
- `no_match` : aucune image du catalogue ne convient — **très important** ;
- `ambiguous` : désaccord ou image discutable ;
- toujours fournir des **hard negatives** quand ils existent ;
- plusieurs images acceptables sont autorisées ;
- conserver `video_id` + timestamps pour la traçabilité.

### Import / validation

```bash
# valider sans écrire
mnemosyne resolve import-golden data/golden.jsonl --dry-run

# importer (upsert idempotent par segment_id)
mnemosyne resolve import-golden data/golden.jsonl

# état du dataset importé
mnemosyne resolve stats
```


## Panneau adversarial

Chaque candidat passe des lentilles indépendantes :

| Lentille | Question | Veto |
|---|---|---|
| `support` | Quelles preuves relient l'image au claim ? | non |
| `refute` | Existe-t-il une contradiction fatale ? | oui |
| `anachronism` | L'image est-elle postérieure à l'événement ? | oui |
| `provenance` | Source, caption, licence, crédibilité | oui si licence/notice incompatible |
| `visual` | Que montre réellement l'image ? | oui si sujet incompatible |

Le `judge` agrège :

```text
score = support - (2 × refute) - penalités
```

- `match` si score ≥ seuil haut et aucun veto ;
- `partial` si score moyen ;
- `no_match` si score < seuil bas ou deux candidats trop proches ;
- sinon `ambiguous` (revue humaine).

Le système doit **préférer l'abstention** à un faux match.

## Boucle adversariale

- Les faux positifs et les near-miss deviennent des **hard negatives** rejoués à
  chaque nouveau modèle/source.
- Les phrases `no_match` sont agrégées par `(pays, période, type)` pour produire
  des **specs de sources** :
  ```json
  {
    "claim": "...",
    "missing": {"country": "BE", "period": "1914", "type": "photo de rue"},
    "candidate_sources": ["Amsab", "KBR", "Bundesarchiv"]
  }
  ```
- Ces specs alimentent la boucle `agency` (browser/coder) qui ajoute les sources.

## Textes historiques

Ils servent à :

- enrichir le vocabulaire et les entités (noms, lieux, unités d'époque) ;
- fournir des **citations** qui soutiennent ou réfutent un candidat ;
- générer des requêtes plus précises que la phrase YouTube.

Sources de départ : Gutenberg/Gutendex, Wikisource, Internet Archive, Gallica,
Europeana, ANNO, NDL, Delpher, Perseus/Fordham. On stocke des **passages** avec
source, date, langue et citation — pas des livres entiers.

## Évaluation

Sur le golden dataset :

- `precision@1`, `recall@k`, taux de faux matchs, taux d'abstention ;
- calibration de la confiance (Brier) ;
- slices par période, pays, type de claim, source ;
- rejeu des hard negatives.

Objectif : **maximiser les phrases correctement illustrées sans inventer**.

## Étapes d'implémentation

1. Schéma DB + importeur golden JSONL/VTT/SRT.
2. Ingestion des textes historiques + chunks/BM25.
3. Extraction de claims + génération de requêtes.
4. Récupération dans le catalogue existant (sans nouvelle source).
5. Panneau adversarial + juge + abstention.
6. CLI `mnemosyne resolve ...` + rapport d'évaluation.
7. Vue observatory : phrase, candidats, verdicts, golden label.
8. Boucle de gaps → specs de sources.

## Questions ouvertes

- Format exact des transcripts du golden dataset (VTT/SRT/JSONL ?).
- Un label `partial` doit-il compter comme succès dans la métrique principale ?
- Seuils de confiance et politique d'abstention.
- Modèle vision : API (Zen) vs modèle local.
- Périmètre initial : une chaîne YouTube + une période + 50–100 phrases.
