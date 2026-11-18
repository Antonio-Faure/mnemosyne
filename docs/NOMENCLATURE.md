# Nomenclature

> **Statut : figée le 18 novembre 2026.** Ce document est la référence pour le
> produit, les docs, les prompts et l'UI. Le code garde ses identifiants
> anglais ; la correspondance est en fin de document.

**Règle d'or** : un concept = un terme. Si un terme manque, on l'ajoute ici ;
on n'invente pas de synonyme. Les termes « à éviter » ne doivent pas apparaître
dans la copie produit, les docs actifs, les prompts ou l'UI. Les documents
historiques peuvent les citer avec une mention « historique ».

## 1. Acteurs

| Terme | Définition | À éviter |
|---|---|---|
| **Mnemosyne** | le moteur de recherche (le produit) | mnemosyne (sauf code/CLI), moteur d'archives |
| **Archivist** | le système autonome complet, composé du Résolveur et de l'Atelier | archiviste, tri-agent, bi-agent, « le système » |
| **Le Résolveur** | l'équipe phrase → image | résolveur seul, resolver (sauf code), système résolveur |
| **L'Atelier** | l'équipe qui ajoute et maintient les sources | système navigateur/codeur, coder+browser |
| **L'agent codeur** | l'agent qui écrit les connecteurs et le code | codeur seul, coder (sauf code) |
| **L'agent navigateur** | l'agent qui agit sur le web (comptes, accès, e-mails) | navigateur seul, browser (sauf code) |
| **L'agent résolveur** | l'agent qui cherche l'image d'une phrase | résolveur seul, resolver (sauf code) |
| **L'opérateur** | l'humain qui répond aux questions et valide les choix | humain, HITL, user |
| **Le gestionnaire du projet** | Antonio Faure, responsable public du projet | fondateur, owner, admin |
| **L'institution** | le musée, la bibliothèque ou l'archive qui conserve les images | fournisseur, provider, partenaire |

**Hiérarchie** : **Archivist** est le système. **Le Résolveur** et **L'Atelier**
sont ses deux équipes. Les **agents** sont « l'agent codeur », « l'agent
navigateur » et « l'agent résolveur ». On ne dit pas « le système résolveur » ni
« le système navigateur/codeur ».

## 2. Unités de travail

| Terme | Définition | À éviter |
|---|---|---|
| **Une tâche** | une unité de travail dans la file, avec un objectif, un agent de départ et un statut ; une carte kanban | job, mission (sauf mission de source), item |
| **Une résolution** | une tâche du Résolveur : une phrase à illustrer | tâche resolver, phrase (comme tâche) |
| **Une demande de source** | une source manquante demandée par une résolution | resolver request (sauf code), requête de source |
| **Une mission de source** | la tâche de l'Atelier qui ajoute une source demandée | tâche coder/browser, onboarding, connect |
| **Une session** | le contexte persistant d'un agent pour une tâche | run, conversation |
| **Une activation** | une exécution de la boucle d'un agent sur une tâche | run, tour |
| **Un tour** | un appel au modèle + ses outils dans une activation | step, iteration |
| **Un job système** | une unité planifiée mécanique (verify, discover, warmup, journal, watchdog) | tâche (pour un job), job seul |
| **Une exécution** | l'occurrence d'un job système ou d'une activation | run |
| **La file** | la liste des tâches en attente | queue (sauf code) |
| **La boîte aux lettres** | la boîte de messages d'une tâche entre agents | mailbox (sauf code) |
| **Le backlog** | les tâches accumulées à traiter avant la refonte ; ne pas confondre avec la file active | arriéré (comme terme principal) |

## 3. Sources et objets

| Terme | Définition | À éviter |
|---|---|---|
| **Une source** | le catalogue en ligne d'une institution, tel que connecté à Mnemosyne | fournisseur, provider (sauf code), site |
| **Un catalogue** | le catalogue de l'institution (l'original) | source (pour le catalogue interne) |
| **Le registre des sources** | la liste interne des sources connues (`catalog`) | catalogue seul, catalogue Mnemosyne |
| **Une collection** | un ensemble d'images dans une institution | fonds (sauf archives) |
| **Un fonds** | un ensemble d'archives par provenance | collection (sauf cas) |
| **Un connecteur** | le code qui interroge une source (`connector`) | adaptateur, plugin |
| **Un descripteur** | le fichier YAML qui décrit une source | config, fiche source |
| **Un protocole** | le mode d'accès technique (IIIF, OAI-PMH, REST, SRU…) | API (pour le protocole) |
| **Une API** | une interface programmatique d'une institution | accès seul |
| **Un accès programmatique** | la possibilité de lire automatiquement un catalogue | accès automatique, scraping (dans les mails) |
| **Une lecture automatique des pages publiques** | parcourir les pages publiques avec un programme, avec autorisation | scraping, moissonnage, collecte |
| **Une vignette** | l'image réduite affichée dans un résultat | thumbnail, preview |
| **L'affichage direct** | l'image chargée depuis le site de l'institution, sans copie | hotlink, hotlinking |
| **Les informations** | titre, auteur, date, lieu et droits affichés dans un résultat | métadonnées (sauf technique) |
| **Les droits** | les conditions d'utilisation connues | licence (sauf licence explicite) |
| **La mention de l'institution** | le nom ou le crédit affiché à côté d'un résultat | crédit (sauf légal) |

