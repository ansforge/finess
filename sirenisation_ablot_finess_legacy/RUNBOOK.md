# Workflow et guide de maintenance

Ce document est la référence opérationnelle pour exécuter, inspecter, modifier et
tester le projet. `project_config.py` centralise les chemins utilisés par les jobs ;
`docs/METHODOLOGY.md` définit l’interprétation statistique.

Les commandes de démarrage du projet sont indiquées dans `README.md`. Les commandes
ci-dessous sont à exécuter depuis la racine du dépôt.

## Profils de données

`SIRENISATION_DATA_PROFILE` sélectionne des chemins, pas des règles métier.
Définissez-la avant que Python ou Jupyter n’importe `project_config`.

### Profil de développement

```powershell
$env:SIRENISATION_DATA_PROFILE = "dev"
uv run --locked python -c "import project_config; print(project_config.PATHS)"
uv run --locked jupyter lab
```

### Profil complet

```powershell
$env:SIRENISATION_DATA_PROFILE = "full"
uv run --locked python -c "import project_config; print(project_config.PATHS)"
uv run --locked jupyter lab
```

`full` est la valeur par défaut si la variable n’est pas définie. Dans un terminal
réutilisé, définissez-la explicitement au lieu de supposer que la valeur précédente
est toujours active.

| Usage | `full` | `dev` |
|---|---|---|
| données sources/préparées | `data/source/` | `dev/data/source/` |
| paramétrage et saisies d’étude | `data/study_inputs/` | `dev/data/study_inputs/` |
| fichiers terminés des évaluateurs | `data/reviewed/` | `dev/data/reviewed/` |
| outputs générés | `results/` | `dev/results/` |

Le profil `full` utilise les données complètes et sert à exécuter l’étude sur son
périmètre complet. Le profil `dev` utilise un jeu compact et relationnellement
cohérent pour le développement et les tests. Le contenu du profil `dev` est versionné
afin de disposer, après clonage du dépôt, d’un jeu de développement directement
utilisable. Ses outputs peuvent être régénérés en exécutant le workflow avec ce profil.

Les remplacements explicites facultatifs sont `SIRENISATION_DATA_ROOT`,
`SIRENISATION_STUDY_INPUTS_ROOT`, `SIRENISATION_REVIEWED_ROOT` et
`SIRENISATION_RESULTS_ROOT`.

En profil `full`, les données sources locales sont placées sous
`data/source/finess_entites_juridiques/raw/`, `data/source/finess_etablissements/raw/`,
`data/source/ANS/raw/`, `data/source/Adrien_Tortel/raw/`,
`data/source/sirene_unites_legales/` et `data/source/sirene_etablissements/`. Les
référentiels sous `data/source/NAF/` et `data/source/statut_juridique/` sont des
versions préparées et versionnées pour leur utilisation par le workflow.

`data/study_inputs/` contient les fichiers de paramétrage et de saisie propres à
l’étude, notamment les tailles d’échantillon et les correspondances
strates-évaluateurs ; `data/reviewed/` contient les classeurs complétés par les
évaluateurs.

En profil `dev`, les données sont construites sous `dev/data/source/`, tandis que
`dev/data/study_inputs/` et `dev/data/reviewed/` remplissent les mêmes
rôles pour l’exécution de développement.

## Dépendances et lockfile

Les dépendances du projet sont gérées avec `uv`. Utilisez `uv add` pour ajouter une
dépendance ; le fichier `pyproject.toml`, le lockfile `uv.lock` et l’environnement du
projet sont alors mis à jour automatiquement.

```powershell
uv add <package>
```

La cohérence du lockfile peut être vérifiée explicitement avec :

```powershell
uv lock --check
```

Le projet utilise également Ruff pour le linting. La conformité du code peut être
vérifiée avec :

```powershell
uv run --locked ruff check .
```

## Prétraitement

Les six inputs préparés maintenus sont construits par des fonctions dans
`source_preprocessing/`. Chaque famille lit uniquement ses propres snapshots bruts et
écrit les produits préparés correspondants sous `data/source/`.

Les familles peuvent être exécutées indépendamment :

