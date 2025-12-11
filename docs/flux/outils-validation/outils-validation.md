# Outils de validation des flux JSON

Ce répertoire contient la documentation relative aux outils utilisés pour valider les flux JSON FINESS, qu’ils soient entrants ou sortants.  
Aucun schéma ou fichier de flux n’est stocké ici ; ils se trouvent dans le répertoire racine `flux/` :

- `flux/out/` — schémas JSON et exemples des flux sortants  
- `flux/in/` — exemples des flux entrants  

---

## Objectif

Les outils décrits ici permettent de :

- vérifier qu’un fichier JSON est conforme au schéma attendu ;
- détecter les erreurs de structure ou de typage ;
- automatiser les contrôles lors des développements ou des intégrations.

---

## Pré-requis

Selon l’outil utilisé, il peut être nécessaire d’installer :

- **Python 3.x** avec la bibliothèque `jsonschema`  
ou  
- **Node.js 18+** avec le paquet `ajv-cli`  

---

## Philosophie et bonnes pratiques

- Valider chaque flux JSON avant son intégration.  
- Versionner les schémas JSON et garder les outils synchronisés.  
- Automatiser la validation via CI/CD lorsque possible.  
- Ne modifier les outils qu’au travers de Pull Requests pour assurer traçabilité et qualité.

---

## Exemples génériques d’utilisation

### Exemple 1 : Validation via un script Python
```bash
python validate_json.py --schema chemin/vers/schema.json --input chemin/vers/fichier.json
```

### Exemple 2 : Validation via Node.js / AJV
```bash
ajv validate -s chemin/vers/schema.json -d chemin/vers/fichier.json
```

### Exemple 3 : Exemple de JSON minimal valide
```json
{
  "id": 123,
  "label": "exemple"
}
```

⚠️ Ces exemples sont génériques et ne représentent aucun flux réel.


---

## Outils web alternatifs

Pour des validations rapides et ponctuelles, il est possible d’utiliser des outils en ligne :

- [JSON Schema Validator](https://www.jsonschemavalidator.net/)

- [AJV Online](https://ajv.js.org/)

Ces outils permettent de coller un JSON et un schéma et de vérifier la conformité sans installer de logiciel.
Attention : ne pas utiliser pour des données sensibles ou pour des validations automatisées à grande échelle.