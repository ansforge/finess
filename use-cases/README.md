# 💡 Cas d'usage

Cette rubrique regroupe des exemples complets d'exploitation des flux FiNESS.

Chaque cas d'usage présente :

- le contexte et les objectifs
- les flux utilisés
- les règles de gestion appliquées
- le mapping des données
- les scripts associés
- des exemples de fichiers d'entrée et de sortie

---

## 📂 Cas d'usage disponibles

| Cas d'usage | Description |
|---|---|
| [finess-activites-json-to-table](./finess-activites-json-to-table/) | Transformation du flux **Activités JSON FiNESS+** vers un modèle tabulaire avec application des règles métier |

---

## 📁 Structure d'un cas d'usage

Chaque cas d'usage est organisé dans un dossier dédié :

```text
nom-du-cas/
│
├── README.md
│   → Présentation du cas d'usage
│
├── mapping.md
│   → Mapping des données et règles métier
│
├── scripts/
│   → Scripts d'exploitation ou de transformation
│
└── examples/
    → Exemples de fichiers d'entrée et de sortie
```

---

## ➕ Ajouter un nouveau cas d'usage

Pour ajouter un nouveau cas d'usage :

1. Créer un sous-dossier dans `use-cases/`.
2. Ajouter un fichier `README.md` décrivant le contexte et l'objectif.
3. Documenter le mapping et les règles de gestion.
4. Ajouter les scripts nécessaires.
5. Fournir des exemples de fichiers d'entrée et de sortie.

L'objectif est de proposer des exemples reproductibles permettant aux consommateurs de mieux exploiter les flux FiNESS.