```powershell
uv run --locked python -m source_preprocessing.jobs --family finess
uv run --locked python -m source_preprocessing.jobs --family ans
uv run --locked python -m source_preprocessing.jobs --family adrien
```

`--family all` exécute les trois familles :

```powershell
uv run --locked python -m source_preprocessing.jobs --family all
```

Par défaut, les produits préparés sont écrits sous la racine du projet. L’option
`--output-root` permet de définir une racine de sortie différente si besoin.

Les produits préparés par le workflow sont :

| Produit | Chemin préparé |
|---|---|
| FINESS EJ | `data/source/finess_entites_juridiques/EntitesJuridiques_2026_05_04.parquet` |
| FINESS EGE | `data/source/finess_etablissements/EtablissementsGeolocalises_2026_05_04.parquet` |
| ANS EJ | `data/source/ANS/df_ans_ej_valides.parquet` |
| ANS EGE | `data/source/ANS/df_ans_ege_valides.parquet` |
| Adrien EJ | `data/source/Adrien_Tortel/df_adrien_sirets_concordants_2026_06_sirenise.parquet` |
| Adrien EGE | `data/source/Adrien_Tortel/df_adrien_sirets_concordants_2026_06_clean.parquet` |

La vague ANS EJ de juillet remplace celle de juin au lieu de s’y concaténer ; les EGE
utilisent juillet. Adrien utilise les candidats nommés de juin. Le stock
d’établissements SIRENE de juillet constitue une actualisation intentionnelle du
statut administratif.

### Chargement des données SIRENE

Les stocks SIRENE complets ne sont pas chargés intégralement en mémoire par les jobs
de comparaison. Lorsque seuls certains SIREN ou SIRET sont nécessaires, les jobs
déterminent d’abord les identifiants utiles puis lisent uniquement les lignes et les
colonnes correspondantes. Pour les fichiers Parquet, le filtrage est appliqué
directement lors de la lecture. Cette organisation permet d’exécuter le profil `full`
sans matérialiser inutilement l’ensemble des stocks SIRENE dans pandas.

## Ordre d’exécution opérationnel

Le workflow comporte plusieurs points d’intervention manuelle, notamment pour la
préparation du plan de revue et pour la revue elle-même. Les décisions EJ doivent
être consolidées avant la construction du pool EGE et de la revue EGE.

Exécutez les scripts applicables dans cet ordre :

1. **Étape 00 — Périmètre FINESS**

   - `00_prepare_data/finess/ej/01_filter_out_EJ_without_EGE_job.py`
     restreint le périmètre EJ aux entités juridiques disposant d’au moins un EGE
     rattaché. Les EJ sans EGE sont conservées séparément afin d’identifier explicitement
     ce périmètre exclu dans la suite du workflow.

     Le job produit :
     - `results/00_prepare_data/finess/ej/EntitesJuridiques_2026_05_04_hors_EJ_sans_EGE.parquet` ;
     - `results/00_prepare_data/finess/ej/ej_excluded_without_ege.parquet`.

   - `00_prepare_data/finess/ej/02_add_categ_ehpad_hopitaux_job.py`
     enrichit les EJ retenues avec l’indicateur `ehpad_hopitaux`, qui identifie les EJ
     ayant au moins un établissement enfant appartenant aux catégories hôpital ou EHPAD,
     et produit :
     - `results/00_prepare_data/finess/ej/EntitesJuridiques_2026_05_04_prepared.parquet`.

   - `00_prepare_data/finess/ege/01_filter_out_EGE_without_EJ_job.py`
     restreint le périmètre EGE aux établissements dont l’EJ parente existe dans le
     référentiel FINESS EJ et produit :
     - `results/00_prepare_data/finess/ege/EtablissementsGeolocalises_2026_05_04_clean.parquet`.

   Les deux jobs de filtrage mettent à jour
   `results/00_prepare_data/filtering_summary.csv`, qui récapitule pour les niveaux EJ et
   EGE les nombres d’entités avant filtrage, exclues et retenues.

