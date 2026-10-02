# Choisir : browser-use seul, ou stirrup + browser-harness ?

> Guide de décision, avec des exemples concrets. Les deux produits viennent du
> même org upstream (browser-use) — ils ne sont pas concurrents, ils répondent
> à des besoins différents.

## L'image d'ensemble

| | browser-use seul | stirrup + browser-harness |
|---|---|---|
| **Qui tient la boucle LLM ?** | la lib : ses prompts, sa mémoire, son tool-calling | nous : notre prompt, nos outils, notre supervision |
| **Le LLM ?** | donné à la lib, elle décide de tout faire avec | appelé par nous à chaque pas, avec ce que NOUS passons |
| **Les mains ?** | les actions intégrées de la lib (+ customs via `@action`) | du code Python exécuté par le harness sur Chrome (CDP) |
| **Règles métier/sécurité** | espérées via prompt (que tu ne contrôles pas) | **appliquées en code** à chaque pas (le guard lève une exception) |
| **Vision** | heuristique de nom de modèle, sans échappatoire (PR #1399) | chaîne ouverte : ce que TU attaches au résultat |
| **Coopération multi-agents** | hors périmètre (l'Agent veut finir SA tâche) | natif : mailbox/vault/finish = outils ordinaires |
| **Vitesse de POC** | ★★★ (10 lignes) | ★ (prompt + outils + gardes à écrire) |
| **Self-extension** | pas naturel | naturel : l'agent écrit ses helpers, les garde en git |
| **Observabilité par pas** | l'historique de la lib | chaque pas = subprocess borné, nos logs, notre token usage |

## Les exemples concrets

### Exemple 1 — « Extrais les 200 pages de prix de ce site, une fois »
**→ browser-use.** Dix lignes : `Agent(task="extrais tous les prix…", llm=…)`.
La pagination, les attentes, les clics : la lib s'en charge. En
stirrup+harness, tu devrais écrire un prompt d'agent, des outils, des
garde-fous — pour un gain nul. C'est le POC de l'après-midi.

### Exemple 2 — « L'agent ne doit JAMAIS double-cliquer ni soumettre via js »
**→ stirrup + harness.** En browser-use, ces règles seraient des PHRASES dans
un prompt que la lib compose — espérées, pas garanties, et réécrites à chaque
mise à jour de la lib. Chez nous, c'est du code : le `_HARNESS_GUARD` lève une
exception au 2e clic sur le même point et refuse tout `js()` qui soumet.
Mécanique, à chaque pas, impossible à « oublier » par le LLM.

### Exemple 3 — « L'agent reçoit des missions d'un autre agent, en 24/7 »
**→ stirrup + harness.** browser-use n'a pas de concept de boîte à lettres ni
de collègue : son Agent veut finir SA tâte. La coopération deviendrait un
contournement autour de sa boucle. En stirrup, mailbox/vault/finish sont des
outils ordinaires et le superviseur (déterministe, sans LLM) ordonnance les
tours. C'est le cœur du bi-agent mnemosyne.

### Exemple 4 — « Ton modèle est plus récent que les heuristiques de la lib »
**→ stirrup + harness.** Le gate deepseek : browser-use désactivait la vision
de deepseek-v4.1-flash par NOM de modèle, sans échappatoire — on a dû patcher
au build (docs/VISION-DEEPSEEK.md). En stirrup+harness, ce que le LLM voit
(images, textes, secrets filtrés) est exactement ce que NOUS attachons —
aucune heuristique de nom sur le chemin de la boucle.

### Exemple 5 — « Le site résiste ; il faut écrire un helper spécifique »
**→ stirrup + harness.** Le harness exécute du code : l'agent peut écrire ses
propres helpers, les garder dans un worktree git, en ouvrir des PR. La
self-extension est naturelle (c'est ce que fait notre agent navigateur).
En browser-use, il faudrait contourner leur registre d'actions.

### Exemple 6 — « Tu veux savoir ce qui est réellement parti au LLM »
**→ stirrup + harness.** Chaque pas : un subprocess borné (300 s), nos logs,
notre usage tokens par tour (prompt/cached/completion), notre entonnoir de
patinage. En browser-use : l'historique de la lib, dans son format.

## La règle du pouce

- **Mission ponctuelle, un agent, pas de règles métier** → **browser-use**.
  Rapidité de mise en œuvre, la lib tout de s'occupe.
- **L'agent fait partie d'un SYSTÈME** (orchestrateur déterministe, autres
  agents, règles imposées, secrets, audit) → **stirrup + browser-harness**.

## La distinction qui compte : agent fermé vs agent de système

La formulation la plus juste (et celle qui décide vraiment) :

- **browser-use est un agent FERMÉ** : très agentique **à l'intérieur** (une
  boucle LLM autogérée, qui décide vraiment), mais fermé **à la frontière** —
  ses mains sont un catalogue figé au lancement (actions intégrées + customs
  écrites À L'AVANCE via `@action`), il ne peut pas écrire ses propres helpers
  pendant sa mission, et son monde s'arrête à sa tâche : pas de boîte à
  lettres, pas de collègue, pas de superviseur.
- **stirrup + harness est un agent OUVERT** : les mains sont un **interpréteur
  Python**, pas un catalogue — l'agent peut écrire une fonction pendant sa
  mission, la réutiliser au pas suivant, la garder en git, en faire une PR.
  Et il participe à un système : mailbox, vault, finish structuré, détection
  de patinage, orchestrateur déterministe.

Le paradoxe à garder en tête : « beaucoup de ce que browser-use fait est très
automatisé » est exact, et c'est une conséquence directe du catalogue. La
boucle choisit **dans un menu** ; la nôtre **écrit dans un langage**. C'est
plus agentique, pas moins : le catalogue borne l'espace d'action, l'interpréteur
le limite seulement aux règles de sécurité que nous imposons.

En termes d'essaim : **browser-use est un excellent sous-agent, un mauvais
collègue.** Un agent d'essaim doit savoir recevoir des ordres (mailbox),
rendre des comptes (finish structuré), coopérer (messages), et être
ordonnancé par un tiers déterministe. Mnemosyne est un mini essaim de deux
agents — browser-use n'aurait aucun des quatre réflexes.

Nuance d'honnêteté : on emprunte quand même ses *mains* (stirrup[browser] →
`BrowserSession`) — on refuse son cerveau, pas sa couche CDP.

## L'identité : archivist = l'archiviste à deux têtes

Le personnage qui touche le web n'est pas « l'agent navigateur » : c'est le
bi-agent ENTIER — **un archiviste à deux têtes**. `identity.agent_email`
(`archivist.mnemosyne@gmail.com`) est sa carte d'identité partagée :

- la tête **navigateur** l'utilise pour tout ce qui touche le web (comptes,
  e-mails, livraisons) — c'est elle qui « signe » ;
- la tête **codeur** signe ce qu'elle produit de son côté (branches `agent/*`,
  PRs) mais ne touche jamais au web ;
