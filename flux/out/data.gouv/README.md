## 📁 Organisation des flux

Chaque flux est structuré de la manière suivante :

### 📦 `schema/`
Contient le **schéma JSON** du flux.  
Il définit la structure des données, les champs attendus ainsi que les règles de validation.  
Ce fichier constitue le **contrat de données** à respecter.

---

### 📄 `examples/`
Contient des **exemples de fichiers JSON** conformes au schéma.  
Ils permettent d’illustrer le format attendu et de faciliter la prise en main du flux.

---

### ⚙️ `api/`
Contient les **fichiers techniques (YAML)** destinés aux développeurs.  
Ils permettent notamment de générer du code ou de faciliter l’intégration du flux dans des applications.