# Harvest — pourquoi, combien, comment régler

## Ce que fait un harvest

Un harvest interroge **une source** (Gallica, ANMT, Wikimedia, Europeana…)
avec **un seed** (requête ou ARK), récupère jusqu'à 20 notices, les normalise
en `Asset` (titre, créateur, date, licence, URL de page, URL d'image, IIIF,
dimensions) et les insère dans la table `assets`. Les doublons sont ignorés.

- **Aucun fichier image n'est téléchargé** : on stocke les métadonnées et les
  URLs ; le consommateur récupère l'image ensuite.
- Un run qui n'ajoute rien est **silencieux** (pas de session visible).
- Un run qui ajoute des assets est visible : `harvest gallica « … » → 3 nouveaux`.

## Pourquoi il y en avait autant

Le rythme était **fixe : toutes les 30 minutes, pour chaque source**.

```
34 sources activées × 48 passages/jour = 1 632 jobs harvest/jour
```

La plupart ne trouvaient rien (seeds déjà moissonnés, doublons, source sans
seed). Résultat : ~1 600 runs/jour, des milliers de lignes `job:…` en base, et
seulement **518 assets uniques** au total. Ce n'était pas un bug de collecte,
mais un **rythme hérité d'une époque à une seule source**, multiplié par 34.

## Statut actuel : désactivé

Décision opérateur du 7/11/2026 : **plus aucun harvest automatique**.
`harvest.enabled: false` dans `config/config.yaml`, les jobs et sessions
existants ont été supprimés (les assets déjà collectés sont conservés). Le code
reste en place pour un retour éventuel ou un usage manuel.

## Ancien rythme adaptatif (conservé pour mémoire)

Réglable dans `config/config.yaml` :

```yaml
harvest:
  enabled: false          # désactivé sur décision opérateur
  interval_s: 21600        # 6 h  — source productive
  empty_interval_s: 86400  # 24 h — dernier passage vide
  no_seed_interval_s: 604800  # 7 j — source sans seed
```

| Situation | Prochain passage |
|---|---|
| Le run a ajouté des assets | 6 h |
| Le run est vide | 24 h |
| La source n'a pas de seed | 7 jours (parquée, aucun appel) |
| `harvest.enabled: false` | parqué 7 jours, aucun appel |

Effet : au pire **136 runs/jour** (34 × 4), et en pratique **~30-50/jour**
après le backoff des sources vides — **30 à 50× moins** qu'avant. Le plafond
`reputation.warmup[].harvest_per_day` reste une sécurité globale.

## Pourquoi en faire ?

Le catalogue `assets` est la matière première du projet : il permet de
retrouver des images culturelles libres avec leur provenance, leur licence et
leur URL. Les seeds tournent pour découvrir progressivement de nouveaux fonds.

Si tu ne consommes pas ce catalogue, coupe-le :

```yaml
harvest:
  enabled: false
```

Les jobs existants se parquent au prochain passage (7 jours), sans appel
réseau. Les commandes manuelles restent disponibles :

```bash
mnemosyne search "usine 1900" --limit 10
mnemosyne harvest --source gallica --query "photographie industrie 1900" --limit 20
```
