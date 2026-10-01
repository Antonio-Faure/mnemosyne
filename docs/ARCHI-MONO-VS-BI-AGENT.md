# Mono-agent vs Bi-agent — bilan de confrontation

> Document destiné à être soumis à d'autres modèles. But : décider de
> l'architecture agentique de **mnemosyne** (agrégateur d'images d'archives
> autonome), en particulier **mono-agent** (un seul agent qui code *et* navigue)
> vs **bi-agent** (un codeur + un agent navigateur), sous contrainte de **coût en
> tokens**.

## 0. Exigence non négociable

L'agent doit savoir **les deux** dans la même mission :
1. **Utiliser le navigateur** (clic, saisie, onglets, uploads, lire un e-mail,
   passer un captcha/log via humain…), et
2. **Écrire du code** (descripteur + connecteur, tests, git commit/push/PR).

Exemple de mission : « connecte le fournisseur X » = *(phase navigateur)* trouver
son endpoint API/IIIF, s'inscrire et obtenir une clé → *(phase code)* écrire le
connecteur, tester, ouvrir une PR.

On ne veut **ni** un « browser-use sans code » **ni** un « codeur sans navigateur ».

## 1. Briques disponibles (état réel)

| Brique | Ce qu'elle fait bien | Limite |
|---|---|---|
| **browser-use `Agent`** | navigateur natif : clic/type/scroll/onglets/dialogs/dropdowns/uploads, vision, système de `skills` | ne fait **pas** d'édition de fichiers/git ; chaque étape porte le DOM (+ screenshot) → prompt lourd |
| **Stirrup (codeur)** | boucle d'agent générique + outils métier ; édite le repo, lint, tests, git/PR | ne pilote pas un vrai navigateur ; context resend (quadratique) |
| **Heartbeat maison** | orchestrateur **déterministe** durable (jobs, quotas) | pas d'IA ; enchaîne les phases |

Aujourd'hui, **de facto bi-agent**, orchestré par le heartbeat / la CLI :
- bras navigateur = browser-use natif (`mnemosyne browse`) — *prouvé* : a envoyé
  une vidéo via WeTransfer en créant le compte et en lisant le code de
  vérification dans Gmail ;
- bras code = Stirrup (`develop` / `connect-next`) — *prouvé* : connecteurs +
  PR mergées.

## 2. Options d'architecture

- **Mono-1 — browser-use + outils code.** Un seul `browser_use.Agent` auquel on
  ajoute des outils fichier/tests/git.
- **Mono-2 — Stirrup + navigateur « natif » encapsulé.** Un agent Stirrup qui
  appelle l'agent browser-use comme **un seul outil** `browse(task)`.
- **Bi-1 — deux spécialistes, orchestration déterministe.** Heartbeat qui
  séquence : phase navigateur → phase code → (boucle si besoin).
- **Bi-2 — manager LLM qui délègue** à deux sous-agents. Ajoute un 3e agent
  (coût + latence) → à éviter par défaut.

## 3. Modèle de coût tokens

Deux régimes différents :
- **browser-use** : à chaque étape, on renvoie l'état de page (arbre DOM/a11y,
  parfois screenshot) + l'historique. **Mesuré : ≈ 5,4 k tokens d'entrée/étape**
  sur une page réelle (Gallica, tâche courte, 4 appels, 63 % en cache).
- **codeur (Stirrup)** : renvoie tout le transcript à chaque étape (croissance
  ~quadratique), atténué par des **plafonds de sorties d'outils** ; et surtout le
  **cache de prompt** du provider (≈ 88-96 % des tokens d'entrée en cache chez
  nous).

Conséquences :
- **Mono-1** : un contexte qui porte *à la fois* l'observation navigateur (volumineuse)
  et le code/historique → le navigateur « encombre » la partie code, et inversement.
  Le pire profil pour les longues missions mixtes.
- **Bi-1** : deux contextes **focalisés**. Le *handoff* passe un **résumé structuré
  compact** (ex. : descripteur YAML + endpoint trouvé), pas le DOM ni le transcript.
  L'orchestration est **gratuite** (déterministe, pas d'appel LLM).
- **Mono-2** : le transcript du codeur porte en plus les résultats de l'outil
  `browse` ; si `browse` retourne un texte court, c'est proche du bi mais sans
  isolation ; si on veut que le codeur « voie » le DOM, on explose le coût.

**Mesures existantes** (à compléter) :

