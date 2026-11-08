# Prise de contact avec une institution

Ce document est la **seule** référence pour les e-mails et formulaires envoyés
aux institutions. Le prompt de l'agent navigateur y renvoie.

## Principe

On ne demande pas la permission de **référencer des pages publiques**. On
informe, on demande les **préférences** (crédit, retrait, accès officiel), et on
laisse toujours une porte humaine.

On ne parle jamais de « réutilisation d'images » : le projet ne copie, n'héberge,
ne redistribue et ne revend aucune image.

Le fondateur signe sous le pseudonyme **Antonio-Faure** ; son **identité civile
reste anonyme** (jamais de prénom/nom réel). Les échanges téléphoniques ou en
visioconférence se **demandent par e-mail** — c'est par e-mail qu'on fixe le
rendez-vous.

## Avant d'écrire — checklist obligatoire

- [ ] **Adresse trouvée sur le site officiel** (page contact, footer, mentions
      légales), pas seulement dans un annuaire.
- [ ] **Domaine officiel vérifié** (le site répond ; le domaine a des MX).
- [ ] **Objet sans « réutilisation »** ni « autorisation ».
- [ ] **Une seule demande principale** + deux préférences.
- [ ] Phrase explicite : *aucune copie, aucun hébergement, aucune redistribution,
      aucune revente ; les images restent chez vous*.
- [ ] Lien vers `docs/POUR-LES-INSTITUTIONS.md`.
- [ ] **Offre d'échange humain, à demander par e-mail** (téléphone ou visio).
- [ ] Signature **pseudonyme uniquement** : « Antonio-Faure (pseudonyme), projet
      Mnemosyne » + mention que l'identité civile reste anonyme. Jamais de prénom/nom réel.
- [ ] **Cc vérifiés un par un** (chaque adresse doit être vivante).
- [ ] Journal : destinataire, objet, date, canal.

## Modèle — première prise de contact (français)

**Objet :** Mnemosyne — référencer les collections du {institution} (projet open source)

> Bonjour,
>
> Je développe **Mnemosyne**, un projet libre et open source qui rend les archives
> photographiques historiques plus faciles à découvrir :
> https://github.com/Antonio-Faure/mnemosyne
>
> Le projet se veut exhaustif sur les sources : le nombre d'institutions
> référencées est amené à croître fortement. Votre collection {collection} est
> l'une des plus pertinentes pour {sujet}. Je vous écris pour vous informer de ma
> démarche et recueillir vos préférences.
>
> **Ce que fait Mnemosyne :** il référence les notices publiques de votre
> catalogue (titre, date, auteur, droits connus) et renvoie vers votre site. Il
> **ne télécharge pas vos images, ne les héberge pas, ne les redistribue pas et
> ne les revend pas**. Vos images restent chez vous, dans vos conditions.
>
> **Ce que je vous demande :**
> 1. la mention de crédit exacte à afficher ;
> 2. si vous disposez d'un accès officiel (API, IIIF, OAI-PMH), ses modalités
>    d'utilisation ;
> 3. si vous préférez ne pas être référencé, dites-le : je retire votre
>    institution immédiatement.
>
> Pour en savoir plus : {lien vers la page institutions}
>
> Vous préférez en parler de vive voix ? **Écrivez-moi par e-mail** et je
> fixerai un échange téléphonique ou en visioconférence, sans connaissance
> technique requise.
>
> Bien cordialement,
> **Antonio-Faure (pseudonyme)** — projet Mnemosyne
> https://github.com/Antonio-Faure/mnemosyne
> archivist.mnemosyne@gmail.com
>
> *Le fondateur signe sous le pseudonyme Antonio-Faure ; son identité civile reste
> anonyme. Ce message a été préparé par l'assistant logiciel du projet ; les
> échanges importants restent humains.*

## Style (à relire avant d'envoyer)

- **Première personne du singulier** : « je », jamais « nous ».
- **Un seul saut de ligne** entre paragraphes : pas de lignes vides multiples,
  pas d'espace avant « Bonjour ».
- Nom officiel : « **Musée français du Pétrole** » (adjectif en minuscule) ou
  « Musée du Pétrole » — ne pas inventer de majuscules.
- Éviter les formules ambiguës : « si vous préférez ne pas être référencé »
  → « si le musée préfère ne pas être référencé ».
- Relire l'orthographe, les accents (référençons, hébergeons) et la ponctuation
  avant de cliquer sur Envoyer.

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

- Pas de `/wp-json/wp/v2/media` ni d'export massif proposé dans un premier
  contact.
- Pas de demande d'autorisation pour des pages publiques.
- Pas de « réutilisation », « catalogue libre », « extraction », « scraping »
  dans un message à une institution.
- Pas de prénom/nom réel du fondateur : uniquement le pseudonyme Antonio-Faure.
- Pas de secret, de clé ou de donnée personnelle dans un message.
- Pas d'envoi à une adresse non vérifiée.
