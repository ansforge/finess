# Synthèse graphique des performances d’appariement

Cet outil produit un graphique de synthèse pour les EJ et un pour les EGE à partir des
estimations globales calculées par l'étape 5. Il compare la qualité et la couverture des
propositions Initial, ANS et Adrien ainsi que les règles déployables avec fallback vers
Initial.

## Inputs

| Niveau | Fichier |
|---|---|
| EJ | `results/05_analyze_reviews/ej/ej_global_review_summary.xlsx` |
| EGE | `results/05_analyze_reviews/ege/ege_global_review_summary.xlsx` |

Le script lit la feuille `global_review_summary`. Les effectifs utilisés sont les
`Population count` déjà produits par l'étape 5. Pour les métriques issues de la revue,
il s'agit donc des estimations pondérées et calées du workflow ; le project tool ne
recalcule ni les poids ni les indicateurs de performance.

## Population représentée

Chaque barre représente la population estimée des entités **à rapprocher**. Les entités
classées **à fermer** lors de la revue ne font pas partie de cette population, conformément
aux dénominateurs utilisés par l'étape 5 pour mesurer la performance des méthodes de
proposition.

Toutes les barres ont donc la même longueur totale et sont décomposées en trois groupes :

- **estimés corrects** ;
- **estimés incorrects** ;
- **non couverts**.

Pour Initial et pour les règles avec fallback, la part non couverte est nulle. Initial
est considéré comme une règle applicable à toutes les entités à rapprocher, y compris
lorsque sa valeur est `NA` ; un `NA` Initial est correct si la décision humaine retenue
est également `NA`.

Pour ANS et Adrien, les entités sans proposition de la méthode sont classées dans
**non couverts**. Les entités couvertes sont séparées entre propositions correctes et
incorrectes.

## Barres représentées

Le graphique contient sept barres :

1. `Initial` ;
2. `ANS` ;
3. `ANS + Initial fallback` ;
4. `Adrien` ;
5. `Adrien + Initial fallback` ;
6. `Adrien — only proposal` ;
7. `Adrien — only proposal + Initial fallback`.

Les règles `+ Initial fallback` utilisent la méthode alternative lorsqu'elle est
disponible et conservent Initial sinon. La règle `Adrien — only proposal` utilise la
condition `1 proposition` déjà définie et évaluée par l'étape 5.

Chaque segment affiche sa part de la population à rapprocher et, lorsque l'espace le
permet, l'effectif estimé `N≈` correspondant.

## Outputs

Les PNG sont écrits par défaut dans `output/` à côté du script :

- `ej_review_performance_summary.png` ;
- `ege_review_performance_summary.png`.

## Exécution

Depuis la racine du dépôt :

```powershell
uv run --locked python project_tools/review_performance_summary/review_performance_summary.py
```

Les options `--project-root` et `--output-dir` permettent respectivement de préciser la
racine du dépôt et le répertoire de sortie.
