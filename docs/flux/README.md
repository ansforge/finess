# 📤 Flux FiNESS — Documentation générale

Ce répertoire regroupe l’ensemble des **flux FiNESS**, organisés en deux familles :

1. **Flux standards historiques (XML, non publics)**  
2. **Nouveaux flux Open Data destinés à data.gouv.fr (JSON, publics)**  

Ce document décrit leur périmètre, leurs différences et renvoie vers la documentation associée.

---

# 🆚 Différences entre les deux familles de flux

| Caractéristique | Flux standard (XML historique) | Flux data.gouv.fr (nouveaux flux Open Data) |
|-----------------|--------------------------------|----------------------------------------------|
| **Format** | XML + XSD | JSON / tables Open Data |
| **Accès** | 🔐 Accès restreint – nécessite certificat ANS | 🔓 Libre accès, public |
| **Origine** | Format historique FiNESS (pré-FiNESS+) | Nouvelle génération FiNESS+ |
| **Contenu** | Données essentielles, limitées | **Plus complet**, inclut les nouveautés (dont les **groupes** GCO/GCC) |
| **Stabilité** | En voie d’obsolescence | Actif, évolutif et recommandé |
| **Public cible** | Partenaires techniques avec authentification | Grand public Open Data, développeurs, chercheurs |

---

# 1️⃣ Flux standards FiNESS (XML historique)

📁 Dossier : [`standard/`](../../flux//out//standard/)

Les flux standards FiNESS correspondent au **format historique XML** composé de 33 fichiers structurés selon des schémas XSD.

Ils sont aujourd’hui **maintenus uniquement pour compatibilité**.

### 🔐 Accès
- Non publics  
- Requiert un **échange de certificat** avec l'ANS,  
- Consultation via services sécurisés.

### 📄 Documentation technique
- **Description technique du flux standard FiNESS – V4.1**  
  [`Description_Technique_Flux_standard_FiNESS - V4.1.pdf`](./out/standard/Description_Technique_Flux_standard_FINESS_V4_1.pdf)

  → Liste des 33 fichiers XML, leurs attributs et règles de structuration.

### 📂 Schémas XSD
Les schémas associés sont disponibles ici :  
👉 [`/flux/out/standard/xsd`](../../flux/out/standard/xsd/)

---

# 2️⃣ Nouveaux flux destinés à data.gouv.fr (Open Data)

📁 Dossier : [`data.gouv/`](../../flux/out/data.gouv/)

Ces flux constituent la **nouvelle génération** des exports FiNESS destinés à la **publication Open Data**.  
Ils sont en **format JSON**, librement accessibles, et intègrent toutes les nouveautés, notamment :

- les **groupes GCO/GCC**,  
- les informations enrichies des entités juridiques et géographiques,  
- des structures plus complètes et cohérentes.

### ✔ Avantages
- Accès libre et immédiat  
- Documentation publique  
- Données plus complètes que le flux XML historique  
- Aligné avec les standards Open Data  
- Formats simples à manipuler (JSON, CSV, tables)  

### 📄 Documentation et fichiers JSON

#### **Flux “activite”**
- Documentation PDF : [`activite-schema-documentation.pdf`](./out/data.gouv/activite/Specifications%20flux%20Activites.pdf)  
- Fichier JSON : [`schema-activites-v1.json`](../../flux//out/data.gouv/activite/schema-activites-v1.json)

#### **Flux “structure”**
- Documentation PDF : [`structure-schema-documentation.pdf`](./out/data.gouv/structure/Specifications%20flux%20Structures.pdf)  
- Fichier JSON : [`schema-structures-v1.json`](../../flux/out/data.gouv/structure/schema-structures-v1.json)

---

# 🛠️ Outils de validation

Pour valider les flux (JSON ou XML) selon leurs schémas :

👉 [`./flux/outils-validation/`](./outils-validation/outils-validation.md)

---

# 📝 Statut des flux

| Type de flux | Statut | Recommandation |
|--------------|--------|----------------|
| **Standard XML** | 🟠 Maintenu mais en obsolescence | ❌ À éviter pour les nouveaux usages |
| **data.gouv (JSON)** | 🟢 Actif et complet | ✅ Recommandé pour tous les usages |

---
