# Vision DeepSeek — chaîne complète, patch build, sonde

> Le problème tel qu'il était perçu (« browser-harness coupe la vision pour
> deepseek ») était doublement faux. Voici l'état réel, le fix, et comment
> détecter une régression.

## 1. Le diagnostic réel

**Le gate de vision vit dans browser-use, pas dans browser-harness.**
- `browser-harness` (0.1.13) est un exécuteur CDP **LLM-free** : il ne voit
  aucun modèle, zéro mention de "deepseek" dans son code.
- Le check est dans **browser-use** (`agent/service.py`) :

  ```python
  # Handle users trying to use use_vision=True with DeepSeek models
  if 'deepseek' in self.llm.model.lower():
      self.logger.warning('⚠️ DeepSeek models do not support use_vision=True yet...')
      self.settings.use_vision = False
  ```

  Heuristique de nom entrée via PR browser-use #1399 (avril 2025), écrite pour
  l'ère `deepseek-chat`/`deepseek-reasoner` (text-only). deepseek-v4.1-flash a
  la vision native — l'heuristique punit un modèle capable par son nom, sans
  échappatoire (elle écrase un `use_vision=True` explicite).

**Mais surtout : ce gate était doublement dormant.** Le bi-agent ne construit
JAMAIS d'Agent browser-use (stirrup crée une `BrowserSession`, pas un Agent).
Et plus fondamental encore : **l'agent navigateur ne recevait aucune image** —
stirrup sait faire passer des captures d'écran au modèle
(`tools/browser_use.py:555-571`, `ImageContentBlock`), mais rien n'était
branché. La vision s'était **perdue dans la migration bi-agent**, pas coupée
par une condition.

## 2. Le rebranchement (le vrai fix)

`browser_exec` (browser_agent.py) attache maintenant la capture de page au
résultat du tool `browser` :

- la capture est produite par le harness (`capture_screenshot('shot.png',
  max_dim=1800)` — le PNG atterrit dans le helpers dir, cwd du harness) ;
- `force_vision=true` (config `agents.force_vision`, maintenant réellement lu) :
  chaque pas navigateur arrive avec SA capture. Si le pas n'en a pas produit,
  un 2e run harness **passif** le fait (`Page.captureScreenshot` ne touche pas
  la page) ;
- le PNG est **consommé** (`unlink`) après lecture : jamais ré-attaché au pas
  suivant ;
- le transport : `ToolResult(content=[texte, ImageContentBlock(data=png)])` —
  le même mécanisme que `screenshot_executor` de stirrup. Un seul patron CDP
  (browser-harness), pas de second client.

## 3. Le patch build (neutraliser l'heuristique browser-use)

Le Dockerfile remplace, dans browser-use 0.11.13 installé dans l'image :

```
if 'deepseek' in self.llm.model.lower():   →   if False and 'deepseek' in ...
```

- **idempotent et prudent** : si le pattern disparaît d'upstream, le patch est
  un no-op loggé (le build ne casse pas) ;
- **prévisible** : versions figées (`stirrup[browser]==0.2.0`,
  `browser-use==0.11.13`, `browser-harness==0.1.13`) — un drift de version ne
  peut pas appliquer un patch à moitié en silence.

## 4. Les filets anti-régression

1. **Sonde batterie `vision`** (`scripts/battery.py:scenario_vision_wiring`) :
   une page `file://` contient un mot visible **uniquement dans le pixel**
   (jamais dans le DOM). La sonde navigue, capture, et vérifie que le PNG est
   attachable en `ImageContentBlock`. Si une future version de browser-use ou
   stirrup recoupe la vision, la sonde échoue au lieu de rendre l'agent aveugle
   en silence.
2. **E2E réel** : une mission au navigateur (« lis le mot dans l'image ») — si
   l'agent lit le mot que `read_page` ne peut pas voir, la chaîne complète
   (harness → PNG → ImageContentBlock → deepseek vision) est prouvée.

## 5. État upstream (browser-use, pas browser-harness)

- Commentaire posté : browser-use #4327
  (https://github.com/browser-use/browser-use/issues/4327#issuecomment-5957459809)
  — datapoint deepseek-v4.1-flash (vision native), demande d'un traitement par
  capacité ou d'un échappatoire explicite, rappel du design initial
  `use_vision: bool | None` de la PR #1393.
- Pas d'engagement mainteneur connu au moment du commentaire.

## 6. Bug du harness découvert au passage

**browser-harness 0.1.13 perd son attache CDP après `goto_url` dans le MÊME
run** : `goto_url(...); capture_screenshot(...)` échoue avec
`Not attached to an active page` (reproduit en file:// ET en https://).
Chaque run du harness se réattache au démarrage, donc :
- le wiring mnemosyne est **épargné** (la capture force_vision est un 2e run
  séparé, c'est même pourquoi il marche) ;
- un agent qui écrit navigation+capture dans un même snippet recevra cette
  erreur — les consignes peuvent séparer les deux, ou le harness devra
  réattacher après navigation (à signaler upstream).
