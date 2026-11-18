# Observatoire — deux kanbans (lecture seule)

Poste de contrôle **local** d'Archivist : deux tableaux qui répondent à « où en
est le travail ? » sans ouvrir une chronologie. **Aucune action n'est possible
depuis l'UI** : l'observatoire lit la base, il ne pilote pas les agents.

## Les deux tableaux

| Kanban | Alimenté par | Agents |
|---|---|---|
| **Le Résolveur** | importation des nouvelles résolutions | `resolver` |
| **L’Atelier** | demandes de source du Résolveur | `coder` + `browser` |

Même grammaire de cartes, mêmes colonnes. Le Résolveur est visuellement traité
comme un agent : une carte = une résolution, pas une session.

## Colonnes et types

| Colonne | Résolveur | Atelier |
|---|---|---|
| **En file** | résolutions importées | missions de source créées |
| **En cours** | session résolveur active | session coder ou browser active |
| **En attente** | **Opérateur** (ambre), **Sources** (rose) | **Opérateur** (ambre), **E-mail** (bleu), **Accès** (violet) |
| **Terminé** | **Match** (vert), **Partiel** (turquoise), **Abstention** (gris), **Ambigu** (orange) | **Source ajoutée** (vert), **Déjà couverte** (turquoise), **Refusée** (gris), **Sans source** (gris) |
| **Échec** | **Technique** (rouge), **Budget** (rouge foncé), **Annulé** (gris) | **Accès refusé** (rouge), **Technique** (rouge), **Abandon** (orange), **Annulé** (gris) |

Chaque colonne affiche un résumé cliquable en tête : total, puis les types
présents (`4 Match · 3 Partiel · 2 Abstention · 1 Ambigu`). Les types sont des
**badges + filtres**, pas des colonnes. Un clic filtre le tableau ; le badge de
filtre actif se retire dans l'en-tête.

## Dépendances

- Une résolution peut demander **N sources**.
- Une mission de source peut servir **N résolutions**.
- Carte Résolution : badge « N sources » et liste des missions avec leur état.
- Carte Mission : badge « N résolutions » et liste des résolutions liées.
- Si une mission est en attente d'e-mail, la résolution affiche
  `en attente de la mission #123 — e-mail`.
- Une mission peut passer par une phase **navigateur** (accès) puis **codeur**
  (connecteur) ; la carte montre l'agent courant et l'historique des activations.
- Si la mission échoue, la demande passe en échec et le Résolveur est réveillé
  pour s'abstenir ou demander une autre source.

## API

```http
GET /api/obs/tasks?board=resolver
GET /api/obs/tasks?board=atelier
```

Chaque carte porte :

| Champ | Valeur |
|---|---|
| `kind` | `resolution` ou `mission` |
| `task_id` | la tâche `tasks` |
| `status` | `pending`, `running`, `done`, `failed`, `cancelled` |
| `column` | `queued`, `running`, `waiting`, `done`, `failed` |
| `waiting_on` | `operator`, `sources`, `email`, `access` ou `null` |
| `waiting` | liste des attentes (type, libellé, détail) |
| `outcome` | `match`, `partial`, `no_match`, `ambiguous`, `source_added`… |
| `outcome_label` | libellé affiché |
| `links.resolver_requests` | ids des demandes de source |
| `links.missions` | missions liées (carte Résolution) |
| `links.resolutions` | résolutions liées (carte Mission) |
| `agents` / `current_agent` | historique et agent courant |
| `created_at` / `updated_at` | horodatage |

La réponse contient aussi `columns` (les cinq colonnes, leurs cartes et leur
`summary`) et `cards` (liste plate). L'API est en lecture seule ; le frontend
rafraîchit toutes les 5 s.

### D'où viennent les états

- **file / cours / attente** : `tasks.status` + `operator_asks` en attente +
  `resolver_requests` ouvertes + `email_waits` en attente.
- **Terminé / Échec** : `resolver_results.status` pour une résolution ;
  `tasks.status` + `tasks.note` + `resolver_requests.note` pour une mission
  (`source_added`, `already_covered`, `refused`, `no_source`, `access_denied`,
  `technique`, `abandon`, `cancelled`).
- **Accès** : mot-clé explicite dans la note de mission (`attente d'accès`,
  `waiting for access`) ; à terme un champ structuré pourra le remplacer.
- **Budget** : note contenant `budget`, `quota`, `rate limit` ou `429`.

## Frontend

- Deux onglets : **Le Résolveur** / **L’Atelier** ; le choix est mémorisé et
  peut être ouvert directement avec `?board=atelier`.
- Cinq colonnes, résumé cliquable, badges de type, filtre global.
- Cartes en lecture seule : titre, sous-titre, agent(s), attentes, dépendances,
  âge de la dernière activation.
- États vides explicites ; aucune carte n'est inventée.

Les anciens composants de relecture (sessions, chronologie, canevas) restent
dans le dépôt et l'API `/api/obs/sessions` reste disponible pour le débogage,
mais l'écran principal est désormais les deux kanbans.
