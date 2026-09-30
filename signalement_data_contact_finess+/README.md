# Mise en qualité des données de contact — FINESS+

Deux contrôles qualité sur l'annuaire FINESS, l'un sur les **adresses email**,
l'autre sur les **numéros de téléphone**. Chaque contrôle tourne sur les deux
niveaux — établissements (EGE) et personnes morales (PM) — et produit un
classeur Excel de signalement destiné aux gestionnaires. Un troisième chantier
route ces signalements vers l'autorité d'enregistrement compétente.

Le principe est le même des deux côtés : on privilégie la précision sur le
rappel. Un signal n'est levé que sur preuve suffisante, et les signaux faibles
restent informatifs pour ne pas noyer les vraies anomalies sous des faux
positifs.

Cette version travaille sur le modèle **FINESS+** (`BIFINESS_DWH_SNAPSHOT`), qui
remplace `dwh_structure`.

---

## Ce qui change par rapport à `dwh_structure`

### Les coordonnées ne sont plus des colonnes de la structure

C'est le changement structurant. `email_stru` et `telephone_stru` étaient portés
par `dwh_structure`. Dans FINESS+, une coordonnée est une ligne de la table
`Telecom`, atteinte par une table de liaison :

```
PM_SMSSE --< PmSmsseContact >-- Contact --< Telecom
EGE      --< EgeContact     >-- Contact --< Telecom
```

`src/chargement.py` fait cette jointure et **pivote les télécoms par canal** :
une ligne par contact, une colonne par type. Sans ce pivot, une structure ayant
un mail et un téléphone occuperait deux lignes.

`TX_Canal` porte un code numérique malgré son préfixe `TX_` : 2 pour le
téléphone, 3 pour le mail, 6 pour la télécopie. D'où les colonnes
`TEL_TELEPHONE`, `TEL_MAIL` et `TEL_TELECOPIE`.

### Le référentiel externe d'emails PM disparaît

L'ancienne chaîne devait joindre un CSV fourni à part, les entités juridiques
n'ayant pas d'email dans `dwh_structure`. Les personnes morales portent
désormais leurs coordonnées nativement, par la même liaison que les
établissements. Le fichier n'est plus nécessaire.

### Correspondance des colonnes

| Ancien | FINESS+ |
|---|---|
| `idstructure_stru` | `NB_EgeId` / `NB_PmSmsseId` |
| `nmfinessetab_stru` | `TX_NumFinessEge` |
| `nmfinessej_stru` | `TX_NumFinessPm`, et `NB_PmSmsseId` pour le rattachement |
| `raisonsociale_stru` | `TX_NomEgeLong` / `TX_DenominationPm` |
| `categetab_stru` | `TX_CategorieEntiteGeographiqueExercice` |
| `cdcommune_stru` | `TX_CogCommune` |
| `lbvoie_stru` | `TX_LibelleVoie`, et `adresse_complete` reconstituée |
| `email_stru` | `TEL_MAIL` |
| `telephone_stru` | `TEL_TELEPHONE` |
| `dtfermestruct_stru` | `TX_EtatActif` + `BL_VersionCourante` |

Le rattachement d'un établissement à sa personne morale passe par
`NB_PmSmsseId`, un entier, là où l'ancien modèle comparait des numéros FINESS
sous forme de chaînes — source de faux négatifs de formatage.

Les tables FINESS+ sont historisées : le filtre `BL_VersionCourante = 1` est
appliqué dans toutes les requêtes.

Les noms techniques ne sont pas écrits en dur. `resoudre_tables()` compare les
noms normalisés du catalogue aux noms logiques du macro-modèle, ce qui rend le
chargement insensible au préfixe (`T_FAC_`, `T_DIM_`) et à la casse.

### Le routage des personnes morales

La catégorie d'établissement est un attribut d'EGE. L'ancienne chaîne remontait
l'autorité depuis les établissements fils et partait en arbitrage dès qu'ils
divergeaient. La règle est désormais alignée sur celle du classement par AE de
la sirenisation :

- **un seul établissement rattaché** → la PM hérite intégralement de son
  résultat, code, statut et motif compris ;
- **plusieurs** → la famille d'autorité majoritaire parmi les domaines des
  catégories des fils l'emporte. Sanitaire et médico-social votent ARS, social
  et formation votent solidarités. La majorité doit être stricte : sur deux fils
  de familles différentes, aucune ne l'emporte et la PM part en arbitrage avec
  le motif `domaine_fils_partage`.

Les logiques d'analyse email et téléphone sont inchangées.

---

## Arborescence

```
config/
  config.ipynb          connexion pyodbc à BIFINESS_DWH_SNAPSHOT
src/
  chargement.py         requêtes FINESS+, pivot des télécoms
  email_checker.py      analyse des emails
  tel_checker.py        analyse des téléphones
  autorites.py          référentiel MOA et résolution territoriale
  routage_contact.py    routage des signalements vers les autorités
data/referentiels/      fichiers de référence (voir plus bas)
notebooks/
  email/                signalement_adresses_ege / _pm
  tel/                  signalement_tel_ege / _pm
  classement_AE/        EMAIL-AE_routage_autorites / TEL-AE_...
results/
  email/  tel/          classeurs de signalement
  classement_AE/        un classeur par autorité, par famille
```