2. **Étape 01 EJ — propositions et enrichissement**
   - `01_build_reconciliation_tables/ej/01_ej_siren_reconciliation_job.py`
     construit la table de cohérence enrichie et les propositions EJ de base ;
   - `01_build_reconciliation_tables/ej/02_build_siren_adresse_siege_job.py`
     ajoute l’adresse du siège SIRENE aux propositions ;
   - `01_build_reconciliation_tables/ej/03_fill_missing_denomination_from_person_name_job.py`
     complète les dénominations SIRENE manquantes et produit
     `results/01_build_reconciliation_tables/ej/ej_siren_proposals.parquet`.

3. **Étape 02 EJ — stratification et plan de revue**

   - `02_build_strata_plan/ej/01_ej_build_strata_plan_job.py`
     construit la stratification EJ à partir de la table de cohérence enrichie,
     propage `stratum_id` aux propositions et produit :
     - `results/02_build_strata_plan/ej/ej_siren_consistency_enriched_stratified.parquet` ;
     - `results/02_build_strata_plan/ej/ej_siren_proposals_stratified.parquet` ;
     - `results/02_build_strata_plan/ej/ej_strata_assignments.parquet` ;
     - `results/02_build_strata_plan/ej/ej_strata_plan.xlsx` ;
     - `results/02_build_strata_plan/stratum_codebook.xlsx`.

     En mode `coding` de stratification, la stratification et la table de codification
     utilisent les niveaux théoriques définis dans le code maintenu, y compris les
     niveaux absents des données observées. En mode `mapping` de stratification,
     renseignez `data/study_inputs/ej/ej_entity_strata_mapping.xlsx` avec
     l’affectation des EJ aux `stratum_id` et les variables de stratification associées ;
     la table de codification reprend les niveaux et combinaisons définis dans ce
     mapping.

   - si le mode `mapping` d’affectation des évaluateurs est utilisé, copiez
     `results/02_build_strata_plan/ej/ej_strata_plan.xlsx` vers
     `data/study_inputs/ej/ej_stratum_reviewer_mapping.xlsx` et renseignez la colonne
     `reviewer` pour chaque strate ;

   - `02_build_strata_plan/ej/02_ej_assign_reviewers_job.py`
     affecte les évaluateurs selon le mode configuré (`mapping` ou `round_robin`) et
     produit :
     - `results/02_build_strata_plan/ej/ej_strata_plan_with_reviewers.xlsx` ;
     - `results/02_build_strata_plan/ej/ej_reviewer_statistics.xlsx` ;

   - interrompez le workflow pour définir les tailles d’échantillon : copiez
     `results/02_build_strata_plan/ej/ej_strata_plan_with_reviewers.xlsx` vers
     `data/study_inputs/ej/ej_strata_plan_with_sample_size_input.xlsx` et renseignez la
     colonne `sample_size` pour chaque strate ;

   - `02_build_strata_plan/ej/03_ej_merge_with_sample_size_job.py`
     ajoute la taille d’échantillon au plan avec évaluateurs et produit :
     - `results/02_build_strata_plan/ej/ej_strata_plan_with_sample_size.xlsx` ;
     - `results/02_build_strata_plan/ej/ej_reviewer_statistics_with_sample_size.xlsx`.