- les deux têtes sont alternées par le superviseur : une seule travaille à la
  fois, elles se passent le relais par la boîte de messages de la tâche.

Résultat : tout ce que le système fait sur le web est traçable à UNE identité
cohérente — celle de l'archiviste — et jamais à deux identités concurrentes.

## Et notre cas précis (mnemosyne)

Nous sommes les exemples 2+3+4+5 réunis : règles de sécurité imposées,
coopération bi-agent, modèle vision-coupé par la lib, self-extension des
helpers. Le choix était donc clair. **Mais** browser-use n'est pas un choix
« cheap » : c'est un cerveau autonome éprouvé (★117k) — excellent pour ce
qu'il fait. Notre critique n'est pas « il est mauvais », c'est « il décide à
notre place » : ses heuristiques de nom de modèle sont le contre-exemple
exact.

Et ils ne s'excluent pas : dans le conteneur, browser-use fournit encore la
couche `BrowserSession` (stirrup[browser]) — cerveau et session ne sont pas la
même couche.

## Qu'est-ce qui pourrait nous faire reconsidérer ?

- **Aucun de nos besoins ne migre vers browser-use** : dès qu'un agent est dans
  le service, ses règles viennent avec lui.
- Un **POC jetable** (hors mnemosyne, un script one-shot) : browser-use y a
  toute sa place.
- Si un jour browser-use offrait un **cerveau déléguable** (prompt système
  entièrement contrôlable, actions seulement passives, pas d'heuristique de
  modèle), la question pourrait se reposer — pour l'instant, non.
