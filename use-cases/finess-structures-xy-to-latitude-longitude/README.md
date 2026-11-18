# Cas d'usage : retrouver la latitude et la longitude à partir des coordonnées planes du flux Structures

## Contexte

Dans le flux JSON **Structures** FiNESS+, chaque adresse de personne morale (PMEJ) ou d'entité géographique d'exercice (EGE) peut porter un bloc `coordonneesGeographique` avec deux jeux de coordonnées :

- `coordonneeX` et `coordonneeY` : coordonnées planes, en mètres, dans la projection du territoire ;
- `directionLatitude` et `directionLongitude` : latitude et longitude en degrés décimaux (WGS 84).

Certaines adresses portent x et y sans latitude ni longitude. Depuis le fichier mensuel `finess-structures-mensuel-202610`, c'est le cas d'environ 53 000 blocs de coordonnées (voir le ticket [#51](https://github.com/ansforge/finess/issues/51)). Or la plupart des outils de cartographie en ligne et des fonds de carte attendent une latitude et une longitude.

Ce cas d'usage montre comment un consommateur du flux peut déduire la latitude et la longitude de x et y, et vérifier son calcul sur les adresses qui portent les deux.

---

## Objectif

- lire le flux Structures au fil de l'eau, sans le charger en mémoire (environ 770 Mo une fois décompressé) ;
- reconnaître la projection de chaque adresse d'après son département ;
- calculer la latitude et la longitude quand le flux ne les donne pas ;
- contrôler le calcul sur les adresses qui portent x, y, latitude et longitude ;
- produire une table des adresses avec l'origine de chaque position.

Le détail des champs, des projections et des règles de gestion est dans :

[`mapping.md`](./mapping.md)

---

## Chaîne de transformation

```text
Flux Structures JSON FiNESS+ (.json ou .json.gz)
          |
          v
Lecture au fil de l'eau des PMEJ et de leurs EGE
          |
          v
Projection selon le département (Lambert 93 ou UTM)
          |
          v
Latitude et longitude, avec leur origine
          |
          v
Export CSV et bilan de contrôle
```

---

## Contenu du dossier

```text
finess-structures-xy-to-latitude-longitude/

├── README.md
│   → Présentation du cas d'usage

├── mapping.md
│   → Champs utilisés, projections par territoire, règles de gestion

├── transform.py
│   → Script Python de transformation et de contrôle

└── examples/
    ├── input.json
    │   → Extrait du flux Structures (établissements de métropole et d'outre-mer)
    │
    └── coordonnees.csv
        → Résultat de la transformation
```

---

## Exécution

### Prérequis

- Python 3.x

Le script n'utilise que la bibliothèque standard de Python.

### Lancement

Sur l'exemple fourni :

```bash
python transform.py examples/input.json coordonnees.csv
```

Sur un flux complet, téléchargé depuis [data.gouv.fr](https://www.data.gouv.fr/datasets/finess-structures-1) et laissé compressé :

```bash
python transform.py finess-structures-journalier-20261118.json.gz coordonnees.csv
```

Le traitement du flux complet prend une quinzaine de secondes. Sans argument, le script lit `input.json` et écrit `coordonnees.csv`.

---

## Modèle tabulaire produit

Une ligne par adresse qui porte des coordonnées :

| Champ | Description |
|---|---|
| niveau | `PMEJ` ou `EGE` |
| finess | Numéro FINESS de la personne morale ou de l'entité géographique |
| usage_adresse | Usage de l'adresse (`usageAdresse`) |
| cog_commune | Code officiel géographique de la commune |
| coordonnee_x, coordonnee_y | Coordonnées planes du flux, recopiées |
| latitude, longitude | Celles du flux quand il les donne, sinon celles calculées, à six décimales |
| origine | `flux`, `calcul`, ou vide quand x et y n'ont pas pu être convertis |

---

## Contrôle

Le script affiche un bilan à la fin du traitement. Sur le flux journalier du 18 novembre 2026 :

| Mesure | Résultat |
|---|---|
| Adresses avec latitude et longitude données par le flux | 188 437 |
| Adresses dont la position est calculée depuis x et y | 53 422 |
| Adresses avec x et y non converties (Wallis-et-Futuna) | 2 |
| Écart maximal entre la position du flux et la position calculée, sur les 188 437 adresses qui portent les deux | 0,01 m |

Le calcul retombe donc sur les positions publiées, en métropole comme outre-mer.

---

## Remarques

- L'exemple `examples/input.json` est un extrait du flux réduit aux champs utilisés ici ; il ne suit pas tout le schéma du flux.
- Les positions calculées sont arrondies à six décimales, comme celles du flux (environ dix centimètres).
- Les deux adresses de Wallis-et-Futuna ne sont pas converties : aucune adresse de ce territoire ne porte à la fois x, y et une latitude, ce qui ne permet pas de vérifier la projection.
- Une position n'est calculée que si elle tombe dans l'emprise du territoire : une coordonnée aberrante reste sans position plutôt que d'en recevoir une fausse.
- Les mêmes formules existent en JavaScript, avec leurs tests, dans le projet libre [referentiels-sante](https://github.com/Irreductix/referentiels-sante/blob/main/src/commun/projection.js) (licence MIT).
