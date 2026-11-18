# Mapping et règles de gestion : coordonnées planes vers latitude et longitude

## 1. Source de données utilisée

Ce cas d'usage utilise exclusivement le fichier **Structures** du flux JSON FiNESS+.

Les adresses sont lues à deux niveaux :

| Niveau | Chemin JSON | Identifiant |
|---|---|---|
| Personne morale (PMEJ) | `pmej[].adresse[]` | `pmej[].informationsGeneralesPMEJ.numFinessPm` |
| Entité géographique (EGE) | `pmej[].ege[].adresse[]` | `pmej[].ege[].informationsGeneralesEGE.numFinessEge` |

---

## 2. Mapping des champs

| Champ cible | Chemin JSON (dans l'adresse) | Règle de transformation |
|---|---|---|
| niveau | | `PMEJ` ou `EGE` selon l'adresse lue |
| finess | voir le tableau ci-dessus | Lecture directe |
| usage_adresse | `usageAdresse` | Lecture directe |
| cog_commune | `cogCommune` | Lecture directe |
| coordonnee_x | `coordonneesGeographique.coordonneeX` | Lecture directe |
| coordonnee_y | `coordonneesGeographique.coordonneeY` | Lecture directe |
| latitude | `coordonneesGeographique.directionLatitude` | Lecture directe si renseignée, sinon calcul (règle 4) |
| longitude | `coordonneesGeographique.directionLongitude` | Lecture directe si renseignée, sinon calcul (règle 4) |
| origine | | `flux`, `calcul` ou vide (règle 5) |

Une adresse qui ne porte ni x et y, ni latitude et longitude, n'est pas écrite dans la table ; elle est comptée dans le bilan.

---

## 3. Projection des coordonnées planes

Le département est déduit du code commune : les trois premiers caractères quand il commence par `97` ou `98`, les deux premiers sinon.

| Territoire | Départements | Projection de x et y | Système légal | Code EPSG |
|---|---|---|---|---|
| Métropole et Corse | `01` à `95`, `2A`, `2B` | Lambert 93 | RGF93 | 2154 |
| Guadeloupe, Saint-Barthélemy, Saint-Martin | `971`, `977`, `978` | UTM fuseau 20 nord | RGAF09 | 5490 |
| Martinique | `972` | UTM fuseau 20 nord | RGAF09 | 5490 |
| Guyane | `973` | UTM fuseau 22 nord | RGFG95 | 2972 |
| La Réunion | `974` | UTM fuseau 40 sud | RGR92 | 2975 |
| Saint-Pierre-et-Miquelon | `975` | UTM fuseau 21 nord | RGSPM06 | 4467 |
| Mayotte | `976` | UTM fuseau 38 sud | RGM04 | 4471 |
| Wallis-et-Futuna | `986` | non vérifiée | | |

Le fuseau de chaque territoire a été vérifié sur les données : pour toutes les adresses qui portent x, y, latitude et longitude, le calcul retombe sur la position du flux à un centimètre près. Les systèmes légaux cités reposent sur l'ellipsoïde GRS 80 et se confondent avec WGS 84 à l'échelle du mètre.

---

## 4. Règles de calcul

### Lambert 93

Projection conique conforme de Lambert, formules inverses de l'IGN, avec les constantes du Lambert 93 :

| Constante | Valeur |
|---|---|
| Exposant de la projection (n) | 0,7256077650532670 |
| Constante de la projection (C) | 11 754 255,426096 |
| Coordonnées du pôle (Xs, Ys) | 700 000 et 12 655 612,049876 |
| Première excentricité de GRS 80 (e) | 0,0818191910428158 |
| Méridien central | 3° est |

La latitude se calcule par itération à partir de la latitude isométrique (huit itérations suffisent largement).

### UTM

Projection de Mercator transverse sur l'ellipsoïde GRS 80 (demi-grand axe 6 378 137 m, aplatissement 1/298,257222101), facteur d'échelle 0,9996, abscisse du méridien central 500 000 m, ordonnée de l'équateur 10 000 000 m dans l'hémisphère sud. Le méridien central du fuseau `f` est à `6 f - 183` degrés. Le calcul inverse suit la série de Krüger à l'ordre 3.

---

## 5. Règles de gestion

| Situation de l'adresse | latitude, longitude | origine |
|---|---|---|
| Le flux donne la latitude et la longitude | celles du flux, inchangées | `flux` |
| Le flux donne x et y seulement, et la position calculée tombe dans l'emprise du territoire | calculées, arrondies à six décimales | `calcul` |
| Le flux donne x et y seulement, mais la projection n'est pas sûre | vides | vide |

La projection n'est pas jugée sûre dans trois cas :

- le territoire n'a pas de projection vérifiée (Wallis-et-Futuna) ;
- en métropole, x et y sortent de l'emprise du Lambert 93 (x entre 90 000 et 1 300 000, y entre 6 000 000 et 7 200 000) ;
- outre-mer, la position calculée sort de l'emprise du territoire (par exemple des coordonnées de La Réunion sous un code commune de Guadeloupe).

Emprises retenues outre-mer :

| Départements | Latitude | Longitude |
|---|---|---|
| `971`, `977`, `978` | 15,7 à 18,2 | -63,3 à -60,9 |
| `972` | 14,3 à 15,0 | -61,3 à -60,7 |
| `973` | 2,0 à 6,0 | -54,7 à -51,5 |
| `974` | -21,5 à -20,8 | 55,1 à 55,9 |
| `975` | 46,7 à 47,2 | -56,5 à -56,0 |
| `976` | -13,1 à -12,5 | 44,9 à 45,4 |

---

## 6. Contrôle

Pour chaque adresse qui porte à la fois x, y, latitude et longitude, le script calcule la position depuis x et y et mesure sa distance à la position du flux. Le bilan affiché en fin de traitement donne le nombre d'adresses contrôlées et l'écart maximal, en mètres. Un écart de plus de quelques centimètres signalerait une projection mal reconnue ou une coordonnée incohérente dans le flux.
