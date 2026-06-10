# Sirénisation FINESS – README technique d’exécution

## 1. Objectif du projet

Ce projet vise à fiabiliser les numéros SIREN des structures FINESS EJ en les rapprochant avec le référentiel SIRENE de l’INSEE.

L’approche repose sur deux phases :

1. **Phase 1 – Matching direct**  
   Vérifier les FINESS EJ qui possèdent déjà un SIREN, en comparant la structure FINESS avec l’unité légale SIRENE correspondante.

2. **Phase 2 – Matching indirect**  
   Rechercher des candidats SIRENE pour les FINESS non validées en phase 1, via un blocking par département et un calcul de similarité nom/adresse.

---

## 2. Organisation attendue du projet

```text
|
sirene
|
|__ stockuntelegal.parquet
|__ stocketablissement.parquet
|
|
sirenisation_finess/
│
├── Conn_db.py
├── Utils.py
├── Matching.py
├── main.ipynb
│
├── data/
│   └── sirene_parquets/
│       ├── dep_01.parquet
│       ├── dep_02.parquet
│       ├── ...
│       └── dep_UNK.parquet
│
├── sirene.duckdb
│
├── phase2_results_by_dep/
│   ├── phase2_dep_01.parquet
│   ├── phase2_dep_02.parquet
│   ├── ...
│   └── departments_done.txt
│
├── matching_phase1.xlsx
└── matching_phase2_final.xlsx
```

---

## 3. Rôle des dossiers importants

### `data/sirene_parquets/`

Ce dossier contient les fichiers SIRENE découpés par département.

Chaque fichier correspond à un bloc de candidats SIRENE utilisé en phase 2 :

```text
dep_75.parquet
dep_92.parquet
dep_13.parquet
dep_UNK.parquet
```

L’objectif est d’éviter de comparer chaque FINESS avec toute la base SIRENE.  
On compare uniquement une FINESS avec les candidats SIRENE du même département.

C’est ce qu’on appelle le **blocking par département**.

---

### `sirene.duckdb`

Ce fichier est la base DuckDB locale créée à partir des fichiers SIRENE sources :

- `StockUniteLegale.parquet`
- `StockEtablissement.parquet`

Elle contient notamment la table consolidée :

```text
sirene_joined
```

Cette table est construite en gardant uniquement :

- les unités légales actives
- les établissements sièges actifs
 

Elle sert principalement pour la phase 1 et pour générer les fichiers parquet par département.

---

### `phase2_results_by_dep/`

Ce dossier contient les résultats intermédiaires de la phase 2.

La phase 2 peut être longue, donc les résultats sont sauvegardés progressivement par département et par chunk :

```text
phase2_dep_75.parquet
phase2_dep_76.parquet
```

Le fichier :

```text
departments_done.txt
```

sert de **checkpoint**.

Il contient la liste des départements déjà traités.  
Si le traitement s’arrête, on peut relancer le notebook sans recommencer depuis le début : les départements déjà terminés sont automatiquement ignorés.

---

# 4. Description des scripts

## 4.1 `Conn_db.py`

### Rôle général

Ce script gère les connexions aux bases et la préparation de la base SIRENE locale.

Il permet de :

- se connecter à SQL Server pour lire FINESS
- se connecter à DuckDB pour lire ou créer la base SIRENE
- charger les fichiers SIRENE source
- créer les tables DuckDB intermédiaires
- créer la table consolidée `sirene_joined`

---

### Fonctions principales

#### `get_finess_active()`

Ouvre une connexion SQL Server vers la base FINESS.

Utilisée pour extraire les FINESS EJ ouvertes.

---

#### `get_sirene_active(read_only=True, force_reload=False)`

Ouvre la base DuckDB `sirene.duckdb`.

- `read_only=True` : lecture seule
- `read_only=False` : création ou reconstruction de la base
- `force_reload=True` : force la reconstruction des tables SIRENE

---

#### `load_unite_legale()`

Charge les unités légales actives depuis `StockUniteLegale.parquet`.

Filtre appliqué :

```sql
etatAdministratifUniteLegale = 'A'
```

---

#### `load_etablissement()`

Charge les établissements actifs et sièges depuis `StockEtablissement.parquet`.

Filtres appliqués :

```sql
etablissementSiege = 'true'
etatAdministratifEtablissement = 'A'
```

---

#### `join_sirene()`

Crée la table `sirene_joined` en joignant :

- `sirene_unite_legale`
- `sirene_etablissement`

Jointure :

```sql
ul.siren = et.siren
AND ul.nic = et.nic
```

---

### Quand utiliser ce script ?

À utiliser au début du projet pour :

