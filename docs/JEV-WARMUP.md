# JEV-ULTRAFAST pour les warmups — analyse et plan

> Proposition du 2026-10-07. Rien n'est intégré : ce document fixe le pourquoi,
> les chiffres et le plan en trois phases.

## 1. Le besoin

Les séances de warmup (navigation humaine, lecture seule) n'ont besoin que
d'actions simples : ouvrir une page, descendre un peu, suivre un lien, rester
immobile 30 s. Pourtant elles tournent sur un agent LLM complet (stirrup +
raisonnement), et le coût vient du **rejeu de contexte** et des **tokens de
raisonnement**, pas des actions.

Baseline (journal, sessions récentes) :

| Session | Appels | Tokens prompt | % cachés | Tokens completion |
|---|---|---|---|---|
| warmup 10:41 | 59 | 2,47 M | 89,7 % | 179 k |
| warmup 11:51 | 38 | 1,14 M | 92,1 % | 57 k |
| warmup 12:41 | 34 | 477 k | 93,2 % | 7 k |
| warmup 15:13 (gmail) | 34 | 398 k | 94,9 % | 6 k |

Depuis, `agents.warmup_model: mimo-v2.6-flash` baisse déjà la facture, mais la
structure reste la même (contexte rejoué à chaque pas).

## 2. Ce qu'est jev-ultrafast

- `browser-use/jev-ultrafast` (MIT, 20/09/2026) : agent navigateur à **espace
  d'actions indexé**.
- **Une requête TypeSafe (System One) par pas** : l'opération *et* la cible
  sont choisies dans le même aller-retour. Opérations : `CLICK`, `TYPE_TEXT`,
  `SELECT`, `SCROLL_UP`, `SCROLL_DOWN`, `WAIT`, `DONE`, `BLOCKED`.
- Un petit LLM texte **uniquement** quand l'opération est `TYPE_TEXT`.
- **Aucun screenshot** dans la boucle par défaut.
- Même couche que nous (browser-harness/CDP) ; la sortie du modèle ne devient
  jamais sélecteur, coordonnée ou JavaScript exécutable ; la fraîcheur et
  l'occlusion de la cible sont revérifiées avant chaque action.
- Clés : `TYPESAFE_API_KEY` (playground gratuit pour tester, puis volume
  payant) + `TEXT_MODEL_API_KEY` (OpenAI-compatible — notre endpoint Zen peut
  servir).
- Limites MVP : pas de shadow DOM, frames, uploads, pop-ups ni nouveaux
  onglets ; cap ~60 actions par run ; `DONE` n'est jamais une preuve.

## 3. Pourquoi ça colle au warmup

- Profil « Système 1 » : décisions micro, aucune délibération longue.
- Pas de screenshots → aligné avec `force_vision: false` et la limite Zen de
  30 images/requête.
- Coût par pas quasi plat : pas de rejeu de contexte quadratique, pas de
  tokens de raisonnement.
- Le **pacing humain** (5-20 s entre actions) doit être imposé en code, pas
  confié au prompt — c'est même un avantage : rythme déterministe.

## 4. Ce que ça coûte à intégrer

- Ce n'est pas un modèle OpenAI-compatible : c'est un **second chemin
  d'exécution** du warmup (loop agent à part, dépendance figée, Python 3.12).
- Journal/usage dédiés + fallback stirrup si TypeSafe est indisponible.
- Deux clés à stocker au vault (TypeSafe + modèle texte).
- Maturité « démo utilisable » : épingler un commit et surveiller l'API.

## 5. Plan en trois phases

1. **Spike offline** (aucun changement pipeline) : vendorer jev-ultrafast à un
   commit figé, clé playground TypeSafe + texte via Zen, 3 flows type warmup
   (Wikipedia, Gallica, archive.org) avec wrapper de pacing. Mesurer
   coût/session, échecs, discrétion → go/no-go.
2. **Feature flag** `agents.warmup_engine: stirrup | jev` (défaut stirrup) :
   un `WarmupRunner` qui pilote jev avec nos règles (lecture seule, pacing
   jitteré, cap d'actions, journal), les tâches warmup restent dans la file
   (quota/cancel inchangés), fallback stirrup sur erreur.
3. **A/B** sur N sessions (coût, durée, diversité d'actions, échecs) puis
   décision : garder le flag, l'activer par défaut, ou abandonner.

## 6. Questions ouvertes

- « en feature » = flag `warmup_engine` avec stirrup par défaut ?
- Clé TypeSafe : déjà disponible, ou à obtenir par le navigateur (playground
  gratuit) et stocker au vault ?
- Modèle texte : Zen (`deepseek-flash`) pour rester sur une seule clé, ou
  `inception/mercury-2.5` via OpenRouter comme l'exemple amont ?
- Vendoring : copie figée dans le repo (MIT) ou installation git épinglée dans
  l'image ?
