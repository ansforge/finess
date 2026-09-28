# Projet FINESS × SIRENE — Siretisation, Sirenisation et Comparaison

Mise en qualité conjointe des numéros **SIRET** et **SIREN** des structures FINESS, par rapprochement avec les répertoires SIRENE de l'INSEE. Méthode déterministe.

## Trois volets

| Volet | Matching | Phases |
|---|---|---|
| **Siretisation** | EG FINESS ↔ Établissements SIRENE | P1 + P2 + P3 |
| **Sirenisation** | EJ FINESS ↔ Unités Légales SIRENE | P1 + P2 + P3 |
| **Comparaison** | Cohérence SIREN ↔ SIRET entre les deux pipelines | Vue A unique |

## Logique des deux pipelines

Principes communs :
- **P1** : matching exact (SIRET ou SIREN) sur la base SIRENE complète
- **P2** : top 5 candidats probabiliste, blocking par commune, bonus +15 sur identifiant cohérent
- **P3** : top 3 matching approfondi (APE + date), blocking par département, même bonus

### Spécificité sirenisation

Construction d'un périmètre A/B/C sur les non-validés P1 :
- A : EJ rattachés à au moins une EG (via `nmfinessej_stru` côté EG)
- B : EJ non rattachés à une EG mais avec `nmsiren_stru` renseigné
- C : EJ non rattachés à une EG ET sans `nmsiren_stru`

### Spécificité siretisation : filtrage de la base SIRENE

Pour réduire le temps de calcul des Phases 2 et 3 siretisation, on construit un **échantillon de SIRENE Etab** filtré à partir des résultats de la sirenisation (étape ST-02bis). On ne garde que les établissements rattachés aux SIREN suivants :
- SIREN validés en sirenisation aux 3 phases (depuis sirenisation_phase1.xlsx,
  sirenisation_phase2_top5.xlsx, sirenisation_phase3_approfondi.xlsx)
- SIREN candidats top 5 en SN-P2 (rang 1 à 5, peu importe le statut)
- SIREN candidats top 3 en SN-P3 (rang 1 à 3, peu importe le statut)

Ce filtrage divise typiquement la base par ~30 à 50, rendant les phases 2 et 3 exécutables en quelques minutes au lieu de plusieurs heures. La sirenisation doit donc être lancée **avant** les phases 2/3 de la siretisation.

## Comparaison finale

Pour chaque EG validé en siretisation, vérifie que `SIRET_EG[:9] == SIREN_EJ` validé pour l'EJ parent (via `nmfinessej_stru`).

| Statut | Signification |
|---|---|
| **COHERENT** | SIRET_EG[:9] == SIREN_EJ validé — confiance maximale |
| **INCOHERENT** | SIRET_EG[:9] ≠ SIREN_EJ validé — à arbitrer |
| **PARTIEL_EG** | EG validé mais EJ parent pas validé |
| **PARTIEL_EJ** | EJ validé mais aucun EG correspondant validé |
| **ORPHELIN** | EG validé sans `nmfinessej_stru` renseigné |

La comparaison s'appuie sur les **3 fichiers de phase** de chaque pipeline (P1, P2, P3) qui sont fusionnés à la volée.

Excel produit (`coherence_globale.xlsx`) à 4 feuilles : **Synthese / Coherent / Incoherent / Partiel**.
Excel produit (`coherence_par_phase.xlsx`) à 7 feuilles : **Synthese / Coherent_P1 / Coherent_P2 / Coherent_P3 / Coherent_Autres / Incoherent / Partiel**.

| Notebook | Scope |
|---|---|
| COMP-01_vue_a | Globale (tous validés confondus, peu importe la phase) | Par phase (classement des cohérence par phase)

## Arborescence

```
projet_finess_sirene/
├── README.md
├── requirements.txt
├── config/settings.py
├── src/
│   ├── connexion.py            FINESS SQL + DuckDB
│   ├── pretraitement.py        normalisations EG / EJ / Etab / UL
│   ├── scoring.py              formules génériques
│   ├── matching.py             classification
│   ├── siretisation.py         logique EG ↔ Etab + scoring approfondi
│   ├── sirenisation.py         logique EJ ↔ UL + périmètre A/B/C + scoring approfondi
│   ├── comparaison.py          cohérence SIREN ↔ SIRET
│   ├── excel_export.py         exports Phase 1 / TopN / Final / Comparaison
│   └── display.py              tableaux Jupyter
└── notebooks/
    ├── 01_chargement_finess.ipynb       EG + EJ depuis SQL
    ├── 02_chargement_sirene.ipynb       Etab actifs + UL avec siège
    ├── 03_pretraitement.ipynb           normalisations
    ├── sirenisation/
    │   ├── SN-01_phase1.ipynb           SIREN exact
    │   ├── SN-02_perimetre_abc.ipynb    construction A/B/C
    │   ├── SN-03_phase2.ipynb           top 5 probabiliste
    │   └── SN-04_phase3.ipynb           APE + dateCreationUniteLegale
    ├── siretisation/
    │   ├── ST-01_phase1.ipynb            SIRET exact (base SIRENE complète)
    │   ├── ST-02_perimetre.ipynb         EG non validés en P1
    │   ├── ST-02bis_filtre_sirene.ipynb  construit l'échantillon SIRENE filtré
    │   ├── ST-03_phase2.ipynb            top 5 probabiliste (base filtrée)
    │   └── ST-04_phase3.ipynb            APE + dateCreationEtablissement (base filtrée)
    └── comparaison/
        └── COMP-01_vue_a.ipynb         cohérence globale (tous validés)
```

