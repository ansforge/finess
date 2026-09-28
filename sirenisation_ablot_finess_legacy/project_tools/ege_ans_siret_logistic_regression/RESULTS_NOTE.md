# Note de résultats — modèle de probabilité pour la proposition SIRET de l'ANS

Cette note présente la méthodologie, les diagnostics et les résultats de l’analyse. Pour l’exécution du notebook, voir [`README.md`](README.md).

## Objectif

Pour un EGE **à rapprocher** et pour lequel l'ANS propose un SIRET, j'estime la probabilité que ce SIRET soit celui retenu après revue manuelle.

L'objectif opérationnel est d'utiliser la proposition ANS uniquement lorsque son score est suffisamment élevé. Les autres EGE peuvent soit être envoyés en revue, soit conserver leur SIRET Initial. La seconde option permet d'évaluer une règle directement déployable de type **« ANS si le score dépasse le seuil, sinon Initial »**.

J'utilise une régression logistique pondérée car l'échantillon n'est pas très grand et les principaux prédicteurs sont directement interprétables.

## Échantillon et variable cible

L'unité statistique est l'EGE.

- 916 EGE examinés
- 21 EGE à fermer (`Incertitude1 = -1`, `-2` ou `-12`)
- 895 EGE à rapprocher
- 687 EGE à rapprocher avec une proposition ANS

Le modèle est donc estimé uniquement sur les EGE pour lesquels l'ANS fournit une proposition. Les 687 EGE ne représentent pas toute la population à rapprocher : après pondération, la **couverture ANS est de 87,6 %**.

La variable cible est définie par :

`Y = 1` si la proposition ANS est égale au SIRET retenu, sinon `Y = 0`.

Un SIRET retenu manquant compte donc comme `Y = 0`.

Le poids EGE calibré utilisé dans l'analyse est :

`Population size / EGEs examined`

au sein de chaque strate d'échantillonnage.

## Choix des prédicteurs

Je n'ai pas commencé avec toutes les variables disponibles. L'échantillon de modélisation contient 687 EGE, les poids sont inégaux et plusieurs indicateurs contiennent des informations proches. J'ai donc retenu un petit nombre de variables disponibles **avant la revue EGE** et faciles à interpréter, puis j'ai vérifié si l'ajout d'une variable supplémentaire améliorait réellement les performances hors-échantillon.

Le modèle final utilise :

- `is_initial_siret` ;
- la cohérence entre le SIREN du SIRET proposé et le SIREN EJ corrigé ;
- `statut_EGE_ANS` ;
- `datasets_consistency_EGE`.

## Effet des prédicteurs

Les *odds ratios* sont ajustés sur les autres variables du modèle.

| Prédicteur | Odds ratio | Interprétation |
|---|---:|---|
| SIREN coherent = yes | 62,89 | De loin le prédicteur positif le plus fort |
| ANS status = `VALIDE_FORT` | 3,26 | Effet positif net |
| Datasets = total consistency | 2,32 | L'accord entre les jeux de données augmente la confiance |
| Initial SIRET = yes | 1,47 | Effet positif plus modéré |
| Datasets = partial consistency | ≈ 0,01 | Association fortement négative |
| SIREN coherence = missing | 7,10 | Effet positif, mais estimé sur seulement 9 EGE |

La cohérence du SIREN est donc l'information la plus discriminante dans ce modèle. Les estimations pour `partial consistency` et pour les valeurs manquantes de cohérence SIREN doivent être interprétées avec plus de prudence, car ces catégories sont peu représentées.

`datasets_consistency_EGE` est également utile car cette variable porte une information sur la proposition d'Adrien.

### Limite de transposition en production

La cohérence du SIREN est calculée ici avec le **SIREN EJ corrigé issu de la revue EJ**. En production, ce SIREN ne serait pas disponible : il faudrait utiliser le SIREN obtenu à l'issue de la sirénisation EJ.

Si cette sirénisation est de bonne qualité, l'information devrait rester proche, mais les performances présentées ici sont probablement un peu optimistes. Elles devront être réévaluées avec un SIREN EJ produit dans des conditions proches de la production avant d'utiliser le modèle comme règle de déploiement.

## Pourquoi une validation croisée ?

Avec 687 EGE, un simple découpage apprentissage/test ferait perdre une part importante de l'échantillon pour l'ajustement et les résultats pourraient dépendre fortement d'un seul découpage aléatoire.

