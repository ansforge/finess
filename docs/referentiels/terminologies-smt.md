# 📚 Terminologies de santé – SMT

Les flux FINESS s’appuient sur des **terminologies de santé** permettant de coder et qualifier certaines données.

Le **SMT – Serveur Multi-Terminologies** met à disposition ces terminologies sous différents formats et permet également de les interroger via une **API FHIR**.

👉 [Accéder au Serveur Multi-Terminologies (SMT)](https://smt.esante.gouv.fr/)

Cette page présente les différentes façons d'identifier, consulter et interroger les terminologies utilisées dans les flux FINESS :

- 🔗 **Identifier** une terminologie à partir du schéma JSON FINESS,
- 📥 **Télécharger** une terminologie depuis le guide d'implémentation,
- 🔌 **Interroger** une terminologie via l'API FHIR,
- 🔎 **Rechercher** les informations associées à un code particulier.

---

## 🔗 1. Identifier la terminologie dans le schéma JSON

Les terminologies utilisées dans les flux FINESS sont référencées directement dans le **schéma JSON** (par exemple, le [schéma des structures](https://github.com/ansforge/finess/blob/main/flux/out/data.gouv/structure/schema/schema-structures-v1.json)).

Pour les champs utilisant une terminologie, le schéma indique notamment le `system` correspondant à la terminologie SMT.

### Exemple : catégorie d'entité géographique d'exercice

Dans le schéma JSON, le champ `categorieentiteGeographiqueExercice` est défini de la manière suivante :

```json
"categorieentiteGeographiqueExercice": {
  "type": "string",
  "coding": {
    "system": "https://smt.esante.gouv.fr/fhir/CodeSystem/tre-r397-categorie-entite-geographique-exercice"
  }
}
```

Le champ `coding.system` permet d'identifier directement la terminologie SMT utilisée pour ce champ.

Dans cet exemple, le `system` correspond à la terminologie :

> **TRE-R397 – Catégorie entité géographique exercice**

👉 [Accéder à la terminologie TRE-R397](https://ansforge.github.io/IG-terminologie-de-sante/ig/main/CodeSystem-tre-r397-categorie-entite-geographique-exercice.html)

Le consommateur peut ainsi :

1. récupérer dans le schéma JSON l'URL indiquée dans `coding.system`,
2. identifier la terminologie SMT correspondante,
3. accéder à la ressource correspondante dans le SMT,
4. consulter ou interroger la terminologie pour obtenir les informations associées aux codes.

---


## 📥 2. Télécharger une terminologie

Les terminologies sont accessibles depuis le [Guide d’implémentation des terminologies de santé](https://ansforge.github.io/IG-terminologie-de-sante/ig/main/index.html).

### Exemple : TRE-R397

Prenons comme exemple la terminologie :

> **TRE-R397 – Catégorie entité géographique exercice**

### Étapes

1. Accéder au [Guide d’implémentation des terminologies de santé](https://ansforge.github.io/IG-terminologie-de-sante/ig/main/index.html).
2. Dans le menu, sélectionner **Terminologies**.
3. Sélectionner l’onglet **Terminologies du NOS**.
4. Utiliser le champ de recherche et rechercher `R397`.
5. Sélectionner la terminologie **TreR397CategorieEntiteGeographiqueExercice**.
6. Dans la page de la terminologie, sélectionner l’onglet **Téléchargement**.
7. Choisir le format souhaité pour télécharger la terminologie.

👉 [Accéder directement à la terminologie TRE-R397](https://ansforge.github.io/IG-terminologie-de-sante/ig/main/CodeSystem-tre-r397-categorie-entite-geographique-exercice.html)


---


## 🔌 3. Interroger une terminologie via l’API FHIR

Le SMT expose les terminologies au travers d'une **API FHIR**.

Pour une terminologie donnée, il est possible d'effectuer une requête HTTP `GET` sur sa ressource FHIR.

### Exemple : TRE-R397

URL de la ressource FHIR :

```text
https://smt.esante.gouv.fr/fhir/CodeSystem/tre-r397-categorie-entite-geographique-exercice
````

Une requête directe sur cette URL peut retourner une représentation HTML de la ressource dans un navigateur.

Pour demander explicitement une réponse au format **JSON FHIR**, utiliser le paramètre `_format=json` :

```text
https://smt.esante.gouv.fr/fhir/CodeSystem/tre-r397-categorie-entite-geographique-exercice?_format=json
```

### Avec Postman

Dans Postman :

1. Créer une requête **GET**.
2. Renseigner l’URL de la ressource FHIR.
3. Dans les headers, ajouter :

```text
Accept: application/fhir+json
```

4. Envoyer la requête.

Le serveur retourne alors la ressource au format **FHIR JSON**.

### Exemple de requête

```http
GET https://smt.esante.gouv.fr/fhir/CodeSystem/tre-r397-categorie-entite-geographique-exercice
Accept: application/fhir+json
```

---

## 🔎 4. Interroger un code particulier

Il est possible de rechercher directement les informations associées à un code dans une terminologie FHIR à l'aide de l'opération `$lookup`.

### Exemple avec le code `377`

Pour la terminologie **TRE-R397 – Catégorie entité géographique exercice** :

```text
https://smt.esante.gouv.fr/fhir/CodeSystem/$lookup?system=https://smt.esante.gouv.fr/fhir/CodeSystem/tre-r397-categorie-entite-geographique-exercice&code=377
```

### Avec Postman

```http
GET https://smt.esante.gouv.fr/fhir/CodeSystem/$lookup?system=https://smt.esante.gouv.fr/fhir/CodeSystem/tre-r397-categorie-entite-geographique-exercice&code=377
```

La réponse est une ressource FHIR de type `Parameters` contenant les informations associées au code recherché.

Parmi les paramètres retournés :

- `code` correspond au code recherché
- `display` correspond au libellé associé au code
- `name` correspond au nom de la terminologie
- `system` correspond à l'identifiant de la terminologie
- `version` correspond à la version de la terminologie
- `property` permet notamment d'indiquer le statut du code (`inactive`) et son code parent
- `designation` contient les différentes désignations associées au code

Dans cet exemple :

- la désignation `preferredForLanguage` correspond au **libellé préféré** : `Etablissement Expérimental pour Enfance Handicapée`
- la désignation associée au code `900000000000013009` correspond à un **synonyme**, utilisé ici comme **libellé court** : `Etab.Expér.Enf.Hand.`.

### Exemple de réponse

```json
{
  "resourceType": "Parameters",
  "parameter": [
    {
      "name": "code",
      "valueCode": "377"
    },
    {
      "name": "display",
      "valueString": "Etablissement Expérimental pour Enfance Handicapée"
    },
    {
      "name": "name",
      "valueString": "TreR397CategorieEntiteGeographiqueExercice"
    },
    {
      "name": "system",
      "valueUri": "https://smt.esante.gouv.fr/fhir/CodeSystem/tre-r397-categorie-entite-geographique-exercice"
    },
    {
      "name": "version",
      "valueString": "20260601120000"
    },
    {
      "name": "property",
      "part": [
        {
          "name": "code",
          "valueCode": "inactive"
        },
        {
          "name": "value",
          "valueBoolean": false
        }
      ]
    },
    {
      "name": "property",
      "part": [
        {
          "name": "code",
          "valueCode": "parent"
        },
        {
          "name": "value",
          "valueCode": "4107"
        }
      ]
    },
    {
      "name": "designation",
      "part": [
        {
          "name": "language",
          "valueCode": "fr-FR"
        },
        {
          "name": "use",
          "valueCoding": {
            "system": "http://snomed.info/sct",
            "code": "900000000000013009"
          }
        },
        {
          "name": "value",
          "valueString": "Etab.Expér.Enf.Hand."
        }
      ]
    },
    {
      "name": "designation",
      "part": [
        {
          "name": "language",
          "valueCode": "fr-FR"
        },
        {
          "name": "use",
          "valueCoding": {
            "system": "http://terminology.hl7.org/CodeSystem/hl7TermMaintInfra",
            "code": "preferredForLanguage"
          }
        },
        {
          "name": "value",
          "valueString": "Etablissement Expérimental pour Enfance Handicapée"
        }
      ]
    }
  ]
}
```


## 📌 Quelle méthode utiliser ?

| Besoin                                                         | Méthode                           |
| -------------------------------------------------------------- | --------------------------------- |
| Consulter ponctuellement une terminologie                      | 📥 Téléchargement depuis le guide |
| Télécharger une terminologie dans un format donné              | 📥 Onglet **Téléchargement**      |
| Intégrer automatiquement une terminologie dans une application | 🔌 API FHIR                       |
| Récupérer régulièrement les terminologies                      | 🔌 API FHIR                       |
| Tester rapidement une ressource                                | 🔌 Postman / requête HTTP `GET`   |

---

## ⚠️ À retenir

* Le **SMT (Serveur Multi-Terminologies)** est la source d'accès aux terminologies de santé utilisées par les flux.
* Le [Guide d’implémentation des terminologies de santé](https://ansforge.github.io/IG-terminologie-de-sante/ig/main/index.html) permet notamment de consulter et télécharger les terminologies.
* L’**API FHIR du SMT** permet d'accéder aux ressources de manière automatisée.
* Pour obtenir une réponse JSON depuis une URL FHIR, utiliser `_format=json` ou préciser le header :

```text
Accept: application/fhir+json
```

* Pour une intégration applicative, privilégier l'interrogation de l'API plutôt qu'un téléchargement manuel.

```
```
