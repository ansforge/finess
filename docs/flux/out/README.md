# 📤 Flux sortants (out)

Ce dossier contient les **flux sortants publiés par le SI FiNESS**.  
Deux types de flux coexistent : les flux **historiques XML** et les flux **ouverts JSON** publiés sur data.gouv.fr.

---

## 🗂️ Flux standards (XML historiques)

Flux XML utilisés historiquement par FiNESS.  
Ils seront progressivement remplacés par les flux JSON dans le cadre de FiNESS+.

⚠️ **Accès restreint** : nécessite un échange de certificat avec l’ANS.

### 📄 Documentation
- [*Description_Technique_Flux_standard_FiNESS - V4.1.pdf*](./standard/Description_Technique_Flux_standard_FINESS_V4_1.pdf)
  *(Liste des 33 fichiers XML et leurs attributs)*

### 🗂️ Schémas XSD
Disponible dans :  
👉 [`/flux/out/standard/xsd`](../../../flux/out/standard/xsd/)

---

## 🌐 Flux data.gouv.fr (JSON ouverts)

Flux modernes, complets, publiés en **accès libre** au format JSON.  
Ils incluent les nouveautés (ex. groupements).

### 📄 Documentation PDF
- 🏢 **Structures** :  
  👉 [`Spécifications Structures`](../../flux/out/data.gouv/structure/Specifications%20flux%20Structures.pdf)
- 📊 **Activités** :  
  👉 [`Spécifications Activités`](../../flux/out/data.gouv/activite/Specifications%20flux%20Activites.pdf)

### 🧩 Schémas JSON
- 🏢 **Structures** :  
  👉 [`schema-structures-v1.json`](../../../flux/out/data.gouv/structure/schema-structures-v1.json)
- 📊 **Activités** :  
  👉 [`schema-activites-v1.json`](../../../flux/out/data.gouv/activite/schema-activites-v1.json)

---

## 🔧 Outils de validation

Les outils de validation JSON sont décrits ici :  
👉 [`docs/flux/outils-validation/README.md`](../outils-validation/outils-validation.md)