1. se connecter aux bases
2. créer la base DuckDB SIRENE si elle n’existe pas
3. vérifier les volumétries SIRENE
4. fournir les connexions nécessaires aux autres scripts

---

## 4.2 `Utils.py`

### Rôle général

Ce script regroupe toutes les fonctions utilitaires utilisées par les deux phases de matching.

Il contient :

- la normalisation des noms
- la normalisation des adresses
- le mapping des types de voie
- les fonctions de similarité
- le calcul du score nom
- le calcul du score adresse
- la génération des fichiers SIRENE par département
- le loader SIRENE avec cache pour la phase 2

---

### Normalisation des noms

Fonction principale :

```python
normalize_text(text)
```

Elle applique :

- suppression des accents
- passage en majuscule
- suppression de la ponctuation
- suppression des espaces multiples
- suppression de certains stop words métier

Exemples de stop words :

```text
DE, DU, DES, LA, LE, LES, ET, SA, SAS, SARL...
```

---

### Normalisation des adresses

Fonction principale :

```python
normalize_adresse(text)
```

Elle applique :

- suppression des accents
- passage en majuscule
- suppression de la ponctuation
- nettoyage des espaces

---

### Mapping des types de voie

Fonction principale :

```python
map_type_voie(type_voie)
```

Elle permet d’harmoniser les abréviations :

```text
AV  → AVENUE
BD  → BOULEVARD
R   → RUE
CHE → CHEMIN
IMP → IMPASSE
PL  → PLACE
```

---

### Similarité texte

Fonctions principales :

```python
levenshtein_score(a, b)
jaccard_score(a, b)
compute_text_similarity(a, b)
```

Score texte utilisé :

```python
score = 0.6 * levenshtein + 0.4 * jaccard
```

---

### Similarité nom

Fonction principale :

```python
compute_name_similarity(a, b)
```

Elle combine :

- similarité texte classique
- gestion des abréviations via les initiales

Exemple :

```text
CENTRE HOSPITALIER UNIVERSITAIRE
CHU
```

---

### Similarité adresse

Fonction principale :

```python
compute_adresse_similarity(row_fi, row_si)
```

Elle compare :

- code commune
- numéro de voie
- type de voie
- libellé de voie

Score adresse :

```python
score_adresse =
    0.30 * score_commune
  + 0.30 * score_numero_voie
  + 0.40 * score_adresse_textuelle
```

---

### Génération des parquets SIRENE par département

Fonction principale :

```python
build_sirene_dep(con_duck, output_dir)
```

Elle crée un fichier parquet par département à partir de la table `sirene_joined`.

Ces fichiers sont stockés dans :

```text
data/sirene_parquets/
```

À lancer une seule fois, sauf si la base SIRENE est mise à jour.

---

### Loader SIRENE avec cache

Classe principale :

```python
SireneLoader
```

Elle charge les fichiers parquet départementaux à la demande.

Intérêt :

- éviter de charger toute la base SIRENE en mémoire
- réutiliser les départements déjà chargés
- accélérer la phase 2

---

## 4.3 `Matching.py`

### Rôle général

Ce script contient le cœur du matching FINESS ↔ SIRENE.

Il est organisé en deux blocs :

1. **Bloc A – Phase 1 : matching direct**
2. **Bloc B – Phase 2 : matching indirect**

---

# 5. Phase 1 – Matching direct

## Objectif

Valider les FINESS EJ qui possèdent déjà un numéro SIREN.

Principe :

1. extraire les FINESS EJ ouvertes avec SIREN
2. récupérer la référence SIRENE correspondante via le SIREN
3. comparer raison sociale et adresse
4. calculer un score global
5. classer en `VALID` ou `REJET`

---

## Fonctions principales

### `get_finess_with_siren(conn)`

Extrait les FINESS EJ ouvertes ayant un SIREN renseigné.

---

### `preprocess_finess(df)`

Normalise les champs FINESS :

- raison sociale
- type de voie
- libellé de voie
- département

---

### `get_sirene_dict(con_duck, siren_list)`

Récupère les références SIRENE depuis `sirene_joined` uniquement pour les SIREN présents côté FINESS.

Cela évite de charger toute la table SIRENE.

---

### `process_direct_matching(finess_df, sirene_dict, threshold=67)`

Calcule les scores et applique les règles de validation.

Score global :

```python
score_global = 0.4 * score_nom + 0.6 * score_adresse
```

Règles de validation utilisées dans le script :

```python
score_global >= threshold
```

ou :

```python
score_nom >= 15 and score_adresse >= 55
```

La deuxième règle sert de rattrapage lorsque l’adresse est suffisamment forte.

---

### `export_matching_excel(valid_df, rejected_df)`

Génère le fichier Excel de sortie :

```text
matching_phase1.xlsx
```