4. **Étapes 03–04 EJ — revue et consolidation**

   - `03_export_review_files/ej/01_ej_review_export_job.py`
     sélectionne dans chaque strate les EJ à examiner selon l’ordre déterministe des
     propositions et la cible `sample_size` du plan final, puis exporte les classeurs
     par évaluateur et par strate. L’affectation `reviewer` est également issue du plan
     final.

     Les décisions déjà disponibles dans `PATHS.ej_additional_decisions` sont
     utilisées pour préremplir les colonnes de revue des EJ présentes dans les
     classeurs, sans modifier leur sélection. Les EJ présentes dans
     `PATHS.ej_additional_decisions` mais non sélectionnées dans le nouvel export
     n’apparaissent pas dans les classeurs de revue ;

   - interrompez le workflow pour la revue manuelle ;

   - complétez les classeurs exportés par l’étape 03 puis placez-les sous
     `data/reviewed/ej/<reviewer>/` en profil `full`, ou
     `dev/data/reviewed/ej/<reviewer>/` en profil `dev` ;

   - `04_merge_reviews/ej/01_ej_merge_review_job.py` charge récursivement ces
     classeurs `.xlsx`, vérifie les EJ et leur strate par rapport aux propositions de
     référence, consolide la revue réalisée et produit l’échantillon revu ainsi que les
     décisions confirmées de la revue courante. Les écarts au plan susceptibles
     d’affecter la qualité statistique de la revue, tels qu’une sous-revue ou des trous
     internes dans l’ordre de revue, sont signalés sans être bloquants ;

   - exécutez
     `04_merge_reviews/ej/02_optional_ej_additional_confirmed_decisions_job.py`
     lorsque l’ensemble des décisions de `PATHS.ej_additional_decisions` doit
     également être conservé dans l’ensemble final des décisions confirmées.

     Ce job combine les décisions consolidées à partir de la revue courante avec
     `PATHS.ej_additional_decisions`. Il permet notamment de réintégrer les EJ
     présentes dans `PATHS.ej_additional_decisions` qui n’avaient pas été
     sélectionnées dans les classeurs exportés à l’étape 03. En cas de recouvrement,
     la décision issue de la revue courante est prioritaire.

     Les EJ ainsi réintégrées peuvent correspondre à des cas examinés hors de l’ordre
     déterministe de la revue courante. Leur inclusion dans l’analyse peut donc
     introduire une limite liée au biais de sélection ; voir
     `docs/METHODOLOGY.md`.

5. **Étape 01 EGE — propositions et enrichissement**
   - `01_build_reconciliation_tables/ege/01_ege_siret_reconciliation_job.py`
     construit la table de cohérence enrichie et les propositions EGE de base. Les EGE
     héritent du contexte et du `stratum_id` de leur EJ parente à partir des propositions
     EJ stratifiées ; le job utilise également les décisions EJ confirmées pour rattacher
     le SIREN retenu de l’EJ parente et vérifier sa cohérence avec les SIRET proposés ;
   - `01_build_reconciliation_tables/ege/02_fill_missing_denomination_from_person_name_job.py`
     complète les dénominations SIRENE manquantes ;
   - `01_build_reconciliation_tables/ege/03_add_libcategetab_job.py`
     ajoute la catégorie FINESS des établissements ;
   - `01_build_reconciliation_tables/ege/04_refresh_etat_siret_job.py`
     actualise le statut administratif des SIRET et produit
     `results/01_build_reconciliation_tables/ege/ege_siret_proposals.parquet`.

6. **Étape 02 EGE — pool EGE et plan de revue**
   - `02_build_strata_plan/ege/01_ege_build_pooled_proposals_job.py`
     construit les propositions du pool EGE à partir des décisions EJ confirmées.
     Ce pool constitue le cadre de sondage du second degré de la revue EGE et est
     enregistré dans
     `results/02_build_strata_plan/ege/pooled_ege_proposals.parquet` ;

   - `02_build_strata_plan/ege/02_ege_build_strata_plan_job.py`
     construit le plan de revue à partir du `stratum_id` hérité de l’EJ parente et
     produit :
     - `results/02_build_strata_plan/ege/ege_strata_assignments.parquet` ;
     - `results/02_build_strata_plan/ege/ege_strata_plan.xlsx`.

     Le plan conserve `n_EGE`, population EGE totale de la strate, et
     `n_EGE_pooled`, nombre d’EGE du pool disponibles pour la revue ;

   - si le mode `mapping` d’affectation des évaluateurs est utilisé, copiez
     `results/02_build_strata_plan/ege/ege_strata_plan.xlsx` vers
     `data/study_inputs/ege/ege_stratum_reviewer_mapping.xlsx` et renseignez la colonne
     `reviewer` pour chaque strate ;

   - `02_build_strata_plan/ege/03_ege_assign_reviewers_job.py`
     affecte les évaluateurs selon le mode configuré (`mapping` ou `round_robin`) et
     produit :
     - `results/02_build_strata_plan/ege/ege_strata_plan_with_reviewers.xlsx` ;
     - `results/02_build_strata_plan/ege/ege_reviewer_statistics.xlsx` ;

   - interrompez le workflow pour définir les tailles d’échantillon : copiez
     `results/02_build_strata_plan/ege/ege_strata_plan_with_reviewers.xlsx` vers
     `data/study_inputs/ege/ege_strata_plan_with_sample_size_input.xlsx` et renseignez la
     colonne `sample_size` pour chaque strate ;

   - `02_build_strata_plan/ege/04_ege_merge_with_sample_size_job.py`
     ajoute la taille d’échantillon au plan avec évaluateurs. La taille demandée ne
     peut pas dépasser `n_EGE_pooled`. Le job produit :
     - `results/02_build_strata_plan/ege/ege_strata_plan_with_sample_size.xlsx` ;
     - `results/02_build_strata_plan/ege/ege_reviewer_statistics_with_sample_size.xlsx`.

