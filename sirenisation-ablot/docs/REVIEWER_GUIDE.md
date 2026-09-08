# Guide de l’évaluateur

## Objectif

Les classeurs de revue servent à vérifier les identifiants d’entreprise associés aux
entités FINESS :

- pour une **EJ**, l’identifiant à vérifier ou à retenir est un **SIREN** ;
- pour un **EGE**, l’identifiant à vérifier ou à retenir est un **SIRET**.

Chaque classeur contient un ensemble d’entités à examiner.

L’objectif est de déterminer, pour chaque entité, le SIREN ou le SIRET qui semble
devoir être retenu et de signaler les situations incertaines ou particulières. Il
n’est pas nécessaire de résoudre à tout prix un cas lorsqu’aucune conclusion fiable
ne peut être tirée des informations disponibles.

## Avant de commencer

Quelques précautions permettent de traiter correctement les classeurs une fois la
revue terminée :

1. Merci de ne pas modifier l’identifiant de l’entité ni le nom ou la fonction des
   colonnes de revue :
   - `Siren_retenu` pour une revue EJ, ou `Siret_retenu` pour une revue EGE ;
   - `Incertitude1` ;
   - `Commentaire`.
2. Les autres colonnes peuvent être modifiées si cela vous est utile pour réaliser
   la revue.
3. L’ordre des entités dans le classeur est à conserver.
4. Le début du nom du fichier doit être conservé afin que nous puissions l’identifier.
   Vous pouvez en revanche ajouter un suffixe à la fin du nom pour votre organisation.
   Par exemple, `123456__5.xlsx` peut devenir `123456__5_OK.xlsx`.
5. Lorsqu’une même EJ ou un même EGE apparaît sur plusieurs lignes, ces lignes
   correspondent à un même cas. Il suffit de prendre une seule décision pour
   l’entité et de la reporter de manière cohérente sur les lignes correspondantes.

## Ordre de la revue

Les entités sont présentées dans un ordre défini à l’avance. Merci de les examiner
dans cet ordre, sans réorganiser le classeur.

Le nombre d’entités demandé est l’objectif proposé pour la revue. Merci d’en examiner
autant que possible.

Si vous avez le temps et souhaitez poursuivre au-delà de ce nombre, vous pouvez bien
sûr continuer avec les entités suivantes dans le même ordre.

Pour toute remarque, question ou difficulté rencontrée pendant la revue, n’hésitez
pas à en parler au responsable du projet.

## Saisie de l’identifiant retenu

Les propositions présentes dans le classeur sont des candidats à examiner : elles ne
sont pas nécessairement correctes et il n’est pas obligatoire de retenir l’une
d’elles.

Vous pouvez rechercher un autre SIREN ou SIRET lorsque les propositions fournies ne
semblent pas convenir, notamment en consultant des sources en ligne telles que
l’Annuaire des Entreprises.

Un candidat indiqué comme fermé n’est pas considéré comme un identifiant correct
pour l’entité revue.

### Pour une EJ

Saisissez dans `Siren_retenu` le SIREN retenu, composé exactement de **9 chiffres**.

### Pour un EGE

Saisissez dans `Siret_retenu` le SIRET retenu, composé exactement de **14 chiffres**.

Dans les deux cas :

- les éventuels zéros initiaux sont à conserver ;
- un seul identifiant est à retenir par entité ;
- l’identifiant retenu peut être l’une des propositions du classeur ou un autre
  identifiant trouvé au cours de la revue ;
- si l’entité apparaît sur plusieurs lignes, le même identifiant peut être reporté
  sur toutes ses lignes ;
- si aucun identifiant ordinaire ne peut être retenu, l’identifiant peut être laissé
  vide ou renseigné avec `NA`/`N/A`, avec le code `Incertitude1` correspondant à la
  situation.

## Codes `Incertitude1`

| Code | À saisir lorsque |
|---:|---|
| *(vide)* | équivalent au code `0` lorsqu’un identifiant retenu est renseigné |
| `0` | l’identifiant retenu est considéré comme certain |
| `1` | l’identifiant retenu est incertain |
| `2` | un passage en gestion FINESS est nécessaire |
| `12` | l’identifiant est incertain et un passage en gestion FINESS est également nécessaire |
| `-1` | l’entité est à fermer et la décision est incertaine |
| `-2` | l’entité est à fermer et un passage en gestion FINESS est nécessaire |
| `-12` | l’entité est à fermer, avec incertitude et besoin de passage en gestion FINESS |

Lorsqu’un SIREN ou un SIRET retenu est renseigné et que `Incertitude1` est laissée
vide, la décision est considérée comme certaine, comme avec le code `0`.

Il n’est donc pas nécessaire de saisir `0` explicitement pour une décision certaine.

Si aucun identifiant n’est retenu, un code `Incertitude1` permet de préciser la
situation.

Un passage en gestion FINESS peut notamment être nécessaire lorsqu’une
incompatibilité structurelle entre FINESS et SIRENE empêche d’obtenir un
appariement cohérent, même lorsque les identifiants pertinents ont été identifiés.

## Traitement des incertitudes

Lorsqu’une décision est incertaine, indiquez-le avec le code `Incertitude1`
correspondant et, si cela peut aider, ajoutez un commentaire sur les éléments qui
vous font hésiter.

Le responsable du projet pourra ensuite revoir ces cas afin d’essayer de déterminer
le bon SIREN ou SIRET. Les incertitudes qui restent non résolues sont conservées
comme telles et prises en compte dans les statistiques de l’étude.

## Commentaires

La colonne `Commentaire` peut servir à indiquer comment le SIREN ou le SIRET retenu
a été identifié : proposition présente dans le classeur, source consultée en ligne,
information déterminante ou recherche complémentaire.

Lorsqu’un identifiant a été trouvé en dehors des propositions du classeur, il est
utile d’indiquer brièvement la source ou la manière dont il a été trouvé.

Le commentaire peut également préciser une incertitude, une décision à fermer, un
passage en gestion FINESS nécessaire ou toute situation inhabituelle.

Lorsque l’identifiant retenu fait déjà partie des propositions et que le choix est
évident, le commentaire peut être très bref ou rester vide.

## Retour des classeurs terminés

Transmettez le classeur terminé selon les modalités indiquées par le responsable du
projet.
