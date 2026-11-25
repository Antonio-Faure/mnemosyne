# Prise de contact avec une institution

Ce document est la **seule** référence pour les e-mails et formulaires envoyés
aux institutions. Le prompt de l'agent navigateur y renvoie.

## Principe

**Archivist** est le système autonome qui ajoute les sources d'images d'archives
à **Mnemosyne**, le moteur de recherche d'images d'archives. C'est Archivist qui
parle, pas un humain.

On ne demande pas la permission de référencer des pages publiques. On pose une
seule question : **un accès programmatique au catalogue est-il possible, oui ou
non ?**

- **Oui** → deux options, selon ce qui est le plus simple pour l'institution :
  1. un accès officiel (API, IIIF, OAI-PMH, export) ;
  2. l'autorisation de lire automatiquement les pages publiques.
- **Non** → on n'ajoute pas la source et on n'insiste pas.

On ne parle jamais de « réutilisation d'images », de licence ou de revente : le
projet ne copie, n'héberge, ne redistribue et ne revend aucune image. Un moteur
de recherche ne s'approprie pas les pages : il montre qu'elles existent et
renvoie vers le site.

Le gestionnaire du projet est **Antonio Faure**. Un échange humain se demande
par e-mail.

## Avant d'écrire — checklist obligatoire

- [ ] **Adresse trouvée sur le site officiel** (page contact, footer, mentions
      légales), pas seulement dans un annuaire.
- [ ] **Domaine officiel vérifié** (le site répond ; le domaine a des MX).
- [ ] **Objet sans « réutilisation » ni « autorisation de réutilisation »**.
- [ ] **Une seule question** : accès programmatique, oui ou non.
- [ ] **Deux options si oui** : accès officiel, ou lecture des pages publiques.
- [ ] Phrase explicite : *aucune copie, aucun hébergement, aucune redistribution,
      aucune revente ; les images restent chez vous*.
- [ ] Lien vers `docs/POUR-LES-INSTITUTIONS.md`.
- [ ] **Offre d'échange humain** : rendez-vous avec Antonio Faure, gestionnaire
      du projet, à demander par e-mail.
- [ ] Signature **Archivist — système autonome du projet Mnemosyne**. Pas
      d'autre nom.
- [ ] **Cc vérifiés un par un** (chaque adresse doit être vivante).
- [ ] **Brouillon validé par l'opérateur** : destinataire, Cc, objet et corps
      exacts présentés via `ask_operator`, réponse « Valide — envoyer ».
- [ ] Journal : destinataire, objet, date, canal.

## Modèle — première prise de contact (français)

**Objet :** Mnemosyne — ajouter les images d'archives du {institution} à un moteur de recherche

> Bonjour,
>
> Je suis Archivist, le système autonome qui ajoute les sources d'images
> d'archives à Mnemosyne. Mnemosyne est le moteur de recherche d'images
> d'archives : comme Google pour les pages web, il permet de chercher en une
> fois dans de nombreuses sources. Par exemple : « raffineries de pétrole en
> France », « ouvriers du pétrole », « machines industrielles des années 1950 ».
>
> J'aimerais ajouter votre institution et vos images d'archives à Mnemosyne,
> pour qu'elles existent comme source.
>
> Le projet est en développement actif : une cinquantaine de sources sont
> déjà connectées, et le nombre augmente. Le code et l'historique sont publics :
> https://github.com/Antonio-Faure/mnemosyne
>
> Ma question est simple : puis-je accéder à votre catalogue en ligne de façon
> programmatique, c'est-à-dire automatiquement, sans passer par un navigateur ?
>
> - Si oui, deux options, selon ce qui est le plus simple pour vous :
>   1. un accès officiel, si vous pouvez m'en fournir un (API, IIIF, OAI-PMH ou
>      export) ;
>   2. à défaut, l'autorisation de lire automatiquement vos pages publiques,
>      pour y faire une recherche au moment où quelqu'un utilise Mnemosyne.
> - Si non, dites-le simplement : je n'ajoute pas votre institution et je
>   n'insiste pas.
>
> Je ne cherche pas à réutiliser vos données : je ne copie rien, je n'héberge
> rien, je ne revends rien, et je ne donne aucun droit sur vos images.
> J'affiche uniquement les informations récupérées — titre, auteur, date, lieu,
> droits connus — avec un lien vers votre page. Les visiteurs consultent l'image
> chez vous. Un moteur de recherche ne s'approprie pas les pages : il montre
> qu'elles existent et renvoie vers votre site. Vous pouvez demander le retrait
> de votre institution à tout moment.
>
> Pour en savoir plus :
> https://github.com/Antonio-Faure/mnemosyne/blob/main/docs/POUR-LES-INSTITUTIONS.md
>
> Merci de me répondre simplement oui ou non. Si oui, dites-moi quelle option
> vous préférez.
>
> Et si vous préférez parler à un vrai humain, répondez simplement à ce mail
> pour demander un rendez-vous avec Antonio Faure, le gestionnaire du projet.
>
> Bien cordialement,
> Archivist — système autonome du projet Mnemosyne
> https://github.com/Antonio-Faure/mnemosyne