7. **Étapes 03–04 EGE — revue et consolidation**

   - `03_export_review_files/ege/01_ege_review_export_job.py`
     sélectionne dans chaque strate les EGE à examiner dans le pool EGE selon l’ordre
     déterministe des propositions et la cible `sample_size` du plan final, puis
     exporte les classeurs par évaluateur et par strate. L’affectation `reviewer` est
     également issue du plan final.

     Les décisions déjà disponibles dans `PATHS.ege_additional_decisions` sont
     utilisées pour préremplir les colonnes de revue des EGE présents dans les
     classeurs, sans modifier leur sélection. Les EGE présents dans
     `PATHS.ege_additional_decisions` mais non sélectionnés dans le nouvel export
     n’apparaissent pas dans les classeurs de revue ;

   - interrompez le workflow pour la revue manuelle ;

   - complétez les classeurs exportés par l’étape 03 puis placez-les sous
     `data/reviewed/ege/<reviewer>/` en profil `full`, ou
     `dev/data/reviewed/ege/<reviewer>/` en profil `dev` ;

   - `04_merge_reviews/ege/01_ege_merge_review_job.py` charge récursivement ces
     classeurs `.xlsx`, vérifie les EGE et leur strate par rapport au pool EGE de
     référence, consolide la revue réalisée et produit l’échantillon revu ainsi que les
     décisions confirmées de la revue courante. Les écarts au plan susceptibles
     d’affecter la qualité statistique de la revue, tels qu’une sous-revue ou des trous
     internes dans l’ordre de revue, sont signalés sans être bloquants ;

   - exécutez
     `04_merge_reviews/ege/02_optional_ege_additional_confirmed_decisions_job.py`
     lorsque l’ensemble des décisions de `PATHS.ege_additional_decisions` doit
     également être conservé dans l’ensemble final des décisions confirmées.

     Ce job combine les décisions consolidées à partir de la revue courante avec
     `PATHS.ege_additional_decisions`. Il permet notamment de réintégrer les EGE
     présents dans `PATHS.ege_additional_decisions` qui n’avaient pas été
     sélectionnés dans les classeurs exportés à l’étape 03. En cas de recouvrement,
     la décision issue de la revue courante est prioritaire.

     Les décisions supplémentaires EGE doivent appartenir au pool EGE utilisé pour
     la revue. Elles peuvent néanmoins correspondre à des cas examinés hors du préfixe
     déterministe de la revue courante ; leur inclusion dans l’analyse peut donc
     introduire une limite liée au biais de sélection. Voir `docs/METHODOLOGY.md`.

