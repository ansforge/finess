# 🛠️ FINESS – Publication de la webapp & des flux

![License](https://img.shields.io/badge/license-MIT-green)
![Issues](https://img.shields.io/github/issues/ansforge/finess)
![Last Commit](https://img.shields.io/github/last-commit/ansforge/finess)

## 📖 Contexte métier

Le **Fichier National des Établissements Sanitaires et Sociaux (FiNESS)** est le répertoire de référence pour les établissements à caractère **Sanitaire, Social ou Médico-Social**, ainsi que pour la formation aux professions sanitaires et sociales.

### 🔗 Ressources officielles

- 🌐 [Page institutionnelle FiNESS](https://esante.gouv.fr/produits-services/repertoire-finess)  
- 📊 [Accès public aux données FiNESS](https://finess.esante.gouv.fr)  


### 📡 API REST basée sur HL7 FHIR

Une partie des données FiNESS est accessible via l’**API FHIR Annuaire Santé**, conforme à la spécification HL7 FHIR :  
- Documentation API : [Annuaire Santé FHIR](https://ansforge.github.io/annuaire-sante-fhir-documentation)

---

## 🎯 Objectifs

Ce projet vise à publier le code source et la documentation associée à **FiNESS**, afin de :

- 🔄 Partager les **flux outillés** pour faciliter leur prise en charge par d'autres équipes
- 🧩 Rendre accessible le **modèle de données** utilisé dans FiNESS
- 🧑‍💻 Permettre à d'autres développeurs de **proposer des améliorations** ou **remonter des anomalies**

---

## 📁 Arborescence du dépôt

```plaintext
README.md
LICENSE
CONTRIBUTING.md
checklist-publication.md
guide-prise-en-main-github.md

webapp/                 → (à venir) Code source de l’IHM

flux/
├── out/
│   ├── standard/
│   └── data.gouv/
└── in/
    ├── BIO2
    ├── PHARMA-SI
    └── SI-Autorisations

database/
└── ddl/

docs/
└── ...

use-cases/
├── README.md                     → Index des cas d'usage
└── json-to-table/
    ├── README.md                 → Présentation du cas d'usage
    ├── transform.py              → Script Python
    ├── examples/                 → Exemples JSON / CSV
    └── mapping.md                → Mapping et règles métier
```

---

## 📂 Flux FINESS

Tous les flux entrants et sortants sont documentés et organisés pour un accès rapide.

### 🌐 Sommaire global des flux

Pour une vue d’ensemble et un sommaire des flux, consultez le README global :

👉 [`docs/flux/README.md`](./docs/flux/README.md)

Ce README décrit tous les flux sortants et entrants et oriente vers les README spécifiques de chaque sous-dossier.

## 📤 Flux sortants

- 📄 Documentation complète : [`docs/flux/out/`](./docs/flux/out/)
- 📁 Schémas JSON & exemples de flux : [`flux/out/`](./flux/out/)
  - 📌 **Nouveau** : échantillons publiés
    - **Flux `structure`**  
      - **Chemin** : [`flux/out/data.gouv/structure/`](./flux/out/data.gouv/structure/examples/)  
      - **Contenu** : échantillons pour tests rapides et jeu complet  
        - `exemple-finess-structures-journalier-20260309.json` → échantillon pour tests  
        - `complet-finess-structures-20060309.7z` → jeu complet pour traitement exhaustif  

    - **Flux `activité`**  
      - **Chemin** : [`flux/out/data.gouv/activite/`](./flux/out/data.gouv/activite/examples/)
      - **Contenu** : échantillons pour tests rapides et jeu complet  
        - `exemple-finess-activite-journalier-20260309.json` → échantillon pour tests  
>   *Ces échantillons permettent aux développeurs et aux équipes de tester la structure des flux avant d’utiliser les fichiers complets.*
- 🛠️ Outils de validation JSON : [`docs/flux/outils-validation.md`](./docs/flux/outils-validation/outils-validation.md)

## 📤 Flux entrants

- 📄 Documentation complète : [`docs/flux/in/`](./docs/flux/in/)
- 📁 Schémas JSON & Exemples de flux : [`flux/in/`](./flux/in/)


---


## 🗃️ Modèle de données

- 💾 Scripts SQL DDL : [`database/ddl/finess-dll.sql`](./database/ddl/finess-dll.sql)
- 📄 Dictionnaire de données FiNESS : [`/docs/database/README.md`](./docs/database/README.md)


---


## 💡 Cas d'usage

En complément de la documentation des flux, ce dépôt propose des cas d'usage illustrant leur exploitation dans des contextes réels.

Ces exemples montrent notamment :

- la consommation des flux JSON FiNESS
- leur transformation vers un modèle relationnel
- l'implémentation de règles de gestion métier
- l'alimentation de bases de données
- des scripts Python réutilisables

📂 Index des cas d'usage :

👉 [`use-cases/README.md`](./use-cases/README.md)

### Cas d'usage disponibles

| Cas d'usage | Description |
|-------------|-------------|
| JSON vers modèle tabulaire | Transformation du flux d'activités JSON FiNESS+ vers une table relationnelle avec application des règles métier |

---


## 📘 Guides & ressources transverses

📚 Guide de prise en main GitHub : [docs/guides/prise-en-main-github.md](./docs/guides/prise-en-main-github.md)

---


## ❓ FAQ – Questions fréquentes

Consultez la page dédiée :  
👉 [`FAQ.md`](./FAQ.md)

---


## 🤝 Contribution

Avant de proposer une modification, merci de lire le guide de contribution pour connaître les règles de collaboration, de formatage, les bonnes pratiques, ainsi que la procédure pour signaler un bug ou proposer une amélioration via les [Issues](https://github.com/ansforge/finess/issues) :

👉 [`CONTRIBUTING.md`](./CONTRIBUTING.md)

---

## ✅ Publication

Avant de publier une version ou de partager le projet, suivez les étapes listées dans :

👉 [`checklist-publication.md`](./checklist-publication.md)

---

## 🧾 Licence

Ce projet est distribué sous la licence [`MIT`](./LICENSE).
