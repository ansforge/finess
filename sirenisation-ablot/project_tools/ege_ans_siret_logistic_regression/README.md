# Régression logistique EGE — proposition SIRET ANS

Cet outil contient une analyse exploratoire par régression logistique pondérée visant
à estimer, pour un EGE à rapprocher disposant d’une proposition ANS, la probabilité
que le SIRET proposé soit celui retenu après revue manuelle.

L’analyse sert notamment à étudier une acceptation automatique sélective des
propositions ANS à forte confiance. Elle ne constitue pas une règle de déploiement
validée.

Pour la méthodologie détaillée, les diagnostics et les résultats, voir
[`RESULTS_NOTE.md`](RESULTS_NOTE.md).

## Fichiers

Le répertoire contient notamment :

- `ege_ans_siret_logistic_regression.ipynb` : notebook principal de l’analyse ;
- `data/ege_reviewed_sample.xlsx` : échantillon EGE revu utilisé pour construire la
  variable cible et les prédicteurs ;
- `data/ege_strata_plan_review_analysis.xlsx` : plan et résultats d’analyse par strate,
  dont la feuille `analysis` fournit les tailles de population et les nombres d’EGE
  examinés utilisés pour les poids ;
- `RESULTS_NOTE.md` : note méthodologique et résultats de l’analyse.

## Exécution

Depuis la racine du dépôt, lancez Jupyter avec :

```powershell
uv run --locked jupyter lab
```

Ouvrez ensuite
`project_tools/ege_ans_siret_logistic_regression/ege_ans_siret_logistic_regression.ipynb`
et exécutez les cellules dans l’ordre.

Le notebook lit les deux fichiers du sous-répertoire `data/` indiqués ci-dessus. Il
calcule les poids, ajuste la régression logistique, construit les prédictions
*out-of-fold* par validation croisée groupée par EJ et évalue les performances du
score selon plusieurs seuils.

La dernière partie applique séparément la règle propre au contexte de l’étude :
**« ANS si le score dépasse le seuil, sinon Initial »**.

## Interprétation

Les performances du modèle et celles de la règle métier sont volontairement séparées
dans le notebook :

1. les performances du score sont évaluées parmi les EGE disposant d’une proposition
   ANS ;
2. la règle « ANS au-dessus du seuil, sinon Initial » est ensuite évaluée sur
   l’ensemble des EGE à rapprocher.

Les résultats sont exploratoires. En particulier, le modèle utilise la cohérence avec
le SIREN EJ corrigé lors de la revue ; cette information devra être remplacée par un
SIREN issu de la sirénisation EJ et les performances réévaluées avant tout usage en
production.
