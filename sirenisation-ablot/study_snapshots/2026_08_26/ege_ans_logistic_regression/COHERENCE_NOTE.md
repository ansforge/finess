# Compléments sur la cohérence interne SIREN

## Résultats dans l'échantillon EGE annoté

Parmi les EGE disposant d'une proposition ANS :

* cohérence SIREN = `True` : **394 propositions, dont 374 correctes → 94,9 % non pondéré / 93,2 % pondéré** ;
* cohérence SIREN = `False` : **284 propositions, dont 63 correctes → 22,2 % non pondéré / 27,9 % pondéré** ;
* cohérence SIREN manquante (SIREN annoté NA) : **9 propositions, dont 4 correctes → 44,4 % non pondéré / 75,2 % pondéré**.

Le résultat pondéré pour les valeurs manquantes doit être interprété avec prudence compte tenu du très faible nombre d'observations (`n = 9`).

Une proposition incohérente avec le SIREN EJ annoté peut donc correspondre au bon SIRET d'après l'annotation.

Cela peut notamment être dû à des incohérences architecturales FINESS/SIRENE à résoudre, ainsi qu'à certaines incertitudes dans l'annotation : une incertitude est signalée dans environ 21 % des cas et peu de ces cas ont pu être retraités.

## Règle limitée aux propositions cohérentes avec le SIREN EJ

Si la règle retenue est de ne basculer que les propositions présentant une cohérence SIREN avec l'EJ, le logit peut être conservé tel quel, mais il est alors appliqué uniquement aux propositions qui passent ce filtre de cohérence.

**Note :** les estimations présentées ci-dessous ont été calculées dans le cadre de cette analyse complémentaire et ne sont pas, à ce stade, reproduites par le code du dépôt.

Les estimations pondérées d'une telle règle sont les suivantes.

### Méthode globale (pas de logit)

* ANS (Coh. SIREN) coverage : **76,8 %**
* ANS (Coh. SIREN) correct when proposed : **93,2 %**
* ANS (Coh. SIREN) + Initial fallback correct : **82,6 %**

### Méthode logit au seuil 0,90

* ANS logit (Coh. SIREN) coverage : **71,7 %**
* ANS logit (Coh. SIREN) correct when proposed : **98,4 %**
* ANS logit (Coh. SIREN) + Initial fallback correct : **82,4 %**

Le logit est à priori surtout utile pour limiter les erreurs introduites, même si l'impact par rapport à la méthode Initial n'a pas été calculé ici.

## Limite de transposition en production

Ces résultats sont probablement un peu optimistes car la cohérence est ici calculée avec le **SIREN EJ annoté** et non avec le SIREN effectivement retenu en production.

Les bons résultats obtenus sur la phase EJ laissent toutefois penser que l'écart devrait rester limité.
