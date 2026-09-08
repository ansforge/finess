# Méthodologie statistique et glossaire

## Populations d’analyse et décisions de revue

La population d’étude FINESS est limitée aux entités participant à la hiérarchie
EJ–EGE. Conformément aux recommandations de l’ANS, les EJ sans EGE associé sont
considérées comme anormales et exclues avant l’échantillonnage. La même règle est
appliquée par hypothèse aux EGE sans EJ associée.

Ce filtrage réduit le snapshot FINESS de mai 2026 de 54,125 à 48,742 EJ
(5,383 exclues) et de 102,939 à 102,926 EGE (13 exclus).

Les entités exclues à cette étape de prétraitement sont distinctes des entités
échantillonnées qui sont ensuite identifiées lors de la revue comme devant être
fermées.

Les 1,577 décisions EJ confirmées constituent l’échantillon EJ de premier degré ; les
5,065 EGE appartenant à ces EJ forment le pool EGE de revue, qui constitue le cadre
de sondage du second degré ; 916 disposent de décisions confirmées.

La revue distingue deux résultats :

- **à rapprocher** : un SIREN/SIRET doit être retenu ;
- **à fermer** : l’évaluateur estime que l’entité FINESS doit être fermée plutôt que
  se voir attribuer un identifiant d’entreprise ordinaire.

La fermeture reste incluse dans les statistiques globales de revue mais est exclue
des dénominateurs de taux de résultats corrects des méthodes de proposition.

Sauf indication contraire, les résultats globaux fondés sur la revue estiment des
quantités pour la population d’analyse FINESS correspondante à l’aide du plan de
revue réalisé et de poids calés. Les mesures du taux de résultats corrects des
méthodes de proposition sont limitées aux entités classées **à rapprocher**.

## Sources de propositions et règles déployables

**Initial** est l’identifiant d’entreprise déjà enregistré dans FINESS. **ANS** et
**Adrien** fournissent des propositions alternatives. La disponibilité d’une méthode
indique uniquement si elle fournit une proposition, indépendamment du caractère
correct de celle-ci.

Pour les entités à rapprocher, l’analyse présente :

- `coverage = entities where a method is available / entities to match` ;
- `correctness when proposed = correct proposals / entities where available` ;
- `fallback correctness = correct deployed outcomes / all entities to match`.

Les règles déployables « méthode sinon Initial » utilisent ANS ou Adrien lorsque la
méthode est disponible et conservent Initial sinon. La règle Adrien à une proposition
utilise Adrien uniquement lorsque sa condition `1 proposition` s’applique. Si une
alternative est disponible mais erronée, Initial ne vient pas corriger le résultat.
Les classifications par seuil et les scénarios de déploiement utilisent le taux de
résultats corrects de la règle « méthode sinon Initial », et non le taux conditionnel
de propositions correctes.

L’analyse au niveau entité enregistre également les erreurs corrigées (Initial erroné,
règle déployée correcte) et les erreurs introduites (Initial correct, règle déployée
erronée). Elle valide l’identité :

`net gain versus Initial = mistakes corrected − mistakes introduced`.

## Strates et table de codification

Les EJ se voient attribuer un `stratum_id` fixe à six chiffres. Chaque chiffre est la
position, à partir de zéro, d’un niveau catégoriel ordonné :

| Chiffre | Variable | Niveaux ordonnés |
|---:|---|---|
| 1 | Cohérence EJ ANS | `<NA>` ; EJ seulement ; incohérent ; cohérent |
| 2 | Statut EJ ANS | `<NA>` ; `VALIDE` ; `VALIDE_FORT` |
| 3 | ANS propose-t-il Initial | `<NA>` ; faux ; vrai |
| 4 | Statut du nombre de propositions Adrien | 0 ; 1 ; 2+ propositions |
| 5 | Cohérence entre jeux de données | incohérence totale ; cohérence partielle ; cohérence totale |
| 6 | Secteur EJ | autre ; hôpital/EHPAD ; SCM/SEL |

Pour les dimensions issues de l’ANS, `<NA>` correspond aux EJ pour
lesquelles l’ANS ne fournit pas de proposition.

L’EGE hérite de la strate de son EJ parente ; aucun code EGE distinct
n’est dérivé.

## Cibles de référence et revue réalisée

À l’intérieur de chaque strate, les entités sont ordonnées de manière déterministe
selon la clé aléatoire enregistrée et les identifiants. Le `sample_size` du plan est
une cible de référence initiale définie manuellement en tenant compte de la taille de
la population de la strate ; il n’est pas exigé que le nombre final d’entités revues
lui soit égal. Les évaluateurs peuvent étendre une strate en poursuivant dans le même
ordre. Toutes les lignes de proposition d’une même entité se déplacent ensemble.

Dans la revue réalisée, on distingue :

- les observations appartenant au préfixe défini par la cible de référence ;
- les extensions poursuivies au-delà de cette cible en suivant l’ordre déterministe ;
- les observations historiques/hors préfixe conservées dans l’analyse.

