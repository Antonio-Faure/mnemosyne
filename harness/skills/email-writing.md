# Écrire à une institution

Utilise ce skill quand la mission demande un **e-mail de prise de contact** :
petite structure sans accès programmatique, demande d'autorisation de lire les
pages publiques, ou demande d'API/IIIF/OAI. Le modèle de référence est dans ton
prompt système et dans `docs/OUTREACH.md` ; ce skill explique comment l'adapter
sans le déformer.

## Avant d'écrire

1. Vérifie que le catalogue n'est **pas déjà** accessible par API, IIIF, SRU,
   OAI-PMH ou export : si oui, utilise l'accès programmatique, pas l'e-mail.
2. Trouve l'adresse sur le **site officiel** (page contact, mentions légales,
   pied de page). Le domaine doit répondre. Ne réutilise jamais une adresse qui
   a déjà rebondi (550).
3. Vérifie que l'institution n'est pas déjà dans Mnemosyne et que la source
   n'est pas déjà demandée.
4. Une seule question : **puis-je accéder à votre catalogue de façon
   programmatique ?** Oui → accès officiel ou autorisation de lire les pages
   publiques. Non → on n'ajoute pas la source.

## Structure (4 paragraphes, pas plus)

1. **Qui** : Archivist, le système autonome qui ajoute les sources à Mnemosyne,
   moteur de recherche d'images d'archives (analogie Google).
2. **Pourquoi** : ajouter l'institution comme source pour que ses images
   existent dans la recherche. Donne 2–3 exemples de requêtes concrètes.
3. **La question** : accès programmatique ? Deux options si oui (accès officiel
   ou lecture des pages publiques) ; si non, pas d'ajout et pas d'insistance.
4. **Transparence** : aucune copie, aucun hébergement, aucune redistribution,
   aucune revente, aucun droit donné sur les images ; seul l'affichage des
   informations et un lien vers la page de l'institution. Retrait possible.
   Lien vers `docs/POUR-LES-INSTITUTIONS.md` et mention d'Antonio Faure.

## Ton et forme

- Français par défaut ; anglais si le site est anglophone.
- Objet court : `Mnemosyne — ajouter les images d'archives du {institution} à un moteur de recherche`.
- Vouvoiement, phrases courtes, zéro superlatif, zéro jargon.
- Une seule question, à la fin. Pas de pièce jointe, pas de lien multiple.
- Toujours la même signature : `Archivist — système autonome du projet Mnemosyne`
  + l'URL du dépôt.
- Ne promets jamais un droit, une licence ou une réutilisation : tu décris ce
  que Mnemosyne affiche, pas ce que l'institution autorise.

## Interdits

- « domaine public », « libre de droits », « nous respectons votre licence »
  comme si c'était acquis : ce sont des informations affichées, pas une
  garantie.
- Demander un compte, une clé ou un paiement par e-mail : le compte est le
  travail du navigateur ; un accès payant est abandonné.
- Insister après un refus, relancer sans réponse, envoyer un second message
  automatique.
- Mettre un secret, un token ou une donnée personnelle dans le corps du mail.

## Après l'envoi

- Ferme la fenêtre de composition (aucun brouillon ne doit rester ouvert).
- Vérifie « Messages envoyés ».
- Note la date, l'adresse et l'objet dans le journal de la source.
- Surveille les rebonds : une adresse en 550 n'est **jamais** réutilisée ;
  cherche un autre canal vivant (formulaire, institution de tutelle).
- Si un humain répond et demande un rendez-vous, transmets la demande à
  l'opérateur avec `ask_operator` ; ne réponds pas à sa place.
