# Cas d’usage – Transformation du flux Activités JSON FiNESS+ vers un modèle tabulaire

## 📌 Contexte

Le flux JSON FiNESS+ est composé de deux fichiers principaux :

- **Structures** : données descriptives des établissements ;
- **Activités** : données relatives aux activités exercées et autorisées.

Dans le cadre de ce cas d’usage, seul le fichier **Activités** est utilisé.

L’objectif est d’illustrer la transformation d’un flux JSON métier vers un modèle tabulaire exploitable dans une base de données ou un outil d’analyse.

---

## 🎯 Objectif

Ce cas d’usage présente une démarche complète de consommation d’un flux JSON :

- lecture d’un flux Activités FiNESS+ ;
- transformation des données JSON vers un modèle tabulaire ;
- application de règles métier ;
- génération d’un fichier exploitable.

Le détail du mapping et des règles de gestion est disponible dans :

👉 [`mapping.md`](./mapping.md)

---

## 🔄 Chaîne de transformation

```text
Flux Activités JSON FiNESS+
          |
          v
Lecture du fichier JSON
          |
          v
Transformation Python
          |
          v
Modèle tabulaire
          |
          v
Export CSV
```

---

## 📂 Contenu du dossier

```text
finess-activites-json-to-table/

├── README.md
│   → Présentation du cas d’usage

├── mapping.md
│   → Mapping JSON → modèle tabulaire
│   → Règles métier

├── transform.py
│   → Script Python de transformation

└── examples/
    ├── input.json
    │   → Exemple de flux Activités JSON
    │
    └── activites.csv
        → Résultat de transformation
```

---

## 🐍 Exécution

### Prérequis

- Python 3.x
- pandas

Installation :

```bash
pip install pandas
```

### Lancement

Déposer le fichier JSON d’entrée :

```text
input.json
```

Puis exécuter :

```bash
python transform.py
```

Le résultat est généré dans :

```text
activites.csv
```

---

## 🗃️ Modèle tabulaire produit

Le traitement génère une table contenant les informations principales d’activité :

| Champ | Description |
|---|---|
| date_maj | Date de génération du flux |
| activite_finess_pmej | FINESS niveau juridique |
| activite_finess_ege | FINESS niveau opérationnel |
| activite_nature | Nature activité |
| activite_code | Code activité calculé |
| activite_statut | Statut activité |
| activite_capacite_autorisee | Capacité autorisée |
| activite_capacite_installee | Capacité installée |

Le détail des règles de construction est décrit dans :

👉 [`mapping.md`](./mapping.md)

---

## ℹ️ Remarque

Ce cas d’usage constitue un exemple d’exploitation du flux Activités JSON FiNESS+.

Il montre comment un consommateur peut transformer un flux JSON métier en données tabulaires adaptées à ses propres traitements.