Le total de référence EJ est de 632 et le total de référence EGE de 633. La revue
réalisée comprend 1,577 EJ et 916 EGE. L’ensemble des 1,577 EJ contient 629 cas du
préfixe de référence, 724 extensions ordonnées du préfixe et 224 cas
historiques/hors préfixe.

La présence de cas historiques hors préfixe introduit une limite potentielle liée au
biais de sélection. Cette limite affecte également le premier degré de l’analyse EGE ;
le calage ne la supprime pas.

Deux positions d’ordre EJ situées à l’intérieur de leurs limites de référence n’ont
pas été revues. Leurs raisons n’ont pas été enregistrées, mais elles ne créent pas de
trous internes et les tailles d’échantillon réalisées sont retenues pour l’analyse.

Au niveau EGE, quatre classeurs présentent des trous dans l’ordre interne et trois
présentent des insuffisances pratiques par rapport à la cible. Ces écarts décrivent
le plan effectivement réalisé et ne rendent pas les décisions correspondantes
invalides.

### Ordre déterministe de revue

Les entités sont ordonnées au sein de chaque strate à l’aide d’une clé pseudo-aléatoire
reproductible.

* **EJ :** l’ordre historique fondé sur `round((fragment / π) % 1, 6)` est conservé dans
un mapping existant ; cette clé n’est pas régénérée par le workflow actuel.
* **EGE :** le workflow peut générer une clé à partir d’un hash BLAKE2b de
`EGE-2026-07|<EGE identifier>`, avec un digest de 8 octets interprété comme un entier
non signé.

La règle BLAKE2b est donc la seule méthode actuellement disponible pour générer un
nouvel ordre déterministe.


## Codes de revue et traitement dans l’analyse

La colonne `Incertitude1` complète l’identifiant retenu et décrit le degré
d’incertitude ou la nécessité d’un passage en gestion FINESS :

| Code | Signification |
|---:|---|
| *(vide)* | équivalent à `0` lorsqu’un identifiant retenu est renseigné |
| `0` | décision certaine |
| `1` | décision incertaine |
| `2` | passage en gestion FINESS nécessaire |
| `12` | décision incertaine et passage en gestion FINESS nécessaire |
| `-1` | décision à fermer, avec incertitude |
| `-2` | décision à fermer, avec passage en gestion FINESS nécessaire |
| `-12` | décision à fermer, avec incertitude et passage en gestion FINESS nécessaire |

Lorsqu’un SIREN ou un SIRET retenu est renseigné et que `Incertitude1` est vide,
la décision est traitée comme certaine, de la même manière qu’avec le code `0`.

Un passage en gestion FINESS peut notamment être nécessaire lorsqu’une
incompatibilité structurelle entre FINESS et SIRENE empêche d’obtenir un
appariement cohérent, même lorsque les identifiants pertinents ont été identifiés.

Les décisions incertaines restent dans l’analyse afin d’éviter une sélection fondée
sur le résultat. Les décisions **à fermer** restent incluses dans les statistiques
globales de revue, mais sont exclues des dénominateurs utilisés pour mesurer le taux
de résultats corrects des méthodes de proposition.

Les trous dans l’ordre de revue et les insuffisances acceptées sont traités comme des
avertissements liés au plan plutôt que comme des exclusions fondées sur le résultat.

Les règles de saisie des identifiants, des codes `Incertitude1` et des commentaires
sont documentées dans `docs/REVIEWER_GUIDE.md`.

## Poids et calage

### EJ

Les EJ sont échantillonnées au sein des strates. Pour la strate `h`, le poids de plan
ordinaire est

`w_h = N_EJ,h / n_reviewed,h`,

où `N_EJ,h` est le nombre d’EJ dans la population d’analyse de la strate `h`, et
`n_reviewed,h` est le nombre d’EJ revues conservées dans cette strate.

Pour le reporting global, les poids sont calés à l’intérieur de chaque strate sur la
taille de population connue. Si `N_h` est la population connue, `n_h` le nombre
revu et `w_h` le poids de plan :

`g_h = N_h / (n_h × w_h)`

`w_h_calibrated = w_h × g_h`

de sorte que la somme des poids calés des entités revues soit égale à `N_h`.

Pour les EJ, puisque `w_h = N_EJ,h / n_reviewed,h`, ce calage est neutre à
l’exception des arrondis enregistrés.

### EGE

L’échantillonnage EGE comporte deux degrés réalisés. Pour chaque strate :

* `p_EJ = selected EJs / EJ population` ;
* `p_EGE|EJ = reviewed EGEs / unique pooled EGEs in the selected EJs` ;
* `raw EGE weight = 1 / (p_EJ × p_EGE|EJ)`.

Le pool EGE de revue compte les identifiants EGE uniques dans
`pooled_ege_proposals.parquet`, et non les lignes de proposition. Le nombre d’EGE
disposant d’une décision confirmée constitue la taille d’échantillon réalisée au
second degré.