| Run | Agent | Étapes | prompt tok | cached | cached % | completion |
|---|---|---|---|---|---|---|
| Connecteur ALBERTINA | codeur Stirrup | 17 | 262 713 | 237 184 | 90.3 % | 12 971 |
| Warmup 5 min | Stirrup + micro-outils nav. | 40 | 223 395 | 210 304 | 94.1 % | 3 284 |
| Gallica (court) | **browser-use natif** | 4 | 21 505 | 13 568 | 63.1 % | 4 546 |
| WeTransfer (échec) | Stirrup + micro-outils | 40/60 | 0.6M→1.9M | ~95 % | | |
| WeTransfer (succès) | browser-use natif | ? | (non capturé) | | | |

## 4. Capacité & robustesse

- **Micro-outils maison** (Stirrup qui « joue » le navigateur) = **fragile** : on
  l'a vu (champs React, onglets, boutons). → on abandonne cette voie pour le web.
- **browser-use natif** = robuste pour le web (c'est sa raison d'être).
- **Stirrup** = robuste pour le code (édition/tests/git/PR ; garde-fous testés).
- **Mono-1** impose d'injecter des outils code dans browser-use : faisable, mais on
  détourne sa boucle (pensée « computer use ») et on mélange deux obsessions
  cognitives dans un contexte.
- **Bi-1** respecte la spécialisation ; chaque framework fait ce qu'il fait le mieux.

## 5. Sécurité / moindre privilège

- **Bi-1** permet un **cloisonnement** : le navigateur n'a **aucun** accès git/jeton ;
  le codeur n'a **aucun** accès navigateur. Surface d'attaque plus faible par agent.
- **Mono** : un agent qui a *tous* les droits (naviguer + écrire + pousser) → plus
  grande surface (prompt injection côté web → actions code/git).

## 6. Latence & ops

- **Mono** : un runtime, un modèle, plus simple à raisonner.
- **Bi-1** : deux runtimes + un protocole de handoff ; mais isolation, testabilité,
  et reprise indépendante (le codeur reprend sur cache, le navigateur sur session
  Chrome persistante).

## 7. Critère de décision

Tout dépend du **degré d'entrelacement** réel des missions :
- missions **séquentielles par phases** (trouver un accès → coder) = majorité ici
  → **bi-agent** gagne (contextes focalisés + handoff compact + orchestration
  gratuite).
- missions **très entrelacées** (naviguer, coder, renaviguer en boucle) → mono-2
  (navigateur encapsulé comme outil) peut réduire les allers-retours.

## 8. Recommandation (à challenger)

**Bi-agent orchestré déterministiquement (Bi-1)**, avec :
- bras navigateur = **browser-use natif** (un agent générique `browse(task)`) ;
- bras code = **Stirrup** (éditeur + tests + git/PR, garde-fous codés) ;
- orchestrateur = **heartbeat maison** (phases + quotas), qui peut **boucler**
  si une phase a besoin d'une info de l'autre ;
- option Mono-2 pour les rares tâches entrelacées : exposer `browse(task)` comme
  **un outil** au codeur (agent imbriqué), sans mélanger les observations.

Et **mesurer** : jouer la même mission (ex. « connecter Europeana ») en Bi-1 et en
Mono-1, comparer tokens totaux, taux de succès, reprises. Décider sur données.

## 9. Questions à soumettre à un modèle plus fort

1. Pour des missions « browse→code », **mono (browser-use + outils code)** vs
   **bi (spécialistes + orchestration déterministe)** : lequel minimise les tokens
   *totaux*, sachant que ~90 % des tokens d'entrée sont **en cache** chez le
   provider (le cache change-t-il le calcul, puisque le préfixe répété est peu facturé) ?
2. Un mono-agent portant **DOM + vision + code** garde-t-il une sélection d'outils
   fiable, ou l'interférence de contexte dégrade-t-elle l'action (hallucination de
   tool calls) ?
3. Orchestrateur **déterministe** (machine à états) vs **manager LLM** : à partir de
   quel degré d'entrelacement le manager LLM devient-il rentable ?
4. Représentation du **handoff** navigateur→codeur : schéma structuré (YAML/JSON)
   vs résumé texte ; comment borner sa taille ?
5. Cloisonnement : vaut-il mieux **deux agents à privilèges séparés** (navigateur
   sans git, codeur sans réseau web) ou un mono-agent plus simple mais plus exposé
   à la prompt-injection ?
6. **Browser-use encapsulé comme outil** dans un agent codeur (imbriqué) vs deux
   agents frères : implications tokens/latence/fiabilité ?
7. Le **cache de prompt** (~90-96 %) plaide-t-il pour **allonger** les contextes
   (une seule boucle) plutôt que les séparer ?

## 10. Prochaine étape

- Capturer les tokens du run **browser-use natif** (fait pour une tâche courte :
  5,4 k/étape ; à refaire sur une longue mission).
- Implémenter un **banc d'essai** mono vs bi sur une mission identique.
- Trancher puis migrer `onboarding`/`outreach` (aujourd'hui Stirrup + micro-outils)
  vers l'approche retenue.