## 4. Le Résolveur

| Terme | Définition | À éviter |
|---|---|---|
| **Une phrase** | l'unité de texte à illustrer | sentence (sauf code) |
| **Un segment** | une phrase avec ses timestamps dans une vidéo | segment (code) |
| **Un corpus** | l'ensemble des phrases importées | dataset |
| **Un fait** | ce que la phrase affirme (date, lieu, personne, événement) | claim (sauf code) |
| **Un candidat** | une image proposée pour une phrase | match (avant validation) |
| **Un résultat** | une carte de recherche : image + informations + lien | asset, record, item |
| **Une fiche** | la page de l'institution pour une image | notice (sauf archives), page |
| **Une issue** | le type de fin d'une tâche | résultat, outcome |
| **Validé** | `match` : image validée | match (sauf code) |
| **Partiel** | `partial` : image d'illustration partielle | partial (sauf code) |
| **Abstention** | `no_match` : aucune image défendable | no_match (sauf code), échec |
| **Ambigu** | `ambiguous` : jugement impossible en l'état | ambiguous (sauf code) |
| **Le jeu de référence** | le corpus avec issues attendues (`resolver_golden`) | golden (sauf code) |
| **Un trou de couverture** | une source manquante révélée par une abstention | gap |

## 5. États, issues et kanbans

### Statut et état

- **Un statut** : l'état de vie d'une tâche (`pending`, `running`, `review`,
  `done`, `failed`, `cancelled`).
- **Un état** : l'état d'une source (`discovered`, `connected`, `degraded`).
- On ne dit pas « statut » pour une source ni « état » pour une tâche.

### Colonnes

Les deux kanbans ont les mêmes colonnes :

**En file** · **En cours** · **En attente** · **Terminé** · **Échec**

- **En file** : tâche créée, pas encore activée (`pending`).
- **En cours** : une activation tourne (`running`).
- **En attente** : la tâche est garée sur une dépendance.
- **Terminé** : la tâche a une issue terminale (`done`).
- **Échec** : la tâche a échoué (`failed`) ou a été annulée (`cancelled`).

`review` se place dans **Terminé** avec le badge **À revoir** (orange) : la
tâche est finie, mais elle demande un regard humain.

### Types d'attente

| Kanban | Type | Couleur | Sens |
|---|---|---|---|
| Les deux | **Opérateur** | ambre | une question attend une réponse humaine |
| Résolveur | **Sources** | rose | attend une ou plusieurs missions de source |
| Atelier | **E-mail** | bleu | attend une réponse d'institution (navigateur) |
| Atelier | **Accès** | violet | attend une clé, un compte ou une autorisation |

### Issues terminales

| Kanban | Type | Couleur | Sens |
|---|---|---|---|
| Résolveur | **Validé** | vert | image validée |
| Résolveur | **Partiel** | turquoise | image d'illustration partielle |
| Résolveur | **Abstention** | gris | aucune image défendable |
| Résolveur | **Ambigu** | orange | jugement impossible en l'état |
| Atelier | **Source ajoutée** | vert | connecteur fusionné et actif |
| Atelier | **Déjà couverte** | turquoise | la source existait déjà |
| Atelier | **Refusée** | gris | l'institution a refusé ; source abandonnée |
| Atelier | **Sans source** | gris | aucune source exploitable trouvée |

### Échecs

| Kanban | Type | Couleur | Sens |
|---|---|---|---|
| Résolveur | **Technique** | rouge | LLM, API, crash, timeout |
| Résolveur | **Budget** | rouge foncé | quota ou coût |
| Résolveur | **Annulé** | gris | arrêté par l'opérateur |
| Atelier | **Accès refusé** | rouge | 401/403/blocage |
| Atelier | **Technique** | rouge | API cassée, parse error, timeout |
| Atelier | **Abandon** | orange | trop complexe ou budget |
| Atelier | **Annulé** | gris | arrêté par l'opérateur |

### Kanban du Résolveur

Alimenté par l'importation des nouvelles résolutions. Une résolution peut
demander plusieurs sources ; elle reste en **En attente — Sources** tant que
toutes ses demandes ne sont pas terminales.

### Kanban de l'Atelier

Alimenté par les demandes de source du Résolveur. Une mission de source peut
servir plusieurs résolutions ; la carte affiche « demandée par N résolutions ».
Une mission peut passer par une phase navigateur (accès) puis une phase codeur
(connecteur) ; la carte montre l'agent courant.

### Résumé de colonne

Chaque colonne affiche un résumé en tête :

> 12 terminés · 4 validés · 3 partiels · 2 abstentions · 3 ambigus

Les types sont des **badges et des filtres**, pas des colonnes.

## 6. UI

