# Compare reconciliation datasets

Cet outil compare directement deux bases alternatives d’appariement, sans dépendre
de FINESS, SIRENE ni des étapes numérotées du workflow. Chaque base doit fournir un
identifiant d'entité et un identifiant métier proposé. Plusieurs propositions par
entité sont autorisées.

## Modes

Deux modes sont disponibles :

- `EJ-SIREN` : sortie entité `EJ`, padding EJ sur 9 caractères et SIREN sur 9 caractères ;
- `EGE-SIRET` : sortie entité `EGE`, padding EGE sur 9 caractères et SIRET sur 14 caractères.

Le mode détermine également les préfixes de sortie : `ej_siren_*` ou `ege_siret_*`.

## Configuration

Les variables principales se trouvent en haut de
`compare_reconciliation_datasets.py` :

```python
MODE = "EJ-SIREN"

DATASET1_PATH = Path("path/to/dataset1.parquet")
DATASET1_NAME = "Dataset 1"
DATASET1_ENTITY_COLUMN = "EJ"
DATASET1_BUSINESS_COLUMN = "SIREN"
DATASET1_SHEET_NAME = 0

DATASET2_PATH = Path("path/to/dataset2.parquet")
DATASET2_NAME = "Dataset 2"
DATASET2_ENTITY_COLUMN = "EJ"
DATASET2_BUSINESS_COLUMN = "SIREN"
DATASET2_SHEET_NAME = 0
```

Les entrées peuvent être des fichiers Parquet, Excel `.xlsx` ou CSV. Pour Excel, la lecture
est faite avec `dtype="string"` afin de préserver les identifiants et leurs zéros
initiaux.

Une fois ces variables renseignées, exécutez depuis la racine du dépôt :

```powershell
uv run --locked python project_tools/compare_reconciliation_datasets/compare_reconciliation_datasets.py
```

## Contrôles

Le script s'arrête si :

- un fichier ou une colonne configurée manque ;
- un identifiant d'entité ou métier est vide ;
- un identifiant n'a pas la longueur attendue après normalisation et padding ;
- un même couple entité–identifiant métier est dupliqué dans une base ;
- les deux bases portent le même nom.

La présence de plusieurs identifiants métier différents pour une même entité est
valide : ils constituent l'ensemble des propositions de cette base.

## Univers et cohérence

L'univers de couverture est l'union des entités présentes dans les deux bases.
`source_dataset`, placée immédiatement après la colonne `EJ` ou `EGE`, indique si
l'entité provient de la première base, de la seconde, ou des deux. Lorsque l'entité
est présente dans les deux, la valeur contient les deux noms configurés.

La cohérence n'est évaluée que pour les entités présentes dans les deux bases :

- `Total consistency` : les deux ensembles de propositions sont identiques ;
- `Partial consistency` : les deux ensembles ont au moins une proposition commune ;
- `Total inconsistency` : les ensembles n'ont aucune proposition commune.

Une entité absente d'une des deux bases est donc un écart de couverture et non une
incohérence. Son `consistency_type` est vide.

## Sorties

En mode `EJ-SIREN` :

- `output/ej_siren_consistency.parquet` ;
- `output/ej_siren_consistency.xlsx` ;
- `output/ej_siren_main_statistics.json`.

En mode `EGE-SIRET` :

- `output/ege_siret_consistency.parquet` ;
- `output/ege_siret_consistency.xlsx` ;
- `output/ege_siret_main_statistics.json`.

La table de cohérence contient, dans cet ordre :

1. `EJ` ou `EGE` ;
2. `source_dataset` ;
3. `dataset1__proposals` ;
4. `dataset1__proposal_count` ;
5. `dataset2__proposals` ;
6. `dataset2__proposal_count` ;
7. `consistency_type`.

Le JSON sépare les statistiques de couverture (`general`) des statistiques de
cohérence calculées uniquement sur les entités présentes dans les deux bases
(`entities_in_both_datasets`).