`n_EGE` est la population EGE plus large connue dans la strate et n’est pas le
dénominateur de second degré. Pour les totaux et proportions globaux, les poids EGE
bruts sont calés au sein de la strate à l’aide de la même étape de calage décrite
ci-dessus, avec `N_h = n_EGE`. Les poids calés obtenus somment donc à la population
EGE connue de chaque strate.

Le calage ne supprime pas la limite héritée de sélection des EJ hors préfixe.

Les estimations globales sont des estimations de population pondérées selon le plan
et calées, et non de simples moyennes des pourcentages par strate. Le nombre
d’identifiants Initial manquants est observé directement dans les tables complètes de
propositions plutôt qu’extrapolé à partir de l’échantillon de revue.

### Intervalles descriptifs et seuils

Des intervalles de type Wilson à 95% avec correction de population finie sont
présentés uniquement au niveau des strates et sont descriptifs. La correction utilise
le nombre d’entités examinées dans la strate, tandis que le dénominateur de la
proportion dépend de l’indicateur (entités à rapprocher pour Initial ; entités avec
une proposition pour ANS/Adrien).

Pour les EGE, ces intervalles ne tiennent pas pleinement compte de l’échantillonnage à
deux degrés par EJ. Aucun intervalle de confiance global n’est produit. Voir
`docs/Note_méthodologique_qualité_sirénisation_sous_ensemble.pdf` pour la méthode
détaillée.

Les indicateurs d’acceptation à 95% et 99% utilisent les estimations ponctuelles, et
non les bornes des intervalles.

## Scénarios de strates acceptées

Les scénarios à règle unique et combinés conservent Initial dans les strates sous le
seuil et déploient la règle « méthode sinon Initial » sélectionnée dans les strates
acceptées. Les scénarios combinés peuvent choisir la plus grande estimation ponctuelle
observée dans la strate parmi les règles nommées. La même règle gagnante est utilisée
pour le taux de résultats corrects, les erreurs corrigées et les erreurs introduites.

Ces scénarios sont des aides descriptives à la décision. Choisir et évaluer un maximum
sur les mêmes données de revue peut être optimiste ; un scénario ne doit pas devenir
une règle de production sans validation séparée.

## Modèle exploratoire de probabilité SIRET ANS

Un modèle de régression logistique pondérée est exploré pour les EGE revus à
rapprocher disposant d’une proposition ANS, à l’aide des poids EGE calés décrits
ci-dessus. La performance est évaluée à partir de prédictions issues d’une validation
croisée regroupée par EJ, dans le but d’évaluer l’acceptation automatique sélective
des propositions ANS à forte confiance.

Le modèle et ses seuils de score sont exploratoires et ne constituent pas des règles
de déploiement validées. Voir
`project_tools/ege_ans_siret_logistic_regression/RESULTS_NOTE.md` pour la méthodologie
complète, les diagnostics et les résultats.

## Glossaire

| Terme | Équivalent français | Sens dans le projet |
|---|---|---|
| EJ | EJ | Entité juridique FINESS (*entité juridique*) ; revue par rapport à un SIREN |
| EGE | EGE | Établissement géographique FINESS ; revu par rapport à un SIRET |
| SIREN | SIREN | Identifiant à neuf chiffres d’une unité légale SIRENE |
| SIRET | SIRET | Identifiant à quatorze chiffres d’un établissement SIRENE |
| Initial | Initial | Identifiant déjà porté par FINESS avant les propositions alternatives |
| ANS | ANS | Source de propositions alternatives en amont utilisée dans les vagues d’étude de juin/juillet |
| Adrien | Adrien | Chaîne amont multi-sources de génération de candidats |
| matching | appariement | Association d’une entité FINESS à un identifiant SIRENE ; terme générique utilisé pour les méthodes, propositions, tables, bases et performances du projet |
| reference target | cible de référence | Taille d’échantillon initialement prévue dans une strate |
| deterministic order | ordre déterministe | Ordre stable des entités utilisé pour former ou étendre un préfixe de revue |
| review prefix | préfixe de revue | Entités consécutives depuis le début de l’ordre déterministe, sans position sautée |
| realised review | revue réalisée | Entités pour lesquelles une décision terminée a été conservée |
| ordinary extension | extension ordinaire | Poursuite de la revue au-delà de la cible de référence en suivant l’ordre |
| historical exception | exception historique | Décision hors préfixe conservée dans l'analyse |
| confirmed decision | décision confirmée | Une décision validée d’identifiant retenu/de fermeture pour une entité |
| annotated reference sample | échantillon annoté de référence | Ensemble d’entités accompagné de décisions confirmées et de leurs poids, destiné notamment à l’entraînement ou à l’évaluation de méthodes d’appariement |
| coverage | couverture | Part des entités à rapprocher pour lesquelles une méthode est disponible |
| conditional correctness | taux de propositions correctes | Taux de résultats corrects lorsque cette méthode est disponible |
| fallback correctness | taux de résultats corrects de la règle « méthode sinon Initial » | Taux de résultats corrects d’une règle déployable utilisant une alternative ou Initial |
| calibration | calage | Mise à l’échelle, au sein de chaque strate, des poids de plan vers un total de population connu |