## Ordre d'exécution complet

```
1. 01_chargement_finess
2. 02_chargement_sirene
3. 03_pretraitement

Volet sirenisation (à lancer AVANT la siretisation phases 2/3) :
4. sirenisation/SN-01_phase1
5. sirenisation/SN-02_perimetre_abc
6. sirenisation/SN-03_phase2
7. sirenisation/SN-04_phase3

Volet siretisation :
8.  siretisation/ST-01_phase1
9. siretisation/ST-02_perimetre
10. siretisation/ST-02bis_filtre_sirene   (utilise les sorties sirenisation)
11. siretisation/ST-03_phase2             (utilise la base filtrée)
12. siretisation/ST-04_phase3             (utilise la base filtrée)

Comparaisons (sur l'ensemble des fichiers (P1, P2, P3)) :
13 comparaison/COMP-01_vue_a
```

**Note** : la siretisation peut être lancée jusqu'à ST-01 et ST-02 indépendamment 
de la sirenisation. En revanche, ST-02bis dépend des sorties de la sirenisation 
(`sirenisation_phase1.xlsx`, `sirenisation_phase2_top5.xlsx`, `sirenisation_phase3_approfondi.xlsx`).

## Scoring

```
score_textuel = 0.6 × Levenshtein + 0.4 × Jaccard
score_nom     = 0.6 × score_textuel + 0.4 × score_initiales
score_adresse = 0.30 × code_commune + 0.30 × numéro_voie + 0.40 × score_textuel(voie)
score_global  = 0.4 × score_nom + 0.6 × score_adresse
```

### Phase 3 — pondération adaptative

| APE | Date | Pondération |
|---|---|---|
| ✓ | ✓ | 0.70 × global + 0.20 × ape + 0.10 × date |
| ✓ | ✗ | 0.80 × global + 0.20 × ape |
| ✗ | ✓ | 0.80 × global + 0.20 × date |
| ✗ | ✗ | score_global standard |

### Score APE (échelle 0-100)

| Cohérence | Score |
|---|---|
| Codes identiques | 100 |
| Même classe (4 premiers car.) | 70 |
| Même groupe (3 premiers car.) | 40 |
| Même division (2 premiers car.) | 20 |
| Pas de cohérence | 0 |

### Score date (écart d'années)

| Écart | Score |
|---|---|
| ≤ 1 an | 100 |
| ≤ 3 ans | 80 |
| ≤ 5 ans | 60 |
| ≤ 10 ans | 40 |
| ≤ 20 ans | 20 |
| > 20 ans | 0 |

### Règle de validation

```
score_global ≥ 67   OU   (score_nom ≥ 15 ET score_adresse ≥ 55)
```

### Statuts produits

| Statut | Condition |
|---|---|
| VALIDE_FORT | Validé et score_global ≥ 85 |
| VALIDE | Validé |
| DOUTEUX | Non validé, score_global ≥ 40 |
| REJETE | Non validé, score_global < 40 |
| SANS_SIRET / SANS_SIREN | Identifiant non renseigné dans FINESS |
| SIRET_INCONNU / SIREN_INCONNU | Identifiant FINESS absent de SIRENE |
| SANS_CANDIDAT | Aucune correspondance dans la commune (P2) ou département (P3) |

### Bonus identifiant cohérent (P2 et P3)

`+15` sur le score_global si l'identifiant candidat (SIRET ou SIREN) correspond à celui de FINESS. Désactivé si l'identifiant FINESS est déjà validé en P1 par un autre EG/EJ jumeau, pour éviter de booster artificiellement un match déjà refusé textuellement.

## Synthèse finale différenciée par phase

Pour traduire les niveaux de confiance, la synthèse de consolidation distingue les validés par phase d'origine :

```
Valide_fort_P1   très haute confiance (SIRET/SIREN exact + score élevé)
Valide_P1
Valide_fort_P2   confiance modérée (matching probabiliste)
Valide_P2
Valide_fort_P3   confiance modérée + critères APE/date
Valide_P3
Douteux / Rejeté / Sans_SIRET / SIRET_inconnu / Sans_candidat
```

## Prérequis

- Python 3.10+
- Accès Citrix au serveur SQL FINESS (BICOEUR_DWH_SNAPSHOT)
- ODBC Driver 17 for SQL Server
- Parquets SIRENE INSEE (StockUniteLegale + StockEtablissement) dans `data/raw/sirene/`

```bash
pip install -r requirements.txt
```

## Livrables

```
results/
├── siretisation/
│   ├── siretisation_phase1.xlsx
│   ├── siretisation_phase2_top5.xlsx
│   └── siretisation_phase3_approfondi.xlsx
├── sirenisation/
│   ├── sirenisation_phase1.xlsx
│   ├── sirenisation_phase2_top5.xlsx
│   └── sirenisation_phase3_approfondi.xlsx
└── comparaison/
    └── coherence_globale.xlsx
```

## Autres

```
14 comparaison/COMP-02_croisement_travaux 
15 comparaison/Result_graph
```