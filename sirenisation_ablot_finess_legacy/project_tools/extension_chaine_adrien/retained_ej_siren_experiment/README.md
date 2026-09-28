# Expérience Adrien utilisant le SIREN retenu de l'EJ

## Objet

Cette expérience étudie l'utilisation du SIREN retenu pour l'EJ parente afin
d'élargir l'espace des SIRET candidats soumis à la chaîne Adrien pour les EGE.

Pour mesurer le potentiel de l'idée, le SIREN utilisé provenait des décisions humaines
de la revue EJ. Il ne s'agissait donc pas d'un SIREN produit automatiquement par le
workflow. L'expérience mesure un potentiel méthodologique et non les performances d'une
règle directement déployable en production.

## Déroulé de l'expérience

Le travail a suivi les étapes suivantes :

1. sélectionner les EGE dont l'EJ parente faisait partie des EJ examinées ;
2. associer à chaque EJ son `Siren_retenu` issu de la revue humaine ;
3. récupérer dans SIRENE les SIRET appartenant à ces SIREN et construire des candidats
   EGE/SIRET supplémentaires ;
4. soumettre ces candidats à la chaîne Adrien. Les deux sorties brutes conservées de
   juillet 2026 sont placées sous `data/raw/` ;
5. prétraiter ces sorties avec les fonctions maintenues de `source_preprocessing.adrien`
   afin de produire une base EGE/SIRET comparable à l'input Adrien canonique du projet ;
6. évaluer cette base expérimentale EGE/SIRET sur l'échantillon annoté de référence EGE
   de `project_tools/review_sample_benchmark/` ;
7. appliquer exactement la même évaluation à la base Adrien EGE/SIRET originale de juin
   2026 afin de disposer d'un point de comparaison.

La génération des deux fichiers bruts de juillet par la chaîne Adrien a été réalisée en
dehors de ce dépôt. Les anciens notebooks de préparation utilisaient des chemins
correspondant à des états antérieurs du projet et ne sont pas conservés comme code
maintenu. À partir des deux fichiers bruts conservés, le prétraitement et l'évaluation
sont en revanche reproductibles avec les scripts maintenus du dépôt.

## Prétraitement des sorties expérimentales

Depuis la racine du dépôt :

```powershell
uv run --locked python project_tools/extension_chaine_adrien/retained_ej_siren_experiment/preprocess.py
```

Pour l'évaluation EGE/SIRET, `preprocess.py` réutilise `prepare_adrien_candidates` et
`resolve_adrien_ege_duplicates` de `source_preprocessing.adrien`. La provenance
expérimentale `source_siret_prop_siren_ej_corrige` est déclarée comme source
supplémentaire lors de la résolution des doublons EGE/SIRET.

Le fichier utilisé pour l'évaluation est :

- `data/df_adrien_sirets_concordants_elargis_sirens_annotes_sample_only_2026_07_clean.parquet`.

## Évaluation sur les échantillons annotés de référence

Les évaluations utilisent `project_tools/review_sample_benchmark/evaluate_dataset.py`.
Après configuration du dataset et du mode en haut du script, la commande utilisée est :

```powershell
uv run --locked python project_tools/review_sample_benchmark/evaluate_dataset.py
```

Deux exécutions ont été réalisées :

| Évaluation | Mode | Dataset | Colonnes |
|---|---|---|---|
| Adrien original EGE | `EGE-SIRET` | `data/source/Adrien_Tortel/df_adrien_sirets_concordants_2026_06_clean.parquet` | `nofinesset`, `siret_prop` |
| Expérience SIREN retenu EGE | `EGE-SIRET` | `project_tools/extension_chaine_adrien/retained_ej_siren_experiment/data/df_adrien_sirets_concordants_elargis_sirens_annotes_sample_only_2026_07_clean.parquet` | `nofinesset`, `siret_prop` |

Les deux évaluations utilisent
`project_tools/review_sample_benchmark/output/ege_review_sample.parquet`. Les cas
`to_close` restent présents dans les tables de comparaison mais sont exclus des
métriques de couverture et de correction.

## Résultats

Les résultats obtenus sont les suivants :

| Dataset | Couverture brute | Couverture calée | Correct quand proposé — brut | Correct quand proposé — calé |
|---|---:|---:|---:|---:|
| Adrien original | 56,87 % | 70,44 % | 76,42 % | 92,45 % |
| Expérience SIREN retenu | 57,77 % | 71,39 % | 80,27 % | 92,23 % |

Par rapport à Adrien original, l'expérience augmente la couverture calée de
**0,94 point**, tandis que le taux calé de résultats corrects parmi les propositions
diminue de **0,22 point**.

Les écarts bruts sont plus favorables, mais les estimations calées utilisées pour le
reporting global montrent un gain de couverture limité, sans amélioration du taux de
résultats corrects lorsqu’une proposition est disponible. Une explication plausible
est que l’élargissement au SIREN retenu de l’EJ introduit des SIRET appartenant à la
bonne unité légale mais ne correspondant pas nécessairement au bon établissement
géographique. La validation lexicale d’Adrien peut alors retenir certains de ces
candidats sans améliorer la précision au niveau EGE. Ces résultats ne justifient pas,
à ce stade, l’intégration de cette extension au workflow opérationnel.

## Fichiers conservés

Les deux fichiers sous `data/raw/` sont les sorties expérimentales historiques reçues de
la chaîne Adrien. Le fichier `*_clean.parquet` directement sous `data/` est la base
EGE/SIRET prétraitée utilisée pour l'évaluation. Les fichiers sous `results/` sont les
comparaisons au niveau EGE et les synthèses produites par `review_sample_benchmark`
pour Adrien original et pour l'expérience.