8. **Étape 05 — analyse et reporting**

   - `05_analyze_reviews/ej/01_ej_analyze_reviews_job.py`
     analyse les décisions EJ confirmées par strate à partir des propositions et du plan
     de stratification. Le job utilise `ej_all_confirmed_decisions` lorsqu’il existe,
     sinon les décisions de la revue courante. Il enrichit le plan avec les principaux
     indicateurs de revue et de performance des propositions Initial, ANS et Adrien,
     ainsi que les indicateurs de précision et les poids d’échantillonnage.

     Il produit :
     - `results/05_analyze_reviews/ej/ej_strata_plan_review_analysis.xlsx` ;
     - `results/05_analyze_reviews/ej/ej_global_review_summary.xlsx`.

     Le premier classeur présente les résultats par strate et inclut la table de
     codification des strates. Le second présente les estimations globales pondérées
     et calées ainsi que des scénarios d’utilisation des méthodes dans les strates
     atteignant les seuils de 95 % ou 99 % ;

   - `05_analyze_reviews/ege/01_ege_analyze_reviews_job.py`
     réalise la même analyse pour les EGE. Avant le calcul des résultats, il reconstruit
     le plan de sondage réalisé à deux degrés EJ → EGE à partir des décisions EJ
     confirmées, du plan EJ et du pool EGE, puis calcule les probabilités d’inclusion
     et les poids d’échantillonnage correspondants.

     Il produit :
     - `results/05_analyze_reviews/ege/ege_strata_plan_review_analysis.xlsx` ;
     - `results/05_analyze_reviews/ege/ege_global_review_summary.xlsx`.

     Comme pour les EJ, le premier classeur présente les résultats par strate et le
     second les estimations globales pondérées et les scénarios associés aux seuils de
     95 % ou 99 %. Les estimations globales EGE tiennent compte du plan de sondage
     réalisé à deux degrés.

   Les jobs vérifient la cohérence des populations et des principaux agrégats avant
   l’export des résultats.

## Revues et validations

À chaque exécution d’un job d’export, `review_files/` est reconstruit et représente
le lot courant complet. Dans chaque strate, `sample_size` définit la cible initiale
de revue ; les classeurs peuvent également contenir les entités suivantes dans
l’ordre déterministe afin de permettre une extension continue de la revue.

Les classeurs de revue de l’étape 03 sont répartis par évaluateur et par strate.
L’étape 04 charge récursivement les classeurs terminés sous
`data/reviewed/<level>/` dans le profil `full` ou
`dev/data/reviewed/<level>/` dans le profil `dev`, puis consolide les décisions
renseignées.

Les fichiers de revue sont en général destinés à un usage interne, car leurs
commentaires peuvent reprendre des informations issues de champs non publics.
Les fichiers de revue du profil `dev` sont en revanche relus et versionnés pour
le développement et l’illustration du workflow.

Les décisions supplémentaires EJ et EGE sont ajoutées, lorsqu’elles sont
applicables, par les jobs `02_optional_*_additional_confirmed_decisions_job.py`.
La revue courante est prioritaire en cas de recouvrement. Une nouvelle exécution du
job de consolidation `01_*_merge_review_job.py` invalide le précédent ensemble
`all_confirmed` ; exécutez de nouveau le job optionnel si les décisions
supplémentaires doivent faire partie du résultat final.

Les étapes opérationnelles valident les données nécessaires à leur fonctionnement.
La consolidation des revues vérifie notamment la structure des classeurs, les
identifiants et la cohérence des décisions pour une même entité. Elle compare aussi
la revue réalisée au plan final et signale les écarts susceptibles d’affecter la
qualité statistique de la revue.

Ces écarts sont informatifs et n’empêchent pas la consolidation. Les décisions
invalides ou contradictoires des évaluateurs restent bloquantes et empêchent la
production des décisions confirmées.

La suite `pytest` protège les invariants métier, relationnels et statistiques
nécessaires au workflow sans rejouer l’étude complète ni dépendre de résultats
préexistants. Les tests sont organisés par étape ; les tests d’intégration restent
limités aux interfaces fichier pour lesquelles ils apportent une protection utile.

Voir `docs/REVIEWER_GUIDE.md` pour les règles de saisie et de consolidation des
revues.

## Snapshots de résultats d’étude

Les principaux livrables correspondant à une version donnée de l’étude peuvent être
manuellement copiés sous `study_snapshots/<YYYY_MM_DD>/` afin de conserver un paquet
figé et facilement transmissible.

Un snapshot peut notamment regrouper :

- sous `analyse`, les quatre classeurs d’analyse et de synthèse EJ/EGE de l’étape 05,
  ainsi que les graphiques synthétiques produits par
  `project_tools/review_performance_summary/` ;
- sous `distribution_ege_par_ej/`, les sorties conservées de
  `project_tools/distribution_ege_par_ej/` ;
- sous `ege_ans_logistic_regression/`, les principaux résultats présentables de
  l’analyse exploratoire de régression logistique ;
