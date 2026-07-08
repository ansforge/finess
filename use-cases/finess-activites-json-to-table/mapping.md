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

| Condition | Valeur du statut |
|---|---|
| etatObjet = "I" | 3 |
| etatObjet = "A" et dernier événement = 12 | 1 |
| Autres cas | 2 |

### Traitement des événements

Pour le calcul du statut :

1. récupérer les événements associés à l'activité
2. filtrer les événements nécessaires
3. trier par date décroissante
4. retenir l'événement le plus récent

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

Lorsqu'une restitution détaillée par appareil est nécessaire :

- utiliser la structure `caracteristiquesSpecifiques.appareil` ;
- générer une ligne par appareil ;
- conserver le rattachement à l'activité AMM d'origine.

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

---

# 4.4 Jointure activités autorisées / installées

La correspondance est réalisée entre :

| Activité exercée | Activité autorisée |
|---|---|
| identifiantAutorisation | activiteAeId |

Règles :

- rechercher l'autorisation correspondante ;
- récupérer la capacité autorisée associée ;
- si aucune correspondance n'est trouvée : valeur = 0.

---

# 4.5 Calcul des capacités

Les capacités sont calculées sans granularité complémentaire :

- mode de financement ;
- habilitation ;
- type de logement ;
- genre.

| Type de capacité | Valeur statutCapacite |
|---|---|
| Capacité installée | 09 |
| Capacité autorisée | 01 |

Valeur par défaut :

```text
0
```

---

# 5. Résultat attendu

Le résultat produit correspond à une ligne tabulaire exploitable par :

- une base relationnelle
- un entrepôt de données
- un outil de reporting
- une chaîne ETL/ELT