Avec les feuilles :

- `Matching_validé`
- `Matching_rejeté`
- `Synthese`

Le script ajoute aussi :

- un flag de doublon SIREN
- un rang par SIREN pour les doublons

---

### `run_direct_matching(conn_sql, con_duck, threshold=67, export_excel=True)`

Pipeline complet de la phase 1.

C’est la fonction principale à appeler pour lancer le matching direct.

---

# 6. Phase 2 – Matching indirect

## Objectif

Rechercher des bons candidats SIRENE pour les FINESS non validées en phase 1.

La phase 2 traite :

- les FINESS sans SIREN
- les FINESS rejetées ou non validées en phase 1

---

## Principe général

Pour chaque département :

1. charger les FINESS du département
2. exclure les FINESS déjà validées en phase 1
3. charger les candidats SIRENE du même département
4. calculer les similarités
5. conserver les Top 3 candidats
6. sauvegarder les résultats intermédiaires
7. marquer le département comme terminé dans le checkpoint

---

## Fonctions principales

### `get_finess_departments(conn_sql)`

Récupère la liste des départements présents dans FINESS.

---

### `get_finess_by_department_chunks(conn_sql, dep, valid_df, chunk_size=5000)`

Charge les FINESS par département et par chunk.

Intérêt :

- éviter de charger trop de lignes en mémoire
- traiter progressivement les grands volumes
- exclure les FINESS déjà validées en phase 1

---

### `match_top3(row, sirene_loader, top_k=3)`

Pour une FINESS donnée :

1. charge le bloc SIRENE du même département
2. applique des pré-filtres rapides
3. calcule le score nom
4. calcule le score adresse
5. calcule le score global
6. retourne les 3 meilleurs candidats

Pré-filtres utilisés pour accélérer :

```python
score_nom < 20          → skip
score_nom < 30 and score_adresse < 50 → skip
```

---

### `process_chunk_phase2(chunk, sirene_loader, dep, part_idx)`

Traite un chunk FINESS complet.

Utilise `tqdm` pour afficher la progression.

---

### `save_phase2_results(results, output_dir, dep, part_idx)`

Sauvegarde les résultats intermédiaires au format parquet :

```text
phase2_results_by_dep/phase2_dep_75_part_0.parquet
```

---

### `load_processed_departments(checkpoint_file)`

Lit le fichier checkpoint :

```text
phase2_results_by_dep/departments_done.txt
```

Retourne les départements déjà traités.

---

### `mark_department_done(dep, checkpoint_file)`

Ajoute le département terminé dans le fichier checkpoint.

Cela permet de reprendre le traitement en cas d’arrêt.

---

### `run_indirect_matching_by_department(...)`

Pipeline complet de la phase 2.

C’est la fonction principale à appeler pour lancer le matching indirect.

---

### `merge_phase2_parquets_to_excel(...)`

Concatène tous les fichiers parquet générés en phase 2 et produit l’Excel final :

```text
matching_phase2_final.xlsx
```

Feuilles générées :

- `Candidats_valides`
- `Candidats_rejetes`
- `Synthese`

Règle métier appliquée à l’export :

```python
score_global >= 67
```

ou :

```python
score_nom >= 50 and score_adresse >= 75
```

---

## 4.4 `main.ipynb`

### Rôle général

Le notebook sert à orchestrer l’exécution complète.

Il ne contient pas toute la logique métier.  
Il appelle les fonctions définies dans :

- `Conn_db.py`
- `Utils.py`
- `Matching.py`

---

### Étapes réalisées dans le notebook

#### 1. Import et reload des modules

```python
import Conn_db
import Utils as ul
import Matching

reload(Conn_db)
reload(ul)
reload(Matching)
```

Intérêt :

- prendre en compte les modifications des scripts sans redémarrer le kernel

---

#### 2. Connexions

```python
conn_sql = get_finess_active()
con_duck = get_sirene_active(read_only=True)
```

---

#### 3. Lancement de la phase 1

```python
valid_df, rejected_df = run_direct_matching(
    conn_sql,
    con_duck,
    threshold=67,
    export_excel=True
)
```

Sortie principale :

```text
matching_phase1.xlsx
```

---

#### 4. Génération des parquets SIRENE par département

À lancer uniquement si les fichiers n’existent pas encore :

```python
SIRENE_PARQUET_DIR = "data/sirene_parquets"

con_duck = get_sirene_active(read_only=True)
ul.build_sirene_dep(con_duck, SIRENE_PARQUET_DIR)
```

---

#### 5. Lancement de la phase 2