- sous `review_samples/`, les échantillons annotés de référence EJ/EGE partageables
  aux formats Excel et Parquet, accompagnés de `REVIEW_SAMPLE_NOTE.md`.

Le snapshot conserve les livrables utiles, pas le code, les notebooks de travail ni les
données sources volumineuses. Un `README.md` à sa racine indique sa date et son contenu.
La date du sous-dossier correspond à la constitution de cette version figée du paquet ;
une nouvelle exécution ne doit pas écraser un snapshot existant.

## Workflow normal de maintenance

1. Sélectionnez le profil `dev` et reproduisez le comportement concerné.
2. Inspectez les outputs produits et, si nécessaire, ajoutez des affichages ou des
   fonctions intermédiaires pour examiner les DataFrames utiles.
3. Modifiez le job ou la fonction Python de référence.
4. Exécutez les tests :

   ```powershell
   $env:SIRENISATION_DATA_PROFILE = "dev"
   uv run --locked pytest
   ```

Les tests sont regroupés sous `tests/` par responsabilité du workflow. Ils couvrent
les règles métier, relationnelles et statistiques à partir de petits jeux de données
synthétiques. Lorsque le format fichier fait partie de l’interface entre deux étapes,
ils utilisent des fichiers temporaires ; un test d’intégration couvre notamment la
chaîne étape 03 → revue → étape 04. Des tests ciblés contrôlent aussi la cohérence de
`dev/data/source/`, la résolution des chemins des profils et les principales
interfaces entre étapes voisines.

Reconstruisez le jeu de données de développement lorsque ses inputs sources
changent intentionnellement ou lorsque la présélection des EJ est modifiée :

```powershell
$env:SIRENISATION_DATA_PROFILE = "full"

uv run --locked python project_tools/build_dev_data.py
```

`build_dev_data.py` construit le jeu de données de développement à partir des
inputs FINESS, ANS, Adrien et SIRENE. La présélection des EJ est définie par
`SEED_EJS`. Le builder vérifie leur présence dans FINESS, conserve leurs EGE,
sélectionne les lignes ANS et Adrien correspondantes et construit la fermeture
SIRENE nécessaire à ce jeu de données.

## Outils complémentaires du projet

Les outils complémentaires conservés sous `project_tools/` regroupent des outils de
développement, d’analyse et d’évaluation qui ne font pas partie du workflow métier
numéroté. Chaque outil ou sous-dossier concerné dispose de son propre README, qui
documente son objectif, son usage, sa configuration et les commandes d’exécution.
Lorsqu’un travail exploratoire nécessite une documentation plus développée, ses
résultats et son interprétation peuvent être conservés dans une note séparée référencée
depuis le README.

`project_tools/distribution_nb_ege_per_ej/` décrit la distribution du nombre d’EGE
rattachés par EJ dans la population d’étude, dans l’échantillon examiné et dans sa
version pondérée.

`project_tools/review_performance_summary/` produit, à partir des résultats globaux
de l’étape 5, des graphiques de synthèse EJ et EGE distinguant les résultats estimés
corrects, incorrects et non couverts pour Initial, ANS et Adrien.

`project_tools/compare_reconciliation_datasets/` compare directement deux bases
d’appariement configurables, en mode EJ–SIREN ou EGE–SIRET, et produit une table
de comparaison ainsi que les principales statistiques de couverture et de cohérence.

`project_tools/review_sample_benchmark/` prépare des échantillons annotés de
référence EJ et EGE à partir des décisions confirmées de revue et permet d’évaluer
sur ces échantillons une autre base d’appariement.

`project_tools/extension_chaine_adrien/` regroupe deux travaux exploratoires autour
de la chaîne Adrien : `acronyms/`, consacré à l’extension manuelle du référentiel
d’acronymes, et `retained_ej_siren_experiment/`, qui étudie l’élargissement des
candidats EGE/SIRET à partir du SIREN retenu de l’EJ parente.

`project_tools/ege_ans_siret_logistic_regression/` contient une analyse exploratoire
par régression logistique pondérée visant à étudier l’acceptation automatique
sélective des propositions ANS de SIRET au niveau EGE. Les résultats obtenus ne
constituent pas une règle de déploiement validée.
