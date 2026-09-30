# Roadmap — benchmark « segment de transcription → image attendue »

## Idée

(Plus tard, pas maintenant.) Transcrire l'ensemble des vidéos de *Le Contremaitre*,
puis associer à **chaque segment** de transcription **ce qu'il faudrait afficher à
l'écran** (l'image d'archive attendue). Ce jeu de données sert à :

1. **benchmarker** les APIs déjà connectées : sauraient-elles fournir l'image
   attendue pour ce segment ?
2. **piloter la recherche d'accès** : chaque échec devient une demande concrète
   (« il manque des photos de X chez Y ») → discovery + onboarding + outreach.

Boucle : `benchmark → trou identifié → obtenir l'accès → re-benchmark` (progrès
mesurable).

## Pourquoi c'est pertinent

- Crée un **jeu d'évaluation** (ground truth) — sans lui, « ça retourne des
  résultats » ≠ « c'est pertinent ». C'est le maillon qui manque pour piloter par
  la mesure.
- Cible le vrai goulot : **l'accès**, pas la recherche. Les échecs priorisent où
  chercher de nouveaux fournisseurs.
- Micro-sujets historiques concrets = stress-test idéal (cf. les limites déjà
  observées dans `youtube-shorts-pipeline/docs/PROBLEM-IMAGES.md`).

## Points de méthode (à faire bien)

- **La « bonne » image n'est pas unique** : un segment peut admettre 0..N images
  valides. → Rubrique (sujet, époque, média, pas de junk) + `recall@k` plutôt
  qu'un match exact.
- **L'association segment → image** produit en réalité une **requête/rubrique**,
  pas une image canonique. Le ground truth est un ensemble acceptable.
- **Éviter la circularité** : ne pas utiliser le même modèle pour générer la
  requête ET juger. Séparer générateur / juge (ou spot-check humain).
- **Droits** : transcrire ses propres vidéos OK ; vérifier si le contenu est
  d'autrui.
- **Coût** : transcription + briefs par segment + retrieval + jugement = lourd →
  commencer par un **sous-ensemble** (10-20 vidéos), itérer la rubrique.

## Où le faire vivre

Comme **consommateur externe de l'API mnemosyne** (dossier `benchmarks/` ou projet
voisin), pour que l'évaluation reste **indépendante** des internes du pipeline.

## Premières étapes

1. Transcriptions (sous-ensemble) + découpage en segments.
2. Rubrique d'illustration + génération de la requête par segment.
3. Retrieval via l'API mnemosyne + jugement (modèle distinct).
4. Rapport : couverture par source, trous prioritaires.