J'utilise donc une validation croisée à 5 plis. Chaque EGE reçoit une prédiction *out-of-fold*, c'est-à-dire issue d'un modèle ajusté sans cet EGE. Ces prédictions servent à calculer le score de Brier, l'AUC, la calibration et les performances selon les seuils.

Les plis sont groupés par EJ afin que des EGE d'une même EJ ne se retrouvent pas à la fois dans l'échantillon d'apprentissage et dans l'échantillon de validation.

## Pourquoi ne pas garder `coherence_EGE_ANS` ?

Je l'ai testée comme prédicteur supplémentaire.

| Modèle | Score de Brier pondéré | AUC pondérée |
|---|---:|---:|
| Modèle final | 0,06084 | 0,91009 |
| + `coherence_EGE_ANS` | 0,06037 | 0,90849 |

Le score de Brier s'améliore de moins de 0,001 et l'AUC diminue légèrement. J'ai donc gardé le modèle plus simple.

## Résultat opérationnel

Le logit ne couvre pas à lui seul tous les EGE à rapprocher : il ne produit un score que lorsqu'une proposition ANS existe. Le tableau ci-dessous distingue donc la part des propositions ANS acceptées, la part de l'ensemble de la population effectivement traitée avec ANS, et le résultat de la règle **« ANS si le score dépasse le seuil, sinon Initial »**.

| Accepter si score ≥ | Part des EGE avec ANS acceptée | Part de tous les EGE traitée par ANS | Correct parmi les ANS acceptés | Correct — logit sinon Initial | Gain vs Initial |
|---:|---:|---:|---:|---:|---:|
| 0,50 | 83,6 % | 73,2 % | 97,0 % | 82,5 % | +16,4 pts |
| 0,80 | 83,2 % | 72,9 % | 97,2 % | 82,5 % | +16,5 pts |
| **0,90** | **82,0 %** | **71,9 %** | **98,4 %** | **82,4 %** | **+16,4 pts** |
| 0,95 | 79,0 % | 69,2 % | 98,3 % | 79,9 % | +13,9 pts |
| 0,97 | 66,5 % | 58,3 % | 98,4 % | 76,6 % | +10,6 pts |

Avec un seuil de **0,90**, 82,0 % des EGE disposant d'une proposition ANS dépassent le seuil. Comme l'ANS couvre 87,6 % des EGE à rapprocher, cela représente **71,9 % de l'ensemble des EGE à rapprocher** traités avec la proposition ANS. Parmi ces propositions acceptées, **98,4 %** sont correctes.

Si l'on conserve Initial pour les EGE sans proposition ANS et pour ceux dont le score est inférieur à 0,90, la règle atteint un taux estimé de résultats corrects de **82,4 %** sur l'ensemble des EGE à rapprocher.

À titre de comparaison :

- **Initial seul : 66,0 %** de résultats corrects ;
- **ANS sinon Initial, sans sélection par le logit : 80,3 %** ;
- **ANS si score ≥ 0,90, sinon Initial : 82,4 %**.

Le seuil de 0,90 apporte donc environ **+16,4 points** par rapport à Initial et **+2,1 points** par rapport à l'utilisation systématique de la proposition ANS lorsqu'elle existe.

Les propositions ANS rejetées ne sont pas nécessairement fausses : à 0,90, environ **26,2 %** d'entre elles sont en réalité correctes. Le modèle sert donc surtout à sélectionner un groupe de propositions à très forte confiance.

## Qualité globale du modèle

- Score de Brier pondéré : **0,061**
- Score de Brier d'un modèle à probabilité constante : **0,125**
- AUC pondérée : **0,910**
- Taux de réussite observé pondéré parmi les EGE avec proposition ANS : **0,854**
- Probabilité prédite moyenne : **0,848**

Les prédictions utilisées pour les résultats de seuil sont *out-of-fold*, ce qui évite d'évaluer chaque EGE avec un modèle ajusté sur ce même EGE. Il s'agit toutefois toujours d'une validation interne sur l'échantillon de revue. Pour un usage opérationnel, il faudrait en particulier réévaluer le modèle avec un SIREN EJ issu de la sirénisation plutôt qu'avec le SIREN EJ corrigé par la revue.
