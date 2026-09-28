# Mise en qualité des données de contact FINESS

Deux contrôles qualité sur l'annuaire FINESS (table `dwh_structure` du datawarehouse
`BICOEUR_DWH_SNAPSHOT`), l'un sur les **adresses email**, l'autre sur les **numéros
de téléphone**. Chaque contrôle tourne sur les deux flux — établissements
géographiques (EG) et entités juridiques (EJ) — et produit un classeur Excel de
signalement destiné aux gestionnaires.

Le principe est le même des deux côtés : on privilégie la précision sur le rappel.
Un signal n'est levé que sur preuve suffisante, et les signaux faibles restent
informatifs pour ne pas noyer les vraies anomalies sous des faux positifs.

## Arborescence

```
config/config.ipynb — connexion pyodbc au datawarehouse
src/
  email_checker.py analyse des emails
  tel_checker.py   analyse des téléphones
data/referentiels/ fichiers de référence (voir plus bas)
notebooks/
  email/EMAIL-01_signalement_adresses_eg / EMAIL-02_..._ej
  tel/signalement_tel_eg / signalement_tel_ej
results/
  email/tel/classeurs Excel produits
docs/notes de conception
```

Les modules ne font que l'analyse ; la synthèse et l'export Excel vivent dans les
notebooks. Chaque notebook lit `config.ipynb` (qui fournit la connexion `conn`),
charge les référentiels, requête `dwh_structure`, applique le module, puis écrit un
classeur dans `results/`.

## Prérequis

- Accès au datawarehouse via `config/config.ipynb` (driver ODBC SQL Server).
- Les référentiels dans `data/referentiels/` :
  - `tlds-alpha-by-domain.txt` — liste IANA des extensions
    (https://data.iana.org/TLD/tlds-alpha-by-domain.txt)
  - `prenom.csv`, `patronymes.csv` — bases de noms data.gouv, colonnes (nom, fréquence)
  - `communes-france-2026.csv` — communes + département + région + population
    (data.gouv, « Communes et villes de France »)

## Contrôle des emails

Pour chaque email : un niveau et un code d'anomalie, une classification de la partie
locale, une correspondance avec la raison sociale ou l'adresse, et une détection
géographique.

Niveaux : **1** critique (email inutilisable — format, domaine inexistant, typo, TLD
inconnu), **2** à surveiller (doublon, service grand public), **0** valide.

Classification de la partie locale : `GENERIQUE`, `INSTITUTIONNEL`, `NOMINATIF`,
`NOMINATIF_PARTIEL`, `INDETERMINE`. On ne déclare nominatif que sur preuve forte
(prénom fréquent + structure plausible), sinon `INDETERMINE`. Le filtrage des bases
de noms par fréquence est le principal garde-fou anti-faux-positifs.

Deux colonnes géographiques : `geo_local` indique si l'adresse porte un nom de ville,
département ou région ; `geo_concordant` dit si ce lieu tombe dans le **département**
(ou la région) de la structure. La concordance est au grain département : une ville
détectée concorde dès lors qu'elle appartient au même département que la structure
(ce qui couvre les arrondissements — Paris 8e, Lyon 1er… — et les communes voisines).
Le signal utile est « porte un lieu **non** concordant » (tête de réseau, boîte
mutualisée, ou incohérence à vérifier).

Feuilles du classeur : Synthèse, Emails_Vides, Anomalies_Critiques, Doublons,
Grand_Public, Emails_Valides.

## Contrôle des téléphones

Le numéro est d'abord nettoyé (format national `0XXXXXXXXX`) puis classé en un seul
passage :

- `MANQUANT` — absent, faux vide (`0`, `00`…), placeholder
- `ANOMALIE_CRITIQUE` — structure invalide, ou motif bidon (répétitions, séquences)
- `SURTAXE` — 08 payant (`081`/`082`/`089`)
- `MOBILE` — 06/07
- `INCOHERENCE_GEO` — zone du fixe 01-05 ≠ zone de la commune
- `DOUBLON` — numéro exploitable partagé par plusieurs structures
- `VALIDE` — fixe cohérent, 09, ou 08 vert (`080x`)

La cohérence géographique s'appuie sur la répartition ARCEP des cinq zones (01 à 05)
par région (plan national, décision 2018-0881). C'est une heuristique faible : depuis
le 1er janvier 2023 la portabilité des numéros 01-05 est totale, une incohérence n'est
donc pas une erreur mais un point à vérifier.

Feuilles du classeur : Synthèse, Manquants, Anomalies_Critiques, Surtaxes, Mobiles,
Incoherences_Geo, Doublons, Numeros_Valides.

## Lancer un contrôle

Ouvrir le notebook voulu et exécuter les cellules dans l'ordre. La connexion et les
référentiels sont chargés en tête, l'analyse est lancée une seule fois, et la dernière
cellule écrit le classeur dans `results/`. Les seuls réglages courants côté email sont
les seuils de fréquence des noms (`SEUIL_PRENOM`, `SEUIL_PATRONYME`) et le seuil de
population des villes (`seuil_population` de `charger_geo_insee`).