```python
OUTPUT_DIR = "phase2_results_by_dep"
CHECKPOINT_FILE = f"{OUTPUT_DIR}/departments_done.txt"

sirene_loader = ul.SireneLoader("data/sirene_parquets")

run_indirect_matching_by_department(
    conn_sql=conn_sql,
    valid_df=valid_df,
    sirene_loader=sirene_loader,
    output_dir=OUTPUT_DIR,
    checkpoint_file=CHECKPOINT_FILE,
    chunk_size=5000
)
```

---

#### 6. Export final phase 2

```python
df_phase2 = merge_phase2_parquets_to_excel(
    input_dir=OUTPUT_DIR,
    output_excel="matching_phase2_final.xlsx"
)
```

Sortie principale :

```text
matching_phase2_final.xlsx
```

---

# 7. Ordre recommandé d’exécution

## Étape 0 – Préparer l’environnement

Installer les dépendances :

```bash
pip install pandas pyodbc duckdb rapidfuzz openpyxl XlsxWriter tqdm pathlib
```

---

## Étape 1 – Créer ou vérifier la base DuckDB SIRENE

Si `sirene.duckdb` n’existe pas encore :

```python
con_duck = get_sirene_active(read_only=False, force_reload=True)
```

Sinon :

```python
con_duck = get_sirene_active(read_only=True)
```

---

## Étape 2 – Générer les fichiers SIRENE par département

À lancer une seule fois :

```python
SIRENE_PARQUET_DIR = "data/sirene_parquets"
ul.build_sirene_dep(con_duck, SIRENE_PARQUET_DIR)
```

Ne pas relancer inutilement si les fichiers existent déjà.

---

## Étape 3 – Lancer la phase 1

```python
conn_sql = get_finess_active()
con_duck = get_sirene_active(read_only=True)

valid_df, rejected_df = run_direct_matching(
    conn_sql,
    con_duck,
    threshold=67,
    export_excel=True
)
```

Résultat :

```text
matching_phase1.xlsx
```

---

## Étape 4 – Lancer la phase 2

```python
sirene_loader = ul.SireneLoader("data/sirene_parquets")

run_indirect_matching_by_department(
    conn_sql=conn_sql,
    valid_df=valid_df,
    sirene_loader=sirene_loader,
    output_dir="phase2_results_by_dep",
    checkpoint_file="phase2_results_by_dep/departments_done.txt",
    chunk_size=5000
)
```

Résultats intermédiaires :

```text
phase2_results_by_dep/*.parquet
phase2_results_by_dep/departments_done.txt
```

---

## Étape 5 – Générer l’Excel final phase 2

```python
df_phase2 = merge_phase2_parquets_to_excel(
    input_dir="phase2_results_by_dep",
    output_excel="matching_phase2_final.xlsx"
)
```

Résultat :

```text
matching_phase2_final.xlsx
```

---

# 8. Gestion de la reprise en cas d’arrêt

La phase 2 est conçue pour être relancée sans repartir de zéro.

Le fichier :

```text
phase2_results_by_dep/departments_done.txt
```

contient les départements déjà finalisés.

Au prochain lancement :

- les départements présents dans ce fichier sont ignorés
- seuls les départements non terminés sont retraités

Exemple :

```text
01
02
03
75
```

Si le traitement s’arrête au département 76, il suffit de relancer le notebook.  
Les départements 01, 02, 03 et 75 ne seront pas recalculés.

---


# 9. Résumé rapide pour un nouvel utilisateur

Pour utiliser le projet :

1. Vérifier que `sirene.duckdb` existe.
2. Vérifier que `data/sirene_parquets/` contient les fichiers par département.
3. Lancer `main.ipynb`.
4. Exécuter la phase 1.
5. Exécuter la phase 2.
6. Générer l’Excel final.
7. En cas d’arrêt, relancer simplement la phase 2 : le checkpoint évite de recommencer les départements déjà faits.

---

# 10. Source officielle des données SIRENE

Les données SIRENE utilisées dans ce projet proviennent de la plateforme data.gouv.fr :

https://www.data.gouv.fr/datasets/base-sirene-des-entreprises-et-de-leurs-etablissements-siren-siret

Fichiers utilisés :
- StockUniteLegale.parquet
- StockEtablissement.parquet

---


# 11. Conclusion

Le projet est structuré pour être :

- explicable
- réutilisable
- relançable
- adapté aux gros volumes
- compréhensible par une équipe interne

Les scripts sont séparés par responsabilité :

```text
Conn_db.py   → connexions et préparation SIRENE
Utils.py     → fonctions de nettoyage, scoring et blocking
Matching.py  → logique métier phase 1 et phase 2
main.ipynb   → orchestration de l’exécution
```

Cette organisation permet à un nouveau contributeur de reprendre facilement le pipeline, de modifier les seuils, d’adapter les chemins ou d’améliorer progressivement les règles de matching.