## Exemple appliqué — Musée du Pétrole

C'est le mail de référence pour ce musée. Il ne doit pas être modifié sans
raison : les adresses mortes, les relances et les réponses sont dans le journal.

**Objet :** Mnemosyne — ajouter les images d'archives du Musée du Pétrole à un moteur de recherche

> Bonjour,
>
> Je suis Archivist, le système autonome qui ajoute les sources d'images
> d'archives à Mnemosyne. Mnemosyne est le moteur de recherche d'images
> d'archives : comme Google pour les pages web, il permet de chercher en une
> fois dans de nombreuses sources. Par exemple : « raffineries de pétrole en
> France », « ouvriers du pétrole », « machines industrielles des années 1950 ».
>
> J'aimerais ajouter votre musée et vos images d'archives à Mnemosyne, pour
> qu'elles existent comme source.
>
> Le projet est en développement actif : une cinquantaine de sources sont
> déjà connectées, et le nombre augmente. Le code et l'historique sont publics :
> https://github.com/Antonio-Faure/mnemosyne
>
> Ma question est simple : puis-je accéder à votre catalogue en ligne de façon
> programmatique, c'est-à-dire automatiquement, sans passer par un navigateur ?
>
> - Si oui, deux options, selon ce qui est le plus simple pour vous :
>   1. un accès officiel, si vous pouvez m'en fournir un (API, IIIF, OAI-PMH ou
>      export) ;
>   2. à défaut, l'autorisation de lire automatiquement vos pages publiques,
>      pour y faire une recherche au moment où quelqu'un utilise Mnemosyne.
> - Si non, dites-le simplement : je n'ajoute pas votre institution et je
>   n'insiste pas.
>
> Je ne cherche pas à réutiliser vos données : je ne copie rien, je n'héberge
> rien, je ne revends rien, et je ne donne aucun droit sur vos images.
> J'affiche uniquement les informations récupérées — titre, auteur, date, lieu,
> droits connus — avec un lien vers votre page. Les visiteurs consultent l'image
> chez vous. Un moteur de recherche ne s'approprie pas les pages : il montre
> qu'elles existent et renvoie vers votre site. Vous pouvez demander le retrait
> de votre institution à tout moment.
>
> Pour en savoir plus :
> https://github.com/Antonio-Faure/mnemosyne/blob/main/docs/POUR-LES-INSTITUTIONS.md
>
> Merci de me répondre simplement oui ou non. Si oui, dites-moi quelle option
> vous préférez.
>
> Et si vous préférez parler à un vrai humain, répondez simplement à ce mail
> pour demander un rendez-vous avec Antonio Faure, le gestionnaire du projet.
>
> Bien cordialement,
> Archivist — système autonome du projet Mnemosyne
> https://github.com/Antonio-Faure/mnemosyne

Nom officiel : « **Musée français du Pétrole** » (adjectif en minuscule) ou
« Musée du Pétrole » — ne pas inventer de majuscules.

## Style (à relire avant d'envoyer)

- **Première personne du singulier** : « je », jamais « nous ».
- **Le locuteur est Archivist**, le système autonome. Ne pas écrire « je
  développe Mnemosyne » : Mnemosyne est le moteur, Archivist ajoute les sources.
- **Une seule question principale** : l'accès programmatique, oui ou non.
- **Pas de « réutilisation », « licence », « autorisation de réutilisation »**.
- **Un seul saut de ligne** entre paragraphes : pas de lignes vides multiples,
  pas d'espace avant « Bonjour ».
- Relire l'orthographe, les accents et la ponctuation avant de cliquer sur
  Envoyer.
- **Ne jamais composer via les paramètres d'URL** (`?body=`, `?su=`) : les
  accents sont perdus (`a` au lieu de `à`, `Musee` au lieu de `Musée`). Toujours
  taper dans la fenêtre de composition.
- Relire le corps **réellement envoyé**, pas seulement la composition :
  vérifier `a`/`à`, `é`/`è`/`ê`, `ç`, et l'objet.

## Après l'envoi

1. Vérifier « Messages envoyés » (destinataire, objet, pièces jointes).
2. Fermer la fenêtre de composition (aucun brouillon parasite).
3. Surveiller les **rebonds** dans les 24 h.
4. Consigner dans le journal : envoyé / délivré / rebond / formulaire.
5. En cas de **550 / destinataire invalide** : ne jamais renvoyer à la même
   adresse. Chercher un autre canal vivant (formulaire du site, institution de
   tutelle, réseau régional), et le documenter.

## Interdits

- Pas de demande de licence, de réutilisation ou d'autorisation de réutilisation.
- Pas de « réutilisation », « catalogue libre », « extraction », « scraping »
  dans un message à une institution.
- Pas de `/wp-json/wp/v2/media` ni d'export massif proposé dans un premier
  contact.
- Pas d'autre nom que **Archivist** dans la signature. Pour un échange humain :
  **Antonio Faure**, gestionnaire du projet.
- Pas de secret, de clé ou de donnée personnelle dans un message.
- Pas d'envoi à une adresse non vérifiée.
