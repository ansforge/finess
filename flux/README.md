# 📁 Flux FiNESS — Répertoire des fichiers

Ce répertoire contient tous les **flux utilisés par FiNESS**, organisés en deux grandes catégories : sortants et entrants.  
Il sert de **point d’accès rapide aux fichiers JSON et XML**, ainsi qu’aux exemples de flux.

---

## 📤 Flux sortants

📂 Dossier : [`out/`](./out/)

### 1️⃣ Flux standards (XML historique)

📂 Dossier : [`standard/`](./out/standard/)

- Contient les fichiers **XML** du flux historique FiNESS (33 fichiers)  
- Schémas XSD : [`xsd/`](./out/standard/xsd)  
- Documentation PDF : [`Description_Technique_Flux_standard_FiNESS - V4.1.pdf`](../docs/flux/out/standard/Description_Technique_Flux_standard_FINESS_V4_1.pdf)  

> ⚠️ Accès restreint : nécessite un échange de certificat.

---

### 2️⃣ Flux data.gouv.fr (JSON, Open Data)

📂 Dossier : [`data.gouv/`](./out/data.gouv/)

| Flux | Fichier JSON | Documentation PDF |
|------|--------------|-----------------|
| **activite** | [`schema-activites-v1.json`](./out/data.gouv/activite/schema-activites-v1.json) | [`activite-schema-documentation.pdf`](../docs/flux/out/data.gouv/activite/Specifications%20flux%20Activites.pdf) |
| **structure** | [`schema-structures-v1.json`](./out/data.gouv/structure/schema-structures-v1.json) | [`structure-schema-documentation.pdf`](../docs/flux/out/data.gouv/structure/Specifications%20flux%20Structures.pdf) |

> Accessible en libre consultation, contient les nouveautés FiNESS+, y compris les groupes.

---

## 📥 Flux entrants

📂 Dossier : [`in/`](./in/)

| Flux | Contenu principal |
|------|-----------------|
| **BIO2** | Exemples de fichiers JSON/XML et documents métier (PDF) |
| **PHARMA-SI** | Exemples de fichiers JSON/XML et documents métier (PDF) |
| **SI-Autorisations** | Exemples de fichiers JSON/XML et documents métier (PDF) |

> Chaque sous-dossier contient les fichiers originaux fournis par les partenaires pour l’import dans FiNESS.

---

## 🔗 Liens utiles

- Documentation globale des flux : [`../docs/flux/README.md`](../docs/flux/README.md)  
- Outils de validation JSON/XML : [`../docs/flux/outils-validation/`](../docs/flux/outils-validation/outils-validation.md)  
- Scripts SQL et modèle de données : [`../database/ddl/`](../database/ddl/)
