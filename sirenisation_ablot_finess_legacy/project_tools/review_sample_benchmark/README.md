# Review sample benchmark

Ce project tool permet de préparer et publier les échantillons annotés de référence EJ
et EGE de l'étude, construits à partir des décisions confirmées de revue et accompagnés
des poids utilisés dans le reporting global, puis d'évaluer une base externe
d’appariement sur ces échantillons sans dépendre du reste du workflow.

Il contient deux scripts distincts :

- `build_review_sample.py` construit les échantillons annotés de référence EJ et EGE ;
- `evaluate_dataset.py` évalue ensuite n'importe quelle base EJ-SIREN ou EGE-SIRET
  respectant les variables de configuration et les contrôles de base.

## 1. Construire les échantillons annotés de référence

Depuis la racine du dépôt :

```powershell
uv run --locked python project_tools/review_sample_benchmark/build_review_sample.py
```

Le script utilise les artefacts canoniques du projet :

- EJ : `ej_all_confirmed_decisions.parquet`, le cadre EJ stratifié et l'analyse
  de l'étape 5 EJ ;
- EGE : `ege_confirmed_decisions.parquet`, le pool EGE et l'analyse de l'étape 5 EGE.

Les sorties sont :

- `output/ej_review_sample.parquet` ;
- `output/ej_review_sample.xlsx` ;
- `output/ege_review_sample.parquet` ;
- `output/ege_review_sample.xlsx`.

Les fichiers Parquet et Excel contiennent exactement le même échantillon annoté de
référence. Le Parquet est destiné aux traitements programmatiques ; le classeur Excel
facilite la consultation et le partage.

Lors du partage d'un échantillon annoté de référence, joignez également
`REVIEW_SAMPLE_NOTE.md`. Cette note autonome décrit le contenu des fichiers, les poids,
les codes `Incertitude1` et les règles d'interprétation utiles à un destinataire qui ne
connaît pas le projet.

Chaque fichier contient une ligne par entité annotée avec :

- l'identifiant `EJ` ou `EGE` ;
- `Siren_retenu` ou `Siret_retenu` ;
- `Incertitude1` ;
- `stratum_id` ;
- `sampling_weight` ;
- `calibrated_weight` ;
- `to_close`.

`sampling_weight` est le poids de plan enregistré par l'étape 5. `calibrated_weight`
est le poids utilisé pour les estimations globales : il est recalé dans chaque strate
de façon que la somme des poids des entités examinées reproduise la population connue
de la strate. Pour les EJ, ce recalage est normalement neutre à l'arrondi près ; pour
les EGE, il conserve explicitement le calage appliqué au plan à deux degrés EJ→EGE.

Les décisions avec une incertitude négative valide (`-1`, `-2` ou `-12`) restent dans
l'échantillon et portent `to_close = True`. Elles sont conservées pour décrire
l'échantillon mais ne participent pas aux dénominateurs de performance
d’appariement.

Le script vérifie notamment l'unicité des décisions, l'unicité de la strate par
entité, la présence de poids positifs et l'identité de calage par strate.

## 2. Évaluer une base

La configuration se trouve en haut de `evaluate_dataset.py` :

```python
MODE = "EJ-SIREN"  # ou "EGE-SIRET"

DATASET_PATH = Path("path/to/dataset.parquet")
DATASET_NAME = "Dataset"
DATASET_ENTITY_COLUMN = "EJ"
DATASET_BUSINESS_COLUMN = "SIREN"
DATASET_SHEET_NAME = 0

REVIEW_SAMPLE_PATH = Path(__file__).resolve().parent / "output/ej_review_sample.parquet"
```

Le mode détermine les noms standard et le padding :

- `EJ-SIREN` : `EJ` sur 9 caractères et `SIREN` sur 9 caractères ;
- `EGE-SIRET` : `EGE` sur 9 caractères et `SIRET` sur 14 caractères.

La base évaluée peut être en Parquet, Excel `.xlsx` ou CSV. Plusieurs propositions
différentes pour une même entité sont autorisées. En revanche, un couple exact
entité–identifiant métier ne peut pas être dupliqué.

Exécution :

```powershell
uv run --locked python project_tools/review_sample_benchmark/evaluate_dataset.py
```

## Définition des métriques

Pour une entité à rapprocher :

- elle est **couverte** si la base évaluée contient au moins une proposition ;
- elle est **correcte quand proposée** si l'identifiant retenu manuellement figure
  parmi les propositions de la base.

Une annotation de référence sans identifiant retenu (`NA`) n'est pas considérée comme
une proposition correcte par simple absence dans la base : l'entité est alors non
couverte. Si la base propose un identifiant alors que l'annotation de référence ne
retient aucun identifiant, la proposition est incorrecte.

Les entités `to_close = True` restent visibles dans la comparaison mais sont exclues
des métriques de couverture et de correction.

## Sorties d'une évaluation

Pour un dataset nommé par exemple `Dataset`, en mode EJ-SIREN :

- `output/dataset_ej_siren_review_comparison.parquet` ;
- `output/dataset_ej_siren_performance_summary.xlsx`.

Aucun CSV ni JSON n'est produit.

La table de comparaison contient l’annotation de référence, les propositions de la
base, les indicateurs `covered` et `correct`, le statut `to_close` et les deux poids.

Le classeur de synthèse contient exactement les colonnes :

- `Metric` ;
- `Population count` ;
- `Proportion` ;
- `Denominator` ;
- `Denominator population`.

Il contient les lignes suivantes :

1. `EJs in review sample` / `EGEs in review sample` ;
2. `EJs to match` / `EGEs to match` ;
3. `EJs to close` / `EGEs to close` ;
4. `Coverage — raw` ;
5. `Coverage — calibrated` ;
6. `Correct when proposed — raw` ;
7. `Correct when proposed — calibrated`.

Les libellés utilisent `EJs` en mode `EJ-SIREN` et `EGEs` en mode `EGE-SIRET`.
Les lignes brutes comptent les entités de l'échantillon. Les lignes calibrées somment
`calibrated_weight` et représentent donc des estimations de population. La colonne
`Proportion` est enregistrée comme une proportion Excel et affichée au format
pourcentage avec deux décimales, par exemple `94,46%`. Les colonnes `Denominator` et
`Denominator population` rendent explicite le dénominateur de chaque proportion.