Les modules ne font que l'analyse ; la synthèse et l'export Excel vivent dans
les notebooks. Chaque notebook lit `config/config.ipynb` qui fournit la
connexion `conn`, charge les référentiels, interroge FINESS+, applique le
module, puis écrit un classeur dans `results/`.

Tous les notebooks sont à deux niveaux sous la racine et remontent avec
`sys.path.insert(0, os.path.abspath('../..'))`.

---

## Prérequis

Accès Citrix au serveur SQL FINESS+, driver ODBC 17 for SQL Server, et les
référentiels dans `data/referentiels/` :

| Fichier | Source |
|---|---|
| `tlds-alpha-by-domain.txt` | liste IANA des extensions, https://data.iana.org/TLD/tlds-alpha-by-domain.txt |
| `prenom.csv`, `patronymes.csv` | bases de noms data.gouv, colonnes (nom, fréquence) |
| `communes-france-2026.csv` | communes, département, région, population — data.gouv « Communes et villes de France » |
| `FINESS_Categories_etablissements_V3_Ouverts.csv` | référentiel MOA des catégories, pour le routage |

---

## Contrôle des emails

Pour chaque email : un niveau et un code d'anomalie, une classification de la
partie locale, une correspondance avec la raison sociale ou l'adresse, et une
détection géographique.

Niveaux : **1** critique (email inutilisable — format, domaine inexistant, typo,
TLD inconnu), **2** à surveiller (doublon, service grand public), **0** valide.

Classification de la partie locale : `GENERIQUE`, `INSTITUTIONNEL`, `NOMINATIF`,
`NOMINATIF_PARTIEL`, `INDETERMINE`. On ne déclare nominatif que sur preuve forte
— prénom fréquent et structure plausible — sinon `INDETERMINE`. Le filtrage des
bases de noms par fréquence est le principal garde-fou anti-faux-positifs.

Deux colonnes géographiques : `geo_local` indique si l'adresse porte un nom de
ville, département ou région ; `geo_concordant` dit si ce lieu tombe dans le
département de la structure. La concordance est au grain département, ce qui
couvre les arrondissements et les communes voisines. Le signal utile est
« porte un lieu **non** concordant » — tête de réseau, boîte mutualisée, ou
incohérence à vérifier.

Côté EGE, la correspondance compare la partie locale à la dénomination de
l'établissement **et** à celle de sa personne morale parente, récupérée sur
`NB_PmSmsseId`.

Feuilles du classeur : Synthèse, Emails_Vides, Anomalies_Critiques, Doublons,
Grand_Public, Emails_Valides, Nominatifs, Indetermines.

---

## Contrôle des téléphones

Le numéro est d'abord nettoyé (format national `0XXXXXXXXX`) puis classé en un
seul passage :

- `MANQUANT` — absent, faux vide (`0`, `00`…), placeholder
- `ANOMALIE_CRITIQUE` — structure invalide, ou motif bidon (répétitions, séquences)
- `SURTAXE` — 08 payant (`081`/`082`/`089`)
- `MOBILE` — 06/07
- `INCOHERENCE_GEO` — zone du fixe 01-05 ≠ zone de la commune
- `DOUBLON` — numéro exploitable partagé par plusieurs structures
- `VALIDE` — fixe cohérent, 09, ou 08 vert (`080x`)

La cohérence géographique s'appuie sur la répartition ARCEP des cinq zones (01 à
05) par région (plan national, décision 2018-0881). C'est une heuristique
faible : depuis le 1er janvier 2023 la portabilité des numéros 01-05 est totale,
une incohérence n'est donc pas une erreur mais un point à vérifier.

Feuilles du classeur : Synthèse, Manquants, Anomalies_Critiques, Surtaxes,
Mobiles, Incoherences_Geo, Doublons, Numeros_Valides.

---

## Routage vers les autorités d'enregistrement

Reprend les classeurs déjà produits et affecte à chaque signalement l'autorité
compétente, déduite de la catégorie d'établissement et du département via le
référentiel MOA.

Trois familles sont routées séparément côté email — critiques, nominatifs,
indéterminés — et trois côté téléphone — critiques, surtaxes, manquants. Chaque
famille produit son propre jeu de fichiers, car elles ne relèvent pas de la même
problématique métier.

Statuts de sortie : `RESOLU`, `A_ARBITRER` avec un motif en clair,
`NON_DETERMINEE` avec un motif. `autorite_source` indique comment la résolution
a été obtenue : `CATEGORIE`, `EGE_UNIQUE` ou `MAJORITE_DOMAINE`.

Chaque classeur porte une feuille de synthèse par département, ventilée entre
EGE et PM, et une feuille de données. Le dossier est purgé des classeurs du même
préfixe avant écriture : une autorité qui n'a plus de cas ne doit pas laisser
traîner le fichier de l'exécution précédente.

Un contrôle d'exhaustivité en fin de notebook vérifie qu'aucune structure n'a
été perdue ni dupliquée au découpage.

---

## Lancer un contrôle

Ouvrir le notebook voulu et exécuter les cellules dans l'ordre. La connexion et
les référentiels sont chargés en tête, l'analyse est lancée une seule fois, et
la dernière cellule écrit le classeur dans `results/`.

Les seuls réglages courants côté email sont les seuils de fréquence des noms
(`SEUIL_PRENOM`, `SEUIL_PATRONYME`) et le seuil de population des villes
(`seuil_population` de `charger_geo_insee`).

Les notebooks de routage exigent que les contrôles correspondants aient déjà
produit leurs classeurs.
