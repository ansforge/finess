# 📚 Terminologies de santé – SMT

Les flux FINESS s’appuient sur des **terminologies de santé** permettant de coder et qualifier certaines données.

Le **SMT – Serveur Multi-Terminologies** met à disposition ces terminologies sous différents formats et permet également de les interroger via une **API FHIR**.

👉 [Accéder au Serveur Multi-Terminologies (SMT)](https://smt.esante.gouv.fr/)

Cette page présente deux façons d’accéder aux terminologies :

- 📥 **Téléchargement manuel** d'une terminologie depuis le guide d'implémentation
- 🔌 **Interrogation automatisée** d'une terminologie via l'API FHIR.

---

## 📥 1. Télécharger une terminologie

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

## 🔌 2. Interroger une terminologie via l’API FHIR

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

## 🔎 3. Interroger un code particulier

Une fois la ressource `CodeSystem` récupérée, les différents codes et leurs libellés sont disponibles dans les concepts de la terminologie.

Par exemple, pour rechercher un code particulier dans la ressource JSON, il est possible d'utiliser la fonction de recherche de son outil de consultation ou de traitement du JSON.

Exemple :

```text
code = 377
```

La réponse FHIR contient notamment, pour chaque concept :

```json
{
  "code": "377",
  "display": "..."
}
```

Le champ `display` correspond au libellé associé au code.

---

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
