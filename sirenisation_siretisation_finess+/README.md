# FINESS+ × SIRENE

Mise en qualité des identifiants SIREN et SIRET des structures FINESS, par
rapprochement avec les répertoires SIRENE de l'INSEE.

La méthode est déterministe : pas d'apprentissage, pas de modèle. Chaque
décision découle de règles écrites, et chaque résultat se retrace jusqu'à la
comparaison qui l'a produit.

Le projet travaille sur le modèle **FINESS+** (`BIFINESS_DWH_SNAPSHOT`), qui
remplace `dwh_structure`.

---

## Sommaire

- [Ce que fait le traitement](#ce-que-fait-le-traitement)
- [Installation](#installation)
- [Ordre d'exécution](#ordre-dexécution)
- [Le scoring](#le-scoring)
- [Les phases en détail](#les-phases-en-détail)
- [Comparaison de cohérence](#comparaison-de-cohérence)
- [Livrables](#livrables)
- [Arborescence](#arborescence)
- [Ce qui change par rapport à `dwh_structure`](#ce-qui-change-par-rapport-à-dwh_structure)
- [Performance et mémoire](#performance-et-mémoire)
- [Dépannage](#dépannage)
- [Traitements annexes](#traitements-annexes)

---

## Ce que fait le traitement

Trois volets.

| Volet | Ce qu'il rapproche |
|---|---|
| **Sirenisation** | personnes morales FINESS ↔ unités légales SIRENE |
| **Siretisation** | établissements FINESS ↔ établissements SIRENE |
| **Cohérence** | SIREN ↔ SIRET, entre les deux volets |

Chaque volet enchaîne quatre étapes. La phase 0 est commune aux deux : elle fait
partie du prétraitement.

| Phase | Méthode | Comparaison | Candidats |
|---|---|---|---|
| **P0** | validation des codes commune sur le COG | — | — |
| **P1** | matching exact sur l'identifiant déclaré | — | 1 |
| **P2** | probabiliste | même commune | top 5 |
| **P3** | probabiliste, enrichi de l'APE et de la date | même département | top 3 |

Une structure validée à une phase ne repasse pas par la suivante : chaque phase
ne traite que ce que la précédente a laissé.

Côté siretisation, un **contrôle du domaine d'activité** s'ajoute en phases 2
et 3. Un candidat au bon nom et à la bonne adresse mais dont l'activité n'a rien
à voir avec le champ FINESS est écarté, quel que soit son score.

---

## Installation

### Prérequis

Python 3.10 ou plus, un accès à `BIFINESS_DWH_SNAPSHOT`, le driver ODBC 17 for
SQL Server, et les parquets SIRENE de l'INSEE.

```bash
pip install -r requirements.txt
```

### Fichiers à déposer

| Emplacement | Fichier | Source |
|---|---|---|
| `data/raw/sirene/` | `StockUniteLegale_utf8.parquet` | data.gouv.fr — Base Sirene |
| `data/raw/sirene/` | `StockEtablissement_utf8.parquet` | data.gouv.fr — Base Sirene |
| `data/referentiels/` | `Extraction_PM_codeape*.csv` | extraction métier |
| `data/referentiels/` | `Extraction_EG_codeape*.csv` | extraction métier |
| `data/referentiels/` | `Extraction_EG_dateouverture*.csv` | extraction métier |
| `data/referentiels/` | `FINESS_Categories_etablissements_V3_Ouverts.csv` | référentiel MOA |
| `data/referentiels/` | `table_passage_geo2003_geo2026.xlsx` | INSEE |

Les CSV de référentiel sont au format `nofiness;valeur`. Un fichier manquant
n'est pas bloquant : le critère correspondant est neutralisé et la pondération
s'adapte à ce qui reste.

Les dates d'ouverture des personnes morales ne viennent pas d'un fichier. Elles
sont extraites de la table `Evenement` par le notebook 01, en retenant les
événements de code `001`.

### Chemins

Tous les chemins dérivent de `ROOT_DIR` dans `config/settings.py`, calculé
depuis l'emplacement du fichier. Rien n'est écrit en dur, le projet se déplace
tel quel.

Les notebooks de premier niveau remontent à la racine avec
`sys.path.insert(0, os.path.abspath('..'))`, ceux rangés dans un sous-dossier
avec `'../..'`. Un notebook déplacé d'un niveau doit voir cette ligne ajustée.

---

## Ordre d'exécution

```
1.  01_chargement_finess      structures FINESS+ et dates d'ouverture
2.  02_chargement_sirene      unités légales et établissements INSEE
3.  03_pretraitement          normalisation, phase 0, partitionnement

Sirenisation                  Siretisation
4.  SN-01_phase1              8.  ST-01_phase1
5.  SN-02_perimetre_abc       9.  ST-02_perimetre
6.  SN-03_phase2              10. ST-02bis_filtre_sirene
7.  SN-04_phase3              11. ST-03_phase2
                              12. ST-04_phase3

13. COMP-01_coherence
```

Les étapes 1 à 3 ne sont à refaire que si les données sources changent.

La sirenisation doit précéder l'étape 10 : `ST-02bis` restreint les candidats
SIRENE aux SIREN qu'elle a validés ou proposés. `ST-01` en revanche est
indépendant, le matching SIRET exact travaillant sur la base complète.

L'enchaînement se fait par parquet : chaque phase écrit les structures qu'elle a
validées, la suivante lit ce fichier. L'Excel est un livrable, pas un maillon de
la chaîne — aucun notebook ne relit une feuille produite par un autre.

Un même identifiant ne porte pas le même nom d'une phase à l'autre : le SIRET
retenu s'écrit `siret_etab`, `siret`, `siret_norm_ege`, `siret_ref` ou
`siret_ref_app`, le code commune `TX_CogCommune`, `cdcommune_norm_pm` ou
`cdcommune_norm_ege`. Les modules qui relisent ces sorties résolvent la colonne
parmi une liste de noms acceptés. Un nom de colonne en dur est à éviter partout
où l'on lit un fichier de phase.

---

## Le scoring

Quatre formules, appliquées à chaque paire de structures comparées.

```
score_textuel = 0.6 × Levenshtein + 0.4 × Jaccard
score_nom     = 0.6 × score_textuel + 0.4 × score_initiales
score_adresse = 0.30 × code_commune + 0.30 × numéro_voie + 0.40 × score_textuel(voie)
score_global  = 0.4 × score_nom + 0.6 × score_adresse
```

Le score textuel combine une distance de caractères et un recouvrement de mots.
La première capte les fautes de frappe, la seconde l'ordre différent des termes.
Le score d'initiales rattrape les sigles développés d'un côté et abrégés de
l'autre.

L'adresse pèse plus lourd que le nom parce qu'elle varie moins : une structure
peut être enregistrée sous sa raison sociale d'un côté et son nom d'usage de
l'autre, son adresse reste la même.

### Le nom comparé côté SIRENE

Il n'est pas fixe. En sirenisation, on retient entre dénomination et sigle celui
qui ressemble le plus au nom FINESS, la dénomination l'emportant à égalité. En
siretisation, on prend la meilleure des trois enseignes ou de la dénomination
usuelle, avec la dénomination de l'unité légale en repli.

### Validation

```
score_global ≥ 67    OU    (score_nom ≥ 15  ET  score_adresse ≥ 55)
```

La seconde branche existe pour les structures dont le nom diffère fortement
entre les deux répertoires mais dont l'adresse est identique.

| Statut | Condition |
|---|---|
| `VALIDE_FORT` | validé, score ≥ 85 |
| `VALIDE` | validé |
| `DOUTEUX` | non validé, score ≥ 40 |
| `REJETE` | non validé, score < 40 |
| `SANS_SIRET` / `SANS_SIREN` | identifiant non renseigné dans FINESS |
| `SIRET_INCONNU` / `SIREN_INCONNU` | identifiant FINESS absent de SIRENE |
| `SANS_CANDIDAT` | aucun candidat dans la maille de comparaison |
| `NON_FIABLE_APE` | le score validait, l'activité l'en empêche (EGE, P2 et P3) |

### Bonus d'identifiant cohérent

`+15` points quand l'identifiant du candidat correspond à celui déclaré dans
FINESS. Il est désactivé lorsque cet identifiant a déjà été validé en phase 1
par une structure jumelle : sans cette réserve, une correspondance refusée sur
le nom et l'adresse serait rattrapée par un identifiant partagé.

Le score qui sort de la phase 3, bonus compris, s'appelle
`score_approfondi_ajuste`. C'est celui à lire pour juger un candidat : c'est le
dernier calculé, et c'est lui que le classement par seuil utilise.

---

## Les phases en détail

### Phase 0 — validation des codes commune

Le code commune n'est pas seulement une donnée à contrôler : il porte le
blocking. Il détermine le département, donc la maille communale de la phase 2 et
la maille départementale de la phase 3. Un code obsolète compare une structure
aux candidats d'une commune qui n'existe plus, et elle ressort sans candidat.

Chaque code est confronté à la table de passage INSEE, au sein du notebook 03.

| Statut | Situation | Action |
|---|---|---|
| `VALIDE` | code actif au 01/01/2026 | conservé |
| `ARRONDISSEMENT` | arrondissement de Paris, Lyon, Marseille | conservé |
| `CORRIGE` | code disparu, successeur unique | remplacé |
| `AMBIGU` | code disparu, plusieurs successeurs | conservé, successeurs listés |
| `HORS_COG` | préfixe 97/98 absent de la table | conservé |
| `INCONNU` | absent sans explication | conservé, signalé |
| `ABSENT` | code vide | conservé |

Un code toujours actif est conservé même après une fusion ou une scission : sur
les 23 codes scindés de la table, 22 survivent et un seul est réellement
ambigu. Aucune structure n'est écartée ; les cas douteux portent `cog_anomalie`
et la liste de leurs successeurs possibles.

Les codes d'arrondissement ne figurent pas dans la table de passage. Sans règle
dédiée, Paris, Lyon et Marseille sortiraient tous en `INCONNU`.

**La Corse.** `pretraiter_code_commune` conserve la lettre des codes `2A` et
`2B`, des deux côtés — FINESS et SIRENE. Sans cette précaution `2A004` devient
`02004`, un code de l'Aisne, et toute la Corse part dans le mauvais département.
Toute modification de cette normalisation impose de relancer le notebook 03, qui
reconstruit les partitions.

### Phase 1 — matching exact

Jointure sur le SIRET ou le SIREN déclaré dans FINESS, puis scoring de la paire
obtenue. Le rapprochement est donné, le scoring sert à le vérifier : un
identifiant déclaré peut être erroné, et c'est justement ce qu'on cherche.

### Phase 2 — probabiliste, maille communale

Les structures non validées sont comparées aux candidats de leur propre commune.
Les cinq meilleurs sont conservés, classés sur le score global.

Côté sirenisation, le périmètre est découpé en trois sous-ensembles : **A** pour
les PM rattachées à au moins un établissement, **B** pour celles sans
établissement mais avec un SIREN renseigné, **C** pour les autres.

Côté siretisation, les candidats viennent de l'échantillon produit par
`ST-02bis`, restreint aux SIREN issus de la sirenisation.

### Phase 3 — probabiliste élargie

La recherche s'étend au département, avec deux critères supplémentaires qui
entrent dans la pondération.

| APE | Date | Pondération |
|---|---|---|
| oui | oui | 0.70 × global + 0.20 × ape + 0.10 × date |
| oui | non | 0.80 × global + 0.20 × ape |
| non | oui | 0.80 × global + 0.20 × date |
| non | non | score global seul |

**Score APE** : 100 si les codes sont identiques, 70 pour la même classe, 40
pour le même groupe, 20 pour la même division, 0 sinon.

**Score date** : 100 si l'écart est d'un an ou moins, puis 80 à trois ans, 60 à
cinq, 40 à dix, 20 à vingt, 0 au-delà.

La phase 3 reprend tout ce que la phase 2 n'a pas validé, `NON_FIABLE_APE`
compris : une structure bloquée par le contrôle d'activité sur sa commune peut
trouver au département un candidat dont l'activité convient.

### Contrôle du domaine d'activité — établissements, phases 2 et 3

Une validation par le score ne suffit pas. Un candidat peut avoir le bon nom et
la bonne adresse mais une activité étrangère au champ FINESS : une SCI qui
détient les murs d'une clinique lui ressemble beaucoup, sans être elle.

Un candidat n'est acceptable que si son code APE est **identique** à celui de la
structure, ou s'il relève du **domaine** sanitaire, social ou médico-social.

La sélection se fait en deux passes, dans cet ordre.

**Première passe — l'égalité exacte.** On cherche, parmi tous les candidats du
top, celui dont le code APE est exactement celui déclaré pour la structure dans
FINESS. Il est retenu quel que soit son rang, et même si un code identique
figure par ailleurs dans la liste d'exclusion : deux répertoires qui déclarent
la même activité constituent le signal le plus fort dont on dispose.

**Seconde passe — le domaine.** À défaut d'égalité exacte, on retient le
candidat du meilleur rang dont l'APE relève du domaine FINESS.

Le statut du candidat n'entre pas dans la sélection. Il est reporté en sortie,
jamais utilisé comme filtre : un candidat `DOUTEUX` portant exactement le code
APE de la structure l'emporte sur trois candidats `VALIDE` dont l'activité ne
fait que relever du domaine.

Quand aucune des deux passes n'aboutit, la structure ressort en
`NON_FIABLE_APE`. Elle repart en phase 3, puis vers le classement par autorité
si elle reste bloquée.

Une structure sans APE au référentiel est jugée sur le seul critère du domaine,
et c'est le meilleur rang qui gagne.

Le domaine repose sur trois divisions cœur — 86 santé humaine, 87 hébergement
médico-social, 88 action sociale — complétées de codes ponctuels légitimes, avec
une liste d'exclusion pour les codes support et patrimoniaux. Hors égalité
exacte, l'exclusion l'emporte sur l'appartenance à une division cœur.

Le code APE et l'année d'ouverture sont rattachés dès la construction du
périmètre, dans `ST-02`. La phase 2 s'en sert pour filtrer, la phase 3 les fait
en plus entrer dans la pondération du score.

Le contrôle laisse sa trace en colonnes, décrites plus bas dans les livrables.

---

## Comparaison de cohérence

Pour chaque établissement validé, on vérifie que les neuf premiers chiffres de
son SIRET correspondent au SIREN validé de sa personne morale, rattachée par
`NB_PmSmsseId`.

| Statut | Signification |
|---|---|
| `COHERENT` | les deux validés, les identifiants concordent |
| `INCOHERENT` | les deux validés, les identifiants divergent |
| `PARTIEL_EG` | établissement validé, personne morale non validée |
| `PARTIEL_EJ` | personne morale validée, aucun établissement validé |
| `ORPHELIN` | établissement validé sans personne morale rattachée |

Les trois phases sont fusionnées à la volée, en cascade : tout le P1, puis du P2
ce qui n'y est pas validé, puis du P3 ce qui ne l'est ni en P1 ni en P2. Seul le
rang 1 est retenu pour les phases probabilistes.

Deux fichiers en sortie : la vue globale, et le découpage par couple de phases
qui distingue les cohérences P1/P1, P2/P2, P3/P3 et mixtes.

---

## Livrables

```
results/
├── phase0_cog/     phase0_codes_commune.xlsx
├── sirenisation/   phase1.xlsx, phase2_top5.xlsx, phase3_approfondi.xlsx
├── siretisation/   les trois équivalents
├── comparaison/    coherence_globale.xlsx, coherence_par_phase.xlsx
├── verif_ape/      contrôle du domaine d'activité et base de comparaison (annexe)
├── routage/
│   ├── sirenisation/   un classeur par autorité, plus frolant_seuil/ et hors_seuil/
│   └── siretisation/   idem
├── model_logit/    métriques, calibration, table de seuils (annexe)
└── graphiques/     figures de restitution (annexe)
```

Chaque fichier de phase porte une feuille par statut, plus une synthèse. Le code
couleur est constant : vert foncé pour `VALIDE_FORT`, vert pour `VALIDE`, orange
pour `DOUTEUX`, rouge pour `REJETE`, gris pour les cas sans information, violet
pour `NON_FIABLE_APE`.

### Les colonnes du contrôle d'activité

Les exports de siretisation des phases 2 et 3 portent la trace du contrôle.

| Colonne | Contenu |
|---|---|
| `ape_finess` | le code APE de la structure, au référentiel |
| `ape_candidat` | le code APE du candidat, côté SIRENE |
| `ape_identique` | les deux codes sont égaux |
| `ape_dans_domaine` | le code du candidat relève du domaine FINESS |
| `ape_acceptable` | l'une des deux conditions est remplie |
| `motif_ape` | `IDENTIQUE`, `DOMAINE` ou `AUCUN` |
| `candidat_retenu` | vrai sur la ligne que le contrôle a choisie |
| `rang_retenu` | le rang de cette ligne |
| `statut_structure` | le verdict au niveau de la structure |

`ape_finess` est placée juste après l'adresse de la structure, avant les colonnes
du candidat. C'est la première à lire : sans elle, aucune décision du contrôle
n'est vérifiable.

### Les fichiers de cohérence

`coherence_globale.xlsx` compte quatre feuilles : `Synthese` au niveau personne
morale, `Coherent`, `Incoherent`, et `Partiel` qui regroupe les trois statuts
partiels avec une colonne indiquant lequel des deux côtés est validé.

`coherence_par_phase.xlsx` en compte huit : une synthèse à deux tableaux, puis
les cohérents répartis par couple de phases, les incohérents, et les partiels de
chaque côté.

---

## Arborescence

```
projet_finess_plus_sirene/
├── README.md
├── requirements.txt
├── config/
│   └── settings.py            chemins, seuils, poids, conventions
├── data/
│   ├── raw/sirene/            parquets INSEE
│   ├── referentiels/          APE, dates, catégories, table COG
│   ├── interim/               extractions brutes
│   └── processed/             données normalisées et partitionnées
├── src/
│   ├── connexion.py           SQL Server et DuckDB
│   ├── chargement.py          requêtes FINESS+, contacts, événements
│   ├── pretraitement.py       normalisations
│   ├── cog.py                 validation des codes commune
│   ├── scoring.py             formules, APE et date
│   ├── scoring_vectorise.py   moteur matriciel des phases 2 et 3
│   ├── phases.py              orchestration et blocking
│   ├── matching.py            règles de validation
│   ├── sirenisation.py        PM ↔ unités légales, périmètre A/B/C
│   ├── siretisation.py        EGE ↔ établissements
│   ├── domaine_ape.py         contrôle du domaine d'activité
│   ├── referentiel.py         APE et dates externes
│   ├── comparaison.py         cohérence SIREN ↔ SIRET
│   ├── autorites.py           référentiel MOA et résolution territoriale
│   ├── routage.py             routage vers les autorités (annexe)
│   ├── phase1bis.py           rejeu adresse historique (annexe)
│   ├── logit.py               score de confiance, modèle DREES (annexe)
│   ├── drees.py               reprise des propositions DREES (annexe)
│   ├── excel_export.py        exports
│   └── display.py             affichage Jupyter
├── notebooks/
│   ├── 01_chargement_finess.ipynb
│   ├── 02_chargement_sirene.ipynb
│   ├── 03_pretraitement.ipynb
│   ├── sirenisation/          SN-01, SN-01bis (annexe), SN-02, SN-03, SN-04
│   ├── siretisation/          ST-01, ST-02, ST-02bis, ST-03, ST-04
│   ├── comparaison/           COMP-01, GRAPH-01 (annexe)
│   ├── verif_ape/             EXP-01 (annexe)
│   ├── classement_par_AE/     SN-06, ST-06, SN-ST-07 (annexes)
│   └── model_logit/           LOGIT-01, LOGIT-02 (annexes)
└── results/
```

---

## Ce qui change par rapport à `dwh_structure`

### Le modèle de données

| Ancien | FINESS+ |
|---|---|
| `dwh_structure`, filtre `typeidpm_stru` | deux tables : `T_FAC_PmSmsse`, `T_FAC_Ege` |
| `idstructure_stru` | `ID_PmSmsse` / `ID_Ege` et `NB_PmSmsseId` / `NB_EgeId` |
| `nmfinessej_stru` sur l'EG | `NB_PmSmsseId` sur l'EGE, identifiant entier |
| `nmsiret_stru`, `nmsiren_stru` | `TX_Siret`, `TX_Siren` |
| `raisonsociale_stru` | `TX_NomEgeLong` / `TX_DenominationPm` |
| adresse en colonnes de la structure | table `Adresse`, via une table de liaison |
| email et téléphone en colonnes | table `Telecom`, via une table de liaison |
| `dtfermestruct_stru` | `TX_EtatActif` + `BL_VersionCourante` |
| `cdape_stru`, `dtouvertstruct_stru` | absents — voir ci-dessous |

Les jointures se font sur les identifiants métier `NB_*Id`, stables entre les
versions, jamais sur les clés techniques `ID_*` qui changent à chaque
modification.

Les tables sont historisées : le filtre `BL_VersionCourante = 1` est appliqué
partout. Sans lui, chaque structure remonte autant de fois qu'elle a de versions.

Les noms techniques ne sont pas écrits en dur. `resoudre_tables()` compare les
noms normalisés du catalogue aux noms logiques du macro-modèle, ce qui rend le
chargement insensible au préfixe et à la casse. Les tables de staging `T_Tmp_`
sont écartées.

### L'APE et la date d'ouverture

FINESS+ ne les porte pas. Vérifié par scan du contenu de 156 colonnes texte sur
29 tables : les seules colonnes au format APE proviennent des tables INSEE
importées. Quant à `DT_DateDebutValidite`, elle coïncide exactement avec la date
de mise à jour des métadonnées — c'est la date de version, pas la date
d'ouverture.

| Information | Source retenue |
|---|---|
| APE des PM | `Extraction_PM_codeape*.csv` |
| APE des EGE | `Extraction_EG_codeape*.csv` |
| Date d'ouverture des EGE | `Extraction_EG_dateouverture*.csv` |
| Date d'ouverture des PM | table `Evenement`, code `001` |

Pour les PM, on retient les événements de code `001` portant sur un objet de
type `PM`, et la date la plus ancienne quand une structure en compte plusieurs.

---

## Performance et mémoire

### Scoring vectorisé

Les phases 2 et 3 calculent leurs scores en matrices plutôt qu'en boucles
Python. Même formule, même résultat : écart nul sur les trois scores, mêmes
candidats retenus, même ordre. Mesuré sur les données réelles, le gain médian
est d'un facteur 99 ; sur un blocking départemental, 207 heures deviennent 2,1.

Deux détails d'implémentation comptent. Tout est en `float64` : en `float32`,
des écarts de l'ordre du centième apparaissent après l'arrondi à deux décimales.
Et les ex æquo sont départagés par l'identifiant SIRENE croissant, ce qui rend
l'ordre reproductible d'une exécution à l'autre.

### Lecture par partition

Les tables SIRENE sont écrites partitionnées par département. Chaque phase lit
un département à la fois : sur Paris, mesuré à 1,23 million d'unités légales, la
lecture passe de 35 secondes et 15 Go à moins de 9 secondes et 1,25 Go.

En phase 2, la lecture reste départementale — seule maille de partitionnement —
et chaque département est ensuite découpé en communes en mémoire. La sélectivité
communale est conservée sans multiplier les accès disque par les 35 000 communes.

### Taille des lots

Le scoring matriciel construit des tableaux `lignes du lot × candidats du bloc`.
`BUDGET_MEMOIRE_GO` dans `config/settings.py` borne la taille des lots. Le
résultat est identique quelle que soit sa valeur, seul le découpage change. À 4
Go, le département le plus dense est traité par lots de 33 structures.

---

## Dépannage

### Le noyau Jupyter s'arrête — mémoire saturée

C'est le cas le plus courant. Rafraîchir la page, exécuter la première cellule
du notebook 01 pour réinstaller les dépendances, puis relancer le notebook
interrompu depuis le début.

Il n'y a pas à tout reprendre : chaque notebook enregistre son résultat sur
disque, en parquet ou en Excel, et le suivant relit ce fichier. En revanche un
notebook interrompu en cours de phase 2 ou 3 repart au premier département, il
n'y a pas de reprise au point d'arrêt.

Baisser `BUDGET_MEMOIRE_GO` réduit le risque sans changer le résultat.

### Un module modifié n'est pas pris en compte

Python garde en mémoire les modules déjà importés. Après avoir remplacé un
fichier de `src/`, redémarrer le noyau et relancer le notebook depuis sa
première cellule. Une erreur qui persiste alors que le correctif est bien sur
disque vient presque toujours de là.

### `Tables introuvables dans le schema dbo`

Le nom technique d'une table a changé. Le message liste les candidats les plus
proches : reporter le nom réel dans `TABLES_LOGIQUES`, en tête de
`src/chargement.py`.

### `Table schema does not match schema used to create file`

Au partitionnement. Un lot ne contient que des valeurs nulles pour une colonne,
et pyarrow lui attribue le type `null`. `traiter_par_lots` et `partitionner`
figent un schéma de référence pour l'éviter : l'erreur signale un écriture
parquet qui passe à côté de ces fonctions.

### `Invalid column name` sur une table FINESS+

Une colonne a été nommée d'après le macro-modèle sans exister au catalogue. Les
modules concernés résolvent leurs colonnes contre `INFORMATION_SCHEMA` et
acceptent plusieurs variantes, en laissant vide ce qu'ils ne trouvent pas. Un
nom écrit en dur est à remplacer par cette résolution, jamais deviné.

### `pandas only supports SQLAlchemy connectable`

Sans effet : la connexion utilise `pyodbc`, comme prévu. L'avertissement est
filtré dans les modules.

### Un fichier Excel ne s'ouvre pas

Le volume dépasse le million de lignes par feuille. Restreindre les colonnes
exportées ou scinder l'export.

---

## Traitements annexes

Ces notebooks ne font pas partie de la chaîne. Ils lisent ses résultats et
n'écrivent rien qu'elle consomme : les lancer ou non ne change pas les fichiers
produits par les phases. Ils s'exécutent après, dans l'ordre que l'on veut.

### SN-01bis — rejeu de l'adresse historique

`notebooks/sirenisation/` · module `src/phase1bis.py`

Quand la phase 1 n'aboutit pas à un `VALIDE_FORT`, on retente la validation du
SIREN déjà lié en comparant l'adresse FINESS aux adresses historiques du SIREN
dans SIRENE.

L'idée est métier. L'adresse d'une PM dans FINESS n'a souvent pas été mise à
jour alors que le siège a déménagé. L'ancienne adresse est en général encore
présente dans SIRENE, sous la forme d'un autre établissement du même SIREN,
souvent fermé. On reconstitue donc les adresses candidates à partir de tous les
établissements du SIREN — siège, secondaires et fermés — et on garde le meilleur
score.

Seul le score adresse est recalculé, le score nom n'en dépendant pas. Le rejeu
ne peut qu'améliorer un statut, jamais le dégrader.

Sortie : `results/sirenisation/sirenisation_phase1bis.xlsx`. L'indicateur à
regarder est la réduction du volume partant en phase 2.

### SN-06 et ST-06 — routage vers les autorités d'enregistrement

`notebooks/classement_par_AE/` · modules `src/autorites.py` et `src/routage.py`

Les structures qui ressortent douteuses, rejetées ou non fiables ne sont pas
abandonnées : elles sont orientées vers l'autorité compétente, qui arbitrera. Un
classeur Excel par autorité, prêt à être envoyé, avec les coordonnées de la
structure.

L'autorité se déduit de la catégorie d'établissement et du département, via le
référentiel MOA. Pour une personne morale, dont la catégorie n'est pas
renseignée, elle vient de ses établissements : héritage direct s'il n'y en a
qu'un, famille majoritaire parmi les domaines des catégories s'il y en a
plusieurs, la majorité devant être stricte.

Les structures que cette règle ne résout pas sont reprises avec l'autorité
déclarée dans FINESS+, lue sur le dernier gestionnaire ayant mis à jour la
structure. `autorite_source` indique par quel chemin la résolution a été
obtenue.

Les codes produits suivent le jeu de valeurs J359 : `DRHIL-11` pour
l'Île-de-France, `DEETS` en Outre-mer, `DREETS` ailleurs. La table
`Gestionnaire` ne respecte pas ce référentiel — elle écrit `DRIHL-11` et des
`DREETS` ultramarins — et les valeurs sont ramenées à la norme à la lecture.

Les coordonnées viennent de la liaison contact puis de la table `Telecom`,
pivotée par canal. Les coordonnées de tous les contacts d'une structure sont
regroupées, ceux-ci étant souvent spécialisés : l'un porte le téléphone, l'autre
le mail. Le décompte affiché à la lecture porte sur toutes les versions
courantes, actives ou non ; seules les structures du lot routé reçoivent
effectivement leurs coordonnées.

Sorties : `results/routage/sirenisation/` et `results/routage/siretisation/`, un
classeur par autorité plus un `A_ARBITRER` et un `NON_DETERMINEE`. Le dossier est
purgé avant écriture, pour qu'une autorité sans cas ne laisse pas traîner son
fichier précédent.

### SN-ST-07 — séparation des non résolus avant routage

`notebooks/classement_par_AE/` · même modules

Même routage que ci-dessus, mais les non résolus sont scindés en deux lots
exportés séparément, pour ne pas mélanger dans un même classeur les dossiers
rattrapables et ceux qui ne le sont pas.

**Frôlant le seuil.** Les structures qui ont au moins un candidat dont le
`score_approfondi_ajuste` tombe entre 50 et 66,99, juste sous le seuil de
validation. Seuls ces candidats sont conservés : si une structure en a trois et
qu'un seul est dans la plage, les deux autres sont abandonnés. Le rang est
renuméroté, le rang d'origine restant en colonne `rang_origine`.

Les structures `NON_FIABLE_APE` rejoignent ce lot quel que soit leur score, avec
leur top entier : elles ont un score suffisant et n'ont été écartées que sur la
divergence de code APE.

**Le reste.** Les `DOUTEUX` dont aucun candidat n'atteint 50, et les `REJETE`.
Aucun filtrage de candidat.

Le partage est exclusif, et contrôlé comme tel : une structure est dans un lot ou
dans l'autre, jamais dans les deux, jamais dans aucun.

Sorties : `frolant_seuil/` et `hors_seuil/` sous chacun des deux dossiers de
routage.

### LOGIT-01 et LOGIT-02 — score de confiance

`notebooks/model_logit/` · modules `src/logit.py` et `src/drees.py`

Régression logistique pondérée qui attribue à chaque rapprochement une
probabilité d'être correct, en complément du score déterministe. `LOGIT-01`
reproduit le modèle de la DREES à l'identique, sur son échantillon revu à la
main ; `LOGIT-02` le réajuste sur nos propres données FINESS+.

C'est un outil d'arbitrage et d'échange avec la DREES, pas un maillon de la
chaîne : aucune décision de phase n'en dépend. Le détail des métriques, de la
calibration et de la table de seuils est dans `README_logit.md`.

Sortie : `results/model_logit/`.

### GRAPH-01 — restitution graphique

`notebooks/comparaison/`

Camemberts de répartition des statuts, histogrammes empilés par phase, synthèse
de cohérence. Chaque entité est ramenée à un verdict unique : la première phase
où elle est validée, ou sa trace dans la dernière phase où elle apparaît. Les
décomptes portent donc sur des structures distinctes, pas sur des candidats.

Sortie : `results/graphiques/`.
