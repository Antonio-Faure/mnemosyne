# Onboarding des sources : manuel par défaut

**Décision du 15/10/2026** : l'ajout automatique de sources est coupé — il
consommait l'abonnement OpenCode Go (missions navigateur + tours du codeur)
sans validation humaine préalable.

## Ce qui est coupé

| Mécanisme | Réglage | État |
|---|---|---|
| Scan de découverte (candidats fournisseurs) | `discovery.enabled` | **false** |
| Jambe CONNEXION du cycle (inscription portail, clé API, branchement) | `agents.auto_connect` | **false** |
| Timer hôte `mnemosyne-connect.timer` (1 connexion/jour) | systemd utilisateur | **désactivé** |

### Timer hôte (la fuite du 16/10)

`mnemosyne-connect.timer` (systemd **utilisateur**, côté hôte) lançait chaque
jour `scripts/daily-connect.sh` → `docker compose exec mnemosyne mnemosyne
connect-next` : une source par jour, sans validation de l'opérateur. Les flags
du conteneur ne le couvraient pas — c'est lui qui a produit la tâche #96 et la
PR #42 (RIT) le 16/10/2026 à 11:00.

**Désactivé le 16/10/2026** :
```bash
systemctl --user disable --now mnemosyne-connect.timer
```
Les unités restent dans `deploy/systemd/` pour un réemploi **manuel** ; elles ne
se relancent plus au démarrage (`disabled`).

- `agents.auto_connect` est **opt-in** (défaut `false` dans le code) : le cycle
  warmup ne poste plus que des missions de lecture, le sélecteur de candidat
  n'est même pas consulté.
- Un job `discover` déjà en file s'achèvera en no-op : le handler sort
  immédiatement **et ne se replanifie pas** ; le scheduler ne le réarme qu'au
  démarrage du service si `discovery.enabled` repasse à `true`.

## Ce qui reste (à la demande, jamais automatique)

- `mnemosyne discover` — scan d'inventaire ponctuel.
- `mnemosyne connect-next` — connecter la prochaine découverte (tâche codeur).
- `mnemosyne agency "<objectif>"` — piloter une session à la main.

## Réactiver l'automatique

1. `config/config.yaml` : `discovery.enabled: true` et/ou `agents.auto_connect: true`.
2. Redémarrer le service (`docker compose restart mnemosyne`) — le YAML est
   monté en read-only, un rebuild n'est requis que pour du code.
3. Pour le timer hôte :
   `systemctl --user enable --now mnemosyne-connect.timer`.

## Ce qui continue de tourner

- **Warmups** (1-2/jour, modèle éco `mimo-v2.6-flash`) : lecture seule, aucune
  inscription. Pour les couper aussi : `warmup_per_day_min: 0` **et**
  `warmup_per_day_max: 0` (le tirage journalier fait `randint(min, max)` — avec
  `min: 1` seul, le plafond ne suffit pas).
- **Harvest / verify / journal / watchdog** : HTTP + base de données,
  **zéro token LLM**.
