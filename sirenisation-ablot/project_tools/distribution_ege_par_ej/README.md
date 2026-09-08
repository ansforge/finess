# Distribution du nombre d’EGE par EJ

Cet outil décrit la distribution des entités juridiques (EJ) du périmètre FINESS
étudié selon leur secteur et selon le nombre d’établissements géographiques (EGE) qui
leur sont rattachés. Il compare la population étudiée à l’échantillon EJ effectivement
examiné, avant et après prise en compte des poids d’échantillonnage.

## Ensembles représentés

Les mêmes graphiques sont produits pour trois ensembles :

- **population EJ étudiée**, en bleu ;
- **échantillon EJ examiné brut**, en orange soutenu ;
- **échantillon EJ examiné pondéré**, en orange clair.

L’échantillon pondéré contient les mêmes EJ que l’échantillon brut. Chaque EJ contribue
alors aux agrégats selon le `Sampling weight` de sa strate.

## Inputs

| Usage | Fichier |
|---|---|
| EGE FINESS | `data/source/finess_etablissements/EtablissementsGeolocalises_2026_05_04.parquet` |
| Périmètre EJ étudié, secteur et strate | `results/02_build_strata_plan/ej/ej_siren_proposals_stratified.parquet` |
| EJ effectivement examinées | `results/04_merge_reviews/ej/ej_all_confirmed_decisions.parquet` |
| Poids d’échantillonnage par strate | `results/05_analyze_reviews/ej/ej_strata_plan_review_analysis.xlsx` |

`ej_siren_proposals_stratified.parquet` définit le périmètre EJ représenté. Pour chaque
EJ, le script utilise `secteur_EJ` et `stratum_id`. Lorsqu’une EJ apparaît sur plusieurs
lignes de proposition, le secteur et la strate doivent être identiques sur toutes ses
lignes.

Le nombre d’EGE par EJ est calculé à partir du fichier FINESS EGE en comptant chaque
identifiant EGE une seule fois. Seuls les EGE rattachés à une EJ du périmètre étudié
sont pris en compte. Une EJ du périmètre sans EGE est considérée comme une incohérence
des inputs.

`ej_all_confirmed_decisions.parquet` définit l’échantillon EJ examiné. Le
`Sampling weight` associé à chaque EJ est récupéré dans
`ej_strata_plan_review_analysis.xlsx` à partir de son `stratum_id`. Le poids utilisé est
celui produit par l’analyse EJ de l'étape 5 ; il n’est pas recalculé par cet outil.

## Graphiques produits

Pour chacun des trois ensembles, le script produit :

- un pie chart de la distribution des EJ par secteur ;
- un bar chart de la distribution du nombre d’EGE par EJ, tous secteurs confondus ;
- un bar chart de la distribution du nombre d’EGE par EJ pour chaque secteur.

Les nombres d’EGE sont regroupés dans les catégories `0`, `1`, ..., `19`, `20+`. Les
pourcentages sont affichés horizontalement au-dessus des barres. Les effectifs sont
inclinés afin de conserver des barres étroites et lisibles.

Dans les graphiques non pondérés, `n=` indique le nombre brut d’EJ. Dans les graphiques
pondérés, `N≈` indique la somme des `Sampling weight` dans la catégorie représentée,
arrondie pour l’affichage.

Les fichiers PNG sont écrits dans `output/` à côté du script. Leurs noms commencent
par `population_`, `echantillon_brut_` ou `echantillon_pondere_` selon l’ensemble
représenté.

## Exécution

Depuis la racine du dépôt :

```powershell
uv run --locked python project_tools/distribution_ege_par_ej/distribution_ege_par_ej.py
```

Les options `--project-root` et `--output-dir` permettent respectivement de préciser la
racine du dépôt et le répertoire de sortie.