| Terme | Définition | À éviter |
|---|---|---|
| **L'Observatoire** | l'UI de suivi des sessions et du système | preview, dashboard, UI |
| **L'Explorateur** | la page publique de recherche | search page, frontend |
| **Un kanban** | un tableau de tâches en colonnes | board |
| **Le kanban du Résolveur** | le tableau des résolutions | board resolver |
| **Le kanban de l'Atelier** | le tableau des missions de source | board sources |
| **Une carte** | une tâche dans un kanban | item, ticket |
| **Une colonne** | un statut du kanban | lane, swimlane |
| **Un badge** | un type d'attente ou d'issue sur une carte | tag, label |
| **Un filtre** | un contrôle de sélection (agent, type) | facette |
| **Le graphe des sessions** | la vue Canvas de l'Observatoire | canvas, graph |
| **La chronologie** | la timeline d'une session | timeline, replay |
| **La relecture** | le replay d'une session | replay |

## 7. Termes bannis ou réservés

| Terme | Statut |
|---|---|
| **harvest**, **moissonnage**, **collecte**, **stockage d'assets** | bannis : fonctionnalité supprimée |
| **bi-agent** | banni : remplacé par Archivist / deux équipes |
| **tri-agent** | banni : remplacé par Archivist / deux équipes |
| **archiviste** | banni : ce n'est pas Archivist |
| **système résolveur**, **système navigateur/codeur** | bannis : Le Résolveur / L'Atelier |
| **fournisseur** | banni des docs : utiliser **source** |
| **asset**, **record**, **item** | code uniquement : produit = **résultat** |
| **provider** | code / docs techniques anglaises uniquement : docs FR = **source** |
| **metadata**, **métadonnées** | technique uniquement : produit = **informations** |
| **notice** | archives/technique uniquement : produit = **fiche** |
| **credit**, **crédit** | légal uniquement : produit = **mention** |
| **hotlink**, **hotlinking** | technique uniquement : produit = **affichage direct** |
| **scraping** | technique uniquement : institutions = **lecture automatique des pages publiques** |
| **onboarding** | code/technique : produit = **intégration d'une source** |
| **connect** | code/technique : produit = **intégration** |
| **warmup** | code/technique : docs = **rodage** |
| **run** | code/technique : docs = **exécution** |
| **status**, **state** | code : docs = **statut** / **état** |
| **outcome** | code : docs = **issue** |
| **golden** | code : docs = **jeu de référence** |
| **claim** | code : docs = **fait** |
| **preview**, **dashboard** | bannis : **Observatoire** |

## 8. Correspondance code ↔ produit

| Code | Produit |
|---|---|
| `mnemosyne` | Mnemosyne |
| `resolver` | agent résolveur / Le Résolveur (équipe) |
| `coder` | agent codeur |
| `browser` | agent navigateur |
| `task` | tâche |
| `job` | job système |
| `session` | session |
| `activation` | activation |
| `turn` | tour |
| `resolver_request` | demande de source |
| `agent_task_id` | mission de source (tâche liée) |
| `Asset` | résultat |
| `SourceDescriptor` / `source` | source |
| `provider` | source (docs FR) |
| `catalog` | registre des sources |
| `connector` | connecteur |
| `descriptor` | descripteur |
| `protocol` | protocole |
| `match` | validé |
| `partial` | partiel |
| `no_match` | abstention |
| `ambiguous` | ambigu |
| `resolver_golden` | jeu de référence |
| `claim` | fait |
| `status` | statut |
| `state` | état |
| `outcome` | issue |
| `operator` | opérateur |
| `ask` | question |
| `email_wait` | attente d'e-mail |
| `onboarding` | intégration d'une source |
| `connect` | intégration |
| `warmup` | rodage |
| `harvest` | banni (supprimé) |

## 9. Écarts connus à corriger

La chasse au vocabulaire devra traiter au minimum :

| Fichier | Écart | Action |
|---|---|---|
| `docs/SOURCES.md` | « fournisseurs déclarés » | → « sources déclarées » |
| `docs/SOURCES.md` | « vérifier par notice » | → « vérifier sur la fiche de l'institution » |
| `docs/ARCHITECTURE.md` | « providers », « catalog », « Asset », « state machine » | aligner sur source / registre / résultat / état |
| `docs/OBSERVATORY.md` | « run de job système », « tâche de la queue » | → exécution d'un job système / tâche de la file |
| `docs/ONBOARDING.md` | « onboarding », « connexion », « catalogue » | → intégration d'une source / mission de source / registre des sources |
| `docs/RESOLVER-ADVERSARIAL.md` | « match », « onboarder », « tâches coder/browser », « tâches resolver » | → validé / intégrer / missions de source / résolutions |
| `docs/VISION-TRIAGENT.md` | « tri-agent » partout | renommer et aligner sur Archivist / deux équipes |
| `docs/CLEANUP-TRIAGENT.md` | « tri-agent » | marquer historique ou aligner |
| `agents/browser.md` | vérifier « source », « institution », « fiche » | aligner si besoin |
| `config/sources/*.yaml` | « provider », « harvest », « notice » dans les notes | remplacer par source / recherche / fiche |
