# Échantillons annotés de référence FINESS–SIRENE

## Objet

Les fichiers joints constituent des échantillons annotés de référence construits à partir
de décisions confirmées issues d'une revue manuelle des appariements entre FINESS et
SIRENE.

Selon le fichier, l'unité examinée est :

- une **entité juridique FINESS (EJ)**, appariée à un **SIREN** ;
- un **établissement géographique FINESS (EGE)**, apparié à un **SIRET**.

Ces échantillons annotés de référence peuvent être utilisés pour décrire les décisions
de revue, entraîner une méthode d’appariement ou évaluer une autre base sur les
mêmes cas. Toute interprétation représentative de la population doit toutefois tenir
compte du plan d'échantillonnage et des poids fournis.

Les versions `.xlsx` et `.parquet` d'un même échantillon annoté de référence contiennent
les mêmes lignes et les mêmes colonnes.

## Contenu des fichiers

Chaque ligne correspond à une EJ ou un EGE annoté par une décision confirmée issue de
la revue manuelle.

| Colonne | Signification |
|---|---|
| `EJ` / `EGE` | Identifiant FINESS de l'entité examinée. |
| `Siren_retenu` / `Siret_retenu` | Identifiant SIRENE retenu après revue manuelle. Une valeur manquante signifie qu'aucun SIREN/SIRET n'a été retenu. |
| `Incertitude1` | Code d'incertitude renseigné lors de la revue. |
| `stratum_id` | Strate d'échantillonnage à laquelle appartient l'entité. |
| `sampling_weight` | Poids associé au plan d'échantillonnage réalisé. |
| `calibrated_weight` | Poids utilisé pour les estimations globales, recalé de façon que les poids reproduisent la population connue de la strate. |
| `to_close` | Indique que la revue conclut que la structure doit être considérée comme à fermer plutôt que comme une entité à rapprocher. |

## Code `Incertitude1`

`Incertitude1` complète l’identifiant retenu et décrit le degré d’incertitude de la
décision ou la nécessité d’un passage en gestion FINESS.

| Code | Interprétation |
|---:|---|
| `0` | Décision certaine. |
| `1` | Décision incertaine. |
| `2` | Passage en gestion FINESS nécessaire. |
| `12` | Décision incertaine et passage en gestion FINESS nécessaire. |
| `-1` | Structure à fermer, avec incertitude. |
| `-2` | Structure à fermer, avec passage en gestion FINESS nécessaire. |
| `-12` | Structure à fermer, avec incertitude et passage en gestion FINESS nécessaire. |

Dans les données de revue d’origine, une valeur vide est équivalente à `0` lorsqu’un
identifiant retenu est renseigné. Dans les échantillons annotés de référence produits
par le project tool, cette valeur est normalisée à `0`.

Les codes négatifs (`-1`, `-2`, `-12`) correspondent aux cas `to_close = True`. Les
codes positifs `2` et `12` signalent un besoin de gestion FINESS mais ne signifient
pas que la structure est à fermer.

## Poids et interprétation

L'échantillon n'est pas destiné à être interprété comme un échantillon aléatoire
simple. Les observations appartiennent à des strates et les poids fournis doivent être
utilisés pour produire des estimations représentatives de la population étudiée.

Pour des statistiques descriptives sur les lignes effectivement examinées, les comptes
bruts peuvent être utilisés. Pour extrapoler les résultats à la population de l'étude,
utiliser en priorité `calibrated_weight`.

Les poids EJ et EGE ne reposent pas exactement sur le même plan : l'échantillonnage EGE
est issu d'un plan à deux degrés, avec sélection d'EJ puis d'EGE appartenant aux EJ
sélectionnées.

## Cas à fermer

Les lignes avec `to_close = True` sont conservées dans l'échantillon afin de représenter
l'ensemble des décisions de revue.

Elles ne doivent toutefois pas être assimilées à des échecs d’appariement : elles
correspondent à des cas pour lesquels la conclusion de la revue est que la structure
doit être considérée comme à fermer. Pour évaluer la couverture ou la justesse d'une
base d’appariement, ces lignes doivent être exclues des dénominateurs
correspondants.

## Évaluation d'une autre base d’appariement

Pour les lignes avec `to_close = False` :

- une entité est **couverte** si la base évaluée fournit au moins une proposition de
SIREN/SIRET pour cette entité ;
- une proposition est **correcte** si l'identifiant retenu manuellement figure parmi
les propositions de la base ;
- une entité absente de la base évaluée est considérée comme **non couverte** ;
- lorsqu'aucun SIREN/SIRET n'a été retenu manuellement, l'absence de proposition dans
la base évaluée n'est pas considérée comme une proposition correcte : il s'agit d'une
absence de couverture.

Ces conventions permettent de distinguer la **couverture** d'une méthode de sa
**justesse lorsqu'elle propose un identifiant**.
