# Mapping JSON → Modèle tabulaire

## 1. Source de données utilisée

Le flux JSON FiNESS+ est composé de deux fichiers :

| Fichier | Description |
|---|---|
| Structures | Données descriptives des établissements |
| Activités | Données relatives aux activités exercées et autorisées |

Ce cas d’usage utilise exclusivement le fichier **Activités**.

Les règles de transformation décrites dans ce document portent uniquement sur les données issues du flux Activités.

---

## 2. Objectif

Ce document décrit les règles de transformation appliquées pour convertir le flux JSON FiNESS+ vers un modèle tabulaire.

Le traitement comprend :

- l'extraction des données depuis le JSON
- le calcul de certains attributs métier
- la construction des codes activités
- le calcul des capacités installées et autorisées

---

# 3. Mapping des champs

| Champ cible | Chemin JSON | Règle de transformation | Commentaire |
|---|---|---|---|
| date_maj | generatedAt | Conversion ISO → YYYY-MM-DD | Date de génération du flux |
| activite_finess | ege.numFinessEge | Lecture directe | Niveau opérationnel |
| activite_finess_pm | pmej.numFiness | Lecture directe | Niveau juridique |
| activite_nature | nature.codeNature | Lecture directe | Nature FINESS |
| activite_code | caracteristiquesSpecifiques | Construction métier | Dépend de la nature |
| activite_statut | etatObjet + evenement[] | Calcul métier | Voir règles de gestion |
| capacite_installee | activitesExercees.capacite[] | Calcul métier | Voir règles de gestion |
| capacite_autorisee | activitesAutorisees.capacite[] | Calcul métier | Voir règles de gestion |

---

# 4. Règles de gestion

## 4.1 Calcul du statut de l'activité

| Condition | Code statut | Signification |
|---|---:|---|
| `etatObjet = "I"` | **3** | Activité inactive |
| `etatObjet = "A"` et dernier événement = `12` | **1** | Activité active et mise en œuvre |
| Autres cas | **2** | Activité active mais pas encore mise en œuvre |

### Traitement des événements

Pour les activités ayant `etatObjet = "A"` :

1. filtrer les événements de type **12** et **15** ;
2. trier les événements par date décroissante ;
3. retenir l'événement le plus récent.

> **Précision :** le filtrage des événements **12** et **15** s'applique uniquement pour le calcul du statut des activités dont `etatObjet = "A"`.

---

# 4.2 Construction du code activité

La règle de construction dépend de la nature de l'activité.

| Nature | Construction |
|---|---|
| AASA / ASR | nature + activité + modalité + forme |
| EML | nature + typeEmlId |
| ASDR / ASOCR / AMSR / AER | concaténation des attributs spécifiques |
| AMF | même logique que AASA |
| AMM | activité + modalité + mention + pratique + déclaration |

---

# 4.3 Cas AMM / AppAMM

Le flux JSON source est exploité sans modification.

Lorsqu'un besoin de restitution détaillée par appareil existe, une transformation complémentaire peut être réalisée côté consommateur :

- exploiter la structure `caracteristiquesSpecifiques.appareil`
- générer une ligne par appareil (dénormalisation **1 → n**)
- conserver le rattachement à l'activité AMM d'origine

Cette transformation correspond à une dénormalisation :

```text
Activité AMM
     |
     +-- Appareil 1
     |
     +-- Appareil 2
     |
     +-- Appareil N
```

### Recommandation

Cette approche constitue un choix d'implémentation propre à ce cas d'usage.

Dans le cadre de la réforme des autorisations, les activités sanitaires et les EML convergent vers le modèle **AMM**. A terme, les EML ont vocation à disparaître au profit des seules activités AMM.

Il est donc recommandé d'évaluer l'opportunité de générer des lignes de type **AppAMM**, car cette représentation peut s'éloigner du modèle cible porté par la réforme.

Par ailleurs, lors de cette évolution réglementaire, les caractéristiques des appareils ne sont plus exposées avec le même niveau de détail qu'auparavant.

---

# 4.4 Jointure activités autorisées / installées

La correspondance entre une activité exercée et son activité autorisée est réalisée à partir des identifiants techniques suivants :

| Activité exercée | Activité autorisée |
|---|---|
| `identifiantAutorisation` | `activiteAeId` |

### Description

Le champ `identifiantAutorisation`, renseigné au niveau des **activités exercées**, référence l'identifiant technique `activiteAeId` de l'activité autorisée correspondante.

Cette correspondance permet de rattacher une activité exercée à son autorisation et de récupérer les informations associées, notamment la capacité autorisée.

### Règles de traitement

1. récupérer la valeur de `identifiantAutorisation` de l'activité exercée
2. rechercher l'activité autorisée dont `activiteAeId` correspond à cette valeur
3. récupérer la capacité autorisée associée (`statutCapacite = "01"`)
4. si aucune activité autorisée correspondante n'est trouvée, la capacité autorisée est fixée à **0**


---

# 4.5 Calcul des capacités

Les capacités sont calculées à partir des informations présentes dans le flux JSON.

### Capacité totale

La **capacité totale** correspond à une capacité ne comportant aucune granularité. Les attributs suivants doivent être absents :

- `modeFinancement`
- `habilitation`
- `typeLogement`
- `genre`

Seules ces capacités sont prises en compte dans le calcul.

### Identification des capacités

| Type de capacité | Valeur de `statutCapacite` |
|---|---:|
| Capacité autorisée | `01` |
| Capacité installée | `09` |

### Règles de traitement

- la capacité autorisée est calculée à partir des capacités ayant `statutCapacite = "01"` ;
- la capacité installée est calculée à partir des capacités ayant `statutCapacite = "09"` ;
- seules les capacités totales sont prises en compte ;
- en l'absence de capacité correspondante, la valeur retenue est **0**.

---

# 5. Résultat attendu

Le résultat produit correspond à une ligne tabulaire exploitable par :

- une base relationnelle
- un entrepôt de données
- un outil de reporting
- une chaîne ETL/ELT